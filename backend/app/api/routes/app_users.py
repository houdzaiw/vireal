from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import AppUserProfileUpdate, AppUserPublic

router = APIRouter(prefix="/app/users", tags=["app users"])


@router.get("/me", response_model=AppUserPublic)
def read_app_user_me(current_app_user: CurrentAppUser) -> Any:
    """
    Get the current App user profile.
    """
    return current_app_user


@router.patch("/me", response_model=AppUserPublic)
def update_app_user_me(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    user_in: AppUserProfileUpdate,
) -> Any:
    """
    Update the current App user's nickname and avatar.
    """
    if user_in.nickname is not None and not user_in.nickname.strip():
        raise HTTPException(status_code=400, detail="Nickname cannot be empty")
    if user_in.avatar_url is not None and not user_in.avatar_url.strip():
        raise HTTPException(status_code=400, detail="Avatar URL cannot be empty")
    return crud.update_app_user_profile(
        session=session, app_user=current_app_user, user_in=user_in
    )
