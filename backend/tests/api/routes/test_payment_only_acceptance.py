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
from app.api.routes import admin_app, app_auth, app_paypal, paypal_webhooks
from app.core.config import settings
from app.models import (
    AppAdminOperationLog,
    AppCoinLedger,
    AppOrder,
    AppOrderEvent,
    AppPaymentCase,
    AppPayPalReplacement,
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
from app.services.paypal_client import PayPalClient, PayPalError
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
        profile = ClerkUserProfile("li522903183@163.com", True, ("email",))

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
    db.execute(
        delete(AppPayPalReplacement).where(AppPayPalReplacement.app_user_id == user.id)
    )
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
        and "li522903183@163.com" not in cfg.text
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


@pytest.mark.parametrize("country", ["CN", "HK", "US"])
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
def test_only_genuine_signed_permitted_context_can_create(client, payment_only, proof):
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


def checkout_path(order):
    return f"{ORDERS}/{order['id']}/checkout"


@pytest.mark.parametrize("provider_status", ["CREATED", "PAYER_ACTION_REQUIRED"])
def test_resume_original_order_is_read_only_and_never_creates_or_captures(
    client, db, payment_only, monkeypatch, provider_status
):
    _, user_id, _, _, fake = payment_only
    order = create(client).json()
    path = checkout_path(order)
    fake.orders[order["provider_order_id"]]["status"] = provider_status
    before = db.get(AppOrder, uuid.UUID(order["id"])).model_dump()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Read-only checkout must not create or capture a payment")

    monkeypatch.setattr(fake, "create_order", forbidden)
    monkeypatch.setattr(fake, "capture_order", forbidden)
    # Existing payments may continue even when no new generation/checkout is available.
    monkeypatch.setattr(app_paypal, "global_real_count", lambda **_kwargs: 30)
    for _ in range(3):
        response = client.get(path, headers=headers(path, "GET"))
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["provider_order_id"] == order["provider_order_id"]
        assert response.json()["id"] == order["id"]
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).model_dump() == before
    assert (
        len(db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()) == 1
    )
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(order["id"]))
    ).first()
    assert fake.create_calls == 1


@pytest.mark.parametrize(
    "status", ["APPROVED", "COMPLETED", "VOIDED", "SAVED", "UNKNOWN"]
)
def test_resume_never_restarts_approved_complete_void_or_unknown_provider_state(
    client, db, payment_only, monkeypatch, status
):
    order = create(client).json()
    fake = payment_only[-1]
    fake.orders[order["provider_order_id"]]["status"] = status
    monkeypatch.setattr(
        fake, "capture_order", lambda *_: pytest.fail("Must not capture")
    )
    path = checkout_path(order)
    assert client.get(path, headers=headers(path, "GET")).status_code == 409
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).status == "created"
    assert fake.create_calls == 1


@pytest.mark.parametrize("kind", ["captures", "authorizations"])
def test_resume_rejects_any_payment_resource_even_if_provider_status_is_action_required(
    client, payment_only, kind
):
    order = create(client).json()
    data = payment_only[-1].orders[order["provider_order_id"]]
    data["status"] = "PAYER_ACTION_REQUIRED"
    data["purchase_units"][0]["payments"] = {kind: [{"status": "PENDING"}]}
    path = checkout_path(order)
    assert client.get(path, headers=headers(path, "GET")).status_code == 409


@pytest.mark.parametrize(
    "tampering", ["amount", "currency", "merchant", "invoice", "provider_id", "country"]
)
def test_resume_verifies_original_provider_ownership_and_snapshot(
    client, payment_only, tampering
):
    order = create(client).json()
    data = payment_only[-1].orders[order["provider_order_id"]]
    unit = data["purchase_units"][0]
    if tampering == "amount":
        unit["amount"]["value"] = "0.01"
    elif tampering == "currency":
        unit["amount"]["currency_code"] = "EUR"
    elif tampering == "merchant":
        unit["payee"]["merchant_id"] = "OTHER-MERCHANT"
    elif tampering == "invoice":
        unit["invoice_id"] = str(uuid.uuid4())
    elif tampering == "provider_id":
        data["id"] = "OTHER-PROVIDER-ORDER"
    else:
        data["payer"] = {"address": {"country_code": "CN"}}
    path = checkout_path(order)
    assert client.get(path, headers=headers(path, "GET")).status_code == 409


@pytest.mark.parametrize(
    "status",
    [
        "approved",
        "capture_pending",
        "payment_review",
        "paid",
        "failed",
        "canceled",
        "refunded",
        "reversed",
    ],
)
def test_resume_rejects_local_terminal_or_uncertain_states_without_provider_call(
    client, db, payment_only, monkeypatch, status
):
    order = create(client).json()
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    saved.status = status
    db.add(saved)
    db.commit()
    fake = payment_only[-1]
    monkeypatch.setattr(
        fake,
        "order_details",
        lambda *_: pytest.fail("Unsafe order must not reach provider"),
    )
    path = checkout_path(order)
    assert client.get(path, headers=headers(path, "GET")).status_code == 409
    assert fake.create_calls == 1


