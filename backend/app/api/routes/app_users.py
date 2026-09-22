import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import AppUserIdentity, AppUserProfileUpdate, AppUserWithIdentityPublic
from app.services.app_identity import serialize_app_user

router = APIRouter(prefix="/app/users", tags=["app users"])


def _identity_for_user(
    *, session: SessionDep, app_user_id: uuid.UUID
) -> AppUserIdentity | None:
    return session.exec(
        select(AppUserIdentity).where(AppUserIdentity.app_user_id == app_user_id)
    ).first()


@router.get("/me", response_model=AppUserWithIdentityPublic)
def read_app_user_me(
    session: SessionDep,
    current_app_user: CurrentAppUser,
) -> Any:
    """
    Get the current App user profile.
    """
    return serialize_app_user(
        current_app_user,
        _identity_for_user(session=session, app_user_id=current_app_user.id),
    )


@router.patch("/me", response_model=AppUserWithIdentityPublic)
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
    updated_user = crud.update_app_user_profile(
        session=session, app_user=current_app_user, user_in=user_in
    )
    return serialize_app_user(
        updated_user,
        _identity_for_user(session=session, app_user_id=updated_user.id),
    )
