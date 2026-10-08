"""Signed edge country context; never trust client-supplied geography."""

import hashlib
import hmac
import re
import time

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from app.core.config import settings
from app.models import AppUser


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