@pytest.mark.parametrize(
    "reason",
    ["expiry", "hold", "revoked", "region", "unsigned", "not-selected", "closed"],
)
def test_resume_keeps_identity_region_freeze_and_time_boundaries(
    client, db, payment_only, monkeypatch, reason
):
    _, user_id, _, session_id, fake = payment_only
    order = create(client).json()
    path = checkout_path(order)
    h = headers(path, "GET")
    if reason == "expiry":
        monkeypatch.setattr(
            settings,
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    elif reason == "hold":
        user = db.get(AppUser, user_id)
        user.payment_hold = True
        db.add(user)
        db.commit()
    elif reason == "revoked":
        local = db.get(AppUserSession, session_id)
        local.revoked_at = datetime.now(UTC)
        db.add(local)
        db.commit()
    elif reason == "region":
        h = headers(path, "GET", country="US")
    elif reason == "unsigned":
        h = {"Authorization": "Bearer isolated-payment-only", "CF-IPCountry": "CN"}
    elif reason == "not-selected":
        monkeypatch.setattr(
            settings, "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID", uuid.uuid4()
        )
    else:
        monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED", False)
        monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    monkeypatch.setattr(
        fake,
        "order_details",
        lambda *_: pytest.fail("Denied request must not reach provider"),
    )
    assert client.get(path, headers=h).status_code == 403


def test_resume_cross_user_missing_provider_and_provider_failure_preserve_original(
    client, db, payment_only, monkeypatch
):
    order = create(client).json()
    path = checkout_path(order)
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    original_user = saved.app_user_id
    other = AppUser(account_type="clerk")
    db.add(other)
    db.flush()
    saved.app_user_id = other.id
    db.add(saved)
    db.commit()
    assert client.get(path, headers=headers(path, "GET")).status_code == 404
    saved.app_user_id = original_user
    provider_id = saved.provider_order_id
    saved.provider_order_id = None
    db.add(saved)
    db.commit()
    assert client.get(path, headers=headers(path, "GET")).status_code == 409
    saved.provider_order_id = provider_id
    db.add(saved)
    db.commit()

    def unavailable(_provider_id):
        raise PayPalError("Isolated timeout or unavailable order")

    monkeypatch.setattr(payment_only[-1], "order_details", unavailable)
    assert client.get(path, headers=headers(path, "GET")).status_code == 502
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).status == "created"
    assert payment_only[-1].create_calls == 1


def test_resume_requires_one_lifetime_order_and_a_configured_provider(
    client, db, payment_only, monkeypatch
):
    order = create(client).json()
    path = checkout_path(order)
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", None)
    assert client.get(path, headers=headers(path, "GET")).status_code == 503
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "unit-private")
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    duplicate = AppOrder(
        app_user_id=saved.app_user_id,
        provider="paypal",
        product_id="coins_100",
        payment_environment="live",
        payment_idempotency_key=str(uuid.uuid4()),
        amount=599,
        currency="USD",
        coin_quantity=100,
    )
    db.add(duplicate)
    db.commit()
    assert client.get(path, headers=headers(path, "GET")).status_code == 409
    assert payment_only[-1].create_calls == 1


@pytest.mark.parametrize("change", ["expiry", "hold", "settled"])
def test_resume_rechecks_changes_while_provider_get_is_in_flight(
    client, db, payment_only, monkeypatch, change
):
    _, user_id, _, _, fake = payment_only
    order = create(client).json()
    original_get = fake.order_details

    def provider_get(provider_id):
        result = original_get(provider_id)
        if change == "expiry":
            monkeypatch.setattr(
                settings,
                "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
                datetime.now(UTC) - timedelta(seconds=1),
            )
        elif change == "hold":
            user = db.get(AppUser, user_id)
            user.payment_hold = True
            db.add(user)
            db.commit()
        else:
            saved = db.get(AppOrder, uuid.UUID(order["id"]))
            saved.status = "capture_pending"
            db.add(saved)
            db.commit()
        return result

    monkeypatch.setattr(fake, "order_details", provider_get)
    path = checkout_path(order)
    assert client.get(path, headers=headers(path, "GET")).status_code == (
        409 if change == "settled" else 403
    )
    assert fake.create_calls == 1


def recovery_path(order):
    return f"{ORDERS}/{order['id']}/recovery"


