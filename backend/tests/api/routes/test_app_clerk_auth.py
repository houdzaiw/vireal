from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api import deps as deps_module
from app.api.routes import admin_app as admin_app_module
from app.api.routes import app_auth as app_auth_module
from app.core.config import settings
from app.models import AppUser, AppUserIdentity, AppUserSession
from app.services import app_identity
from app.services.clerk_auth import ClerkSessionClaims, ClerkUserProfile


class FakeClerkService:
    def __init__(self) -> None:
        self.revoked_session_ids: list[str] = []
        self.revoked_user_ids: list[str] = []
        self.claims = ClerkSessionClaims(
            issuer="https://clerk.example.test",
            subject="user_clerk_test",
            session_id="sess_one",
            authorized_party="https://app.example.test",
        )

    def verify_session_token(self, _token: str) -> ClerkSessionClaims:
        return self.claims

    def get_user_profile(self, _subject: str) -> ClerkUserProfile:
        return ClerkUserProfile(
            primary_email="invited@example.com",
            email_verified=True,
            providers=("email", "google"),
        )

    def revoke_user_sessions(self, subject: str) -> int:
        self.revoked_user_ids.append(subject)
        return 1

    def revoke_session(self, session_id: str) -> None:
        self.revoked_session_ids.append(session_id)


@pytest.fixture
def clerk_mode(monkeypatch: pytest.MonkeyPatch) -> FakeClerkService:
    service = FakeClerkService()
    monkeypatch.setattr(settings, "APP_AUTH_MODE", "dual")
    monkeypatch.setattr(
        deps_module,
        "get_clerk_auth_service",
        lambda: service,
    )
    monkeypatch.setattr(
        app_auth_module,
        "get_clerk_auth_service",
        lambda: service,
    )
    monkeypatch.setattr(
        admin_app_module,
        "get_clerk_auth_service",
        lambda: service,
    )
    return service


def test_clerk_session_creates_one_app_user_and_updates_login_summary(
    client: TestClient,
    db: Session,
    clerk_mode: FakeClerkService,
) -> None:
    headers = {"Authorization": "Bearer clerk-token"}
    first = client.post(
        f"{settings.API_V1_STR}/app/auth/session",
        headers=headers,
    )
    second = client.post(
        f"{settings.API_V1_STR}/app/auth/session",
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["is_new_user"] is True
    assert second.status_code == 200
    assert second.json()["is_new_user"] is False
    assert second.json()["app_user"]["identity"] == {
        "email": "invited@example.com",
        "email_verified": True,
        "auth_providers": ["email", "google"],
        "last_login_at": second.json()["app_user"]["identity"]["last_login_at"],
        "login_count": 1,
    }

    clerk_mode.claims = replace(clerk_mode.claims, session_id="sess_two")
    third = client.post(
        f"{settings.API_V1_STR}/app/auth/session",
        headers=headers,
    )
    profile = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
    )

    assert third.status_code == 200
    assert third.json()["app_user"]["identity"]["login_count"] == 2
    assert profile.status_code == 200
    assert profile.json()["identity"]["email"] == "invited@example.com"

    identities = db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == "user_clerk_test")
    ).all()
    assert len(identities) == 1
    app_users = db.exec(select(AppUser).where(AppUser.account_type == "clerk")).all()
    assert (
        len([user for user in app_users if user.id == identities[0].app_user_id]) == 1
    )
    app_sessions = db.exec(
        select(AppUserSession).where(
            AppUserSession.app_user_id == identities[0].app_user_id
        )
    ).all()
    assert len(app_sessions) == 2


def test_clerk_logout_immediately_revokes_local_session(
    client: TestClient,
    db: Session,
    clerk_mode: FakeClerkService,
) -> None:
    clerk_mode.claims = replace(
        clerk_mode.claims,
        subject="user_logout_test",
        session_id="sess_logout",
    )
    headers = {"Authorization": "Bearer clerk-token"}
    initialized = client.post(
        f"{settings.API_V1_STR}/app/auth/session",
        headers=headers,
    )
    before_logout = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
    )
    logout = client.post(
        f"{settings.API_V1_STR}/app/auth/logout",
        headers=headers,
    )
    after_logout = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
    )

    assert initialized.status_code == 200
    assert before_logout.status_code == 200
    assert logout.status_code == 200
    assert after_logout.status_code == 403
    assert clerk_mode.revoked_session_ids == ["sess_logout"]
    app_session = db.exec(
        select(AppUserSession).where(
            AppUserSession.session_id_hash
            == app_identity.hash_clerk_session_id("sess_logout")
        )
    ).one()
    assert app_session.revoked_at is not None


def test_concurrent_first_login_is_idempotent(
    client: TestClient,
    db: Session,
    clerk_mode: FakeClerkService,
) -> None:
    clerk_mode.claims = replace(
        clerk_mode.claims,
        subject="user_concurrent_test",
        session_id="sess_concurrent",
    )
    headers = {"Authorization": "Bearer clerk-token"}

    def initialize() -> int:
        return client.post(
            f"{settings.API_V1_STR}/app/auth/session",
            headers=headers,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _index: initialize(), range(2)))

    assert statuses == [200, 200]
    identities = db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == "user_concurrent_test")
    ).all()
    assert len(identities) == 1
    app_sessions = db.exec(
        select(AppUserSession).where(
            AppUserSession.app_user_id == identities[0].app_user_id
        )
    ).all()
    assert len(app_sessions) == 1
    assert identities[0].login_count == 1


def test_admin_disable_revokes_local_and_clerk_sessions(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    clerk_mode: FakeClerkService,
) -> None:
    clerk_mode.claims = replace(
        clerk_mode.claims,
        subject="user_disable_test",
        session_id="sess_disable",
    )
    headers = {"Authorization": "Bearer clerk-token"}
    initialized = client.post(
        f"{settings.API_V1_STR}/app/auth/session",
        headers=headers,
    )
    app_user_id = initialized.json()["app_user"]["id"]

    disabled = client.patch(
        f"{settings.API_V1_STR}/admin/app/users/{app_user_id}/status",
        headers=superuser_token_headers,
        json={"status": "disabled"},
    )
    profile = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
    )

    assert initialized.status_code == 200
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert profile.status_code == 403
    assert clerk_mode.revoked_user_ids == ["user_disable_test"]


def test_clerk_mode_retires_device_login(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_AUTH_MODE", "clerk")
    response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json={"device_uuid": "device-for-retired-login", "platform": "ios"},
    )

    assert response.status_code == 410
