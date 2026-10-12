"""Provider observations settle existing tasks; they never create predictions.

Callers hold the task row lock. Webhooks, polling and administrator reconciliation
use the same transition/refund transaction. Transport errors are NOT failure proof.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.models import AppVideoTask
from app.services.coin_wallet import refund_video_task
from app.services.replicate_video import (
    ReplicateAPIError,
    ReplicateConfigurationError,
    get_replicate_video_client,
)
from app.services.video_generation import VideoTaskResult, VideoTaskStatus

logger = logging.getLogger(__name__)
PROVIDER_ACTIVE_STATUSES = ("submitting", "submission_unknown", "pending", "running")
PROVIDER_TERMINAL_STATUSES = (
    "rendering_demo",
    "saving",
    "succeeded",
    "failed",
    "canceled",
    "expired",
)


class VideoTaskStateError(ValueError):
    pass


def lock_task(session: Session, task_id: uuid.UUID) -> AppVideoTask | None:
    return session.exec(
        select(AppVideoTask)
        .where(AppVideoTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def apply_provider_result(
    *, session: Session, task: AppVideoTask, result: VideoTaskResult
) -> None:
    if task.provider_task_id not in {None, result.provider_task_id}:
        raise VideoTaskStateError("Prediction does not match video task")
    now = datetime.now(UTC)
    task.provider_last_checked_at = now
    # Do not revive deleted/expired or financially settled tasks.
    if task.status in PROVIDER_TERMINAL_STATUSES:
        session.add(task)
        return
    task.provider_task_id = result.provider_task_id
    if task.real_submission_counted_at is None:
        task.real_submission_counted_at = now
    task.provider_next_check_at = now + timedelta(seconds=60)
    if result.status == VideoTaskStatus.SUCCEEDED:
        task.provider_next_check_at = None
        if result.output_url:
            task.status = "saving"
            task.provider_output_url = result.output_url
            task.error = None
            task.metrics_json = json.dumps(result.metrics) if result.metrics else None
            task.next_attempt_at = now
        else:
            task.status = "failed"
            task.error = "Provider succeeded without an available video output"
            task.completed_at = now
    elif result.status in {VideoTaskStatus.FAILED, VideoTaskStatus.CANCELED}:
        task.provider_next_check_at = None
        if result.status == VideoTaskStatus.FAILED and settings.LOCAL_DEMO_ENABLED:
            task.status = "rendering_demo"
            task.execution_type = "local_demo"
            task.is_demo = True
            task.fallback_reason = "provider_failed"
            task.error = None
            task.next_attempt_at = now
            task.metrics_json = json.dumps({"fallback_provider_error": result.error})
        else:
            task.status = (
                "failed" if result.status == VideoTaskStatus.FAILED else "canceled"
            )
            task.error = result.error or "Provider did not complete the generation"
            task.completed_at = now
    elif result.status == VideoTaskStatus.RUNNING:
        task.status = "running"
        task.error = None
    elif result.status == VideoTaskStatus.PENDING and task.status != "running":
        task.status = "pending"
        task.error = None
    # UNKNOWN is an authenticated observation, not a settlement instruction.
    task.updated_at = now
    if task.status in {"failed", "canceled"}:
        refund_video_task(session=session, task=task)
    session.add(task)


async def reconcile_task(*, session: Session, task_id: uuid.UUID) -> AppVideoTask:
    task = lock_task(session, task_id)
    if task is None:
        raise VideoTaskStateError("Video task not found")
    if task.status not in PROVIDER_ACTIVE_STATUSES or not task.provider_task_id:
        return task
    # Release the DB lock during provider I/O, then refresh under the same lock.
    provider_id = task.provider_task_id
    session.commit()
    client = None
    try:
        client = get_replicate_video_client()
        async with asyncio.timeout(10):
            result = await client.get_task(provider_id)
    except (
        httpx.HTTPError,
        ReplicateAPIError,
        ReplicateConfigurationError,
        TimeoutError,
    ):
        task = lock_task(session, task_id)
        if task is None:
            raise VideoTaskStateError("Video task not found")
        task.provider_last_checked_at = datetime.now(UTC)
        if task.status in PROVIDER_ACTIVE_STATUSES:
            task.provider_next_check_at = datetime.now(UTC) + timedelta(seconds=60)
        session.add(task)
        # Do not store provider bodies/URLs or turn 404/timeout into a refund.
        logger.warning(
            "Video provider reconciliation unavailable",
            extra={"video_task_id": str(task_id)},
        )
        return task
    finally:
        if client is not None:
            await client.aclose()
    task = lock_task(session, task_id)
    if task is None:
        raise VideoTaskStateError("Video task not found")
    apply_provider_result(session=session, task=task, result=result)
    return task


async def _reconcile_due_tasks() -> int:
    now = datetime.now(UTC)
    with Session(engine) as session:
        task_ids = list(
            session.exec(
                select(AppVideoTask.id)
                .where(
                    col(AppVideoTask.status).in_(PROVIDER_ACTIVE_STATUSES),
                    AppVideoTask.provider == "replicate",
                    col(AppVideoTask.provider_task_id).is_not(None),
                    or_(
                        col(AppVideoTask.provider_next_check_at).is_(None),
                        col(AppVideoTask.provider_next_check_at) <= now,
                    ),
                )
                .order_by(col(AppVideoTask.provider_next_check_at).asc())
                .limit(30)
            ).all()
        )
    slots = asyncio.Semaphore(5)

    async def check_one(task_id: uuid.UUID) -> int:
        async with slots:
            return await check_locked(task_id)

    async def check_locked(task_id: uuid.UUID) -> int:
        with Session(engine) as session:
            try:
                await reconcile_task(session=session, task_id=task_id)
                session.commit()
                return 1
            except VideoTaskStateError:
                session.rollback()
                logger.warning(
                    "Video reconciliation identity conflict",
                    extra={"video_task_id": str(task_id)},
                )
                return 0

    return sum(await asyncio.gather(*(check_one(task_id) for task_id in task_ids)))


def reconcile_video_tasks() -> int:
    return asyncio.run(_reconcile_due_tasks())
