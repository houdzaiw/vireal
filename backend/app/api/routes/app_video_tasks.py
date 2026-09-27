import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import func, or_, text
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import (
    AppEffect,
    AppEffectCategory,
    AppEffectVariant,
    AppUpload,
    AppVideoTask,
    AppVideoTaskCreate,
    AppVideoTaskPublic,
    AppVideoTasksPublic,
    Message,
)
from app.services.coin_wallet import (
    CoinBalanceError,
    adjust_coin_balance,
    get_coin_balance,
    refund_video_task,
)
from app.services.effect_validation import (
    execution_type_for_model,
    validate_effect_variant,
)
from app.services.replicate_video import (
    ReplicateAPIError,
    ReplicateConfigurationError,
    get_replicate_video_client,
)
from app.services.storage import ImageStorageError, get_image_storage
from app.services.video_generation import VideoTaskStatus
from app.services.video_quota import build_video_quota, quota_counts

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

TaskStatus = Literal[
    "submitting",
    "pending",
    "running",
    "rendering_demo",
    "saving",
    "succeeded",
    "failed",
    "canceled",
    "submission_unknown",
    "expired",
]
TaskMode = Literal["standard", "advanced", "effect"]
TaskExecution = Literal["minimax", "wan", "seedance", "local_demo"]


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
    effect = session.get(AppEffect, task.effect_id) if task.effect_id else None
    return AppVideoTaskPublic(
        id=task.id,
        template_id=task.template_id,
        status=cast(TaskStatus, task.status),
        mode=cast(TaskMode, task.mode),
        execution_type=cast(TaskExecution, task.execution_type),
        is_demo=task.is_demo,
        fallback_reason=task.fallback_reason,
        duration=task.duration,
        effect_id=task.effect_id,
        variant_id=task.variant_id,
        effect_slug=effect.slug if effect else None,
        effect_title=effect.title_zh if effect else None,
        coin_cost=task.coin_cost_snapshot,
        balance=get_coin_balance(session=session, app_user_id=task.app_user_id),
        resolution=task.resolution,
        aspect_ratio=task.aspect_ratio,
        error=task.error,
        playback_url=playback_url,
        created_at=task.created_at,
        completed_at=task.completed_at,
        expires_at=task.expires_at,
        quota=build_video_quota(
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
    same_uploads = json.loads(existing.upload_ids_json) == [
        str(upload_id) for upload_id in body.upload_ids
    ]
    if body.effect_id is not None:
        same_request = (
            existing.effect_id == body.effect_id
            and existing.variant_id == body.variant_id
            and same_uploads
        )
    else:
        same_request = (
            existing.effect_id is None
            and existing.template_id == body.template_id
            and existing.mode == body.mode
            and existing.duration == body.duration
            and same_uploads
        )
    if not same_request:
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

    effect: AppEffect | None = None
    variant: AppEffectVariant | None = None
    if body.effect_id is not None and body.variant_id is not None:
        effect = session.get(AppEffect, body.effect_id)
        variant = session.get(AppEffectVariant, body.variant_id)
        category = (
            session.get(AppEffectCategory, effect.category_id) if effect else None
        )
        if (
            effect is None
            or category is None
            or variant is None
            or variant.effect_id != effect.id
            or not category.is_enabled
            or effect.publish_status != "published"
            or not effect.is_enabled
            or not variant.is_enabled
        ):
            raise HTTPException(status_code=409, detail="Effect is no longer available")
        if len(body.upload_ids) != effect.input_image_count:
            raise HTTPException(
                status_code=422,
                detail=f"This effect requires {effect.input_image_count} images",
            )
        try:
            validate_effect_variant(
                provider=variant.provider,
                model=variant.model,
                input_image_count=effect.input_image_count,
                duration_seconds=variant.duration_seconds,
                prompt=variant.prompt,
                negative_prompt=variant.negative_prompt,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        resolved_template_id = effect.slug
        resolved_mode = "effect"
        resolved_duration = variant.duration_seconds
        planned_execution_type = execution_type_for_model(variant.model)
        resolved_model = variant.model
        resolved_prompt = variant.prompt
        resolved_negative_prompt = variant.negative_prompt
        configured_coin_cost = variant.coin_cost
    else:
        if body.mode == "standard" and body.duration != 5:
            raise HTTPException(
                status_code=422,
                detail="Standard mode only supports five-second video",
            )
        if body.template_id is None or body.duration is None:
            raise HTTPException(status_code=422, detail="Legacy task is incomplete")
        resolved_template_id = body.template_id
        resolved_mode = body.mode
        resolved_duration = body.duration
        planned_execution_type = "minimax" if body.mode == "standard" else "wan"
        resolved_model = (
            settings.REPLICATE_STANDARD_MODEL
            if body.mode == "standard"
            else settings.REPLICATE_ADVANCED_MODEL
        )
        resolved_prompt = DANCE_PROMPT
        resolved_negative_prompt = (
            None if body.mode == "standard" else DANCE_NEGATIVE_PROMPT
        )
        configured_coin_cost = 0

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
    user_count, wan_count, active_count, _resets_at = quota_counts(
        session=session,
        app_user_id=current_app_user.id,
        now=now,
    )
    attempted_count = 0
    if settings.REPLICATE_POC_MAX_SUBMISSIONS > 0:
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

    fallback_reason: str | None = None
    if not settings.REPLICATE_ENABLED:
        fallback_reason = "replicate_disabled"
    elif user_count >= settings.APP_USER_DAILY_REAL_SUBMISSIONS:
        fallback_reason = "user_daily_quota"
    elif (
        settings.REPLICATE_POC_MAX_SUBMISSIONS > 0
        and attempted_count >= settings.REPLICATE_POC_MAX_SUBMISSIONS
    ):
        fallback_reason = "poc_submission_limit"
    elif active_count >= settings.APP_USER_MAX_CONCURRENT_VIDEO_TASKS:
        fallback_reason = "user_concurrent_quota"
    elif (
        planned_execution_type == "wan"
        and wan_count >= settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS
    ):
        fallback_reason = "wan_daily_global_quota"

    if fallback_reason is not None and not settings.LOCAL_DEMO_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="Real video generation quota or provider is unavailable",
        )

    is_demo = fallback_reason is not None
    execution_type = "local_demo" if is_demo else planned_execution_type
    model = "local/ffmpeg" if is_demo else resolved_model
    charged_coin_cost = 0 if is_demo else configured_coin_cost
    task = AppVideoTask(
        app_user_id=current_app_user.id,
        idempotency_key=idempotency_key,
        template_id=resolved_template_id,
        effect_id=effect.id if effect else None,
        variant_id=variant.id if variant else None,
        coin_cost_snapshot=charged_coin_cost,
        prompt_version_snapshot=variant.prompt_version if variant else None,
        upload_ids_json=json.dumps([str(upload_id) for upload_id in body.upload_ids]),
        mode=resolved_mode,
        provider="local" if is_demo else "replicate",
        model=model,
        execution_type=execution_type,
        is_demo=is_demo,
        fallback_reason=fallback_reason,
        status="rendering_demo" if is_demo else "submitting",
        duration=resolved_duration,
        source_duration=6 if resolved_mode == "standard" and not is_demo else None,
        seed=secrets.randbelow(2_147_483_648),
        submission_attempted_at=None if is_demo else now,
        next_attempt_at=now if is_demo else None,
        expires_at=now + timedelta(hours=settings.APP_MEDIA_RETENTION_HOURS),
    )
    session.add(task)
    session.flush()
    if charged_coin_cost:
        try:
            adjust_coin_balance(
                session=session,
                app_user_id=current_app_user.id,
                delta=-charged_coin_cost,
                entry_type="generation_debit",
                idempotency_key=f"video-task-debit:{task.id}",
                task_id=task.id,
                reason=f"生成 {effect.title_zh if effect else resolved_template_id}",
            )
        except CoinBalanceError as exc:
            session.rollback()
            raise HTTPException(
                status_code=409, detail="Insufficient coin balance"
            ) from exc
    session.commit()
    session.refresh(task)

    if is_demo:
        return _serialize_video_task(session=session, task=task)

    client = None
    try:
        client = get_replicate_video_client()
        submission = await client.submit_reference_to_video(
            reference_image_urls=[upload.url for upload in uploads],
            prompt=resolved_prompt,
            duration=resolved_duration,
            aspect_ratio="9:16",
            resolution="720p",
            negative_prompt=resolved_negative_prompt,
            seed=None
            if resolved_model == settings.REPLICATE_STANDARD_MODEL
            else task.seed,
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
    if task.status in {"failed", "canceled"}:
        refund_video_task(session=session, task=task)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _serialize_video_task(session=session, task=task)


@router.get("", response_model=AppVideoTasksPublic)
def read_video_tasks(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    skip: int = 0,
    limit: int = 50,
) -> AppVideoTasksPublic:
    filters = (
        AppVideoTask.app_user_id == current_app_user.id,
        col(AppVideoTask.deleted_at).is_(None),
    )
    count = session.exec(
        select(func.count()).select_from(AppVideoTask).where(*filters)
    ).one()
    tasks = session.exec(
        select(AppVideoTask)
        .where(*filters)
        .order_by(col(AppVideoTask.created_at).desc())
        .offset(skip)
        .limit(min(max(limit, 1), 100))
    ).all()
    return AppVideoTasksPublic(
        data=[_serialize_video_task(session=session, task=task) for task in tasks],
        count=int(count),
    )


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


@router.delete("/{task_id}", response_model=Message)
def delete_video_task(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    task_id: uuid.UUID,
) -> Message:
    task = _get_task_for_user(
        session=session, current_app_user=current_app_user, task_id=task_id
    )
    if task.status not in {"succeeded", "failed", "canceled", "expired"}:
        raise HTTPException(status_code=409, detail="Active task cannot be deleted")
    if task.output_object_key:
        try:
            get_image_storage().delete_object(task.output_object_key)
        except ImageStorageError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    now = datetime.now(UTC)
    task.deleted_at = now
    task.output_object_key = None
    task.provider_output_url = None
    task.status = "expired"
    task.updated_at = now
    session.add(task)
    session.commit()
    return Message(message="Video task deleted")
