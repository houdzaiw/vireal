import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import (
    AppGeneration,
    AppGenerationCreate,
    AppGenerationPublic,
    AppGenerationQuotaPublic,
    AppGenerationsPublic,
    AppUser,
    Message,
)
from app.services import ai_generation
from app.services.storage import is_supported_uploaded_image_url

router = APIRouter(prefix="/app/generations", tags=["app generations"])

FREE_GENERATION_LIMIT = 2
GENERATION_MODELS = {
    "video": "Seedance 2.0",
    "image": "Seedream",
}


def _clean_optional_url(value: str | None) -> str | None:
    if value is None:
        return None
    clean_value = value.strip()
    return clean_value or None


def _normalize_generation_input(
    generation_in: AppGenerationCreate,
) -> AppGenerationCreate:
    prompt = generation_in.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    style = generation_in.style.strip()
    if not style:
        raise HTTPException(status_code=400, detail="Style is required")

    aspect_ratio = generation_in.aspect_ratio.strip()
    if not aspect_ratio:
        raise HTTPException(status_code=400, detail="Aspect ratio is required")

    reference_image_url = _clean_optional_url(generation_in.reference_image_url)
    character_image_url = _clean_optional_url(generation_in.character_image_url)
    for image_url in (reference_image_url, character_image_url):
        if image_url and not is_supported_uploaded_image_url(image_url):
            raise HTTPException(
                status_code=400,
                detail="Image URL must be local upload URL",
            )

    duration_seconds = generation_in.duration_seconds
    if generation_in.kind == "video":
        duration_seconds = duration_seconds or 5
    else:
        duration_seconds = None

    return AppGenerationCreate(
        kind=generation_in.kind,
        prompt=prompt,
        style=style,
        aspect_ratio=aspect_ratio,
        duration_seconds=duration_seconds,
        consistency=generation_in.consistency,
        reference_image_url=reference_image_url,
        character_image_url=character_image_url,
    )


def _serialize_generation(generation: AppGeneration) -> AppGenerationPublic:
    return AppGenerationPublic.model_validate(generation)


def _build_quota(
    *, session: Session, current_app_user: AppUser
) -> AppGenerationQuotaPublic:
    video_used = crud.count_app_generations_by_kind(
        session=session,
        app_user=current_app_user,
        kind="video",
    )
    image_used = crud.count_app_generations_by_kind(
        session=session,
        app_user=current_app_user,
        kind="image",
    )
    return AppGenerationQuotaPublic(
        video_total=FREE_GENERATION_LIMIT,
        video_used=video_used,
        video_remaining=max(0, FREE_GENERATION_LIMIT - video_used),
        image_total=FREE_GENERATION_LIMIT,
        image_used=image_used,
        image_remaining=max(0, FREE_GENERATION_LIMIT - image_used),
    )


@router.get("/quota", response_model=AppGenerationQuotaPublic)
def read_generation_quota(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
) -> Any:
    """
    Return the current App user's free generation quota.
    """
    return _build_quota(session=session, current_app_user=current_app_user)


@router.post("/", response_model=AppGenerationPublic)
def create_generation(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    generation_in: AppGenerationCreate,
) -> Any:
    """
    Create a Seedance or Seedream generation task.

    The local MVP records the task as processing, then a lightweight background
    worker marks it succeeded. A real provider adapter can replace the local
    worker without changing the public API contract.
    """
    normalized_generation = _normalize_generation_input(generation_in)
    used_count = crud.count_app_generations_by_kind(
        session=session,
        app_user=current_app_user,
        kind=normalized_generation.kind,
    )
    if used_count >= FREE_GENERATION_LIMIT:
        raise HTTPException(
            status_code=402,
            detail="Free generation quota exhausted",
        )

    generation = crud.create_app_generation(
        session=session,
        app_user=current_app_user,
        generation_in=normalized_generation,
        model=GENERATION_MODELS[normalized_generation.kind],
    )
    ai_generation.enqueue_generation(generation.id)
    return _serialize_generation(generation)


@router.get("/", response_model=AppGenerationsPublic)
def read_generations(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    kind: Annotated[Literal["video", "image"] | None, Query()] = None,
) -> Any:
    """
    Retrieve the current App user's visible generation works.
    """
    generations, count = crud.list_app_generations_for_app(
        session=session,
        app_user=current_app_user,
        skip=skip,
        limit=limit,
        kind=kind,
    )
    return AppGenerationsPublic(
        data=[_serialize_generation(generation) for generation in generations],
        count=count,
    )


@router.get("/{generation_id}", response_model=AppGenerationPublic)
def read_generation(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    generation_id: uuid.UUID,
) -> Any:
    """
    Get one visible generation work for the current App user.
    """
    generation = crud.get_app_generation_for_app(
        session=session,
        app_user=current_app_user,
        generation_id=generation_id,
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return _serialize_generation(generation)


@router.delete("/{generation_id}", response_model=Message)
def delete_generation(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    generation_id: uuid.UUID,
) -> Any:
    """
    Hide a generation work from the current App user's works list.
    """
    generation = crud.get_app_generation_for_app(
        session=session,
        app_user=current_app_user,
        generation_id=generation_id,
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")

    crud.soft_delete_app_generation(session=session, generation=generation)
    return Message(message="Generation deleted successfully")
