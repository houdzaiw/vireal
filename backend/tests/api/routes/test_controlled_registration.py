"""Isolated/mocked account setup; never creates a real Clerk user or payment."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from pydantic import HttpUrl, ValidationError
from sqlalchemy import func
from sqlmodel import select

from app.api import deps
from app.api.routes import app_auth
from app.core.config import settings
from app.models import AppCoinLedger, AppOrder, AppUser, AppUserIdentity
from app.services import commercial_access
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from tests.api.routes.test_paypal_commerce import signed_headers
from tests.core.test_config_v12 import _settings

PATH = "/api/v1/app/auth/session"
EMAIL = "controlled@example.com"


@pytest.fixture
def controlled(monkeypatch):
    class Clerk:
        claims = ClerkSessionClaims(
            "https://clerk.example.test",
            f"user_controlled_{uuid.uuid4()}",
            f"session_{uuid.uuid4()}",
            "https://app.example.test",
        )
        profile = ClerkUserProfile(
            f"controlled-{uuid.uuid4()}@example.com", True, ("email",)
        )

        def verify_session_token(self, token):
            if token == "invalid":
                raise ClerkAuthenticationError("Invalid token")
            return self.claims

        def get_user_profile(self, _subject):
            return self.profile

    clerk = Clerk()
    for module in (deps, app_auth, commercial_access):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    for key, value in {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": HttpUrl("https://clerk.example.test"),
        "APP_CONTROLLED_REGISTRATION_ENABLED": True,
        "APP_CONTROLLED_REGISTRATION_EMAIL": clerk.profile.primary_email,
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_SUBJECTS": [],
        "APP_COMMERCE_TERMS_APPROVED": False,
        "ADMIN_PUBLIC_SIGNUP_ENABLED": False,
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-edge-secret-at-least-32-chars",
        "PAYPAL_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, key, value)
    return clerk, {
        "Authorization": "Bearer controlled-test-token",
        **signed_headers(PATH, "POST", "US"),
    }


def test_only_verified_target_can_initialize_zero_wallet_without_commerce(
    client, db, controlled
):
    clerk, headers = controlled
    target_email = clerk.profile.primary_email
    clerk.profile = replace(clerk.profile, primary_email=target_email.upper())
    for _ in range(2):
        response = client.post(PATH, headers=headers)
        assert response.status_code == 200, response.text
    assert not response.json()["is_new_user"]
    user_id = uuid.UUID(response.json()["app_user"]["id"])
    wallet = client.get("/api/v1/app/wallet", headers=headers)
    assert wallet.status_code == 200 and wallet.json()["balance"] == 0
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == user_id)
    ).all()
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()
    config_path = "/api/v1/app/paypal/config"
    config = client.get(config_path, headers=signed_headers(config_path, "GET", "US"))
    assert config.status_code == 200
    assert config.json()["controlled_registration_enabled"] is True
    assert not config.json()["registration_enabled"]
    assert not config.json()["recharge_enabled"]
    assert target_email not in config.text
    recharge = client.post(
        "/api/v1/app/paypal/orders",
        headers={
            **headers,
            **signed_headers("/api/v1/app/paypal/orders", "POST", "US"),
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"product_id": "coins_100"},
    )
    assert recharge.status_code == 503
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()


@pytest.mark.parametrize("region", [None, "CN", "XX", "T1"])
def test_controlled_registration_never_overrides_unknown_or_blocked_region(
    client, db, controlled, region
):
    clerk, headers = controlled
    headers = {"Authorization": headers["Authorization"], "CF-IPCountry": "US"}
    if region:
        headers.update(signed_headers(PATH, "POST", region))
    assert client.post(PATH, headers=headers).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()
    config_path = "/api/v1/app/paypal/config"
    config = client.get(
        config_path,
        headers=signed_headers(config_path, "GET", region) if region else {},
    )
    assert not config.json()["controlled_registration_enabled"]
    assert not config.json()["registration_enabled"]


@pytest.mark.parametrize(
    "reason",
    [
        "other_email",
        "unverified",
        "issuer",
        "invalid_token",
        "disabled_gate",
        "fake_signature",
    ],
)
def test_forged_or_unapproved_identity_cannot_initialize(
    client, db, controlled, monkeypatch, reason
):
    clerk, headers = controlled
    if reason == "other_email":
        clerk.profile = replace(clerk.profile, primary_email="other@example.com")
        headers["x-vireal-controlled-email"] = EMAIL
    elif reason == "unverified":
        clerk.profile = replace(clerk.profile, email_verified=False)
    elif reason == "issuer":
        clerk.claims = replace(clerk.claims, issuer="https://staging.example.test")
    elif reason == "invalid_token":
        headers["Authorization"] = "Bearer invalid"
    elif reason == "disabled_gate":
        monkeypatch.setattr(settings, "APP_CONTROLLED_REGISTRATION_ENABLED", False)
    elif reason == "fake_signature":
        headers["x-vireal-edge-signature"] = "f" * 64
    response = client.post(PATH, headers=headers, json={"email": EMAIL})
    assert response.status_code in {401, 403}
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


@pytest.mark.parametrize("deleted", [False, True])
def test_disabled_or_deleted_identity_is_never_reactivated(
    client, db, controlled, deleted
):
    from datetime import UTC, datetime

    clerk, headers = controlled
    result = client.post(PATH, headers=headers)
    assert result.status_code == 200
    user = db.get(AppUser, uuid.UUID(result.json()["app_user"]["id"]))
    user.status = "disabled"
    if deleted:
        user.deleted_at = datetime.now(UTC)
    db.add(user)
    db.commit()
    assert client.post(PATH, headers=headers).status_code == 403
    clerk.claims = replace(clerk.claims, subject=f"user_replacement_{uuid.uuid4()}")
    assert client.post(PATH, headers=headers).status_code == 409
    db.refresh(user)
    assert user.status == "disabled"
    assert bool(user.deleted_at) == deleted


def test_concurrent_initialization_binds_exactly_one_identity(client, db, controlled):
    clerk, headers = controlled
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(lambda _: client.post(PATH, headers=headers), range(4))
        )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["app_user"]["id"] for response in responses}) == 1
    assert sum(response.json()["is_new_user"] for response in responses) == 1
    assert (
        db.exec(
            select(func.count())
            .select_from(AppUserIdentity)
            .where(AppUserIdentity.subject == clerk.claims.subject)
        ).one()
        == 1
    )


def controlled_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": "https://clerk.example.test",
        "CLERK_JWKS_URL": "https://clerk.example.test/.well-known/jwks.json",
        "CLERK_AUDIENCE": "vireal",
        "CLERK_SECRET_KEY": "isolated-not-a-real-secret",
        "CLERK_AUTHORIZED_PARTIES": ["https://app.example.test"],
        "APP_CONTROLLED_REGISTRATION_ENABLED": True,
        "APP_CONTROLLED_REGISTRATION_EMAIL": EMAIL,
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-edge-secret-at-least-32-chars",
    }
    values.update(overrides)
    return _settings(**values)


def test_controlled_settings_are_independent_of_live_and_public_commerce():
    configured = controlled_settings()
    assert configured.APP_CONTROLLED_REGISTRATION_ENABLED
    assert not configured.APP_PUBLIC_REGISTRATION_ENABLED
    assert not configured.APP_LIVE_ACCEPTANCE_ENABLED
    assert not configured.PAYPAL_ENABLED
    assert not configured.APP_COMMERCE_TERMS_APPROVED


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENVIRONMENT": "staging"},
        {"APP_AUTH_MODE": "device"},
        {"APP_CONTROLLED_REGISTRATION_EMAIL": None},
        {"APP_CONTROLLED_REGISTRATION_EMAIL": "not-an-email"},
        {"APP_PUBLIC_REGISTRATION_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {"PAYPAL_ENABLED": True},
        {"APP_COMMERCE_TERMS_APPROVED": True},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": "short"},
        {"ADMIN_PUBLIC_SIGNUP_ENABLED": True},
    ],
)
def test_controlled_settings_reject_expanded_or_unsafe_access(overrides):
    with pytest.raises(ValidationError):
        controlled_settings(**overrides)
