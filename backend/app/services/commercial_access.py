"""Signed edge country context; never trust client-supplied geography."""

import hashlib
import hmac
import re
import time
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import AppOrder, AppUser, AppUserIdentity, AppUserSession
from app.services.app_identity import hash_clerk_session_id
from app.services.clerk_auth import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkSessionClaims,
    ClerkUserProfile,
    get_clerk_auth_service,
)

PAYMENT_ONLY_EMAIL = "li8483@yeah.net"


def payment_only_acceptance_enabled() -> bool:
    """Fail closed after expiry or an unsafe in-process configuration change."""
    subject = settings.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT
    expires = settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
    return bool(
        settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
        and settings.ENVIRONMENT == "production"
        and settings.APP_AUTH_MODE == "clerk"
        and settings.CLERK_ISSUER_URL
        and subject
        and re.fullmatch(r"user_[A-Za-z0-9_-]+", subject)
        and settings.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID
        and expires
        and expires.tzinfo is not None
        and 0 < (expires - datetime.now(UTC)).total_seconds() <= 86400
        and settings.APP_REGION_ENFORCEMENT_ENABLED
        and settings.APP_EDGE_SIGNING_SECRET
        and len(settings.APP_EDGE_SIGNING_SECRET) >= 32
        and settings.PAYPAL_ENABLED
        and settings.PAYPAL_ENVIRONMENT == "live"
        and settings.APP_COMMERCE_TERMS_APPROVED
        and not settings.APP_PUBLIC_REGISTRATION_ENABLED
        and not settings.APP_CONTROLLED_REGISTRATION_ENABLED
        and not settings.APP_INTERNAL_ACCEPTANCE_ENABLED
        and not settings.APP_LIVE_ACCEPTANCE_ENABLED
        and not settings.APP_LIVE_ACCEPTANCE_SUBJECTS
        and not settings.APP_VIDEO_SUBMISSIONS_ENABLED
        and not settings.ADMIN_PUBLIC_SIGNUP_ENABLED
        and not settings.LOCAL_DEMO_ENABLED
        and not settings.APP_LEGACY_VIDEO_TASKS_ENABLED
    )


def payment_only_user(
    request: Request, session: Session, *, verify_profile: bool = False
) -> AppUser | None:
    # Geography remains a real signed CN context, never a substituted US header.
    if not payment_only_acceptance_enabled() or edge_country(request) != "CN":
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
    if (
        not isinstance(claims, ClerkSessionClaims)
        or claims.subject != settings.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT
        or claims.issuer.rstrip("/") != str(settings.CLERK_ISSUER_URL).rstrip("/")
    ):
        return None
    identity = session.exec(
        select(AppUserIdentity).where(
            AppUserIdentity.app_user_id == settings.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID,
            AppUserIdentity.subject == claims.subject,
            AppUserIdentity.issuer == claims.issuer,
            col(AppUserIdentity.email_verified).is_(True),
        )
    ).first()
    if not identity or identity.primary_email.casefold() != PAYMENT_ONLY_EMAIL:
        return None
    local_session = session.exec(
        select(AppUserSession).where(
            AppUserSession.app_user_id == identity.app_user_id,
            AppUserSession.session_id_hash == hash_clerk_session_id(claims.session_id),
            col(AppUserSession.revoked_at).is_(None),
        )
    ).first()
    user = session.get(AppUser, identity.app_user_id)
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
            or profile.primary_email.casefold() != PAYMENT_ONLY_EMAIL
        ):
            return None
    return user


def payment_only_order_created(session: Session, user: AppUser) -> bool:
    # Lifetime slot, including canceled, failed, unknown and refunded orders.
    # No toggled flag, refreshed tab or new idempotency key resets this slot.
    return (
        session.exec(
            select(AppOrder.id)
            .where(
                AppOrder.app_user_id == user.id,
                AppOrder.provider == "paypal",
                AppOrder.payment_environment == "live",
            )
            .limit(1)
        ).first()
        is not None
    )


def launch_effect_allowed(slug: str) -> bool:
    return (
        settings.ENVIRONMENT != "production" or slug in settings.APP_LAUNCH_EFFECT_SLUGS
    )


def acceptance_subject_allowed(*, subject: str, issuer: str) -> bool:
    return bool(
        settings.ENVIRONMENT == "production"
        and settings.APP_LIVE_ACCEPTANCE_ENABLED
        and settings.APP_AUTH_MODE == "clerk"
        and settings.APP_COMMERCE_TERMS_APPROVED
        and settings.CLERK_ISSUER_URL
        and issuer.rstrip("/") == str(settings.CLERK_ISSUER_URL).rstrip("/")
        and subject in settings.APP_LIVE_ACCEPTANCE_SUBJECTS
    )


def controlled_registration_enabled() -> bool:
    """Account setup only; never an entitlement to payment or generation."""
    return bool(
        settings.APP_CONTROLLED_REGISTRATION_ENABLED
        and settings.ENVIRONMENT == "production"
        and settings.APP_AUTH_MODE == "clerk"
        and settings.CLERK_ISSUER_URL
        and settings.APP_CONTROLLED_REGISTRATION_EMAIL
        and settings.APP_REGION_ENFORCEMENT_ENABLED
        and not settings.APP_PUBLIC_REGISTRATION_ENABLED
        and not settings.PAYPAL_ENABLED
        and not settings.APP_LIVE_ACCEPTANCE_ENABLED
        and not settings.APP_COMMERCE_TERMS_APPROVED
        and not settings.ADMIN_PUBLIC_SIGNUP_ENABLED
        and not settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    )


