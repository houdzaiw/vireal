import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import func, text
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import (
    AppUpload,
    AppVideoTask,
    AppVideoTaskCreate,
    AppVideoTaskPublic,
)
from app.services.replicate_video import (
    ReplicateAPIError,
    ReplicateConfigurationError,
    get_replicate_video_client,
)
from app.services.storage import ImageStorageError, get_image_storage
from app.services.video_generation import VideoTaskStatus

router = APIRouter(prefix="/app/video-tasks", tags=["app video tasks"])

DANCE_PROMPT = (
    "A single adult person performs a smooth natural full-body dance with balanced "
    "rhythmic movements, remaining centered in frame, full body visible, consistent "
    "identity, realistic motion, and a static camera."
)
DANCE_NEGATIVE_PROMPT = (
    "extra people, duplicate person, deformed hands, extra limbs, missing limbs, "
    "cropped body, identity drift, camera shake, text, watermark"
)
POC_BUDGET_LOCK_ID = 836_274_901


def _serialize_video_task(task: AppVideoTask) -> AppVideoTaskPublic:
    playback_url: str | None = None
    if task.status == "succeeded" and task.output_object_key:
        try:
            playback_url = get_image_storage().create_object_read_url(
                task.output_object_key,
                expires_in=settings.R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS,
            )
        except ImageStorageError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AppVideoTaskPublic(
        id=task.id,
        template_id=task.template_id,
        status=task.status,
        duration=task.duration,
        resolution=task.resolution,
        aspect_ratio=task.aspect_ratio,
        error=task.error,
        playback_url=playback_url,
        created_at=task.created_at,
        completed_at=task.completed_at,
        expires_at=task.expires_at,
    )


def _webhook_url(task_id: uuid.UUID) -> str:
    if settings.REPLICATE_WEBHOOK_URL is None:
        raise ReplicateConfigurationError("Replicate webhook URL is required")
    parsed = urlsplit(str(settings.REPLICATE_WEBHOOK_URL))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["task_id"] = str(task_id)
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _get_owned_uploads(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    upload_ids: list[uuid.UUID],
) -> list[AppUpload]:
    uploads = list(
        session.exec(
            select(AppUpload).where(
                col(AppUpload.id).in_(upload_ids),
                AppUpload.app_user_id == current_app_user.id,
                AppUpload.status == "active",
                AppUpload.expires_at > datetime.now(UTC),
            )
        ).all()
    )
    uploads_by_id = {upload.id: upload for upload in uploads}
    try:
        return [uploads_by_id[upload_id] for upload_id in upload_ids]
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail="Every upload must exist, belong to the current user, and be active",
        ) from exc


def _get_task_for_user(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    task_id: uuid.UUID,
) -> AppVideoTask:
    task = session.exec(
        select(AppVideoTask).where(
            AppVideoTask.id == task_id,
            AppVideoTask.app_user_id == current_app_user.id,
        )
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    return task


def _lock_video_task(session: SessionDep, task_id: uuid.UUID) -> AppVideoTask:
    return session.exec(
        select(AppVideoTask)
        .where(AppVideoTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _serialize_idempotent_task(
    existing: AppVideoTask,
    body: AppVideoTaskCreate,
) -> AppVideoTaskPublic:
    if (
        existing.template_id != body.template_id
        or existing.duration != body.duration
        or json.loads(existing.upload_ids_json)
        != [str(upload_id) for upload_id in body.upload_ids]
    ):
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key was already used for another request",
        )
    return _serialize_video_task(existing)


@router.post(
    "", response_model=AppVideoTaskPublic, status_code=status.HTTP_202_ACCEPTED
)
async def create_video_task(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    body: AppVideoTaskCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> AppVideoTaskPublic:
    if not settings.REPLICATE_ENABLED:
        raise HTTPException(status_code=503, detail="Replicate integration is disabled")
    idempotency_key = idempotency_key.strip()
    if not 8 <= len(idempotency_key) <= 255:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain between 8 and 255 characters",
        )

    existing = session.exec(
        select(AppVideoTask).where(
            AppVideoTask.app_user_id == current_app_user.id,
            AppVideoTask.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return _serialize_idempotent_task(existing, body)

    uploads = _get_owned_uploads(
        session=session,
        current_app_user=current_app_user,
        upload_ids=body.upload_ids,
    )
    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": POC_BUDGET_LOCK_ID},
    )
    existing = session.exec(
        select(AppVideoTask).where(
            AppVideoTask.app_user_id == current_app_user.id,
            AppVideoTask.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return _serialize_idempotent_task(existing, body)
    attempted_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(col(AppVideoTask.submission_attempted_at).is_not(None))
    ).one()
    if attempted_count >= settings.REPLICATE_POC_MAX_SUBMISSIONS:
        raise HTTPException(
            status_code=409,
            detail="Replicate PoC submission limit has been reached",
        )

    now = datetime.now(UTC)
    task = AppVideoTask(
        app_user_id=current_app_user.id,
        idempotency_key=idempotency_key,
        template_id=body.template_id,
        upload_ids_json=json.dumps([str(upload_id) for upload_id in body.upload_ids]),
        model=settings.REPLICATE_R2V_MODEL,
        duration=body.duration,
        seed=secrets.randbelow(2_147_483_648),
        submission_attempted_at=now,
        expires_at=now + timedelta(hours=settings.APP_MEDIA_RETENTION_HOURS),
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    try:
        client = get_replicate_video_client()
    except ReplicateConfigurationError as exc:
        task.status = "failed"
        task.error = str(exc)
        task.completed_at = datetime.now(UTC)
    else:
        try:
            submission = await client.submit_reference_to_video(
                reference_image_urls=[upload.url for upload in uploads],
                prompt=DANCE_PROMPT,
                duration=body.duration,
                aspect_ratio="9:16",
                resolution="720p",
                negative_prompt=DANCE_NEGATIVE_PROMPT,
                seed=task.seed,
                webhook_url=_webhook_url(task.id),
            )
            # A completed webhook can race the create response. Refresh first so a
            # newer provider state is never overwritten with pending.
            task = _lock_video_task(session, task.id)
            if task.provider_task_id not in {None, submission.provider_task_id}:
                task.status = "submission_unknown"
                task.error = "Replicate returned a conflicting prediction id"
            else:
                task.provider_task_id = submission.provider_task_id
                if task.status == "submitting":
                    task.status = (
                        "running"
                        if submission.status == VideoTaskStatus.RUNNING
                        else "pending"
                    )
        except httpx.TimeoutException, httpx.RequestError:
            task = _lock_video_task(session, task.id)
            if task.status == "submitting":
                task.status = "submission_unknown"
                task.error = (
                    "Replicate submission result is unknown; it will not be retried"
                )
        except ReplicateAPIError as exc:
            task = _lock_video_task(session, task.id)
            if task.status == "submitting":
                task.provider_task_id = exc.prediction_id
                task.status = "failed"
                task.error = str(exc)
                task.completed_at = datetime.now(UTC)
        except (ReplicateConfigurationError, ImageStorageError, ValueError) as exc:
            task = _lock_video_task(session, task.id)
            if task.status == "submitting":
                task.status = "failed"
                task.error = str(exc)
                task.completed_at = datetime.now(UTC)
        finally:
            await client.aclose()

    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _serialize_video_task(task)


@router.get("/{task_id}", response_model=AppVideoTaskPublic)
def read_video_task(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    task_id: uuid.UUID,
) -> AppVideoTaskPublic:
    return _serialize_video_task(
        _get_task_for_user(
            session=session,
            current_app_user=current_app_user,
            task_id=task_id,
        )
    )
