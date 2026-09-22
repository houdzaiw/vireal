from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, col, select

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import (
    AppTokenPayload,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    TokenPayload,
    User,
)
from app.services.app_identity import hash_clerk_session_id
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkSessionClaims,
    get_clerk_auth_service,
)
from app.services.cloudflare_access import (
    CloudflareAccessError,
    get_cloudflare_access_verifier,
)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)
app_reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/app/auth/device-login",
    scheme_name="AppBearer",
)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
AppTokenDep = Annotated[str, Depends(app_reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_app_user(session: SessionDep, token: AppTokenDep) -> AppUser:
    if settings.APP_AUTH_MODE in {"dual", "clerk"}:
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except InvalidTokenError:
            unverified = {}
        if settings.APP_AUTH_MODE == "clerk" or unverified.get("typ") != "app":
            try:
                claims = get_clerk_auth_service().verify_session_token(token)
            except ClerkAuthenticationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Could not validate app credentials",
                ) from exc
            identity = session.exec(
                select(AppUserIdentity).where(
                    AppUserIdentity.issuer == claims.issuer,
                    AppUserIdentity.subject == claims.subject,
                )
            ).first()
            if identity is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="App session has not been initialized",
                )
            app_session = session.exec(
                select(AppUserSession).where(
                    AppUserSession.app_user_id == identity.app_user_id,
                    AppUserSession.session_id_hash
                    == hash_clerk_session_id(claims.session_id),
                    col(AppUserSession.revoked_at).is_(None),
                )
            ).first()
            if app_session is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="App session is no longer active",
                )
            app_user = session.get(AppUser, identity.app_user_id)
            if not app_user:
                raise HTTPException(status_code=404, detail="App user not found")
            if (
                app_user.account_type != "clerk"
                or app_user.status != "active"
                or app_user.deleted_at is not None
            ):
                raise HTTPException(status_code=403, detail="Inactive app user")
            return app_user

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = AppTokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate app credentials",
        )
    if token_data.typ != "app" or not token_data.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate app credentials",
        )
    app_user = session.get(AppUser, token_data.sub)
    if not app_user:
        raise HTTPException(status_code=404, detail="App user not found")
    if app_user.status != "active" or app_user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Inactive app user")
    return app_user


CurrentAppUser = Annotated[AppUser, Depends(get_current_app_user)]


def get_verified_clerk_session(token: AppTokenDep) -> ClerkSessionClaims:
    if settings.APP_AUTH_MODE == "device":
        raise HTTPException(status_code=503, detail="Clerk authentication is disabled")
    try:
        return get_clerk_auth_service().verify_session_token(token)
    except ClerkAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate Clerk credentials",
        ) from exc


VerifiedClerkSession = Annotated[
    ClerkSessionClaims, Depends(get_verified_clerk_session)
]


def require_cloudflare_access(request: Request) -> None:
    if not settings.CLOUDFLARE_ACCESS_REQUIRED:
        return
    token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get(
        "CF_Authorization"
    )
    if not token:
        raise HTTPException(status_code=403, detail="Cloudflare Access is required")
    try:
        get_cloudflare_access_verifier().verify(token)
    except CloudflareAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail="Invalid Cloudflare Access session",
        ) from exc


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
