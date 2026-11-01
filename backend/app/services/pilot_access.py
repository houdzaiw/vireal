"""Five verified-email invitations; never a region or commerce-switch bypass."""

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import AppUser, AppUserIdentity, AppUserSession
from app.services.app_identity import hash_clerk_session_id
from app.services.clerk_auth import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
    get_clerk_auth_service,
)


def pilot_enabled() -> bool:
    return bool(settings.APP_PILOT_ENABLED and settings.pilot_configuration_safe())


def pilot_profile_allowed(*, profile: ClerkUserProfile, issuer: str) -> bool:
    return bool(
        pilot_enabled()
        and settings.CLERK_ISSUER_URL
        and issuer.rstrip("/") == str(settings.CLERK_ISSUER_URL).rstrip("/")
        and profile.email_verified
        and profile.primary_email.isascii()
        and profile.primary_email.casefold()
        in {str(v).casefold() for v in settings.APP_PILOT_INVITED_EMAILS}
    )


def pilot_user(
    request: Request,
    session: Session,
    *,
    user: AppUser | None = None,
    verify_profile: bool = False,
) -> AppUser | None:
    if not pilot_enabled():
        return None
    claims = getattr(request.state, "clerk_claims", None)
    if claims is None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        try:
            claims = get_clerk_auth_service().verify_session_token(authorization[7:])
        except ClerkAuthenticationError, ValueError:
            return None
    if not isinstance(claims, ClerkSessionClaims) or claims.issuer.rstrip("/") != str(
        settings.CLERK_ISSUER_URL
    ).rstrip("/"):
        return None
    identity = session.exec(
        select(AppUserIdentity)
        .where(
            AppUserIdentity.issuer == claims.issuer,
            AppUserIdentity.subject == claims.subject,
            col(AppUserIdentity.email_verified).is_(True),
        )
        .execution_options(populate_existing=True)
    ).first()
    if identity is None:
        return None
    email = identity.primary_email.casefold()
    if email not in {str(v).casefold() for v in settings.APP_PILOT_INVITED_EMAILS}:
        return None
    # Historical duplicates fail closed, including disabled/deleted identities.
    matches = session.exec(
        select(AppUserIdentity.id).where(
            AppUserIdentity.issuer == claims.issuer,
            func.lower(AppUserIdentity.primary_email) == email,
        )
    ).all()
    if matches != [identity.id]:
        return None
    current = session.get(AppUser, identity.app_user_id, populate_existing=True)
    local_session = session.exec(
        select(AppUserSession)
        .where(
            AppUserSession.app_user_id == identity.app_user_id,
            AppUserSession.session_id_hash == hash_clerk_session_id(claims.session_id),
            col(AppUserSession.revoked_at).is_(None),
        )
        .execution_options(populate_existing=True)
    ).first()
    if (
        current is None
        or (user is not None and user.id != current.id)
        or current.account_type != "clerk"
        or current.status != "active"
        or current.deleted_at is not None
        or current.payment_hold
        or local_session is None
    ):
        return None
    cached = getattr(request.state, "pilot_verified_profile", None)
    if verify_profile and cached is None:
        try:
            profile = get_clerk_auth_service().get_user_profile(claims.subject)
        except ClerkAPIError:
            return None
        cached = (claims.issuer, claims.subject, profile)
        request.state.pilot_verified_profile = cached
    if cached is not None:
        issuer, subject, profile = cached
        if (
            issuer != claims.issuer
            or subject != claims.subject
            or not pilot_profile_allowed(profile=profile, issuer=issuer)
            or profile.primary_email.casefold() != email
        ):
            return None
    return current


def require_pilot_commerce(
    request: Request,
    session: Session | None,
    user: AppUser | None,
    *,
    verify_profile: bool = False,
) -> None:
    if settings.APP_PILOT_ENABLED and (
        session is None
        or user is None
        or pilot_user(request, session, user=user, verify_profile=verify_profile)
        is None
    ):
        raise HTTPException(403, "A verified pilot invitation is required")
    if settings.APP_PILOT_ENABLED:
        from app.services.commercial_access import require_region

        require_region(request)
