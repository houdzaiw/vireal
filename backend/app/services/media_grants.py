"""Opaque, short-lived, metered bearer reads. Never expose direct R2 URLs."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models import AppManagedMediaAsset, AppUpload, AppVideoTask
from app.models_resources import AppMediaReadGrant
from app.services.resource_limits import charge, locked_policy, unavailable

AUDIENCE = "vireal-metered-media"


def live_object(session: Session, key: str, now: datetime) -> bool:
    upload = session.exec(select(AppUpload).where(AppUpload.object_key == key)).first()
    if upload is not None:
        return (
            upload.status == "active"
            and upload.deleted_at is None
            and upload.expires_at > now
        )
    task = session.exec(
        select(AppVideoTask).where(AppVideoTask.output_object_key == key)
    ).first()
    if task is not None:
        return (
            task.status == "succeeded"
            and task.deleted_at is None
            and task.expires_at > now
        )
    asset = session.exec(
        select(AppManagedMediaAsset).where(AppManagedMediaAsset.object_key == key)
    ).first()
    return bool(
        asset is not None and asset.status == "active" and asset.deleted_at is None
    )


def issue_read_url(key: str, expires_in: int, *, delivery: bool = False) -> str:
    base = str(settings.APP_MEDIA_READ_BASE_URL or "").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise unavailable()
    if type(expires_in) is not int or not 1 <= expires_in <= 1800:
        raise unavailable()
    now = datetime.now(UTC)
    try:
        with Session(engine) as session:
            policy = locked_policy(session, admission=False)
            if not live_object(session, key, now):
                raise HTTPException(404, "Media not found")
            end = min(now + timedelta(seconds=expires_in), policy.delivery_until)
            grant = AppMediaReadGrant(
                scope=policy.scope, object_key=key, expires_at=end, delivery=delivery
            )
            charge(
                session,
                policy,
                "media-grant",
                {"grants_delivery" if delivery else "grants": 1},
            )
            session.add(grant)
            session.commit()
            token = jwt.encode(
                {
                    "jti": str(grant.id),
                    "aud": AUDIENCE,
                    "exp": end,
                    "typ": "metered-media",
                },
                settings.SECRET_KEY,
                algorithm="HS256",
            )
    except SQLAlchemyError as exc:
        raise unavailable() from exc
    return f"{base}{settings.API_V1_STR}/app/media/read?token={token}"


def resolve_read_token(token: str) -> tuple[str, bool]:
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            audience=AUDIENCE,
            options={"require": ["exp", "jti", "aud", "typ"]},
        )
        if claims["typ"] != "metered-media":
            raise ValueError("wrong token type")
        identifier = uuid.UUID(claims["jti"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(404, "Media not found") from exc
    try:
        with Session(engine) as session:
            policy = locked_policy(session, admission=False)
            grant = session.get(AppMediaReadGrant, identifier)
            now = datetime.now(UTC)
            if (
                grant is None
                or grant.scope != policy.scope
                or grant.expires_at <= now
                or not live_object(session, grant.object_key, now)
            ):
                raise HTTPException(404, "Media not found")
            return grant.object_key, grant.delivery
    except SQLAlchemyError as exc:
        raise unavailable() from exc
