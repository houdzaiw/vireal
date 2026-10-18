"""A closed, existing-account, one-task check; no new payment or free credits."""

from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import (
    AppEffect,
    AppEffectVariant,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    AppVideoTask,
)
from app.services.app_identity import hash_clerk_session_id
from app.services.clerk_auth import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkSessionClaims,
    get_clerk_auth_service,
)

GENERATION_ACCEPTANCE_EMAIL = "li522903183@163.com"
GENERATION_ACCEPTANCE_MODEL = "wan-video/wan-2.7-r2v"


def generation_acceptance_mode_safe() -> bool:
    return bool(
        settings.APP_GENERATION_ACCEPTANCE_ENABLED
        and settings.generation_acceptance_configuration_safe()
    )


def generation_acceptance_window_open() -> bool:
    expires = settings.APP_GENERATION_ACCEPTANCE_EXPIRES_AT
    return bool(
        generation_acceptance_mode_safe() and expires and expires > datetime.now(UTC)
    )


def generation_acceptance_user(
    request: Request,
    session: Session,
    *,
    claims: ClerkSessionClaims | None = None,
    verify_profile: bool = False,
) -> AppUser | None:
    # Reading an existing task is allowed after expiry, never another submission.
    from app.services.commercial_access import edge_country

    if not generation_acceptance_mode_safe() or edge_country(request) != "CN":
        return None
    claims = claims or getattr(request.state, "clerk_claims", None)
    if claims is None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        try:
            claims = get_clerk_auth_service().verify_session_token(authorization[7:])
        except ClerkAuthenticationError, ValueError:
            return None
    if (
        not isinstance(claims, ClerkSessionClaims)
        or claims.subject != settings.APP_GENERATION_ACCEPTANCE_SUBJECT
        or claims.issuer.rstrip("/") != str(settings.CLERK_ISSUER_URL).rstrip("/")
    ):
        return None
    identity = session.exec(
        select(AppUserIdentity)
        .where(
            AppUserIdentity.app_user_id == settings.APP_GENERATION_ACCEPTANCE_USER_ID,
            AppUserIdentity.subject == claims.subject,
            AppUserIdentity.issuer == claims.issuer,
            col(AppUserIdentity.email_verified).is_(True),
        )
        .execution_options(populate_existing=True)
    ).first()
    if not identity or identity.primary_email.casefold() != GENERATION_ACCEPTANCE_EMAIL:
        return None
    local_session = session.exec(
        select(AppUserSession)
        .where(
            AppUserSession.app_user_id == identity.app_user_id,
            AppUserSession.session_id_hash == hash_clerk_session_id(claims.session_id),
            col(AppUserSession.revoked_at).is_(None),
        )
        .execution_options(populate_existing=True)
    ).first()
    user = session.get(AppUser, identity.app_user_id, populate_existing=True)
    if (
        not local_session
        or not user
        or user.account_type != "clerk"
        or user.status != "active"
        or user.deleted_at is not None
        or user.payment_hold
    ):
        return None
    if verify_profile:
        try:
            profile = get_clerk_auth_service().get_user_profile(claims.subject)
        except ClerkAPIError:
            return None
        if (
            not profile.email_verified
            or profile.primary_email.casefold() != GENERATION_ACCEPTANCE_EMAIL
        ):
            return None
    return user


def generation_acceptance_task(session: Session, user: AppUser) -> AppVideoTask | None:
    # Every row consumes the lifetime slot, including deleted/failed/refunded or
    # unknown tasks. Never reset it by changing a flag, key, day or expiry.
    return session.exec(
        select(AppVideoTask)
        .where(AppVideoTask.app_user_id == user.id)
        .order_by(col(AppVideoTask.created_at), col(AppVideoTask.id))
        .limit(1)
    ).first()


def require_generation_access(
    request: Request, session: Session, user: AppUser, *, verify_profile: bool = False
) -> None:
    from app.services.commercial_access import (
        require_generation_region,
        require_new_commerce_user,
    )

    if settings.APP_GENERATION_ACCEPTANCE_ENABLED:
        permitted = generation_acceptance_user(
            request, session, verify_profile=verify_profile
        )
        if not permitted or permitted.id != user.id:
            raise HTTPException(
                403, "Generation acceptance is unavailable for this account"
            )
    else:
        require_generation_region(request, session, user)
        require_new_commerce_user(request)


def require_new_generation(request: Request, session: Session, user: AppUser) -> None:
    require_generation_access(request, session, user)
    if settings.APP_GENERATION_ACCEPTANCE_ENABLED:
        if not generation_acceptance_window_open():
            raise HTTPException(403, "Generation acceptance window has expired")
        if generation_acceptance_task(session, user):
            raise HTTPException(
                409,
                "The one-time generation slot is already used; view the existing task",
            )
    elif not settings.APP_VIDEO_SUBMISSIONS_ENABLED:
        raise HTTPException(
            503, "New uploads and video submissions are temporarily paused"
        )


def require_acceptance_variant(
    effect: AppEffect | None, variant: AppEffectVariant | None
) -> None:
    if settings.APP_GENERATION_ACCEPTANCE_ENABLED and (
        not effect
        or not variant
        or effect.slug != "dance-1"
        or effect.input_image_count != 1
        or variant.duration_seconds != 5
        or variant.coin_cost != 28
        or variant.provider != "replicate"
        or variant.model != GENERATION_ACCEPTANCE_MODEL
        or variant.prompt_version != "v1"
    ):
        raise HTTPException(
            403, "Acceptance permits only dance-1 / 5 seconds / 28 credits / Wan 2.7"
        )
