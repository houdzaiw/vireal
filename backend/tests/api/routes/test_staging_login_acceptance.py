"""Local database + mocked Clerk only. Never contact a provider or deployed DB."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Connection
from sqlmodel import select

from app.core.config import (
    STAGING_LOGIN_ACCEPTANCE_ISSUER as ISSUER,
)
from app.core.config import (
    STAGING_LOGIN_ACCEPTANCE_ORIGIN as ORIGIN,
)
from app.core.config import (
    settings,
)
from app.models import (
    AppCoinLedger,
    AppOrder,
    AppUpload,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    AppVideoTask,
)
from app.services.staging_login_acceptance import STAGING_LOGIN_HEADER
from tests.api.routes.test_app_clerk_auth import clerk_mode as clerk_mode
from tests.api.routes.test_paypal_commerce import signed_headers
from tests.core.test_config_v12 import _settings

AUTH = "/api/v1/app/auth/session"
CONFIG = "/api/v1/app/paypal/config"
BUSINESS_GATES = (
    "APP_PUBLIC_REGISTRATION_ENABLED",
    "APP_CONTROLLED_REGISTRATION_ENABLED",
    "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED",
    "APP_INTERNAL_ACCEPTANCE_ENABLED",
    "APP_LIVE_ACCEPTANCE_ENABLED",
    "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED",
    "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED",
    "APP_GENERATION_ACCEPTANCE_ENABLED",
    "APP_VIDEO_SUBMISSIONS_ENABLED",
    "PAYPAL_ENABLED",
    "APP_COMMERCE_TERMS_APPROVED",
    "ADMIN_PUBLIC_SIGNUP_ENABLED",
    "LOCAL_DEMO_ENABLED",
    "APP_LEGACY_VIDEO_TASKS_ENABLED",
)


def configured(**overrides):
    values = {
        "ENVIRONMENT": "staging",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": ISSUER,
        "CLERK_JWKS_URL": ISSUER + "/.well-known/jwks.json",
        "CLERK_AUDIENCE": "staging-test-audience",
        "CLERK_AUTHORIZED_PARTIES": [ORIGIN],
        "CLERK_SECRET_KEY": "synthetic-test-key-never-use-online",
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "synthetic-edge-secret-only-for-offline-unit-tests",
        "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED": True,
        "APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT": "user_stagingAcceptance",
        "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
        + timedelta(minutes=20),
        **dict.fromkeys(BUSINESS_GATES, False),
    }
    values.update(overrides)
    return _settings(**values)


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Staging login tests must not contact any external service")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.fixture
def staging(db, clerk_mode, monkeypatch):
    subject = "user_staging" + uuid.uuid4().hex
    safe = configured(APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT=subject)
    names = (
        *BUSINESS_GATES,
        "ENVIRONMENT",
        "APP_AUTH_MODE",
        "CLERK_ISSUER_URL",
        "CLERK_JWKS_URL",
        "CLERK_AUTHORIZED_PARTIES",
        "APP_REGION_ENFORCEMENT_ENABLED",
        "APP_EDGE_SIGNING_SECRET",
        "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED",
        "APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT",
        "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT",
    )
    for name in names:
        monkeypatch.setattr(settings, name, getattr(safe, name))
    clerk_mode.claims = replace(
        clerk_mode.claims,
        issuer=ISSUER,
        subject=subject,
        session_id="sess_staging" + uuid.uuid4().hex,
        authorized_party=ORIGIN,
    )
    user = AppUser(account_type="clerk")
    db.add(user)
    db.flush()
    identity = AppUserIdentity(
        app_user_id=user.id,
        issuer=ISSUER,
        subject=subject,
        primary_email="existing-test@example.com",
        email_verified=True,
        providers_json='["email"]',
        login_count=0,
    )
    db.add(identity)
    db.commit()
    headers = {
        "Authorization": "Bearer synthetic-offline-token",
        STAGING_LOGIN_HEADER: "1",
        **signed_headers(AUTH, "POST", "CN"),
    }
    return clerk_mode, headers, user, identity


def user_sessions(db, user):
    return db.exec(
        select(AppUserSession).where(AppUserSession.app_user_id == user.id)
    ).all()


def test_defaults_off_and_expired_config_can_boot():
    defaults = _settings()
    assert defaults.APP_STAGING_LOGIN_ACCEPTANCE_ENABLED is False
    assert defaults.APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT is None
    assert defaults.APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT is None
    assert configured(
        APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT=datetime.now(UTC) - timedelta(seconds=1)
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENVIRONMENT": "production"},
        {"ENVIRONMENT": "local"},
        {"APP_AUTH_MODE": "dual"},
        {"APP_AUTH_MODE": "device"},
        {"CLERK_ISSUER_URL": "https://different.clerk.accounts.dev"},
        {
            "CLERK_JWKS_URL": "https://different.clerk.accounts.dev/.well-known/jwks.json"
        },
        {"CLERK_AUTHORIZED_PARTIES": ["https://app.usevireal.com"]},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": "short"},
        {"APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT": None},
        {"APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT": " user_other "},
        {"APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT": None},
        {
            "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
            + timedelta(minutes=31)
        },
        {
            "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT": datetime.now().replace(
                tzinfo=None
            )
        },
        {"APP_LIVE_ACCEPTANCE_SUBJECTS": ["user_other"]},
        *({name: True} for name in BUSINESS_GATES),
    ],
)
def test_unsafe_configuration_never_boots(overrides):
    with pytest.raises(ValidationError):
        configured(**overrides)


def test_correct_existing_user_only_updates_identity_and_sessions(client, db, staging):
    _, headers, user, identity = staging
    response = client.post(AUTH, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["app_user"]["id"] == str(user.id)
    assert not response.json()["is_new_user"]
    assert not response.json()["internal_generation_allowed"]
    assert not response.json()["generation_acceptance_read_allowed"]
    assert len(user_sessions(db, user)) == 1
    assert client.post(AUTH, headers=headers).status_code == 200
    assert len(user_sessions(db, user)) == 1
    db.refresh(identity)
    assert identity.login_count == 1
    assert (
        len(
            db.exec(
                select(AppUserIdentity).where(AppUserIdentity.app_user_id == user.id)
            ).all()
        )
        == 1
    )
    for model in (AppCoinLedger, AppOrder, AppUpload, AppVideoTask):
        assert not db.exec(select(model).where(model.app_user_id == user.id)).all()


def test_public_hint_has_no_identity_and_changes_no_business_entitlement(
    client, staging
):
    clerk, _, _, _ = staging
    response = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN"))
    data = response.json()
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert data["staging_sign_in_enabled"] and data["staging_sign_in_expires_at"]
    assert data["country"] == "CN" and not data["region_allowed"]
    for name in (
        "registration_enabled",
        "controlled_registration_enabled",
        "recharge_enabled",
        "uploads_enabled",
        "generation_enabled",
        "internal_sign_in_enabled",
        "payment_only_sign_in_enabled",
        "generation_acceptance_sign_in_enabled",
    ):
        assert data[name] is False
    assert clerk.claims.subject not in response.text
    assert "existing-test@example.com" not in response.text
    assert "synthetic-test-key" not in response.text


@pytest.mark.parametrize(
    "reason",
    [
        "wrong_subject",
        "wrong_issuer",
        "wrong_origin",
        "off",
        "expired",
        "future",
        "production",
        "missing_signature",
        "forged_signature",
        "stale_signature",
        "wrong_path",
        "spoofed_country",
        "unknown_country",
        "tor_country",
        "US",
        "invalid_marker",
        "missing_identity",
        "unverified_identity",
        "inactive",
        "deleted",
        "legacy",
        "payment_hold",
    ],
)
def test_denied_requests_do_not_write_or_query_provider(
    client, db, staging, monkeypatch, reason
):
    clerk, headers, user, identity = staging
    if reason == "wrong_subject":
        clerk.claims = replace(clerk.claims, subject="user_other")
    elif reason == "wrong_issuer":
        clerk.claims = replace(clerk.claims, issuer="https://other.clerk.accounts.dev")
    elif reason == "wrong_origin":
        clerk.claims = replace(
            clerk.claims, authorized_party="https://app.usevireal.com"
        )
    elif reason == "off":
        monkeypatch.setattr(settings, "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED", False)
    elif reason in {"expired", "future"}:
        monkeypatch.setattr(
            settings,
            "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) + timedelta(minutes=-1 if reason == "expired" else 31),
        )
    elif reason == "production":
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    elif reason in {"missing_signature", "spoofed_country"}:
        headers = {
            "Authorization": headers["Authorization"],
            STAGING_LOGIN_HEADER: "1",
            "CF-IPCountry": "CN",
        }
    elif reason == "forged_signature":
        headers["x-vireal-edge-signature"] = "0" * 64
    elif reason == "stale_signature":
        headers.update(signed_headers(AUTH, "POST", "CN", timestamp="1"))
    elif reason == "wrong_path":
        headers.update(signed_headers("/different", "POST", "CN"))
    elif reason in {"unknown_country", "tor_country", "US"}:
        headers.update(
            signed_headers(
                AUTH,
                "POST",
                {"unknown_country": "XX", "tor_country": "T1"}.get(reason, "US"),
            )
        )
    elif reason == "invalid_marker":
        headers[STAGING_LOGIN_HEADER] = "0"
    elif reason == "missing_identity":
        db.delete(identity)
        db.commit()
    elif reason == "unverified_identity":
        identity.email_verified = False
        db.add(identity)
        db.commit()
    elif reason == "inactive":
        user.status = "disabled"
        db.add(user)
        db.commit()
    elif reason == "deleted":
        user.deleted_at = datetime.now(UTC)
        db.add(user)
        db.commit()
    elif reason == "legacy":
        user.account_type = "device"
        db.add(user)
        db.commit()
    elif reason == "payment_hold":
        user.payment_hold = True
        db.add(user)
        db.commit()

    def forbidden_profile(_subject):
        pytest.fail("Denied staging login must not query provider profile")

    monkeypatch.setattr(clerk, "get_user_profile", forbidden_profile)
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not user_sessions(db, user)


@pytest.mark.parametrize("country", [None, "US", "XX", "T1"])
def test_hint_rejects_unsigned_or_non_CN_context(client, staging, country):
    assert staging[0].claims.subject == settings.APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT
    headers = (
        signed_headers(CONFIG, "GET", country) if country else {"CF-IPCountry": "CN"}
    )
    data = client.get(CONFIG, headers=headers).json()
    assert data["staging_sign_in_enabled"] is False
    assert data["staging_sign_in_expires_at"] is None


def test_expiry_during_profile_fetch_writes_nothing(client, db, staging, monkeypatch):
    clerk, headers, user, _ = staging
    original = clerk.get_user_profile

    def expire(subject):
        profile = original(subject)
        monkeypatch.setattr(
            settings,
            "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        return profile

    monkeypatch.setattr(clerk, "get_user_profile", expire)
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not user_sessions(db, user)


def test_expiry_after_identity_lock_writes_nothing(client, db, staging, monkeypatch):
    _, headers, user, _ = staging
    original = Connection.execute

    def expire(connection, statement, *args, **kwargs):
        result = original(connection, statement, *args, **kwargs)
        if "FOR UPDATE" in str(statement) and "app_user_identity" in str(statement):
            monkeypatch.setattr(
                settings,
                "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT",
                datetime.now(UTC) - timedelta(seconds=1),
            )
        return result

    monkeypatch.setattr(Connection, "execute", expire)
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not user_sessions(db, user)


def test_expired_mode_does_not_change_ordinary_existing_session_behavior(
    client, staging, monkeypatch
):
    _, headers, _, _ = staging
    monkeypatch.setattr(
        settings,
        "APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    assert client.post(AUTH, headers=headers).status_code == 403
    ordinary = {
        key: value for key, value in headers.items() if key != STAGING_LOGIN_HEADER
    }
    assert client.post(AUTH, headers=ordinary).status_code == 200
    data = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN")).json()
    assert (
        not data["staging_sign_in_enabled"]
        and data["staging_sign_in_expires_at"] is None
    )
    assert not data["region_allowed"] and not data["recharge_enabled"]


def test_unverified_provider_profile_never_updates_existing_identity(
    client, db, staging, monkeypatch
):
    clerk, headers, user, identity = staging
    profile = replace(
        clerk.get_user_profile(clerk.claims.subject), email_verified=False
    )
    monkeypatch.setattr(clerk, "get_user_profile", lambda _subject: profile)
    assert client.post(AUTH, headers=headers).status_code == 403
    assert not user_sessions(db, user)
    db.refresh(identity)
    assert identity.primary_email == "existing-test@example.com"
    assert identity.login_count == 0


def test_staging_acceptance_cannot_revive_a_revoked_app_session(client, db, staging):
    _, headers, user, _ = staging
    assert client.post(AUTH, headers=headers).status_code == 200
    session = user_sessions(db, user)[0]
    session.revoked_at = datetime.now(UTC)
    db.add(session)
    db.commit()
    assert client.post(AUTH, headers=headers).status_code == 403
    assert len(user_sessions(db, user)) == 1
    db.refresh(session)
    assert session.revoked_at is not None
