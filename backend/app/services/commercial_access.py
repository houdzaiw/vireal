"""Signed edge country context; never trust client-supplied geography."""

import hashlib
import hmac
import re
import time

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from app.core.config import settings
from app.models import AppUser
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    get_clerk_auth_service,
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
