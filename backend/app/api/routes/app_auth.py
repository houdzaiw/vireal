from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app import crud
from app.api.deps import CurrentAppUser, SessionDep, VerifiedClerkSession
from app.core import security
from app.core.config import settings
from app.models import (
    AppAuthSessionResponse,
    AppDeviceLoginRequest,
    AppDeviceLoginResponse,
    AppUser,
    AppUserIdentity,
    AppUserPublic,
    AppUserSession,
    Message,
)
from app.services.app_identity import hash_clerk_session_id, serialize_app_user
from app.services.clerk_auth import ClerkAPIError, get_clerk_auth_service
from app.services.commercial_access import (
    acceptance_subject_allowed,
    controlled_cn_account_setup_profile_allowed,
    controlled_registration_profile_allowed,
    internal_generation_allowed,
    require_region,
)
from app.services.generation_acceptance import generation_acceptance_user
from app.services.staging_login_acceptance import (
    STAGING_LOGIN_HEADER,
    require_staging_sign_in_context,
    require_staging_sign_in_identity,
)

router = APIRouter(prefix="/app/auth", tags=["app auth"])


@router.post("/device-login", response_model=AppDeviceLoginResponse)
def device_login(*, session: SessionDep, body: AppDeviceLoginRequest) -> Any:
    """
    Create or return an App user for a mobile device UUID.
    """
    if settings.APP_AUTH_MODE == "clerk":
        raise HTTPException(
            status_code=410,
            detail="Device login has been retired; use Clerk authentication",
        )
    device_uuid = body.device_uuid.strip()
    if not device_uuid:
        raise HTTPException(status_code=422, detail="Device UUID is required")

    device_uuid_hash = crud.hash_device_uuid(device_uuid)
    app_device = crud.get_app_device_by_hash(
        session=session, device_uuid_hash=device_uuid_hash
    )
    is_new_user = False

    if app_device:
        app_user = session.get(AppUser, app_device.app_user_id)
        if not app_user:
            raise HTTPException(status_code=404, detail="App user not found")
        crud.touch_app_device_login(session=session, app_device=app_device)
    else:
        app_user, app_device = crud.create_app_user_with_device(
            session=session,
            device_uuid_hash=device_uuid_hash,
            platform=body.platform,
        )
        is_new_user = True

    access_token_expires = timedelta(minutes=settings.APP_ACCESS_TOKEN_EXPIRE_MINUTES)
    return AppDeviceLoginResponse(
        access_token=security.create_app_access_token(
            app_user.id,
            expires_delta=access_token_expires,
        ),
        app_user=AppUserPublic.model_validate(app_user),
        is_new_user=is_new_user,
    )