@pytest.mark.parametrize("status", ["CREATED", "PAYER_ACTION_REQUIRED"])
@pytest.mark.parametrize("expired", [False, True])
def test_recovery_reads_original_after_expiry_without_granting_a_new_payment(
    client, db, payment_only, monkeypatch, status, expired
):
    order = create(client).json()
    fake = payment_only[-1]
    fake.orders[order["provider_order_id"]]["status"] = status
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    # Never use a generic six-hour rule as proof an actual provider order expired.
    saved.created_at = datetime.now(UTC) - timedelta(days=3)
    db.add(saved)
    db.commit()
    db.refresh(saved)
    before = saved.model_dump()
    if expired:
        monkeypatch.setattr(
            settings,
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(minutes=1),
        )
    monkeypatch.setattr(
        fake, "create_order", lambda *_: pytest.fail("Read-only recovery cannot create")
    )
    monkeypatch.setattr(
        fake,
        "capture_order",
        lambda *_: pytest.fail("Read-only recovery cannot capture"),
    )
    path = recovery_path(order)
    for _ in range(2):
        response = client.get(path, headers=headers(path, "GET"))
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        assert result["decision"] == (
            "authorization_required" if expired else "resume_original"
        )
        assert result["resume_allowed"] is not expired
        assert result["replacement_allowed"] is False
        assert result["replacement_candidate"] is False
        assert result["provider_order_status"] == status
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).model_dump() == before
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(order["id"]))
    ).first()


@pytest.mark.parametrize("provider_http_status", [None, 400, 403, 404, 422, 500, 503])
def test_recovery_http_failures_never_prove_unpaid_release_slot_or_change_finances(
    client, db, payment_only, monkeypatch, provider_http_status
):
    order = create(client).json()
    before = db.get(AppOrder, uuid.UUID(order["id"])).model_dump()
    fake = payment_only[-1]

    def unavailable(_provider_id):
        raise PayPalError(
            "Provider body must not be forwarded",
            provider_status_code=provider_http_status,
        )

    monkeypatch.setattr(fake, "order_details", unavailable)
    monkeypatch.setattr(
        fake, "capture_order", lambda *_: pytest.fail("Must not capture")
    )
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "manual_review"
    assert result["reason_code"] == (
        "provider_order_unavailable"
        if provider_http_status == 404
        else "provider_query_unconfirmed"
    )
    assert result["provider_http_status"] == provider_http_status
    assert (
        not result["resume_allowed"]
        and not result["replacement_allowed"]
        and not result["replacement_candidate"]
    )
    assert "Provider body" not in response.text
    assert create(client).status_code == 409
    assert fake.create_calls == 1
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).model_dump() == before
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(order["id"]))
    ).first()


@pytest.mark.parametrize("local_status", ["created", "canceled"])
def test_genuine_void_only_prepares_manual_candidate_and_never_resets_lifetime_slot(
    client, db, payment_only, local_status
):
    order = create(client).json()
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    saved.status = local_status
    db.add(saved)
    db.commit()
    payment_only[-1].orders[order["provider_order_id"]]["status"] = "VOIDED"
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    assert response.status_code == 200
    assert response.json()["decision"] == "replacement_candidate"
    assert response.json()["replacement_candidate"] is True
    assert response.json()["replacement_allowed"] is False
    assert response.json()["resume_allowed"] is False
    assert create(client).status_code == 409
    db.expire_all()
    assert db.get(AppOrder, uuid.UUID(order["id"])).status == local_status


@pytest.mark.parametrize("status", ["APPROVED", "COMPLETED", "SAVED", "UNKNOWN"])
def test_recovery_never_captures_or_replaces_approved_completed_or_unknown_state(
    client, payment_only, monkeypatch, status
):
    order = create(client).json()
    fake = payment_only[-1]
    fake.orders[order["provider_order_id"]]["status"] = status
    monkeypatch.setattr(
        fake, "capture_order", lambda *_: pytest.fail("Even APPROVED is GET only")
    )
    path = recovery_path(order)
    result = client.get(path, headers=headers(path, "GET")).json()
    assert result["decision"] == (
        "settlement_pending" if status == "APPROVED" else "manual_review"
    )
    assert (
        not result["resume_allowed"]
        and not result["replacement_candidate"]
        and not result["replacement_allowed"]
    )


@pytest.mark.parametrize(
    "capture_status",
    ["COMPLETED", "PENDING", "DENIED", "REFUNDED", "PARTIALLY_REFUNDED", "REVERSED"],
)
def test_recovery_capture_evidence_never_restarts_payment_or_mints_credits(
    client, db, payment_only, monkeypatch, capture_status
):
    order = create(client).json()
    fake = payment_only[-1]
    data = fake.orders[order["provider_order_id"]]
    data["status"] = "COMPLETED"
    data["purchase_units"][0]["payments"] = {
        "captures": [
            {
                "id": "CAP-ONLY-READ",
                "status": capture_status,
                "amount": {"currency_code": "USD", "value": "5.99"},
            }
        ]
    }
    monkeypatch.setattr(fake, "capture_order", lambda *_: pytest.fail("Cannot capture"))
    path = recovery_path(order)
    result = client.get(path, headers=headers(path, "GET")).json()
    assert result["decision"] == (
        "settlement_pending"
        if capture_status in {"COMPLETED", "PENDING"}
        else "manual_review"
    )
    assert not result["resume_allowed"] and not result["replacement_candidate"]
    db.expire_all()
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    assert (
        saved.status == "created"
        and saved.capture_id is None
        and saved.fulfilled_at is None
    )
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == saved.id)
    ).first()


