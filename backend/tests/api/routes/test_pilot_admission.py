"""Synthetic identities and local PostgreSQL only; no provider or storage HTTP."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl, ValidationError
from sqlalchemy import func
from sqlmodel import select

from app.api import deps
from app.api.routes import app_auth, app_paypal, app_uploads
from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppOrder,
    AppUpload,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    AppVideoTask,
)
from app.services import commercial_access, pilot_access
from app.services.clerk_auth import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
)
from tests.api.routes.test_controlled_registration import controlled_settings
from tests.api.routes.test_paypal_commerce import signed_headers

AUTH = "/api/v1/app/auth/session"
CONFIG = "/api/v1/app/paypal/config"


@pytest.fixture
def pilot(db, monkeypatch):
    class Clerk:
        def __init__(self):
            self.claims = {}
            self.profiles = {}
            self.profile_calls = 0

        def add(self, email, *, subject=None):
            token = str(uuid.uuid4())
            subject = subject or f"user_{uuid.uuid4().hex}"
            self.claims[token] = ClerkSessionClaims(
                "https://clerk.example.test",
                subject,
                f"sess_{token}",
                "https://app.example.test",
            )
            self.profiles[subject] = ClerkUserProfile(email, True, ("email",))
            return token

        def verify_session_token(self, token):
            if token not in self.claims:
                raise ClerkAuthenticationError("Invalid synthetic token")
            return self.claims[token]

        def get_user_profile(self, subject):
            self.profile_calls += 1
            value = self.profiles[subject]
            if isinstance(value, Exception):
                raise value
            return value

    clerk = Clerk()
    emails = [f"pilot-{uuid.uuid4().hex}@example.com" for _ in range(5)]
    clerk.tokens = [clerk.add(email) for email in emails]
    for module in (deps, app_auth, commercial_access, pilot_access):
        monkeypatch.setattr(module, "get_clerk_auth_service", lambda: clerk)
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": HttpUrl("https://clerk.example.test"),
        "APP_PILOT_ENABLED": True,
        "APP_PILOT_INVITED_EMAILS": emails,
        "APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS": 1,
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "synthetic-edge-secret-at-least-32-characters",
        "APP_PUBLIC_REGISTRATION_ENABLED": False,
        "APP_CONTROLLED_REGISTRATION_ENABLED": False,
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED": False,
        "APP_INTERNAL_ACCEPTANCE_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_SUBJECTS": [],
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": False,
        "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED": False,
        "APP_GENERATION_ACCEPTANCE_ENABLED": False,
        "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED": False,
        "ADMIN_PUBLIC_SIGNUP_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "PAYPAL_ENABLED": False,
        "APP_COMMERCE_TERMS_APPROVED": False,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    assert settings.pilot_configuration_safe()
    yield clerk
    db.rollback()


def headers(token, path=AUTH, method="POST", country="US"):
    return {"Authorization": f"Bearer {token}", **signed_headers(path, method, country)}


def counts(db):
    db.expire_all()
    return tuple(
        db.exec(select(func.count()).select_from(model)).one()
        for model in (
            AppUser,
            AppUserIdentity,
            AppUserSession,
            AppCoinLedger,
            AppOrder,
            AppVideoTask,
            AppUpload,
        )
    )


def identity(db, pilot, token):
    return db.exec(
        select(AppUserIdentity).where(
            AppUserIdentity.subject == pilot.claims[token].subject,
        )
    ).one()


def test_five_verified_invitations_and_sixth_rejection(client, db, pilot):
    before = counts(db)
    for token in pilot.tokens:
        response = client.post(AUTH, headers=headers(token))
        assert response.status_code == 200, response.text
        assert response.json()["is_new_user"]
        assert (
            client.get("/api/v1/app/wallet", headers=headers(token)).json()["balance"]
            == 0
        )
    after = counts(db)
    assert tuple(a - b for a, b in zip(after, before, strict=True)) == (
        5,
        5,
        5,
        0,
        0,
        0,
        0,
    )
    outsider = pilot.add("uninvited@example.com")
    assert client.post(AUTH, headers=headers(outsider)).status_code == 403
    assert counts(db) == after
    for token in pilot.tokens:
        response = client.post(AUTH, headers=headers(token))
        assert response.status_code == 200 and not response.json()["is_new_user"]
    assert counts(db) == after


@pytest.mark.parametrize(
    "reason",
    [
        "unverified",
        "wrong_issuer",
        "uninvited",
        "invalid_token",
        "profile_unavailable",
        "CN",
        "XX",
        "unsigned",
        "forged_signature",
        "unsafe_mode",
    ],
)
def test_denial_never_creates_identity_or_business_records(
    client, db, pilot, monkeypatch, reason
):
    token = pilot.tokens[0]
    subject = pilot.claims[token].subject
    proof = headers(token)
    if reason == "unverified":
        pilot.profiles[subject] = replace(pilot.profiles[subject], email_verified=False)
    elif reason == "wrong_issuer":
        pilot.claims[token] = replace(
            pilot.claims[token], issuer="https://other.example.test"
        )
    elif reason == "uninvited":
        pilot.profiles[subject] = replace(
            pilot.profiles[subject], primary_email="other@example.com"
        )
        proof["x-vireal-pilot-email"] = settings.APP_PILOT_INVITED_EMAILS[0]
    elif reason == "invalid_token":
        proof["Authorization"] = "Bearer invalid"
    elif reason == "profile_unavailable":
        pilot.profiles[subject] = ClerkAPIError("Synthetic provider unavailable")
    elif reason in {"CN", "XX"}:
        proof = headers(token, country=reason)
    elif reason == "unsigned":
        proof = {"Authorization": f"Bearer {token}", "CF-IPCountry": "US"}
    elif reason == "forged_signature":
        proof["x-vireal-edge-signature"] = "f" * 64
    else:
        monkeypatch.setattr(settings, "APP_GENERATION_ACCEPTANCE_ENABLED", True)
    before = counts(db)
    assert client.post(AUTH, headers=proof).status_code in {401, 403, 502}
    assert counts(db) == before


def test_concurrent_first_login_binds_each_email_once(client, db, pilot):
    before = counts(db)
    # Six eligible subjects: two try to claim the same first invited email.
    duplicate = pilot.add(settings.APP_PILOT_INVITED_EMAILS[0])
    tokens = [*pilot.tokens, duplicate]
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(
            pool.map(lambda t: client.post(AUTH, headers=headers(t)), tokens)
        )
    assert sorted(r.status_code for r in responses) == [200] * 5 + [409]
    assert tuple(a - b for a, b in zip(counts(db), before, strict=True)) == (
        5,
        5,
        5,
        0,
        0,
        0,
        0,
    )


def test_concurrent_same_subject_initialization_is_idempotent(client, db, pilot):
    before = counts(db)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(AUTH, headers=headers(pilot.tokens[0])), range(3)
            )
        )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["app_user"]["id"] for r in responses}) == 1
    assert tuple(a - b for a, b in zip(counts(db), before, strict=True)) == (
        1,
        1,
        1,
        0,
        0,
        0,
        0,
    )


@pytest.mark.parametrize("deleted", [False, True])
def test_invitation_cannot_rebind_disabled_or_deleted_identity(
    client, db, pilot, deleted
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    linked = identity(db, pilot, token)
    user = db.get(AppUser, linked.app_user_id)
    user.status = "disabled"
    if deleted:
        user.deleted_at = datetime.now(UTC)
    db.add(user)
    db.commit()
    duplicate = pilot.add(linked.primary_email)
    before = counts(db)
    assert client.post(AUTH, headers=headers(duplicate)).status_code == 409
    assert client.post(AUTH, headers=headers(token)).status_code == 403
    assert counts(db) == before


def test_removed_invitee_keeps_history_but_cannot_start_any_commerce(
    client, db, pilot, monkeypatch
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    monkeypatch.setattr(
        settings, "APP_PILOT_INVITED_EMAILS", settings.APP_PILOT_INVITED_EMAILS[1:]
    )
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)

    def forbidden():
        raise AssertionError("Uninvited request reached provider/storage")

    monkeypatch.setattr(app_paypal, "get_paypal_client", forbidden)
    monkeypatch.setattr(app_uploads, "get_image_storage", forbidden)
    before = counts(db)
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    assert client.get("/api/v1/app/wallet", headers=headers(token)).status_code == 200
    assert (
        client.post(
            "/api/v1/app/uploads/images",
            headers=headers(token, "/api/v1/app/uploads/images"),
            files={"file": ("test.png", b"synthetic", "image/png")},
        ).status_code
        == 403
    )
    for path, body in (
        ("/api/v1/app/paypal/orders", {"product_id": "coins_100"}),
        (f"/api/v1/app/paypal/orders/{uuid.uuid4()}/capture", {}),
        (
            "/api/v1/app/video-tasks",
            {
                "effect_id": str(uuid.uuid4()),
                "variant_id": str(uuid.uuid4()),
                "upload_ids": [str(uuid.uuid4())],
            },
        ),
    ):
        assert (
            client.post(
                path,
                headers={**headers(token, path), "Idempotency-Key": str(uuid.uuid4())},
                json=body,
            ).status_code
            == 403
        )
    assert counts(db) == before


@pytest.mark.parametrize(
    "reason",
    [
        "profile_email",
        "unverified",
        "profile_error",
        "revoked",
        "disabled",
        "hold",
        "duplicate_email",
        "unsafe_runtime",
    ],
)
def test_current_profile_and_local_identity_rechecked_before_capture(
    client, db, pilot, monkeypatch, reason
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    linked = identity(db, pilot, token)
    user = db.get(AppUser, linked.app_user_id)
    if reason == "profile_email":
        pilot.profiles[linked.subject] = replace(
            pilot.profiles[linked.subject], primary_email="changed@example.com"
        )
    elif reason == "unverified":
        pilot.profiles[linked.subject] = replace(
            pilot.profiles[linked.subject], email_verified=False
        )
    elif reason == "profile_error":
        pilot.profiles[linked.subject] = ClerkAPIError("Synthetic error")
    elif reason == "revoked":
        local = db.exec(
            select(AppUserSession).where(AppUserSession.app_user_id == user.id)
        ).one()
        local.revoked_at = datetime.now(UTC)
        db.add(local)
    elif reason == "disabled":
        user.status = "disabled"
    elif reason == "hold":
        user.payment_hold = True
    elif reason == "duplicate_email":
        other = AppUser(account_type="clerk")
        db.add(other)
        db.flush()
        db.add(
            AppUserIdentity(
                app_user_id=other.id,
                issuer=linked.issuer,
                subject=f"other_{uuid.uuid4()}",
                primary_email=linked.primary_email,
                email_verified=True,
            )
        )
    else:
        monkeypatch.setattr(settings, "APP_PUBLIC_REGISTRATION_ENABLED", True)
    db.add(user)
    db.commit()

    def forbidden():
        raise AssertionError("Rejected capture reached provider")

    monkeypatch.setattr(app_paypal, "get_paypal_client", forbidden)
    path = f"/api/v1/app/paypal/orders/{uuid.uuid4()}/capture"
    before = counts(db)
    assert client.post(path, headers=headers(token, path)).status_code == 403
    assert counts(db) == before


def test_public_hints_never_publish_invite_list_or_open_individual_switches(
    client, pilot, monkeypatch
):
    response = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "US"))
    assert response.status_code == 200
    info = response.json()
    assert info["pilot_mode"] and info["pilot_registration_enabled"]
    assert info["global_concurrent_limit"] == 1
    assert not any(
        info[key]
        for key in (
            "registration_enabled",
            "recharge_enabled",
            "uploads_enabled",
            "generation_enabled",
            "pilot_access_allowed",
        )
    )
    for email in settings.APP_PILOT_INVITED_EMAILS:
        assert email not in response.text
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    proof = headers(token, CONFIG, "GET")
    assert client.get(CONFIG, headers=proof).json()["pilot_access_allowed"]
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)
    info = client.get(CONFIG, headers=proof).json()
    # This remains an availability hint, never a terms/quota entitlement.
    assert info["generation_enabled"]
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", False)
    assert not client.get(CONFIG, headers=proof).json()["generation_enabled"]
    for country in ("CN", "XX"):
        info = client.get(CONFIG, headers=headers(token, CONFIG, "GET", country)).json()
        assert not info["region_allowed"] and not info["pilot_registration_enabled"]
        assert not info["uploads_enabled"] and not info["generation_enabled"]


def pilot_settings(**overrides):
    values = {
        "APP_CONTROLLED_REGISTRATION_ENABLED": False,
        "APP_PILOT_ENABLED": True,
        "APP_PILOT_INVITED_EMAILS": ["invited@example.com"],
        "APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS": 1,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }
    values.update(overrides)
    return controlled_settings(**values)


def test_pilot_default_off_and_no_migration_or_auto_opening():
    configured = controlled_settings(APP_CONTROLLED_REGISTRATION_ENABLED=False)
    assert not configured.APP_PILOT_ENABLED and not configured.APP_PILOT_INVITED_EMAILS
    for environment in ("staging", "production"):
        configured = pilot_settings(ENVIRONMENT=environment)
        assert configured.pilot_configuration_safe()
        assert not configured.APP_PUBLIC_REGISTRATION_ENABLED
        assert (
            not configured.PAYPAL_ENABLED and not configured.APP_COMMERCE_TERMS_APPROVED
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENVIRONMENT": "local"},
        {"APP_AUTH_MODE": "device"},
        {"APP_PILOT_INVITED_EMAILS": []},
        {"APP_PILOT_INVITED_EMAILS": [f"u{i}@example.com" for i in range(6)]},
        {"APP_PILOT_INVITED_EMAILS": ["same@example.com", "SAME@example.com"]},
        {"APP_PILOT_INVITED_EMAILS": ["not-an-email"]},
        {"APP_PILOT_INVITED_EMAILS": ["straße@example.com"]},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": "short"},
        {"APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS": 2},
        *(
            {key: True}
            for key in (
                "APP_PUBLIC_REGISTRATION_ENABLED",
                "APP_CONTROLLED_REGISTRATION_ENABLED",
                "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED",
                "APP_INTERNAL_ACCEPTANCE_ENABLED",
                "APP_LIVE_ACCEPTANCE_ENABLED",
                "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED",
                "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED",
                "APP_GENERATION_ACCEPTANCE_ENABLED",
                "APP_STAGING_LOGIN_ACCEPTANCE_ENABLED",
                "ADMIN_PUBLIC_SIGNUP_ENABLED",
                "LOCAL_DEMO_ENABLED",
                "APP_LEGACY_VIDEO_TASKS_ENABLED",
            )
        ),
    ],
)
def test_unsafe_pilot_configuration_rejected_at_startup(overrides):
    with pytest.raises(ValidationError):
        pilot_settings(**overrides)


def test_unicode_casefold_cannot_impersonate_an_ascii_invitation(
    client, db, pilot, monkeypatch
):
    monkeypatch.setattr(settings, "APP_PILOT_INVITED_EMAILS", ["strasse@example.com"])
    token = pilot.add("straße@example.com")
    before = counts(db)
    assert client.post(AUTH, headers=headers(token)).status_code == 403
    assert counts(db) == before


def test_invited_ascii_email_is_case_insensitive(client, db, pilot):
    token = pilot.tokens[0]
    subject = pilot.claims[token].subject
    pilot.profiles[subject] = replace(
        pilot.profiles[subject],
        primary_email=pilot.profiles[subject].primary_email.upper(),
    )
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    assert client.get(CONFIG, headers=headers(token, CONFIG, "GET")).json()[
        "pilot_access_allowed"
    ]
    duplicate = pilot.add(pilot.profiles[subject].primary_email.lower())
    before = counts(db)
    assert client.post(AUTH, headers=headers(duplicate)).status_code == 409
    assert counts(db) == before


def test_invited_member_is_reverified_once_per_request_without_bypassing_pause(
    client, db, pilot
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    before = counts(db)
    calls = pilot.profile_calls
    path = "/api/v1/app/paypal/orders"
    response = client.post(
        path,
        headers={**headers(token, path), "Idempotency-Key": str(uuid.uuid4())},
        json={"product_id": "coins_100"},
    )
    assert response.status_code == 503
    assert pilot.profile_calls == calls + 1
    path = f"/api/v1/app/paypal/orders/{uuid.uuid4()}/capture"
    assert client.post(path, headers=headers(token, path)).status_code == 404
    assert pilot.profile_calls == calls + 2
    assert counts(db) == before


@pytest.mark.parametrize("country", ["CN", "XX", None])
def test_invitation_never_bypasses_region_for_customer_capture(
    client, db, pilot, country
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    path = f"/api/v1/app/paypal/orders/{uuid.uuid4()}/capture"
    proof = (
        headers(token, path, country=country)
        if country
        else {"Authorization": f"Bearer {token}", "CF-IPCountry": "US"}
    )
    before = counts(db)
    assert client.post(path, headers=proof).status_code == 403
    assert counts(db) == before


def test_invitation_removal_during_account_lock_prevents_order_reservation(
    client, db, pilot, monkeypatch
):
    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    for key, value in {
        "PAYPAL_ENABLED": True,
        "PAYPAL_ENVIRONMENT": "live",
        "PAYPAL_CLIENT_ID": "synthetic-id",
        "PAYPAL_CLIENT_SECRET": "synthetic-secret",
        "PAYPAL_MERCHANT_ID": "synthetic-merchant",
        "PAYPAL_WEBHOOK_ID": "synthetic-webhook",
    }.items():
        monkeypatch.setattr(settings, key, value)
    original = app_paypal.lock_commercial_user

    def changed(session, user):
        original(session, user)
        monkeypatch.setattr(
            settings, "APP_PILOT_INVITED_EMAILS", settings.APP_PILOT_INVITED_EMAILS[1:]
        )

    def forbidden():
        raise AssertionError("Removed invitation reached provider")

    monkeypatch.setattr(app_paypal, "lock_commercial_user", changed)
    monkeypatch.setattr(app_paypal, "get_paypal_client", forbidden)
    before = counts(db)
    path = "/api/v1/app/paypal/orders"
    assert (
        client.post(
            path,
            headers={**headers(token, path), "Idempotency-Key": str(uuid.uuid4())},
            json={"product_id": "coins_100"},
        ).status_code
        == 403
    )
    assert counts(db) == before


def test_invitation_removal_during_storage_io_cleans_own_upload(
    client, db, pilot, monkeypatch
):
    from app.services.storage import StoredImage

    token = pilot.tokens[0]
    assert client.post(AUTH, headers=headers(token)).status_code == 200
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)

    class Storage:
        deleted = []

        def store_app_image(self, **kwargs):
            monkeypatch.setattr(
                settings,
                "APP_PILOT_INVITED_EMAILS",
                settings.APP_PILOT_INVITED_EMAILS[1:],
            )
            return StoredImage(
                "https://storage.example.invalid/own",
                "own-object",
                "image/png",
                len(kwargs["content"]),
            )

        def delete_object(self, key):
            self.deleted.append(key)

    storage = Storage()
    monkeypatch.setattr(app_uploads, "get_image_storage", lambda: storage)
    before = counts(db)
    path = "/api/v1/app/uploads/images"
    response = client.post(
        path,
        headers=headers(token, path),
        files={"file": ("test.png", b"synthetic", "image/png")},
    )
    assert response.status_code == 403, response.text
    assert storage.deleted == ["own-object"]
    assert counts(db) == before
