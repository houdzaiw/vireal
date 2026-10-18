"""Isolated account setup only. Never contact Clerk, storage or a payment API."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Connection
from sqlmodel import select

from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppOrder,
    AppUpload,
    AppUser,
    AppUserIdentity,
    AppVideoTask,
)
from tests.api.routes.test_controlled_registration import controlled as controlled
from tests.api.routes.test_controlled_registration import controlled_settings
from tests.api.routes.test_paypal_commerce import signed_headers
from tests.core.test_config_v12 import _settings

AUTH = "/api/v1/app/auth/session"
CONFIG = "/api/v1/app/paypal/config"


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("CN account setup tests must not perform external HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.fixture
def cn_setup(controlled, monkeypatch):
    clerk, headers = controlled
    for key, value in {
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED": True,
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT": datetime.now(UTC)
        + timedelta(hours=1),
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": False,
        "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED": False,
        "APP_INTERNAL_ACCEPTANCE_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, key, value)
    return clerk, {
        "Authorization": headers["Authorization"],
        **signed_headers(AUTH, "POST", "CN"),
    }


def test_default_is_off_and_no_target_is_embedded_in_config():
    configured = _settings()
    assert not configured.APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED
    assert configured.APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT is None
    assert configured.APP_CONTROLLED_REGISTRATION_EMAIL is None


def test_verified_target_initializes_once_with_zero_credits_and_can_login(
    client, db, cn_setup
):
    clerk, headers = cn_setup
    first = client.post(AUTH, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["is_new_user"]
    second = client.post(AUTH, headers=headers)
    assert second.status_code == 200 and not second.json()["is_new_user"]
    assert first.json()["app_user"]["id"] == second.json()["app_user"]["id"]
    assert not second.json()["internal_generation_allowed"]
    uid = uuid.UUID(first.json()["app_user"]["id"])
    assert client.get("/api/v1/app/wallet", headers=headers).json()["balance"] == 0
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == uid)
    ).all()
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == uid)).all()
    cfg = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN"))
    assert cfg.headers["cache-control"] == "no-store"
    data = cfg.json()
    assert data["country"] == "CN" and not data["region_allowed"]
    assert (
        data["controlled_registration_enabled"]
        and data["controlled_account_setup_enabled"]
    )
    assert (
        data["controlled_account_setup_mode"]
        and data["controlled_account_setup_expires_at"]
    )
    assert not data["registration_enabled"] and not data["recharge_enabled"]
    assert (
        not data["internal_sign_in_enabled"]
        and not data["payment_only_sign_in_enabled"]
    )
    assert (
        clerk.profile.primary_email not in cfg.text
        and clerk.claims.subject not in cfg.text
    )


@pytest.mark.parametrize("country", [None, "US", "XX", "T1"])
def test_unknown_proxy_or_other_country_never_initializes(
    client, db, cn_setup, country
):
    clerk, headers = cn_setup
    headers = {"Authorization": headers["Authorization"], "CF-IPCountry": "CN"}
    if country:
        headers.update(signed_headers(AUTH, "POST", country))
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()
    cfg = client.get(
        CONFIG, headers=signed_headers(CONFIG, "GET", country) if country else {}
    ).json()
    assert not cfg["controlled_account_setup_enabled"]
    assert not cfg["controlled_registration_enabled"] and not cfg["recharge_enabled"]


@pytest.mark.parametrize(
    "reason",
    [
        "other_email",
        "unverified",
        "issuer",
        "fake_signature",
        "expired",
        "future",
        "naive",
        "off",
    ],
)
def test_unverified_or_expired_requests_never_create_identity(
    client, db, cn_setup, monkeypatch, reason
):
    clerk, headers = cn_setup
    if reason == "other_email":
        clerk.profile = replace(
            clerk.profile, primary_email="somebody-else@example.com"
        )
        headers["x-vireal-controlled-email"] = str(
            settings.APP_CONTROLLED_REGISTRATION_EMAIL
        )
    elif reason == "unverified":
        clerk.profile = replace(clerk.profile, email_verified=False)
    elif reason == "issuer":
        clerk.claims = replace(clerk.claims, issuer="https://staging.example.test")
    elif reason == "fake_signature":
        headers["x-vireal-edge-signature"] = "f" * 64
    elif reason == "off":
        monkeypatch.setattr(settings, "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED", False)
    else:
        expiry = datetime.now(UTC) + timedelta(hours=9 if reason == "future" else -1)
        if reason == "naive":
            expiry = datetime.now().replace(tzinfo=None)
        monkeypatch.setattr(
            settings, "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT", expiry
        )
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


def test_expiry_while_waiting_for_account_lock_creates_no_identity(
    client, db, cn_setup, monkeypatch
):
    clerk, headers = cn_setup
    execute = Connection.execute

    def expire(connection, statement, *args, **kwargs):
        if "pg_advisory_xact_lock(hashtextextended" in str(statement):
            monkeypatch.setattr(
                settings,
                "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT",
                datetime.now(UTC) - timedelta(seconds=1),
            )
        return execute(connection, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", expire)
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


def test_concurrent_setup_has_one_identity_and_never_creates_a_payment(
    client, db, cn_setup
):
    _, headers = cn_setup
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(
            pool.map(lambda _: client.post(AUTH, headers=headers), range(3))
        )
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["app_user"]["id"] for r in responses}) == 1
    assert sum(r.json()["is_new_user"] for r in responses) == 1
    uid = uuid.UUID(responses[0].json()["app_user"]["id"])
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == uid)).all()


@pytest.mark.parametrize("state", ["expired", "disabled", "deleted", "frozen"])
def test_setup_never_revives_expired_or_disabled_existing_accounts(
    client, db, cn_setup, monkeypatch, state
):
    _, headers = cn_setup
    response = client.post(AUTH, headers=headers)
    assert response.status_code == 200
    user = db.get(AppUser, uuid.UUID(response.json()["app_user"]["id"]))
    if state == "expired":
        monkeypatch.setattr(
            settings,
            "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    elif state == "disabled":
        user.status = "disabled"
    elif state == "deleted":
        user.deleted_at = datetime.now(UTC)
    else:
        user.payment_hold = True
    db.add(user)
    db.commit()
    assert client.post(AUTH, headers=headers).status_code == 403
    db.refresh(user)
    assert state != "frozen" or user.payment_hold
    assert state != "deleted" or user.deleted_at
    assert state != "disabled" or user.status == "disabled"


def test_account_switch_never_moves_original_order_or_mints_credits(
    client, db, cn_setup
):
    old_user = AppUser(account_type="clerk")
    db.add(old_user)
    db.flush()
    order = AppOrder(
        app_user_id=old_user.id,
        provider="paypal",
        payment_environment="live",
        payment_idempotency_key=uuid.uuid4().hex,
        provider_order_id="unconfirmed-original",
        product_id="coins_100",
        amount=599,
        currency="USD",
        coin_quantity=100,
    )
    db.add(order)
    db.commit()
    _, headers = cn_setup
    response = client.post(AUTH, headers=headers)
    assert response.status_code == 200
    assert response.json()["app_user"]["id"] != str(old_user.id)
    db.refresh(order)
    assert order.app_user_id == old_user.id and order.status == "created"
    assert order.capture_id is None and order.fulfilled_at is None
    assert (
        client.get(
            f"/api/v1/app/paypal/orders/{order.id}/recovery", headers=headers
        ).status_code
        == 404
    )
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == order.id)
    ).all()


@pytest.mark.parametrize("unsafe_runtime", [False, True])
def test_setup_never_allows_upload_generate_or_new_payment(
    client, db, cn_setup, monkeypatch, unsafe_runtime
):
    _, headers = cn_setup
    response = client.post(AUTH, headers=headers)
    assert response.status_code == 200
    uid = uuid.UUID(response.json()["app_user"]["id"])
    if unsafe_runtime:
        monkeypatch.setattr(settings, "PAYPAL_ENABLED", True)
        monkeypatch.setattr(settings, "APP_PUBLIC_REGISTRATION_ENABLED", True)
        monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)
    # Even an allowed-country header cannot turn account setup into commerce.
    for path, payload in [
        ("/api/v1/app/paypal/orders", {"product_id": "coins_100"}),
        (
            "/api/v1/app/orders",
            {
                "provider": "apple",
                "product_id": "coins_100",
                "amount": 599,
                "currency": "USD",
            },
        ),
        (
            "/api/v1/app/video-tasks",
            {
                "effect_id": str(uuid.uuid4()),
                "variant_id": str(uuid.uuid4()),
                "upload_ids": [str(uuid.uuid4())],
            },
        ),
    ]:
        h = {
            "Authorization": headers["Authorization"],
            **signed_headers(path, "POST", "US"),
            "Idempotency-Key": uuid.uuid4().hex,
        }
        assert client.post(path, headers=h, json=payload).status_code == 403
    path = "/api/v1/app/uploads/images"
    h = {
        "Authorization": headers["Authorization"],
        **signed_headers(path, "POST", "US"),
    }
    assert (
        client.post(
            path,
            headers=h,
            files={"file": ("not-stored.png", b"not uploaded", "image/png")},
        ).status_code
        == 403
    )
    cfg = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "US")).json()
    assert not cfg["registration_enabled"] and not cfg["recharge_enabled"]
    for model in (AppOrder, AppCoinLedger, AppUpload, AppVideoTask):
        assert not db.exec(select(model).where(model.app_user_id == uid)).all()


def cn_settings(**overrides):
    values = {
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED": True,
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT": datetime.now(UTC)
        + timedelta(hours=1),
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }
    values.update(overrides)
    return controlled_settings(**values)


def test_expired_startup_remains_closed_instead_of_extending_window():
    configured = cn_settings(
        APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT=datetime.now(UTC)
        - timedelta(hours=1)
    )
    assert configured.APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED
    assert configured.APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT < datetime.now(UTC)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENVIRONMENT": "staging"},
        {"APP_AUTH_MODE": "device"},
        {"APP_CONTROLLED_REGISTRATION_ENABLED": False},
        {"APP_CONTROLLED_REGISTRATION_EMAIL": None},
        {"APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT": None},
        {"APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT": datetime.now()},
        {
            "APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT": datetime.now(UTC)
            + timedelta(hours=9)
        },
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": "short"},
        {"APP_PUBLIC_REGISTRATION_ENABLED": True},
        {"PAYPAL_ENABLED": True},
        {"APP_COMMERCE_TERMS_APPROVED": True},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": True},
        {"APP_PAYMENT_ONLY_REPLACEMENT_ENABLED": True},
        {"APP_INTERNAL_ACCEPTANCE_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_SUBJECTS": ["user_other"]},
        {"APP_VIDEO_SUBMISSIONS_ENABLED": True},
        {"ADMIN_PUBLIC_SIGNUP_ENABLED": True},
        {"LOCAL_DEMO_ENABLED": True},
        {"APP_LEGACY_VIDEO_TASKS_ENABLED": True},
    ],
)
def test_unsafe_settings_cannot_start(overrides):
    with pytest.raises(ValidationError):
        cn_settings(**overrides)
