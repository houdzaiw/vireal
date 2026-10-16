"""Isolated PostgreSQL + mocked Clerk/PayPal. Never spend real money."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import HttpUrl, ValidationError
from sqlmodel import delete, select

from app.api import deps
from app.api.routes import app_auth, app_paypal, paypal_webhooks
from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppOrder,
    AppOrderEvent,
    AppPaymentCase,
    AppUser,
    AppUserIdentity,
    AppUserSession,
)
from app.services import commercial_access, paypal_orders
from app.services.app_identity import hash_clerk_session_id
from app.services.clerk_auth import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from app.services.paypal_client import PayPalError
from tests.api.routes.test_paypal_commerce import FakePayPal, signed_headers
from tests.core.test_config_v12 import _commerce_settings

AUTH = "/api/v1/app/auth/session"
CONFIG = "/api/v1/app/paypal/config"
ORDERS = "/api/v1/app/paypal/orders"
UPLOAD = "/api/v1/app/uploads/images"
TASKS = "/api/v1/app/video-tasks"


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Payment-only isolated tests must never perform external HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.fixture
def payment_only(db, monkeypatch):
    class Clerk:
        claims = ClerkSessionClaims(
            "https://clerk.example.test",
            f"user_{uuid.uuid4().hex}",
            f"session_{uuid.uuid4().hex}",
            "https://app.example.test",
        )
        profile = ClerkUserProfile("li8483@yeah.net", True, ("email",))

        def verify_session_token(self, token):
            if token == "invalid":
                raise ClerkAuthenticationError("Invalid isolated token")
            return self.claims

        def get_user_profile(self, _subject):
            return self.profile

    clerk = Clerk()
    user = AppUser(account_type="clerk")
    db.add(user)
    db.flush()
    identity = AppUserIdentity(
        app_user_id=user.id,
        issuer=clerk.claims.issuer,
        subject=clerk.claims.subject,
        primary_email=clerk.profile.primary_email,
        email_verified=True,
    )
    local_session = AppUserSession(
        app_user_id=user.id,
        session_id_hash=hash_clerk_session_id(clerk.claims.session_id),
    )
    db.add(identity)
    db.add(local_session)
    db.commit()
    for module in (deps, app_auth, commercial_access):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": HttpUrl(clerk.claims.issuer),
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": True,
        "APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT": clerk.claims.subject,
        "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID": user.id,
        "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
        + timedelta(hours=1),
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_CONTROLLED_REGISTRATION_ENABLED": False,
        "APP_INTERNAL_ACCEPTANCE_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_SUBJECTS": [],
        "APP_COMMERCE_TERMS_APPROVED": True,
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-payment-only-signed-edge-32-chars",
        "PAYPAL_ENABLED": True,
        "PAYPAL_ENVIRONMENT": "live",
        "PAYPAL_CLIENT_ID": "unit-public",
        "PAYPAL_CLIENT_SECRET": "unit-private",
        "PAYPAL_MERCHANT_ID": "TEST-MERCHANT",
        "PAYPAL_WEBHOOK_ID": "unit-hook",
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "ADMIN_PUBLIC_SIGNUP_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(app_paypal, "global_real_count", lambda **_kwargs: 0)
    fake = FakePayPal()
    for module in (app_paypal, paypal_orders, paypal_webhooks):
        monkeypatch.setattr(module, "get_paypal_client", lambda: fake)
    yield clerk, user.id, identity.id, local_session.id, fake
    db.rollback()
    db.execute(delete(AppPaymentCase).where(AppPaymentCase.app_user_id == user.id))
    ids = select(AppOrder.id).where(AppOrder.app_user_id == user.id)
    db.execute(delete(AppOrderEvent).where(AppOrderEvent.order_id.in_(ids)))
    db.execute(delete(AppOrder).where(AppOrder.app_user_id == user.id))
    db.commit()


def headers(path, method="POST", *, country="CN", key=None):
    result = {
        "Authorization": "Bearer isolated-payment-only",
        **signed_headers(path, method, country),
    }
    if key:
        result["Idempotency-Key"] = key
    return result


def create(client, *, key=None, product="coins_100", country="CN"):
    return client.post(
        ORDERS,
        headers=headers(ORDERS, key=key or str(uuid.uuid4()), country=country),
        json={"product_id": product},
    )


def test_target_existing_login_one_package_no_signup_or_identity_leak(
    client, db, payment_only
):
    clerk, user_id, _, _, _ = payment_only
    cfg = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN"))
    assert cfg.headers["cache-control"] == "no-store"
    assert cfg.json()["payment_only_sign_in_enabled"]
    assert not cfg.json()["recharge_enabled"]
    assert (
        clerk.claims.subject not in cfg.text
        and "li8483@yeah.net" not in cfg.text
        and str(user_id) not in cfg.text
    )
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert cfg["country"] == "CN" and not cfg["region_allowed"]
    assert cfg["recharge_enabled"] and cfg["payment_only_acceptance_allowed"]
    assert (
        not cfg["registration_enabled"]
        and not cfg["controlled_registration_enabled"]
        and not cfg["internal_sign_in_enabled"]
    )
    assert cfg["products"] == [
        {"product_id": "coins_100", "coins": 100, "amount": 599, "currency": "USD"}
    ]
    assert not client.post(AUTH, headers=headers(AUTH)).json()["is_new_user"]
    clerk.claims = replace(clerk.claims, subject=f"user_{uuid.uuid4().hex}")
    assert client.post(AUTH, headers=headers(AUTH, country="US")).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


@pytest.mark.parametrize("country", ["CN", "US"])
def test_upload_and_generation_closed_even_with_credits(
    client, db, payment_only, country
):
    _, user_id, _, _, _ = payment_only
    from app.services.coin_wallet import adjust_coin_balance

    adjust_coin_balance(
        session=db,
        app_user_id=user_id,
        delta=100,
        entry_type="admin_adjustment",
        idempotency_key=f"isolated-fixture:{user_id}",
        reason="isolated fixture",
    )
    db.commit()
    assert (
        client.post(
            UPLOAD,
            headers=headers(UPLOAD, country=country),
            files={"file": ("test.png", b"not-submitted", "image/png")},
        ).status_code
        == 403
    )
    assert (
        client.post(
            TASKS,
            headers=headers(TASKS, country=country, key=str(uuid.uuid4())),
            json={
                "effect_id": str(uuid.uuid4()),
                "variant_id": str(uuid.uuid4()),
                "upload_ids": [str(uuid.uuid4())],
            },
        ).status_code
        == 403
    )
    assert client.post(
        "/api/v1/app/generations/",
        headers=headers("/api/v1/app/generations/", country=country),
        json={"kind": "video", "prompt": "isolated request, never generate"},
    ).status_code == (403 if country == "CN" else 410)


@pytest.mark.parametrize("product", ["coins_220", "coins_500", "unknown"])
def test_other_packages_create_no_order(client, db, payment_only, product):
    _, user_id, _, _, fake = payment_only
    assert create(client, product=product).status_code == 403
    assert fake.create_calls == 0
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).first()


@pytest.mark.parametrize("field", ["amount", "currency", "coin_quantity"])
def test_client_cannot_override_snapshot(client, payment_only, field):
    assert (
        client.post(
            ORDERS,
            headers=headers(ORDERS, key=str(uuid.uuid4())),
            json={"product_id": "coins_100", field: 1},
        ).status_code
        == 422
    )
    assert payment_only[-1].create_calls == 0


@pytest.mark.parametrize(
    "proof",
    ["missing", "bare", "unknown", "invalid", "expired", "path", "method", "US"],
)
def test_only_genuine_signed_cn_context_can_create(client, payment_only, proof):
    h = headers(ORDERS, key=str(uuid.uuid4()))
    if proof in {"missing", "bare"}:
        h = {k: v for k, v in h.items() if not k.startswith("x-vireal-edge-")}
        h["CF-IPCountry"] = "CN"
        h["x-vireal-payment-only"] = "true"
    elif proof in {"unknown", "US"}:
        h.update(signed_headers(ORDERS, "POST", "XX" if proof == "unknown" else "US"))
    elif proof == "invalid":
        h["x-vireal-edge-signature"] = "0" * 64
    elif proof == "expired":
        h.update(signed_headers(ORDERS, "POST", "CN", timestamp="1"))
    elif proof == "path":
        h.update(signed_headers(CONFIG, "POST", "CN"))
    else:
        h.update(signed_headers(ORDERS, "GET", "CN"))
    assert (
        client.post(ORDERS, headers=h, json={"product_id": "coins_100"}).status_code
        == 403
    )
    assert payment_only[-1].create_calls == 0


@pytest.mark.parametrize(
    "reason",
    [
        "subject",
        "issuer",
        "user_id",
        "email",
        "unverified",
        "revoked",
        "missing_session",
        "disabled",
        "deleted",
        "hold",
        "profile_email",
        "profile_unverified",
        "clerk_unavailable",
        "invalid_token",
    ],
)
def test_identity_and_account_safety_fail_closed(
    client, db, payment_only, monkeypatch, reason
):
    clerk, user_id, identity_id, session_id, fake = payment_only
    identity = db.get(AppUserIdentity, identity_id)
    local = db.get(AppUserSession, session_id)
    user = db.get(AppUser, user_id)
    if reason == "subject":
        clerk.claims = replace(clerk.claims, subject="user_other")
    elif reason == "issuer":
        clerk.claims = replace(clerk.claims, issuer="https://other.example.test")
    elif reason == "user_id":
        monkeypatch.setattr(
            settings, "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID", uuid.uuid4()
        )
    elif reason == "email":
        identity.primary_email = "someone@example.com"
    elif reason == "unverified":
        identity.email_verified = False
    elif reason == "revoked":
        local.revoked_at = datetime.now(UTC)
    elif reason == "missing_session":
        db.delete(local)
    elif reason == "disabled":
        user.status = "disabled"
    elif reason == "deleted":
        user.deleted_at = datetime.now(UTC)
    elif reason == "hold":
        user.payment_hold = True
    elif reason == "profile_email":
        clerk.profile = replace(clerk.profile, primary_email="someone@example.com")
    elif reason == "profile_unverified":
        clerk.profile = replace(clerk.profile, email_verified=False)
    elif reason == "clerk_unavailable":

        def unavailable(_subject):
            raise ClerkAPIError("isolated unavailable")

        monkeypatch.setattr(clerk, "get_user_profile", unavailable)
    db.commit()
    h = headers(ORDERS, key=str(uuid.uuid4()))
    if reason == "invalid_token":
        h["Authorization"] = "Bearer invalid"
    assert (
        client.post(ORDERS, headers=h, json={"product_id": "coins_100"}).status_code
        == 403
    )
    assert fake.create_calls == 0


def test_one_lifetime_order_same_key_retry_and_concurrent_different_keys(
    client, db, payment_only
):
    _, user_id, _, _, fake = payment_only
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(client), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert fake.create_calls == 1
    saved = db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).one()
    assert (saved.product_id, saved.amount, saved.currency, saved.coin_quantity) == (
        "coins_100",
        599,
        "USD",
        100,
    )
    assert create(client, key=saved.payment_idempotency_key).json()["id"] == str(
        saved.id
    )
    assert fake.create_calls == 1
    for status in ("canceled", "failed", "capture_pending", "refunded", "paid"):
        saved.status = status
        db.add(saved)
        db.commit()
        assert create(client).status_code == 409
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert cfg["payment_only_order_created"] and not cfg["recharge_enabled"]


def test_another_initialized_account_cannot_use_the_exception(client, db, payment_only):
    clerk = payment_only[0]
    other = AppUser(account_type="clerk")
    db.add(other)
    db.flush()
    clerk.claims = replace(
        clerk.claims,
        subject="user_other_existing",
        session_id=f"session_{uuid.uuid4().hex}",
    )
    db.add(
        AppUserIdentity(
            app_user_id=other.id,
            issuer=clerk.claims.issuer,
            subject=clerk.claims.subject,
            primary_email="other@example.com",
            email_verified=True,
        )
    )
    db.add(
        AppUserSession(
            app_user_id=other.id,
            session_id_hash=hash_clerk_session_id(clerk.claims.session_id),
        )
    )
    db.commit()
    assert (
        client.get("/api/v1/app/users/me", headers=headers(CONFIG, "GET")).status_code
        == 200
    )
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert not cfg["recharge_enabled"] and not cfg["payment_only_acceptance_allowed"]
    assert create(client).status_code == 403
    assert payment_only[-1].create_calls == 0
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == other.id)).first()


def test_expiry_while_waiting_for_budget_lock_creates_no_order(
    client, db, payment_only, monkeypatch
):
    original = app_paypal.lock_commercial_user
    calls = 0

    def expired_after_lock(session, user):
        nonlocal calls
        result = original(session, user)
        calls += 1
        if calls == 2:
            monkeypatch.setattr(
                settings,
                "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
                datetime.now(UTC) - timedelta(seconds=1),
            )
        return result

    monkeypatch.setattr(app_paypal, "lock_commercial_user", expired_after_lock)
    assert create(client).status_code == 403
    assert payment_only[-1].create_calls == 0
    assert not db.exec(
        select(AppOrder).where(AppOrder.app_user_id == payment_only[1])
    ).first()


def test_provider_create_unknown_preserves_slot_without_a_second_order(
    client, db, payment_only, monkeypatch
):
    _, user_id, _, _, fake = payment_only
    original = fake.create_order

    def lost_response(order):
        original(order)
        raise PayPalError()

    monkeypatch.setattr(fake, "create_order", lost_response)
    key = str(uuid.uuid4())
    assert create(client, key=key).status_code == 502
    assert create(client).status_code == 409
    assert (
        len(db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()) == 1
    )
    monkeypatch.setattr(fake, "create_order", original)
    assert create(client, key=key).status_code == 409
    assert fake.create_calls == 1
    assert len(fake.orders) == 1


@pytest.mark.parametrize("close", ["expiry", "disabled"])
def test_pending_existing_payment_can_complete_once_after_close(
    client, db, payment_only, monkeypatch, close
):
    _, user_id, _, _, fake = payment_only
    order = create(client).json()
    data = fake.orders[order["provider_order_id"]]
    fake.capture_order(type("Order", (), order)())
    cap = data["purchase_units"][0]["payments"]["captures"][0]
    cap["status"] = "PENDING"
    path = f"{ORDERS}/{order['id']}/capture"
    assert (
        client.post(path, headers=headers(path)).json()["status"] == "capture_pending"
    )
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(order["id"]))
    ).first()
    if close == "expiry":
        monkeypatch.setattr(
            settings,
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    else:
        monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED", False)
        monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    assert create(client).status_code in {403, 503}
    cap["status"] = "COMPLETED"
    event = {
        "id": f"WH-{uuid.uuid4()}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": cap["id"],
            "supplementary_data": {
                "related_ids": {"order_id": order["provider_order_id"]}
            },
        },
    }
    for _ in range(2):
        paypal_orders.process_webhook(db, event, fake)
        assert client.post(path, headers=headers(path)).json()["fulfilled_at"]
    credits = db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(order["id"]))
    ).all()
    assert (
        len(credits) == 1
        and credits[0].delta == 100
        and credits[0].app_user_id == user_id
    )
    assert (
        client.get("/api/v1/app/wallet", headers=headers(CONFIG, "GET")).json()[
            "balance"
        ]
        == 100
    )


def test_financial_verification_and_quota_are_not_bypassed(
    client, payment_only, monkeypatch
):
    monkeypatch.setattr(app_paypal, "global_real_count", lambda **_kwargs: 30)
    assert create(client).status_code == 409
    monkeypatch.setattr(app_paypal, "global_real_count", lambda **_kwargs: 0)
    order = create(client).json()
    fake = payment_only[-1]
    data = fake.orders[order["provider_order_id"]]
    data["status"] = "APPROVED"
    data["payer"] = {"address": {"country_code": "CN"}}
    path = f"{ORDERS}/{order['id']}/capture"
    assert client.post(path, headers=headers(path)).status_code == 409
    assert "payments" not in data["purchase_units"][0]


def mode_settings(**overrides):
    values = {
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": True,
        "APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT": "user_isolated",
        "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID": uuid.uuid4(),
        "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
        + timedelta(hours=1),
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
    }
    values.update(overrides)
    return _commerce_settings(**values)


def test_configuration_defaults_and_expired_restart_preserve_settlement():
    assert not _commerce_settings().APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    assert mode_settings().APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    assert mode_settings(
        APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT=datetime.now(UTC) - timedelta(seconds=1)
    )


@pytest.mark.parametrize(
    "reason",
    [
        "expired",
        "terms",
        "payments",
        "public",
        "internal",
        "controlled",
        "live",
        "generation",
        "secret",
        "environment",
    ],
)
def test_runtime_changes_cannot_broaden_payment_only_permissions(
    client, payment_only, monkeypatch, reason
):
    field, value = {
        "expired": (
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        ),
        "terms": ("APP_COMMERCE_TERMS_APPROVED", False),
        "payments": ("PAYPAL_ENABLED", False),
        "public": ("APP_PUBLIC_REGISTRATION_ENABLED", True),
        "internal": ("APP_INTERNAL_ACCEPTANCE_ENABLED", True),
        "controlled": ("APP_CONTROLLED_REGISTRATION_ENABLED", True),
        "live": ("APP_LIVE_ACCEPTANCE_ENABLED", True),
        "generation": ("APP_VIDEO_SUBMISSIONS_ENABLED", True),
        "secret": ("APP_EDGE_SIGNING_SECRET", "short"),
        "environment": ("PAYPAL_ENVIRONMENT", "sandbox"),
    }[reason]
    monkeypatch.setattr(settings, field, value)
    assert create(client).status_code == 403
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert not cfg["recharge_enabled"] and not cfg["registration_enabled"]
    assert (
        not cfg["controlled_registration_enabled"]
        and not cfg["payment_only_acceptance_allowed"]
    )
    assert payment_only[-1].create_calls == 0


def test_existing_snapshot_and_cross_user_capture_remain_protected(
    client, db, payment_only
):
    order = create(client).json()
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    key = saved.payment_idempotency_key
    saved.amount = 1199
    db.add(saved)
    db.commit()
    assert create(client, key=key).status_code == 409
    other = AppUser(account_type="clerk")
    db.add(other)
    db.flush()
    saved.app_user_id = other.id
    db.add(saved)
    db.commit()
    path = f"{ORDERS}/{order['id']}/capture"
    assert client.post(path, headers=headers(path)).status_code == 404
    assert payment_only[-1].create_calls == 1
    db.delete(saved)
    db.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT": None},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT": "invalid"},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID": None},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT": None},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT": datetime.now()},
        {
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
            + timedelta(days=2)
        },
        {"ENVIRONMENT": "staging"},
        {"APP_PUBLIC_REGISTRATION_ENABLED": True},
        {"APP_CONTROLLED_REGISTRATION_ENABLED": True},
        {"APP_INTERNAL_ACCEPTANCE_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_SUBJECTS": ["user_someone"]},
        {"APP_VIDEO_SUBMISSIONS_ENABLED": True},
        {"PAYPAL_ENABLED": False},
        {"PAYPAL_ENVIRONMENT": "sandbox"},
        {"APP_COMMERCE_TERMS_APPROVED": False},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"ADMIN_PUBLIC_SIGNUP_ENABLED": True},
        {"LOCAL_DEMO_ENABLED": True},
        {"APP_LEGACY_VIDEO_TASKS_ENABLED": True},
    ],
)
def test_unsafe_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        mode_settings(**overrides)
