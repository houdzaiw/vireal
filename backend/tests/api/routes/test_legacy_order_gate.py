"""Local synthetic actors only; no external identity or payment requests."""

import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import func
from sqlmodel import Session, select

from app.api import deps
from app.api.routes import app_auth
from app.core.config import settings
from app.models import (
    AppCoinAccount,
    AppCoinLedger,
    AppOrder,
    AppOrderEvent,
    AppVideoTask,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from tests.api.routes.test_paypal_commerce import signed_headers

ORDER_PATH = "/api/v1/app/orders"
AUTH_PATH = "/api/v1/app/auth/session"


class SyntheticClerk:
    def __init__(self) -> None:
        self.claims = ClerkSessionClaims(
            issuer="https://clerk.example.test",
            subject=f"user_{uuid.uuid4().hex}",
            session_id=f"sess_{uuid.uuid4().hex}",
            authorized_party="https://app.example.test",
        )
        self.email = f"legacy-gate-{uuid.uuid4().hex}@example.com"

    def verify_session_token(self, token: str) -> ClerkSessionClaims:
        if token != "synthetic-order-session":
            raise ClerkAuthenticationError("Invalid synthetic session")
        return self.claims

    def get_user_profile(self, subject: str) -> ClerkUserProfile:
        assert subject == self.claims.subject
        return ClerkUserProfile(self.email, True, ("email",))


@pytest.fixture
def existing_actor(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> SyntheticClerk:
    clerk = SyntheticClerk()
    for module in (deps, app_auth):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    for name, value in {
        "ENVIRONMENT": "local",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": HttpUrl("https://clerk.example.test"),
        "APP_PILOT_ENABLED": False,
        "APP_PILOT_INVITED_EMAILS": [],
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_REGION_ENFORCEMENT_ENABLED": False,
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED": False,
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": False,
        "APP_GENERATION_ACCEPTANCE_ENABLED": False,
        "PAYPAL_ENABLED": False,
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    response = client.post(AUTH_PATH, headers=_authorization())
    assert response.status_code == 200
    assert response.json()["is_new_user"] is True
    return clerk


def _authorization() -> dict[str, str]:
    return {"Authorization": "Bearer synthetic-order-session"}


def _payload(provider: str) -> dict[str, object]:
    return {
        "provider": provider,
        "product_id": "synthetic.local-product",
        "amount": 599,
        "currency": "USD",
    }


def _business_counts(db: Session) -> tuple[int, ...]:
    db.expire_all()
    return tuple(
        db.exec(select(func.count()).select_from(model)).one()
        for model in (
            AppOrder,
            AppOrderEvent,
            AppCoinAccount,
            AppCoinLedger,
            AppVideoTask,
        )
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("provider", ["apple", "google"])
@pytest.mark.parametrize("scenario", ["closed", "public", "pilot", "CN", "unsigned"])
def test_hosted_legacy_order_creation_is_always_closed(
    client: TestClient,
    db: Session,
    existing_actor: SyntheticClerk,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    provider: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(
        settings, "APP_EDGE_SIGNING_SECRET", "synthetic-order-edge-secret-at-least-32"
    )
    if scenario == "public":
        monkeypatch.setattr(settings, "APP_PUBLIC_REGISTRATION_ENABLED", True)
        monkeypatch.setattr(settings, "PAYPAL_ENABLED", True)
        monkeypatch.setattr(settings, "APP_COMMERCE_TERMS_APPROVED", True)
        monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)
    elif scenario == "pilot":
        monkeypatch.setattr(settings, "APP_PILOT_ENABLED", True)
        monkeypatch.setattr(
            settings, "APP_PILOT_INVITED_EMAILS", [existing_actor.email]
        )
    proof = (
        {"CF-IPCountry": "US"}
        if scenario == "unsigned"
        else signed_headers(ORDER_PATH, "POST", "CN" if scenario == "CN" else "US")
    )
    before = _business_counts(db)
    response = client.post(
        ORDER_PATH, headers={**_authorization(), **proof}, json=_payload(provider)
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Legacy mobile payment orders are unavailable"
    assert _business_counts(db) == before


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("provider", ["apple", "google"])
@pytest.mark.usefixtures("existing_actor")
def test_hosted_historical_order_reads_remain_available(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    provider: str,
) -> None:
    created = client.post(ORDER_PATH, headers=_authorization(), json=_payload(provider))
    assert created.status_code == 200
    order_id = created.json()["id"]
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    before = _business_counts(db)
    listed = client.get(ORDER_PATH, headers=_authorization())
    detail = client.get(f"{ORDER_PATH}/{order_id}", headers=_authorization())
    assert listed.status_code == 200
    assert any(order["id"] == order_id for order in listed.json()["data"])
    assert detail.status_code == 200 and detail.json()["id"] == order_id
    assert detail.json()["status"] == "created"
    assert _business_counts(db) == before


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.usefixtures("existing_actor")
def test_hosted_legacy_order_still_requires_valid_session(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    before = _business_counts(db)
    for headers in ({}, {"Authorization": "Bearer invalid-synthetic-session"}):
        response = client.post(ORDER_PATH, headers=headers, json=_payload("apple"))
        assert response.status_code in {401, 403}
    assert _business_counts(db) == before


def test_public_email_registration_has_no_invitation_or_five_user_ceiling(
    client: TestClient,
    existing_actor: SyntheticClerk,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APP_PUBLIC_REGISTRATION_ENABLED", True)
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(
        settings, "APP_EDGE_SIGNING_SECRET", "synthetic-order-edge-secret-at-least-32"
    )
    assert settings.APP_PILOT_ENABLED is False
    assert settings.APP_PILOT_INVITED_EMAILS == []
    users = set()
    for _ in range(6):
        existing_actor.claims = replace(
            existing_actor.claims,
            subject=f"user_{uuid.uuid4().hex}",
            session_id=f"sess_{uuid.uuid4().hex}",
        )
        existing_actor.email = f"public-{uuid.uuid4().hex}@example.com"
        response = client.post(
            AUTH_PATH,
            headers={**_authorization(), **signed_headers(AUTH_PATH, "POST", "US")},
        )
        assert response.status_code == 200 and response.json()["is_new_user"] is True
        users.add(response.json()["app_user"]["id"])
        wallet = client.get("/api/v1/app/wallet", headers=_authorization())
        assert wallet.status_code == 200 and wallet.json()["balance"] == 0
    assert len(users) == 6
