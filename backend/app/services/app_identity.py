import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlmodel import Session, col, select

from app.models import (
    AppUser,
    AppUserIdentity,
    AppUserIdentityPublic,
    AppUserSession,
    AppUserWithIdentityPublic,
)

AuthProvider = Literal["email", "google", "apple"]
SUPPORTED_AUTH_PROVIDERS = {"email", "google", "apple"}


def hash_clerk_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def revoke_local_app_sessions(*, session: Session, app_user_id: uuid.UUID) -> int:
    sessions = session.exec(
        select(AppUserSession).where(
            AppUserSession.app_user_id == app_user_id,
            col(AppUserSession.revoked_at).is_(None),
        )
    ).all()
    revoked_at = datetime.now(UTC)
    for app_session in sessions:
        app_session.revoked_at = revoked_at
        session.add(app_session)
    if sessions:
        session.commit()
    return len(sessions)


def identity_providers(identity: AppUserIdentity) -> list[AuthProvider]:
    try:
        values = json.loads(identity.providers_json)
    except TypeError, json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []
    return [
        cast(AuthProvider, value)
        for value in values
        if isinstance(value, str) and value in SUPPORTED_AUTH_PROVIDERS
    ]


def serialize_app_user(
    app_user: AppUser,
    identity: AppUserIdentity | None,
) -> AppUserWithIdentityPublic:
    identity_public = None
    if identity is not None:
        identity_public = AppUserIdentityPublic(
            email=identity.primary_email,
            email_verified=identity.email_verified,
            auth_providers=identity_providers(identity),
            last_login_at=identity.last_login_at,
            login_count=identity.login_count,
        )
    return AppUserWithIdentityPublic(
        **app_user.model_dump(),
        identity=identity_public,
    )
