"""A sign-in-only staging exception; never changes ordinary region policy."""

from datetime import UTC, datetime

from fastapi import HTTPException, Request

from app.core.config import (
    STAGING_LOGIN_ACCEPTANCE_ISSUER,
    STAGING_LOGIN_ACCEPTANCE_ORIGIN,
    settings,
)
from app.models import AppUser, AppUserIdentity
from app.services.clerk_auth import ClerkSessionClaims
from app.services.commercial_access import edge_country

STAGING_LOGIN_HEADER = "x-vireal-staging-login-acceptance"


def staging_sign_in_enabled(request: Request) -> bool:
    expiry = settings.APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT
    return bool(
        settings.staging_login_acceptance_configuration_safe()
        and expiry
        and datetime.now(UTC) < expiry
        and edge_country(request) == "CN"
    )


def require_staging_sign_in_context(
    request: Request, claims: ClerkSessionClaims
) -> None:
    if not (
        request.headers.get(STAGING_LOGIN_HEADER) == "1"
        and staging_sign_in_enabled(request)
        and claims.subject == settings.APP_STAGING_LOGIN_ACCEPTANCE_SUBJECT
        and claims.issuer.rstrip("/") == STAGING_LOGIN_ACCEPTANCE_ISSUER
        and claims.authorized_party == STAGING_LOGIN_ACCEPTANCE_ORIGIN
    ):
        raise HTTPException(403, "Staging sign-in acceptance is unavailable")


def require_staging_sign_in_identity(
    request: Request,
    claims: ClerkSessionClaims,
    identity: AppUserIdentity | None,
    user: AppUser | None,
) -> None:
    require_staging_sign_in_context(request, claims)
    if not (
        identity
        and user
        and identity.subject == claims.subject
        and identity.issuer == claims.issuer
        and identity.email_verified
        and identity.app_user_id == user.id
        and user.account_type == "clerk"
        and user.status == "active"
        and user.deleted_at is None
        and not user.payment_hold
    ):
        raise HTTPException(403, "Staging sign-in requires the existing test identity")