@router.post("/session", response_model=AppAuthSessionResponse)
def initialize_clerk_session(
    *,
    request: Request,
    session: SessionDep,
    clerk_session: VerifiedClerkSession,
) -> AppAuthSessionResponse:
    """Create or refresh the local App identity for a verified Clerk session."""
    cn_setup_request = settings.APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED
    staging_request = STAGING_LOGIN_HEADER in request.headers
    staging_identity: AppUserIdentity | None = None
    staging_user: AppUser | None = None
    if staging_request:
        # Reject wrong subjects/contexts before even querying the provider profile.
        require_staging_sign_in_context(request, clerk_session)
        identities = session.exec(
            select(AppUserIdentity).where(
                AppUserIdentity.issuer == clerk_session.issuer,
                AppUserIdentity.subject == clerk_session.subject,
            )
        ).all()
        if len(identities) == 1:
            staging_identity = identities[0]
            staging_user = session.get(AppUser, staging_identity.app_user_id)
        require_staging_sign_in_identity(
            request, clerk_session, staging_identity, staging_user
        )

    def require_current_setup_authorization() -> None:
        if staging_request:
            # Recheck after provider calls/locks and immediately before commit.
            require_staging_sign_in_identity(
                request, clerk_session, staging_identity, staging_user
            )
        if cn_setup_request and not controlled_cn_account_setup_profile_allowed(
            request, profile=profile, issuer=clerk_session.issuer
        ):
            raise HTTPException(
                403, "Controlled account setup is unavailable or expired"
            )

    try:
        profile = get_clerk_auth_service().get_user_profile(clerk_session.subject)
    except ClerkAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not profile.email_verified:
        raise HTTPException(status_code=403, detail="A verified email is required")
    require_current_setup_authorization()

    identity = session.exec(
        select(AppUserIdentity).where(
            AppUserIdentity.issuer == clerk_session.issuer,
            AppUserIdentity.subject == clerk_session.subject,
        )
    ).first()
    is_new_user = identity is None
    if staging_request and (
        identity is None
        or staging_identity is None
        or identity.id != staging_identity.id
    ):
        raise HTTPException(403, "Staging sign-in requires the existing test identity")
    now = datetime.now(UTC)
    session_id_hash = hash_clerk_session_id(clerk_session.session_id)

    app_user: AppUser | None = None
    if identity is None:
        if (
            settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
            or settings.APP_GENERATION_ACCEPTANCE_ENABLED
        ):
            raise HTTPException(
                403, "Controlled acceptance requires an existing account"
            )
        if not cn_setup_request:
            require_region(request)
        controlled = controlled_registration_profile_allowed(
            profile=profile, issuer=clerk_session.issuer
        )
        if (
            settings.ENVIRONMENT == "production"
            and not settings.APP_PUBLIC_REGISTRATION_ENABLED
            and not acceptance_subject_allowed(
                subject=clerk_session.subject, issuer=clerk_session.issuer
            )
            and not controlled
        ):
            raise HTTPException(403, "Registration is not yet open / 注册尚未开放")
        if controlled:
            # Bind this verified email to one business identity, including when
            # concurrent first logins arrive. Never revive an old disabled user.
            session.connection().execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": f"controlled-registration:{clerk_session.issuer}:{profile.primary_email.casefold()}"
                },
            )
            # A slow lock must not extend or revive the temporary authorization.
            require_current_setup_authorization()
            existing = session.exec(
                select(AppUserIdentity).where(
                    AppUserIdentity.issuer == clerk_session.issuer,
                    func.lower(AppUserIdentity.primary_email)
                    == profile.primary_email.casefold(),
                )
            ).first()
            if existing is not None and existing.subject != clerk_session.subject:
                raise HTTPException(
                    409, "Controlled email is already linked to an account"
                )
            if existing is not None:
                # A concurrent request already initialized this same subject.
                identity = existing
                app_user = session.get(AppUser, identity.app_user_id)
                is_new_user = False
    if identity is None:
        require_current_setup_authorization()
        email_name = profile.primary_email.split("@", 1)[0].strip()
        app_user = AppUser(
            account_type="clerk",
            nickname=email_name[:50] or None,
        )
        session.add(app_user)
        session.flush()
        identity = AppUserIdentity(
            app_user_id=app_user.id,
            issuer=clerk_session.issuer,
            subject=clerk_session.subject,
            primary_email=profile.primary_email,
            email_verified=profile.email_verified,
            providers_json=profile.providers_json(),
            login_count=0,
        )
        session.add(identity)
        require_current_setup_authorization()
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            identity = session.exec(
                select(AppUserIdentity).where(
                    AppUserIdentity.issuer == clerk_session.issuer,
                    AppUserIdentity.subject == clerk_session.subject,
                )
            ).first()
            if identity is None:
                raise HTTPException(
                    status_code=409,
                    detail="Unable to initialize the Clerk identity",
                )
            app_user = session.get(AppUser, identity.app_user_id)
            if app_user is None:
                raise HTTPException(status_code=404, detail="App user not found")
            is_new_user = False
    else:
        app_user = session.get(AppUser, identity.app_user_id)
        if app_user is None:
            raise HTTPException(status_code=404, detail="App user not found")

    identity = session.exec(
        select(AppUserIdentity)
        .where(
            AppUserIdentity.issuer == clerk_session.issuer,
            AppUserIdentity.subject == clerk_session.subject,
        )
        .with_for_update()
    ).one()
    app_user = session.get(AppUser, identity.app_user_id)
    if app_user is None:
        raise HTTPException(status_code=404, detail="App user not found")
    if app_user.status != "active" or app_user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Inactive app user")
    if app_user.account_type != "clerk":
        raise HTTPException(status_code=403, detail="Legacy App users cannot use Clerk")
    require_current_setup_authorization()
    if cn_setup_request and app_user.payment_hold:
        raise HTTPException(status_code=403, detail="Account requires payment review")

    app_session = session.exec(
        select(AppUserSession).where(AppUserSession.session_id_hash == session_id_hash)
    ).first()
    if app_session is not None and app_session.revoked_at is not None:
        raise HTTPException(status_code=403, detail="App session is no longer active")
    is_new_session = app_session is None
    if app_session is None:
        app_session = AppUserSession(
            app_user_id=app_user.id,
            session_id_hash=session_id_hash,
            last_seen_at=now,
        )
        session.add(app_session)
    elif app_session.app_user_id != app_user.id:
        raise HTTPException(status_code=403, detail="App session owner mismatch")
    else:
        app_session.last_seen_at = now
        session.add(app_session)

    identity.primary_email = profile.primary_email
    identity.email_verified = profile.email_verified
    identity.providers_json = profile.providers_json()
    identity.updated_at = now
    if is_new_session:
        identity.last_session_id_hash = session_id_hash
        identity.last_login_at = now
        identity.login_count += 1
    session.add(identity)
    require_current_setup_authorization()
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        identity = session.exec(
            select(AppUserIdentity).where(
                AppUserIdentity.issuer == clerk_session.issuer,
                AppUserIdentity.subject == clerk_session.subject,
            )
        ).first()
        app_session = session.exec(
            select(AppUserSession).where(
                AppUserSession.session_id_hash == session_id_hash
            )
        ).first()
        if identity is None or app_session is None:
            raise HTTPException(
                status_code=409,
                detail="Unable to initialize the Clerk session",
            )
        if app_session.revoked_at is not None:
            raise HTTPException(
                status_code=403, detail="App session is no longer active"
            )
        app_user = session.get(AppUser, identity.app_user_id)
        if app_user is None:
            raise HTTPException(status_code=404, detail="App user not found")
        is_new_user = False
    session.refresh(app_user)
    session.refresh(identity)
    return AppAuthSessionResponse(
        app_user=serialize_app_user(app_user, identity),
        is_new_user=is_new_user,
        internal_generation_allowed=internal_generation_allowed(
            request, session, app_user, claims=clerk_session
        ),
        generation_acceptance_read_allowed=generation_acceptance_user(
            request, session, claims=clerk_session
        )
        is not None,
    )


@router.post("/logout", response_model=Message)
def logout_clerk_session(
    *,
    session: SessionDep,
    clerk_session: VerifiedClerkSession,
) -> Message:
    """Immediately invalidate the current Clerk session for Vireal APIs."""
    session_id_hash = hash_clerk_session_id(clerk_session.session_id)
    app_session = session.exec(
        select(AppUserSession).where(AppUserSession.session_id_hash == session_id_hash)
    ).first()
    if app_session is not None and app_session.revoked_at is None:
        app_session.revoked_at = datetime.now(UTC)
        session.add(app_session)
        session.commit()
    try:
        get_clerk_auth_service().revoke_session(clerk_session.session_id)
    except ClerkAPIError:
        # The local revocation is authoritative for this API. Clerk session tokens
        # are short-lived, and the browser still completes Clerk sign-out.
        pass
    return Message(message="Logged out successfully")


@router.post("/test-token", response_model=AppUserPublic)
def test_app_token(current_app_user: CurrentAppUser) -> Any:
    """
    Test an App access token.
    """
    return current_app_user