def controlled_registration_profile_allowed(
    *, profile: ClerkUserProfile, issuer: str
) -> bool:
    # Only the authoritative Clerk profile is used, not a client email/header.
    return bool(
        controlled_registration_enabled()
        and issuer.rstrip("/") == str(settings.CLERK_ISSUER_URL).rstrip("/")
        and profile.email_verified
        and profile.primary_email.casefold()
        == str(settings.APP_CONTROLLED_REGISTRATION_EMAIL).casefold()
    )


def acceptance_request_allowed(request: Request) -> bool:
    claims = getattr(request.state, "clerk_claims", None)
    if claims is None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return False
        try:
            claims = get_clerk_auth_service().verify_session_token(authorization[7:])
        except ClerkAuthenticationError, ValueError:
            return False
    if not isinstance(claims, ClerkSessionClaims):
        return False
    return acceptance_subject_allowed(subject=claims.subject, issuer=claims.issuer)


def require_new_commerce_user(request: Request) -> None:
    if settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED:
        raise HTTPException(
            403, "Payment-only acceptance does not permit uploads or generation"
        )
    if settings.APP_LIVE_ACCEPTANCE_ENABLED and not acceptance_request_allowed(request):
        raise HTTPException(
            403,
            "Only approved Live acceptance identities may create new commerce actions",
        )


def edge_country(request: Request) -> str | None:
    timestamp = request.headers.get("x-vireal-edge-time", "")
    country = request.headers.get("x-vireal-edge-country", "")
    signature = request.headers.get("x-vireal-edge-signature", "")
    if not settings.APP_EDGE_SIGNING_SECRET or not re.fullmatch(r"[A-Z]{2}", country):
        return None
    try:
        if (
            abs(time.time() - int(timestamp))
            > settings.APP_EDGE_SIGNATURE_TOLERANCE_SECONDS
        ):
            return None
    except ValueError:
        return None
    message = "\n".join((request.method, request.url.path, timestamp, country))
    expected = hmac.new(
        settings.APP_EDGE_SIGNING_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return country if hmac.compare_digest(expected, signature) else None


def region_allowed(request: Request) -> bool:
    if not settings.APP_REGION_ENFORCEMENT_ENABLED:
        return True
    return edge_country(request) not in {None, "CN", "XX", "T1"}


def require_region(request: Request) -> None:
    if not region_allowed(request):
        raise HTTPException(
            403, "Service is unavailable in this region / 当前地区暂未开放服务"
        )


def internal_acceptance_enabled() -> bool:
    """Fail closed even if runtime settings are changed without validation."""
    subject = settings.APP_INTERNAL_ACCEPTANCE_SUBJECT
    return bool(
        settings.APP_INTERNAL_ACCEPTANCE_ENABLED
        and settings.ENVIRONMENT == "production"
        and settings.APP_AUTH_MODE == "clerk"
        and settings.CLERK_ISSUER_URL
        and subject
        and re.fullmatch(r"user_[A-Za-z0-9_-]+", subject)
        and settings.APP_REGION_ENFORCEMENT_ENABLED
        and not settings.APP_PUBLIC_REGISTRATION_ENABLED
        and not settings.PAYPAL_ENABLED
        and not settings.APP_LIVE_ACCEPTANCE_ENABLED
        and not settings.APP_COMMERCE_TERMS_APPROVED
        and not settings.ADMIN_PUBLIC_SIGNUP_ENABLED
        and not settings.LOCAL_DEMO_ENABLED
        and not settings.APP_LEGACY_VIDEO_TASKS_ENABLED
        and not settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    )


def internal_generation_allowed(
    request: Request,
    session: Session,
    user: AppUser,
    *,
    claims: ClerkSessionClaims | None = None,
) -> bool:
    # Callers must authenticate an existing, unrevoked local session first.
    # Never look at email, query strings or identity headers supplied by clients.
    claims = claims or getattr(request.state, "clerk_claims", None)
    if (
        not internal_acceptance_enabled()
        or edge_country(request) != "CN"
        or not isinstance(claims, ClerkSessionClaims)
        or claims.subject != settings.APP_INTERNAL_ACCEPTANCE_SUBJECT
        or claims.issuer.rstrip("/") != str(settings.CLERK_ISSUER_URL).rstrip("/")
        or user.account_type != "clerk"
        or user.status != "active"
        or user.deleted_at is not None
        or user.payment_hold
    ):
        return False
    identity = session.exec(
        select(AppUserIdentity).where(
            AppUserIdentity.app_user_id == user.id,
            AppUserIdentity.subject == claims.subject,
            AppUserIdentity.issuer == claims.issuer,
            col(AppUserIdentity.email_verified).is_(True),
        )
    ).first()
    return identity is not None


def require_generation_region(
    request: Request, session: Session, user: AppUser
) -> None:
    """Narrow exception for upload/task creation; financial guards stay separate."""
    if not region_allowed(request) and not internal_generation_allowed(
        request, session, user
    ):
        require_region(request)


def lock_commercial_user(session: Session, user: AppUser) -> AppUser:
    locked = session.exec(
        select(AppUser)
        .where(AppUser.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if locked.status != "active" or locked.deleted_at is not None:
        raise HTTPException(403, "Inactive app user")
    if locked.payment_hold:
        raise HTTPException(
            409,
            "Payment account is under review; contact support / 支付账户审核中，请联系客服",
        )
    return locked