@pytest.mark.parametrize(
    "tampering",
    [
        "amount",
        "merchant",
        "invoice",
        "country",
        "resources",
        "capture_amount",
        "multiple_captures",
    ],
)
def test_recovery_unverified_evidence_is_never_a_replacement_candidate(
    client, payment_only, tampering
):
    order = create(client).json()
    data = payment_only[-1].orders[order["provider_order_id"]]
    data["status"] = "VOIDED"
    unit = data["purchase_units"][0]
    if tampering == "amount":
        unit["amount"]["value"] = "0.01"
    elif tampering == "merchant":
        unit["payee"]["merchant_id"] = "OTHER"
    elif tampering == "invoice":
        unit["invoice_id"] = "OTHER"
    elif tampering == "country":
        data["payer"] = {"address": {"country_code": "CN"}}
    elif tampering == "resources":
        unit["payments"] = {"captures": "bad"}
    else:
        capture = {
            "id": "CAP-BAD",
            "status": "COMPLETED",
            "amount": {
                "currency_code": "USD",
                "value": "0.01" if tampering == "capture_amount" else "5.99",
            },
        }
        unit["payments"] = {
            "captures": [capture] * (2 if tampering == "multiple_captures" else 1)
        }
    path = recovery_path(order)
    result = client.get(path, headers=headers(path, "GET")).json()
    assert result["decision"] == "manual_review"
    assert not result["replacement_candidate"] and not result["resume_allowed"]


def test_recovery_records_remain_owned_and_no_unknown_order_reaches_provider(
    client, db, payment_only, monkeypatch
):
    order = create(client).json()
    fake = payment_only[-1]
    monkeypatch.setattr(
        fake,
        "order_details",
        lambda *_: pytest.fail("Unowned/missing order must not reach provider"),
    )
    path = recovery_path(order)
    assert client.get(path).status_code == 401
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    original_user = saved.app_user_id
    other = AppUser(account_type="clerk")
    db.add(other)
    db.flush()
    saved.app_user_id = other.id
    db.add(saved)
    db.commit()
    assert client.get(path, headers=headers(path, "GET")).status_code == 404
    saved.app_user_id = original_user
    saved.provider_order_id = None
    db.add(saved)
    db.commit()
    result = client.get(path, headers=headers(path, "GET")).json()
    assert result["reason_code"] == "provider_submission_unknown"


@pytest.mark.parametrize("reason", ["multiple", "snapshot", "financial"])
def test_recovery_local_conflicts_stop_before_provider_get(
    client, db, payment_only, monkeypatch, reason
):
    order = create(client).json()
    saved = db.get(AppOrder, uuid.UUID(order["id"]))
    if reason == "multiple":
        db.add(
            AppOrder(
                app_user_id=saved.app_user_id,
                provider="paypal",
                product_id="coins_100",
                payment_environment="live",
                amount=599,
                currency="USD",
                coin_quantity=100,
                payment_idempotency_key=str(uuid.uuid4()),
            )
        )
    elif reason == "snapshot":
        saved.amount = 1199
        db.add(saved)
    else:
        saved.capture_id = "EXISTING-CAPTURE"
        db.add(saved)
    db.commit()
    monkeypatch.setattr(
        payment_only[-1],
        "order_details",
        lambda *_: pytest.fail("Conflicting local evidence is manual only"),
    )
    path = recovery_path(order)
    result = client.get(path, headers=headers(path, "GET")).json()
    assert result["decision"] == "manual_review"
    assert (
        result["reason_code"]
        == {
            "multiple": "multiple_order_history",
            "snapshot": "order_snapshot_mismatch",
            "financial": "financial_history_requires_review",
        }[reason]
    )
    assert not result["resume_allowed"] and not result["replacement_allowed"]


@pytest.mark.parametrize("malformed", ["empty", "payments", "payer", "authorization"])
def test_recovery_malformed_or_authorized_resources_cannot_unlock_payment(
    client, payment_only, monkeypatch, malformed
):
    order = create(client).json()
    fake = payment_only[-1]
    if malformed == "empty":
        monkeypatch.setattr(fake, "order_details", lambda *_: None)
    else:
        data = fake.orders[order["provider_order_id"]]
        if malformed == "payer":
            data["payer"] = []
        else:
            data["purchase_units"][0]["payments"] = (
                []
                if malformed == "payments"
                else {"authorizations": [{"id": "AUTH-EXISTS"}]}
            )
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == (
        "settlement_pending" if malformed == "authorization" else "manual_review"
    )
    assert not result["resume_allowed"] and not result["replacement_candidate"]
    assert not result["replacement_allowed"]


