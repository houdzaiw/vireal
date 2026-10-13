"""Mocked identity/release gates, not genuine overseas or Live acceptance."""

import uuid
from dataclasses import replace

import jwt
import pytest
from pydantic import HttpUrl, ValidationError
from sqlmodel import delete

from app.api import deps
from app.api.routes import app_auth, app_paypal
from app.core.config import settings
from app.models import AppOrder, AppOrderEvent, AppUser
from app.services import commercial_access
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from tests.api.routes.test_paypal_commerce import FakePayPal, signed_headers
from tests.core.test_config_v12 import _commerce_settings, _settings


@pytest.fixture
def acceptance(monkeypatch):
    class Clerk:
        def __init__(self):
            self.claims = ClerkSessionClaims(
                "https://clerk.example.test",
                f"user_acceptance_{uuid.uuid4()}",
                f"session_{uuid.uuid4()}",
                "https://app.example.test",
            )
            self.verified = True

        def verify_session_token(self, token):
            if token == "invalid":
                raise ClerkAuthenticationError("Invalid token")
            return self.claims

        def get_user_profile(self, _subject):
            return ClerkUserProfile("acceptance@example.com", self.verified, ("email",))

    clerk = Clerk()
    for module in (deps, app_auth, commercial_access):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": HttpUrl("https://clerk.example.test"),
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_ENABLED": True,
        "APP_LIVE_ACCEPTANCE_SUBJECTS": [clerk.claims.subject],
        "APP_COMMERCE_TERMS_APPROVED": True,
        "APP_REGION_ENFORCEMENT_ENABLED": False,
        "PAYPAL_ENABLED": True,
        "PAYPAL_ENVIRONMENT": "live",
        "PAYPAL_CLIENT_ID": "mock-client",
        "PAYPAL_CLIENT_SECRET": "mock-secret",
        "PAYPAL_MERCHANT_ID": "TEST-MERCHANT",
        "PAYPAL_WEBHOOK_ID": "MOCK-WEBHOOK",
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    paypal = FakePayPal()
    monkeypatch.setattr(app_paypal, "get_paypal_client", lambda: paypal)
    token = jwt.encode(
        {"iss": clerk.claims.issuer},
        "isolated-test-key-at-least-32-bytes-long",
        algorithm="HS256",
    )
    return clerk, paypal, {"Authorization": f"Bearer {token}"}


def test_closed_anonymous_config_and_verified_allowlisted_zero_wallet(
    client, db, acceptance
):
    _, _, headers = acceptance
    config = client.get("/api/v1/app/paypal/config").json()
    assert not config["registration_enabled"] and not config["recharge_enabled"]
    config = client.get("/api/v1/app/paypal/config", headers=headers).json()
    assert config["registration_enabled"] and config["recharge_enabled"]
    response = client.post("/api/v1/app/auth/session", headers=headers)
    assert response.status_code == 200 and response.json()["is_new_user"]
    assert client.get("/api/v1/app/wallet", headers=headers).json()["balance"] == 0
    user = db.get(AppUser, uuid.UUID(response.json()["app_user"]["id"]))
    user.status = "disabled"
    db.add(user)
    db.commit()
    assert client.post("/api/v1/app/auth/session", headers=headers).status_code == 403


def test_nonallowlisted_subject_fake_header_invalid_token_and_email_are_denied(
    client, acceptance
):
    clerk, _, headers = acceptance
    clerk.claims = replace(clerk.claims, subject=f"user_other_{uuid.uuid4()}")
    fake_headers = {
        **headers,
        "x-vireal-acceptance-subject": settings.APP_LIVE_ACCEPTANCE_SUBJECTS[0],
    }
    assert (
        client.post("/api/v1/app/auth/session", headers=fake_headers).status_code == 403
    )
    assert not client.get("/api/v1/app/paypal/config", headers=fake_headers).json()[
        "recharge_enabled"
    ]
    assert not client.get(
        "/api/v1/app/paypal/config", headers={"Authorization": "Bearer invalid"}
    ).json()["registration_enabled"]
    clerk.claims = replace(
        clerk.claims, subject=settings.APP_LIVE_ACCEPTANCE_SUBJECTS[0]
    )
    clerk.verified = False
    assert client.post("/api/v1/app/auth/session", headers=headers).status_code == 403


