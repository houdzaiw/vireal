"""Single existing identity; isolated DB/mocked Clerk, no real paid operations."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl, ValidationError
from sqlmodel import select

from app.api import deps
from app.api.routes import app_auth
from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppEffect,
    AppEffectCategory,
    AppEffectVariant,
    AppOrder,
    AppUser,
    AppUserIdentity,
    AppUserSession,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from tests.api.routes.test_app_video_tasks import PNG_BYTES
from tests.api.routes.test_paypal_commerce import signed_headers
from tests.core.test_config_v12 import _settings

AUTH = "/api/v1/app/auth/session"
UPLOAD = "/api/v1/app/uploads/images"
TASKS = "/api/v1/app/video-tasks"
CONFIG = "/api/v1/app/paypal/config"
PAYMENT = "/api/v1/app/paypal/orders"


@pytest.fixture
def internal(client, monkeypatch, tmp_path):
    class Clerk:
        claims = ClerkSessionClaims(
            "https://clerk.example.test",
            f"user_{uuid.uuid4()}",
            f"session_{uuid.uuid4()}",
            "https://app.example.test",
        )
        profile = ClerkUserProfile(
            f"internal-{uuid.uuid4()}@example.com", True, ("email",)
        )

        def verify_session_token(self, token):
            if token == "invalid":
                raise ClerkAuthenticationError("Invalid test token")
            return self.claims

        def get_user_profile(self, _subject):
            return self.profile

    clerk = Clerk()
    for module in (deps, app_auth):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "APP_AUTH_MODE", "clerk")
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", False)
    headers = {"Authorization": "Bearer isolated-clerk-token"}
    initialized = client.post(AUTH, headers=headers)
    assert initialized.status_code == 200, initialized.text
    user_id = uuid.UUID(initialized.json()["app_user"]["id"])
    for key, value in {
        "ENVIRONMENT": "production",
        "CLERK_ISSUER_URL": HttpUrl(clerk.claims.issuer),
        "APP_INTERNAL_ACCEPTANCE_ENABLED": True,
        "APP_INTERNAL_ACCEPTANCE_SUBJECT": clerk.claims.subject,
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-internal-edge-key-32-characters",
        "APP_CONTROLLED_REGISTRATION_ENABLED": False,
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "PAYPAL_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_ENABLED": False,
        "APP_COMMERCE_TERMS_APPROVED": False,
        "ADMIN_PUBLIC_SIGNUP_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
        "LOCAL_UPLOAD_DIR": str(tmp_path),
    }.items():
        monkeypatch.setattr(settings, key, value)
    return clerk, headers, user_id


def cn(headers, path, method="POST"):
    return {**headers, **signed_headers(path, method, "CN")}


def upload(client, headers):
    return client.post(
        UPLOAD, headers=headers, files={"file": ("qa.png", PNG_BYTES, "image/png")}
    )


def test_existing_target_can_upload_but_not_register_or_pay(client, db, internal):
    clerk, headers, user_id = internal
    response = client.post(AUTH, headers=cn(headers, AUTH))
    assert response.status_code == 200 and not response.json()["is_new_user"]
    assert response.json()["internal_generation_allowed"] is True
    assert upload(client, cn(headers, UPLOAD)).status_code == 200
    config = client.get(CONFIG, headers=cn({}, CONFIG, "GET"))
    assert config.json()["internal_sign_in_enabled"] is True
    assert not config.json()["region_allowed"]
    assert not config.json()["registration_enabled"]
    assert not config.json()["controlled_registration_enabled"]
    assert not config.json()["recharge_enabled"]
    assert config.headers["cache-control"] == "no-store"
    assert (
        clerk.claims.subject not in config.text
        and clerk.profile.primary_email not in config.text
    )
    assert (
        client.post(
            PAYMENT,
            headers={**cn(headers, PAYMENT), "Idempotency-Key": str(uuid.uuid4())},
            json={"product_id": "coins_100"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/app/wallet", headers=headers).json()["balance"] == 0
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == user_id)
    ).all()
    # An exact configured subject with no business identity still cannot register.
    clerk.claims = replace(clerk.claims, subject=f"user_new_{uuid.uuid4()}")
    settings.APP_INTERNAL_ACCEPTANCE_SUBJECT = clerk.claims.subject
    assert client.post(AUTH, headers=cn(headers, AUTH)).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


@pytest.mark.parametrize(
    "proof",
    ["missing", "bare", "unknown", "invalid", "expired", "wrong_path", "wrong_method"],
)
def test_invalid_country_never_gets_internal_exception(client, internal, proof):
    _clerk, headers, _user_id = internal
    proof_headers = cn(headers, UPLOAD)
    if proof in {"missing", "bare"}:
        proof_headers = {
            **headers,
            "CF-IPCountry": "CN",
            "x-vireal-internal-acceptance": "true",
        }
    elif proof == "unknown":
        proof_headers.update(signed_headers(UPLOAD, "POST", "XX"))
    elif proof == "invalid":
        proof_headers["x-vireal-edge-signature"] = "f" * 64
    elif proof == "expired":
        proof_headers.update(signed_headers(UPLOAD, "POST", "CN", timestamp="1"))
    elif proof == "wrong_path":
        proof_headers.update(signed_headers(CONFIG, "POST", "CN"))
    else:
        proof_headers.update(signed_headers(UPLOAD, "GET", "CN"))
    assert upload(client, proof_headers).status_code == 403
    config = client.get(CONFIG, headers=proof_headers)
    assert not config.json()["internal_sign_in_enabled"]


@pytest.mark.parametrize(
    "reason",
    [
        "other_subject",
        "other_issuer",
        "disabled",
        "deleted",
        "payment_hold",
        "unverified",
        "revoked",
        "invalid_token",
        "gate_off",
        "public_on",
        "payments_on",
        "terms_on",
        "live_on",
    ],
)
def test_internal_exception_does_not_override_identity_or_safety_gates(
    client, db, internal, monkeypatch, reason
):
    clerk, headers, user_id = internal
    user = db.get(AppUser, user_id)
    if reason == "other_subject":
        monkeypatch.setattr(
            settings, "APP_INTERNAL_ACCEPTANCE_SUBJECT", "user_someone_else"
        )
        headers["x-vireal-subject"] = clerk.claims.subject
    elif reason == "other_issuer":
        monkeypatch.setattr(
            settings, "CLERK_ISSUER_URL", HttpUrl("https://other-clerk.example.test")
        )
    elif reason == "invalid_token":
        headers["Authorization"] = "Bearer invalid"
    elif reason in {"disabled", "deleted", "payment_hold"}:
        if reason == "disabled":
            user.status = "disabled"
        elif reason == "deleted":
            user.deleted_at = datetime.now(UTC)
        else:
            user.payment_hold = True
        db.add(user)
    elif reason == "unverified":
        identity = db.exec(
            select(AppUserIdentity).where(AppUserIdentity.app_user_id == user_id)
        ).one()
        identity.email_verified = False
        db.add(identity)
    elif reason == "revoked":
        local = db.exec(
            select(AppUserSession).where(AppUserSession.app_user_id == user_id)
        ).one()
        local.revoked_at = datetime.now(UTC)
        db.add(local)
    else:
        field, value = {
            "gate_off": ("APP_INTERNAL_ACCEPTANCE_ENABLED", False),
            "public_on": ("APP_PUBLIC_REGISTRATION_ENABLED", True),
            "payments_on": ("PAYPAL_ENABLED", True),
            "terms_on": ("APP_COMMERCE_TERMS_APPROVED", True),
            "live_on": ("APP_LIVE_ACCEPTANCE_ENABLED", True),
        }[reason]
        monkeypatch.setattr(settings, field, value)
    db.commit()
    assert upload(client, cn(headers, UPLOAD)).status_code == 403
    result = client.post(
        TASKS,
        headers={**cn(headers, TASKS), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "effect_id": str(uuid.uuid4()),
            "variant_id": str(uuid.uuid4()),
            "upload_ids": [str(uuid.uuid4())],
        },
    )
    assert result.status_code == 403


def test_internal_generation_still_requires_credits_without_provider_submission(
    client, db, internal, monkeypatch
):
    _clerk, headers, user_id = internal
    # Configure only this isolated test catalogue, never a deployed catalogue.
    slug = f"internal-qa-{uuid.uuid4().hex}"
    category = AppEffectCategory(
        slug=slug,
        name_zh="内部测试",
        name_en="Isolated QA",
        tones_json='["#000000","#111111","#222222"]',
    )
    db.add(category)
    db.flush()
    effect = AppEffect(
        category_id=category.id,
        slug=slug,
        title_zh="内部测试",
        title_en="Isolated QA",
        publish_status="published",
        input_image_count=1,
    )
    db.add(effect)
    db.flush()
    variant = AppEffectVariant(
        effect_id=effect.id,
        duration_seconds=5,
        coin_cost=12,
        model="minimax/video-01",
        model_type="reference-to-video",
        prompt="Isolated credit validation only",
    )
    db.add(variant)
    db.commit()
    monkeypatch.setattr(settings, "APP_LAUNCH_EFFECT_SLUGS", [slug])
    uploaded = upload(client, cn(headers, UPLOAD)).json()
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", True)
    monkeypatch.setattr(settings, "REPLICATE_POC_MAX_SUBMISSIONS", 0)
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)

    # Provider resolution occurs only after the debit; any accidental call fails.
    def no_provider():
        pytest.fail("Zero-balance request must never contact a provider")

    monkeypatch.setattr(
        "app.api.routes.app_video_tasks.get_replicate_video_client", no_provider
    )
    response = client.post(
        TASKS,
        headers={**cn(headers, TASKS), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "effect_id": str(effect.id),
            "variant_id": str(variant.id),
            "upload_ids": [uploaded["id"]],
        },
    )
    assert response.status_code == 409 and "coin" in response.text.lower(), (
        response.text
    )
    assert client.get("/api/v1/app/wallet", headers=headers).json()["balance"] == 0
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == user_id)
    ).all()
    db.delete(effect)
    db.delete(category)
    db.commit()


def internal_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": "https://clerk.example.test",
        "CLERK_JWKS_URL": "https://clerk.example.test/.well-known/jwks.json",
        "CLERK_AUDIENCE": "vireal",
        "CLERK_SECRET_KEY": "isolated-test-key",
        "CLERK_AUTHORIZED_PARTIES": ["https://app.example.test"],
        "APP_INTERNAL_ACCEPTANCE_ENABLED": True,
        "APP_INTERNAL_ACCEPTANCE_SUBJECT": "user_internal",
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-internal-edge-key-32-characters",
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }
    values.update(overrides)
    return _settings(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENVIRONMENT": "staging"},
        {"APP_AUTH_MODE": "device"},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": None},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": "user_internal "},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": ""},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": "a,b"},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": "user_a,user_b"},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": "user_a user_b"},
        {"APP_INTERNAL_ACCEPTANCE_SUBJECT": "user_"},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": None},
        {"PAYPAL_ENABLED": True},
        {"APP_PUBLIC_REGISTRATION_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {"APP_COMMERCE_TERMS_APPROVED": True},
        {"ADMIN_PUBLIC_SIGNUP_ENABLED": True},
        {"LOCAL_DEMO_ENABLED": True},
        {"APP_LEGACY_VIDEO_TASKS_ENABLED": True},
    ],
)
def test_unsafe_internal_configuration_rejected(overrides):
    with pytest.raises(ValidationError):
        internal_settings(**overrides)


def test_safe_internal_configuration_and_default_off():
    assert internal_settings().APP_INTERNAL_ACCEPTANCE_ENABLED
    assert not _settings().APP_INTERNAL_ACCEPTANCE_ENABLED