@pytest.mark.usefixtures("payment_only")
def test_recovery_client_construction_failure_does_not_enable_payment(
    client, monkeypatch
):
    order = create(client).json()

    def unavailable():
        raise PayPalError("Private provider details must not escape")

    monkeypatch.setattr(app_paypal, "get_paypal_client", unavailable)
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    assert response.status_code == 200
    assert response.json()["reason_code"] == "provider_query_unconfirmed"
    assert not response.json()["resume_allowed"]
    assert "Private provider" not in response.text


@pytest.mark.parametrize("change", ["expiry", "hold", "reference", "owner", "settled"])
def test_recovery_refreshes_callback_and_identity_state_after_provider_read(
    client, db, payment_only, monkeypatch, change
):
    order = create(client).json()
    fake = payment_only[-1]
    original_get = fake.order_details

    def in_flight(provider_id):
        data = original_get(provider_id)
        saved = db.get(AppOrder, uuid.UUID(order["id"]))
        if change == "expiry":
            monkeypatch.setattr(
                settings,
                "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
                datetime.now(UTC) - timedelta(seconds=1),
            )
        elif change == "hold":
            user = db.get(AppUser, saved.app_user_id)
            user.payment_hold = True
            db.add(user)
            db.commit()
        elif change == "reference":
            saved.provider_order_id = "DIFFERENT-PROVIDER-ORDER"
            db.add(saved)
            db.commit()
        elif change == "owner":
            user = AppUser(account_type="clerk")
            db.add(user)
            db.flush()
            saved.app_user_id = user.id
            db.add(saved)
            db.commit()
        else:
            fake.capture_order(saved)
            paypal_orders.apply_order_state(db, saved.id, original_get(provider_id))
            db.commit()
        return data

    monkeypatch.setattr(fake, "order_details", in_flight)
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    if change == "owner":
        assert response.status_code == 404
        return
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["decision"]
        == {
            "expiry": "authorization_required",
            "hold": "manual_review",
            "reference": "manual_review",
            "settled": "credited",
        }[change]
    )
    assert not result["replacement_allowed"] and not result["resume_allowed"]


@pytest.mark.parametrize("reason", ["mode", "user", "environment", "secret"])
def test_recovery_does_not_broaden_live_account_or_provider_access(
    client, payment_only, monkeypatch, reason
):
    order = create(client).json()
    fake = payment_only[-1]
    monkeypatch.setattr(
        fake,
        "order_details",
        lambda *_: pytest.fail("Closed configuration must not reach provider"),
    )
    if reason == "mode":
        monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED", False)
        monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    elif reason == "user":
        monkeypatch.setattr(
            settings, "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID", uuid.uuid4()
        )
    elif reason == "environment":
        monkeypatch.setattr(settings, "PAYPAL_ENVIRONMENT", "sandbox")
    else:
        monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", None)
    path = recovery_path(order)
    response = client.get(path, headers=headers(path, "GET"))
    if reason == "secret":
        assert (
            response.status_code == 200
            and response.json()["reason_code"] == "payment_service_unavailable"
        )
    else:
        assert response.status_code == 404


@pytest.mark.usefixtures("payment_only")
def test_paypal_http_error_keeps_internal_404_without_forwarding_raw_provider_data():
    calls = []

    def transport(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "isolated-not-real-token"})
        return httpx.Response(
            404, json={"name": "RESOURCE_NOT_FOUND", "private": "never forward"}
        )

    client = PayPalClient(httpx.MockTransport(transport))
    try:
        with pytest.raises(PayPalError) as caught:
            client.order_details("ORIGINAL-ONLY")
        assert (
            caught.value.status_code == 409 and caught.value.provider_status_code == 404
        )
        assert "private" not in str(caught.value) and "never forward" not in str(
            caught.value
        )
        assert calls == [
            ("POST", "/v1/oauth2/token"),
            ("GET", "/v2/checkout/orders/ORIGINAL-ONLY"),
        ]
    finally:
        client.close()


@pytest.mark.parametrize("close", ["expiry", "disabled", "account-setup"])
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
    if close == "account-setup":
        monkeypatch.setattr(settings, "APP_COMMERCE_TERMS_APPROVED", False)
        monkeypatch.setattr(settings, "APP_CONTROLLED_REGISTRATION_ENABLED", True)
        monkeypatch.setattr(
            settings, "APP_CONTROLLED_REGISTRATION_EMAIL", "new-setup@example.com"
        )
        monkeypatch.setattr(settings, "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED", True)
        monkeypatch.setattr(
            settings,
            "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT",
            datetime.now(UTC) + timedelta(hours=1),
        )
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