def test_allowlist_never_overrides_region_or_issuer(client, acceptance, monkeypatch):
    clerk, _, headers = acceptance
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "APP_EDGE_SIGNING_SECRET", "x" * 32)
    path = "/api/v1/app/auth/session"
    assert client.post(path, headers=headers).status_code == 403
    assert (
        client.post(
            path, headers={**headers, **signed_headers(path, "POST", "CN")}
        ).status_code
        == 403
    )
    assert (
        client.post(
            path, headers={**headers, **signed_headers(path, "POST", "US")}
        ).status_code
        == 200
    )
    clerk.claims = replace(
        clerk.claims,
        issuer="https://other.example.test",
        subject=f"user_wrong_issuer_{uuid.uuid4()}",
    )
    monkeypatch.setattr(
        settings, "APP_LIVE_ACCEPTANCE_SUBJECTS", [clerk.claims.subject]
    )
    assert (
        client.post(
            path, headers={**headers, **signed_headers(path, "POST", "US")}
        ).status_code
        == 403
    )


def test_acceptance_blocks_new_actions_but_not_existing_capture_or_history(
    client, db, acceptance, monkeypatch
):
    clerk, paypal, headers = acceptance
    response = client.post("/api/v1/app/auth/session", headers=headers)
    assert response.status_code == 200
    user_id = uuid.UUID(response.json()["app_user"]["id"])
    order = client.post(
        "/api/v1/app/paypal/orders",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"product_id": "coins_100"},
    )
    assert order.status_code == 200, order.text
    paypal.orders[order.json()["provider_order_id"]]["status"] = "APPROVED"
    monkeypatch.setattr(settings, "APP_LIVE_ACCEPTANCE_SUBJECTS", ["user_different"])
    assert (
        client.post(
            "/api/v1/app/paypal/orders",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"product_id": "coins_100"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/app/uploads/images",
            headers=headers,
            files={"file": ("test.png", b"\x89PNG\r\n\x1a\nmock", "image/png")},
        ).status_code
        == 403
    )
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", True)
    assert (
        client.post(
            "/api/v1/app/video-tasks",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "effect_id": str(uuid.uuid4()),
                "variant_id": str(uuid.uuid4()),
                "upload_ids": [str(uuid.uuid4())],
            },
        ).status_code
        == 403
    )
    result = client.post(
        f"/api/v1/app/paypal/orders/{order.json()['id']}/capture", headers=headers
    )
    assert result.status_code == 200 and result.json()["fulfilled_at"]
    assert client.get("/api/v1/app/wallet", headers=headers).json()["balance"] == 100
    assert client.get("/api/v1/app/orders", headers=headers).status_code == 200
    db.execute(
        delete(AppOrderEvent).where(
            AppOrderEvent.order_id == uuid.UUID(order.json()["id"])
        )
    )
    db.execute(delete(AppOrder).where(AppOrder.app_user_id == user_id))
    db.commit()


@pytest.mark.parametrize(
    "values",
    [
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {
            "APP_LIVE_ACCEPTANCE_ENABLED": True,
            "ENVIRONMENT": "production",
            "PAYPAL_ENABLED": False,
            "APP_LIVE_ACCEPTANCE_SUBJECTS": ["user_test"],
        },
        {"APP_LIVE_ACCEPTANCE_SUBJECTS": [" "]},
        {"ENVIRONMENT": "production", "APP_LAUNCH_EFFECT_SLUGS": []},
    ],
)
def test_invalid_acceptance_configuration_fails_closed(values):
    with pytest.raises(ValidationError):
        _settings(**values)


def test_complete_acceptance_configuration_keeps_public_registration_closed():
    configured = _commerce_settings(
        APP_LIVE_ACCEPTANCE_ENABLED=True,
        APP_LIVE_ACCEPTANCE_SUBJECTS=["user_approved"],
        APP_PUBLIC_REGISTRATION_ENABLED=False,
    )
    assert configured.APP_LIVE_ACCEPTANCE_ENABLED
    assert not configured.APP_PUBLIC_REGISTRATION_ENABLED
    assert configured.APP_LAUNCH_EFFECT_SLUGS == ["dance-1", "romance-1"]
