import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import (
    AppContent,
    AppContentAuthorPublic,
    AppContentCreate,
    AppContentImagePublic,
    AppContentPublic,
    AppContentsPublic,
)
from app.services.storage import is_supported_uploaded_image_url

router = APIRouter(prefix="/app/contents", tags=["app contents"])

MAX_CONTENT_IMAGES = 9


def _normalize_content_input(content_in: AppContentCreate) -> AppContentCreate:
    text = content_in.text.strip() if content_in.text else None
    image_urls = [image_url.strip() for image_url in content_in.image_urls]
    image_urls = [image_url for image_url in image_urls if image_url]
    if not text and not image_urls:
        raise HTTPException(status_code=400, detail="Text or images are required")
    if len(image_urls) > MAX_CONTENT_IMAGES:
        raise HTTPException(status_code=400, detail="Too many images")
    if any(not is_supported_uploaded_image_url(image_url) for image_url in image_urls):
        raise HTTPException(status_code=400, detail="Image URL must be local upload URL")
    return AppContentCreate(text=text, image_urls=image_urls)


def serialize_app_content(content: AppContent) -> AppContentPublic:
    if content.app_user is None:
        raise HTTPException(status_code=500, detail="Content author not found")
    images = sorted(content.images, key=lambda image: image.sort_order)
    return AppContentPublic(
        id=content.id,
        app_user_id=content.app_user_id,
        author=AppContentAuthorPublic(
            id=content.app_user.id,
            nickname=content.app_user.nickname,
            avatar_url=content.app_user.avatar_url,
        ),
        text=content.text,
        images=[AppContentImagePublic.model_validate(image) for image in images],
        created_at=content.created_at,
    )


@router.post("/", response_model=AppContentPublic)
def create_content(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    content_in: AppContentCreate,
) -> Any:
    """
    Publish a text/image post. It is visible immediately after commit.
    """
    normalized_content = _normalize_content_input(content_in)
    content = crud.create_app_content(
        session=session, app_user=current_app_user, content_in=normalized_content
    )
    return serialize_app_content(content)


@router.get("/feed", response_model=AppContentsPublic)
def read_content_feed(
    session: SessionDep,
    _current_app_user: CurrentAppUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve visible App contents.
    """
    contents, count = crud.list_active_app_contents(
        session=session, skip=skip, limit=limit
    )
    return AppContentsPublic(
        data=[serialize_app_content(content) for content in contents],
        count=count,
    )


@router.get("/{content_id}", response_model=AppContentPublic)
def read_content(
    session: SessionDep,
    _current_app_user: CurrentAppUser,
    content_id: uuid.UUID,
) -> Any:
    """
    Get a visible App content detail.
    """
    content = crud.get_active_app_content(session=session, content_id=content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    return serialize_app_content(content)