@pytest.fixture
def replacement_setup(client, payment_only, superuser_token_headers, monkeypatch):
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED", True)
    monkeypatch.setattr(admin_app, "get_paypal_client", lambda: payment_only[-1])
    original = create(client).json()
    payment_only[-1].orders[original["provider_order_id"]]["status"] = "VOIDED"
    body = {
        "reason": "Owner separately approved this isolated replacement",
        "evidence_reference": "Isolated VOIDED provider record; not real funds",
        "idempotency_key": str(uuid.uuid4()),
        "merchant_checked_no_payment": True,
        "payer_confirmed_no_payment": True,
        "expires_at": settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT.isoformat(),
    }
    return original, body, superuser_token_headers, payment_only[-1]


def grant_replacement(client, setup, **overrides):
    old, body, admin, _ = setup
    return client.post(
        f"/api/v1/admin/app/orders/{old['id']}/replacement-approval",
        headers=admin,
        json={**body, **overrides},
    )


def replace_order(client, old, key=None, **extra):
    path = f"{ORDERS}/{old['id']}/replacement"
    return client.post(
        path, headers=headers(path, key=key or str(uuid.uuid4())), **extra
    )


def test_replacement_default_off_and_admin_approval_is_audited_not_payment(
    client, db, replacement_setup, monkeypatch
):
    old, _, admin, fake = replacement_setup
    assert not _commerce_settings().APP_PAYMENT_ONLY_REPLACEMENT_ENABLED
    with pytest.raises(ValidationError):
        _commerce_settings(APP_PAYMENT_ONLY_REPLACEMENT_ENABLED=True)
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED", False)
    assert grant_replacement(client, replacement_setup).status_code == 403
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED", True)
    path = f"/api/v1/admin/app/orders/{old['id']}/replacement-approval"
    assert client.post(path, json=replacement_setup[1]).status_code == 401
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", True)
    assert (
        client.post(path, headers=admin, json=replacement_setup[1]).status_code == 403
    )
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", False)
    for _ in range(2):
        result = grant_replacement(client, replacement_setup)
        assert result.status_code == 200, result.text
        assert result.json()["replacement_order_id"] is None
    assert (
        grant_replacement(
            client, replacement_setup, reason="Another independently changed reason"
        ).status_code
        == 409
    )
    logs = db.exec(
        select(AppAdminOperationLog).where(
            AppAdminOperationLog.target_id == uuid.UUID(old["id"]),
            AppAdminOperationLog.action == "paypal_replacement.approve",
        )
    ).all()
    assert len(logs) == 1 and "VOIDED" in logs[0].details_json
    assert fake.create_calls == 1
    assert create(client).status_code == 409
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert cfg["payment_only_replacement_original_id"] == old["id"]
    assert not cfg["recharge_enabled"] and not cfg["registration_enabled"]
    anonymous = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN")).json()
    assert anonymous["payment_only_replacement_original_id"] is None
    assert anonymous["payment_only_checkout_order_id"] is None


@pytest.mark.parametrize(
    "state",
    [
        "CREATED",
        "APPROVED",
        "COMPLETED",
        "PAYER_ACTION_REQUIRED",
        "SAVED",
        "404",
        "capture",
        "authorization",
        "wrong-merchant",
    ],
)
def test_replacement_never_approves_unknown_payable_or_financial_provider_state(
    client, db, replacement_setup, monkeypatch, state
):
    old, _, _, fake = replacement_setup
    data = fake.orders[old["provider_order_id"]]
    if state == "404":

        def missing(_):
            raise PayPalError(provider_status_code=404)

        monkeypatch.setattr(fake, "order_details", missing)
    elif state in {"capture", "authorization"}:
        data["purchase_units"][0]["payments"] = {
            "captures" if state == "capture" else "authorizations": [
                {"id": "EXISTING-FINANCIAL-RESOURCE"}
            ]
        }
    elif state == "wrong-merchant":
        data["purchase_units"][0]["payee"]["merchant_id"] = "OTHER"
    else:
        data["status"] = state
    response = grant_replacement(client, replacement_setup)
    assert response.status_code == 409, response.text
    assert not db.exec(select(AppPayPalReplacement)).first()
    assert fake.create_calls == 1


