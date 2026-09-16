import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import and_, func, or_, text
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import (
    AppUpload,
    AppVideoTask,
    AppVideoTaskCreate,
    AppVideoTaskPublic,
    AppVideoTaskQuotaPublic,
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
REAL_EXECUTION_TYPES = ("minimax", "wan")
RESERVED_REAL_STATUSES = ("submitting", "submission_unknown")


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _quota_counts(
    *,
    session: SessionDep,
    app_user_id: uuid.UUID,
    now: datetime,
) -> tuple[int, int, datetime]:
    day_start, resets_at = _utc_day_bounds(now)
    counted_today = and_(
        col(AppVideoTask.real_submission_counted_at).is_not(None),
        col(AppVideoTask.real_submission_counted_at) >= day_start,
        col(AppVideoTask.real_submission_counted_at) < resets_at,
    )
    reserved_today = and_(
        col(AppVideoTask.created_at).is_not(None),
        col(AppVideoTask.created_at) >= day_start,
        col(AppVideoTask.created_at) < resets_at,
        col(AppVideoTask.execution_type).in_(REAL_EXECUTION_TYPES),
        col(AppVideoTask.status).in_(RESERVED_REAL_STATUSES),
    )
    real_today = or_(counted_today, reserved_today)
    user_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(
            AppVideoTask.app_user_id == app_user_id,
            real_today,
        )
    ).one()
    wan_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(
            AppVideoTask.mode == "advanced",
            real_today,
        )
    ).one()
    return int(user_count), int(wan_count), resets_at


def _build_quota(
    *,
    session: SessionDep,
    app_user_id: uuid.UUID,
    now: datetime | None = None,
) -> AppVideoTaskQuotaPublic:
    user_count, wan_count, resets_at = _quota_counts(
        session=session,
        app_user_id=app_user_id,
        now=now or datetime.now(UTC),
    )
    return AppVideoTaskQuotaPublic(
        user_real_limit=settings.APP_USER_DAILY_REAL_SUBMISSIONS,
        user_real_remaining=max(
            settings.APP_USER_DAILY_REAL_SUBMISSIONS - user_count,
            0,
        ),
        wan_global_limit=settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS,
        wan_global_remaining=max(
            settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS - wan_count,
            0,
        ),
        resets_at=resets_at,
    )


def _serialize_video_task(
    *,
    session: SessionDep,
    task: AppVideoTask,
) -> AppVideoTaskPublic:
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
        mode=task.mode,
        execution_type=task.execution_type,
        is_demo=task.is_demo,
        fallback_reason=task.fallback_reason,
        duration=task.duration,
        resolution=task.resolution,
        aspect_ratio=task.aspect_ratio,
        error=task.error,
        playback_url=playback_url,
        created_at=task.created_at,
        completed_at=task.completed_at,
        expires_at=task.expires_at,
        quota=_build_quota(
            session=session,
            app_user_id=task.app_user_id,
        ),
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
    session: SessionDep,
    existing: AppVideoTask,
    body: AppVideoTaskCreate,
) -> AppVideoTaskPublic:
    if (
        existing.template_id != body.template_id
        or existing.mode != body.mode
        or existing.duration != body.duration
        or json.loads(existing.upload_ids_json)
        != [str(upload_id) for upload_id in body.upload_ids]
    ):
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key was already used for another request",
        )
    return _serialize_video_task(session=session, task=existing)


def _fallback_reason_for_api_error(exc: ReplicateAPIError) -> str | None:
    if exc.status_code == 402:
        return "provider_insufficient_credit"
    if exc.status_code == 429:
        return "provider_rate_limited"
    if exc.status_code is not None and exc.status_code >= 500:
        return "provider_unavailable"
    return None


