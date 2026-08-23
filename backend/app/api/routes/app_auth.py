from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.core import security
from app.core.config import settings
from app.models import (
    AppDeviceLoginRequest,
    AppDeviceLoginResponse,
    AppUser,
    AppUserPublic,
)

router = APIRouter(prefix="/app/auth", tags=["app auth"])


@router.post("/device-login", response_model=AppDeviceLoginResponse)
def device_login(*, session: SessionDep, body: AppDeviceLoginRequest) -> Any:
    """
    Create or return an App user for a mobile device UUID.
    """
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


@router.post("/test-token", response_model=AppUserPublic)
def test_app_token(current_app_user: CurrentAppUser) -> Any:
    """
    Test an App access token.
    """
    return current_app_user