@pytest.mark.parametrize(
    "change",
    [
        "naive",
        "late",
        "no-merchant",
        "no-payer",
        "blank-reason",
        "extra-amount",
        "hold",
        "identity",
        "capture",
        "expired",
    ],
)
def test_replacement_approval_evidence_and_window_fail_closed(
    client, db, payment_only, replacement_setup, monkeypatch, change
):
    old = replacement_setup[0]
    overrides = {}
    if change == "naive":
        overrides["expires_at"] = datetime.now().isoformat()
    elif change == "late":
        overrides["expires_at"] = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    elif change == "no-merchant":
        overrides["merchant_checked_no_payment"] = False
    elif change == "no-payer":
        overrides["payer_confirmed_no_payment"] = False
    elif change == "blank-reason":
        overrides["reason"] = " " * 20
    elif change == "extra-amount":
        overrides["amount"] = 1
    elif change == "expired":
        monkeypatch.setattr(
            settings,
            "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    elif change == "hold":
        user = db.get(AppUser, payment_only[1])
        user.payment_hold = True
        db.add(user)
        db.commit()
    elif change == "identity":
        identity = db.get(AppUserIdentity, payment_only[2])
        identity.email_verified = False
        db.add(identity)
        db.commit()
    else:
        row = db.get(AppOrder, uuid.UUID(old["id"]))
        row.capture_id = "PRIOR-CAPTURE"
        db.add(row)
        db.commit()
    assert grant_replacement(client, replacement_setup, **overrides).status_code in {
        403,
        409,
        422,
    }
    assert not db.exec(select(AppPayPalReplacement)).first()


def test_one_replacement_link_survives_refresh_and_settles_once_after_close(
    client, db, replacement_setup, monkeypatch
):
    old, _, _, fake = replacement_setup
    assert grant_replacement(client, replacement_setup).status_code == 200
    key = str(uuid.uuid4())
    response = replace_order(client, old, key)
    assert response.status_code == 200, response.text
    child = response.json()
    assert child["id"] != old["id"] and (
        child["amount"],
        child["currency"],
        child["coin_quantity"],
    ) == (599, "USD", 100)
    assert replace_order(client, old, key).json()["id"] == child["id"]
    assert replace_order(client, old).status_code == 409
    assert create(client).status_code == 409
    original_key = db.get(AppOrder, uuid.UUID(old["id"])).payment_idempotency_key
    assert create(client, key=original_key).status_code == 409
    assert fake.create_calls == 2
    cfg = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert (
        cfg["payment_only_replacement_original_id"] is None
        and cfg["payment_only_checkout_order_id"] == child["id"]
    )
    for order, status in [(old, 409), (child, 200)]:
        path = checkout_path(order)
        assert client.get(path, headers=headers(path, "GET")).status_code == status
    path = f"{ORDERS}/{child['id']}/capture"
    fake.capture_order(db.get(AppOrder, uuid.UUID(child["id"])))
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED", False)
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED", False)
    monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    for _ in range(2):
        assert client.post(path, headers=headers(path)).json()["fulfilled_at"]
    ledger = db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(child["id"]))
    ).all()
    assert len(ledger) == 1 and ledger[0].delta == 100
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(old["id"]))
    ).first()
    assert (
        len(
            db.exec(
                select(AppAdminOperationLog).where(
                    AppAdminOperationLog.action == "paypal_replacement.consume",
                    AppAdminOperationLog.target_id == uuid.UUID(old["id"]),
                )
            ).all()
        )
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        "no-grant",
        "grant-expired",
        "mode-off",
        "reference",
        "multiple",
        "same-key",
        "capacity",
        "session-revoked-in-flight",
        "expiry-in-flight",
        "owner-before-reserve",
    ],
)
def test_replacement_create_rechecks_identity_budget_and_original(
    client, db, payment_only, replacement_setup, monkeypatch, change
):
    old, _, _, fake = replacement_setup
    if change != "no-grant":
        assert grant_replacement(client, replacement_setup).status_code == 200
    key = str(uuid.uuid4())
    if change == "grant-expired":
        grant = db.exec(select(AppPayPalReplacement)).one()
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.add(grant)
        db.commit()
    elif change == "mode-off":
        monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED", False)
    elif change == "reference":
        saved = db.get(AppOrder, uuid.UUID(old["id"]))
        saved.provider_order_id = "CHANGED"
        db.add(saved)
        db.commit()
    elif change == "multiple":
        db.add(
            AppOrder(
                app_user_id=payment_only[1],
                provider="paypal",
                payment_environment="live",
                product_id="coins_100",
                amount=599,
                currency="USD",
                coin_quantity=100,
                payment_idempotency_key=str(uuid.uuid4()),
            )
        )
        db.commit()
    elif change == "same-key":
        key = db.get(AppOrder, uuid.UUID(old["id"])).payment_idempotency_key
    elif change == "capacity":
        monkeypatch.setattr(
            "app.services.video_quota.global_real_count", lambda **_: 30
        )
    elif change == "owner-before-reserve":
        saved = db.get(AppOrder, uuid.UUID(old["id"]))
        other = AppUser(account_type="clerk")
        db.add(other)
        db.flush()
        saved.app_user_id = other.id
        db.add(saved)
        db.commit()
    elif change.endswith("in-flight"):
        original_get = fake.order_details

        def during_get(provider_id):
            result = original_get(provider_id)
            if change == "session-revoked-in-flight":
                local = db.get(AppUserSession, payment_only[3])
                local.revoked_at = datetime.now(UTC)
                db.add(local)
                db.commit()
            else:
                monkeypatch.setattr(
                    settings,
                    "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
                    datetime.now(UTC) - timedelta(seconds=1),
                )
            return result

        monkeypatch.setattr(fake, "order_details", during_get)
    response = replace_order(client, old, key)
    assert response.status_code in {403, 409}, response.text
    assert fake.create_calls == 1
    grant = db.exec(select(AppPayPalReplacement)).first()
    assert not grant or grant.replacement_order_id is None