def _route_to_local_demo(
    task: AppVideoTask,
    *,
    reason: str,
    now: datetime,
    provider_error: str | None = None,
) -> None:
    task.status = "rendering_demo"
    task.execution_type = "local_demo"
    task.is_demo = True
    task.fallback_reason = reason
    task.provider_output_url = None
    task.error = None
    task.next_attempt_at = now
    task.completed_at = None
    if provider_error:
        task.metrics_json = json.dumps(
            {"fallback_provider_error": provider_error},
            ensure_ascii=False,
            sort_keys=True,
        )


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
    if not settings.REPLICATE_ENABLED and not settings.LOCAL_DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Replicate integration is disabled")
    if body.mode == "standard" and body.duration != 5:
        raise HTTPException(
            status_code=422,
            detail="Standard mode only supports five-second video",
        )
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
        return _serialize_idempotent_task(session, existing, body)

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
        return _serialize_idempotent_task(session, existing, body)

    now = datetime.now(UTC)
    user_count, wan_count, _resets_at = _quota_counts(
        session=session,
        app_user_id=current_app_user.id,
        now=now,
    )
    fallback_reason: str | None = None
    if not settings.REPLICATE_ENABLED:
        fallback_reason = "replicate_disabled"
    elif user_count >= settings.APP_USER_DAILY_REAL_SUBMISSIONS:
        fallback_reason = "user_daily_quota"
    elif (
        body.mode == "advanced"
        and wan_count >= settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS
    ):
        fallback_reason = "wan_daily_global_quota"
    elif settings.REPLICATE_POC_MAX_SUBMISSIONS > 0:
        attempted_count = session.exec(
            select(func.count())
            .select_from(AppVideoTask)
            .where(
                or_(
                    col(AppVideoTask.real_submission_counted_at).is_not(None),
                    col(AppVideoTask.status) == "submission_unknown",
                )
            )
        ).one()
        if attempted_count >= settings.REPLICATE_POC_MAX_SUBMISSIONS:
            fallback_reason = "poc_submission_limit"

    if fallback_reason is not None and not settings.LOCAL_DEMO_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="Real video generation quota or provider is unavailable",
        )

    is_demo = fallback_reason is not None
    execution_type = (
        "local_demo"
        if is_demo
        else "minimax"
        if body.mode == "standard"
        else "wan"
    )
    model = (
        "local/ffmpeg"
        if is_demo
        else settings.REPLICATE_STANDARD_MODEL
        if body.mode == "standard"
        else settings.REPLICATE_ADVANCED_MODEL
    )
    task = AppVideoTask(
        app_user_id=current_app_user.id,
        idempotency_key=idempotency_key,
        template_id=body.template_id,
        upload_ids_json=json.dumps([str(upload_id) for upload_id in body.upload_ids]),
        mode=body.mode,
        provider="local" if is_demo else "replicate",
        model=model,
        execution_type=execution_type,
        is_demo=is_demo,
        fallback_reason=fallback_reason,
        status="rendering_demo" if is_demo else "submitting",
        duration=body.duration,
        source_duration=6 if body.mode == "standard" and not is_demo else None,
        seed=secrets.randbelow(2_147_483_648),
        submission_attempted_at=None if is_demo else now,
        next_attempt_at=now if is_demo else None,
        expires_at=now + timedelta(hours=settings.APP_MEDIA_RETENTION_HOURS),
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    if is_demo:
        return _serialize_video_task(session=session, task=task)

    client = None
    try:
        client = get_replicate_video_client()
        submission = await client.submit_reference_to_video(
            reference_image_urls=[upload.url for upload in uploads],
            prompt=DANCE_PROMPT,
            duration=body.duration,
            aspect_ratio="9:16",
            resolution="720p",
            negative_prompt=(
                None if body.mode == "standard" else DANCE_NEGATIVE_PROMPT
            ),
            seed=None if body.mode == "standard" else task.seed,
            model=task.model,
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
            task.real_submission_counted_at = datetime.now(UTC)
            if task.status == "submitting":
                task.status = (
                    "running"
                    if submission.status == VideoTaskStatus.RUNNING
                    else "pending"
                )
    except (httpx.TimeoutException, httpx.RequestError):
        task = _lock_video_task(session, task.id)
        if task.status == "submitting":
            task.status = "submission_unknown"
            task.error = "Replicate submission result is unknown; it will not be retried"
    except ReplicateAPIError as exc:
        task = _lock_video_task(session, task.id)
        if task.status == "submitting":
            task.provider_task_id = exc.prediction_id
            if exc.prediction_id:
                task.real_submission_counted_at = datetime.now(UTC)
            reason = _fallback_reason_for_api_error(exc)
            if reason is not None and settings.LOCAL_DEMO_ENABLED:
                _route_to_local_demo(
                    task,
                    reason=reason,
                    now=datetime.now(UTC),
                    provider_error=str(exc),
                )
            else:
                task.status = "failed"
                task.error = str(exc)
                task.completed_at = datetime.now(UTC)
    except (ReplicateConfigurationError, ImageStorageError) as exc:
        task = _lock_video_task(session, task.id)
        if task.status == "submitting" and settings.LOCAL_DEMO_ENABLED:
            _route_to_local_demo(
                task,
                reason="provider_configuration_error",
                now=datetime.now(UTC),
                provider_error=str(exc),
            )
        elif task.status == "submitting":
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = datetime.now(UTC)
    except ValueError as exc:
        task = _lock_video_task(session, task.id)
        if task.status == "submitting":
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = datetime.now(UTC)
    finally:
        if client is not None:
            await client.aclose()

    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _serialize_video_task(session=session, task=task)


@router.get("/{task_id}", response_model=AppVideoTaskPublic)
def read_video_task(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    task_id: uuid.UUID,
) -> AppVideoTaskPublic:
    return _serialize_video_task(
        session=session,
        task=_get_task_for_user(
            session=session,
            current_app_user=current_app_user,
            task_id=task_id,
        ),
    )