def test_replacement_unknown_create_result_consumes_budget_without_retry(
    client, db, replacement_setup, monkeypatch
):
    old, _, _, fake = replacement_setup
    assert grant_replacement(client, replacement_setup).status_code == 200
    original_create = fake.create_order

    def lost(order):
        original_create(order)
        raise PayPalError()

    monkeypatch.setattr(fake, "create_order", lost)
    key = str(uuid.uuid4())
    assert replace_order(client, old, key).status_code == 502
    for attempt in [key, str(uuid.uuid4())]:
        assert replace_order(client, old, attempt).status_code == 409
    assert fake.create_calls == 2
    grant = db.exec(select(AppPayPalReplacement)).one()
    assert grant.replacement_order_id and grant.consumed_at
    assert db.get(AppOrder, grant.replacement_order_id).provider_order_id is None
    assert not db.exec(
        select(AppCoinLedger).where(
            AppCoinLedger.order_id == grant.replacement_order_id
        )
    ).first()


@pytest.mark.parametrize(
    "when", ["before-reserve", "before-new-capture", "after-new-credit"]
)
def test_late_original_payment_is_never_captured_or_double_credited(
    client, db, payment_only, replacement_setup, when, monkeypatch
):
    old, _, _, fake = replacement_setup
    assert grant_replacement(client, replacement_setup).status_code == 200
    child = None
    if when != "before-reserve":
        child = replace_order(client, old).json()
    if when == "after-new-credit":
        fake.orders[child["provider_order_id"]]["status"] = "APPROVED"
        path = f"{ORDERS}/{child['id']}/capture"
        assert client.post(path, headers=headers(path)).json()["fulfilled_at"]
    data = fake.orders[old["provider_order_id"]]
    data["status"] = "APPROVED"
    saved = db.get(AppOrder, uuid.UUID(old["id"]))
    if when == "before-reserve":
        assert replace_order(client, old).status_code == 409
        path = f"{ORDERS}/{old['id']}/capture"
        monkeypatch.setattr(
            fake,
            "capture_order",
            lambda *_: pytest.fail("Never capture replaced original"),
        )
        response = client.post(path, headers=headers(path))
        assert response.status_code == 200 and response.json()["status"] == "approved"
    else:
        fake.capture_order(saved)
        paypal_orders.apply_order_state(
            db, saved.id, fake.order_details(saved.provider_order_id)
        )
        db.commit()
    db.expire_all()
    assert db.get(AppUser, payment_only[1]).payment_hold
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == uuid.UUID(old["id"]))
    ).first()
    conflict = db.exec(
        select(AppPaymentCase).where(
            AppPaymentCase.app_user_id == payment_only[1],
            AppPaymentCase.kind == "replacement_conflict",
        )
    ).first()
    assert conflict
    for resolution in ["recover", "dismiss"]:
        response = client.post(
            f"/api/v1/admin/app/payment-cases/{conflict.id}/resolve",
            headers=replacement_setup[2],
            json={
                "resolution": resolution,
                "reason": "Cannot clear a real financial conflict with zero recovery",
            },
        )
        assert response.status_code == 409
    db.expire_all()
    assert db.get(AppUser, payment_only[1]).payment_hold
    if child and when == "before-new-capture":
        fake.orders[child["provider_order_id"]]["status"] = "APPROVED"
        path = f"{ORDERS}/{child['id']}/capture"
        assert client.post(path, headers=headers(path)).status_code == 409
    if child:
        credits = db.exec(
            select(AppCoinLedger).where(
                AppCoinLedger.order_id == uuid.UUID(child["id"])
            )
        ).all()
        assert len(credits) == (1 if when == "after-new-credit" else 0)


def test_concurrent_replacement_keys_share_one_committed_reservation(
    client, db, replacement_setup
):
    old, _, _, fake = replacement_setup
    assert grant_replacement(client, replacement_setup).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda key: replace_order(client, old, key),
                [str(uuid.uuid4()), str(uuid.uuid4())],
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert fake.create_calls == 2
    assert (
        len(
            db.exec(
                select(AppOrder).where(
                    AppOrder.app_user_id == uuid.UUID(old["app_user_id"])
                )
            ).all()
        )
        == 2
    )


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
