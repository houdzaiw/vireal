"""Restricted operations for the current paid H5 task lifecycle."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Field, SQLModel, col, select

from app import crud
from app.api.deps import (
    SessionDep,
    get_current_active_superuser,
    require_cloudflare_access,
)
from app.core.config import settings
from app.models import (
    AppAdminOperationLog,
    AppCoinLedger,
    AppCoinLedgerPublic,
    AppVideoTask,
    User,
)
from app.services.coin_wallet import refund_video_task
from app.services.video_task_reconciliation import (
    PROVIDER_ACTIVE_STATUSES,
    VideoTaskStateError,
    lock_task,
    reconcile_task,
)

router = APIRouter(
    prefix="/admin/app/video-tasks",
    tags=["admin video tasks"],
    dependencies=[
        Depends(require_cloudflare_access),
        Depends(get_current_active_superuser),
    ],
)


class AdminVideoTaskPublic(SQLModel):
    id: uuid.UUID
    app_user_id: uuid.UUID
    effect_id: uuid.UUID | None
    template_id: str
    model: str
    provider: str
    provider_task_id: str | None
    status: str
    duration: int
    coin_cost_snapshot: int | None
    coin_refunded_at: datetime | None
    provider_last_checked_at: datetime | None
    provider_next_check_at: datetime | None
    submission_attempted_at: datetime | None
    real_submission_counted_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    error: str | None
    needs_review: bool = False
    ledger: list[AppCoinLedgerPublic] = Field(default_factory=list)


class AdminVideoTasksPublic(SQLModel):
    data: list[AdminVideoTaskPublic]
    count: int


class AdminVideoTaskAction(SQLModel):
    reason: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=120)


class AdminVideoTaskResolve(AdminVideoTaskAction):
    resolution: Literal["not_submitted", "failed", "canceled", "unavailable"]
    evidence: str = Field(min_length=10, max_length=1000)
    provider_confirmed: Literal[True]


def _review_filter() -> ColumnElement[bool]:
    now = datetime.now(UTC)
    return or_(
        col(AppVideoTask.status) == "submission_unknown",
        and_(
            col(AppVideoTask.status) == "saving",
            col(AppVideoTask.worker_attempts) >= settings.VIDEO_WORKER_MAX_ATTEMPTS,
        ),
        and_(
            col(AppVideoTask.status).in_((*PROVIDER_ACTIVE_STATUSES, "saving")),
            col(AppVideoTask.created_at) < now - timedelta(minutes=15),
        ),
        and_(
            col(AppVideoTask.status) == "expired",
            col(AppVideoTask.completed_at).is_(None),
            col(AppVideoTask.coin_cost_snapshot) > 0,
            col(AppVideoTask.coin_refunded_at).is_(None),
        ),
    )


def _serialize(session: SessionDep, task: AppVideoTask) -> AdminVideoTaskPublic:
    payload = AdminVideoTaskPublic.model_validate(task)
    payload.needs_review = bool(
        session.exec(
            select(AppVideoTask.id).where(AppVideoTask.id == task.id, _review_filter())
        ).first()
    )
    payload.ledger = [
        AppCoinLedgerPublic.model_validate(row)
        for row in session.exec(
            select(AppCoinLedger)
            .where(AppCoinLedger.task_id == task.id)
            .order_by(col(AppCoinLedger.created_at))
        ).all()
    ]
    return payload


def _get_task(session: SessionDep, task_id: uuid.UUID) -> AppVideoTask:
    task = lock_task(session, task_id)
    if task is None:
        raise HTTPException(404, "Video task not found")
    return task


def _duplicate(
    session: SessionDep, task_id: uuid.UUID, action: str, body: AdminVideoTaskAction
) -> bool:
    logs = session.exec(
        select(AppAdminOperationLog).where(
            AppAdminOperationLog.target_id == task_id,
            AppAdminOperationLog.target_type == "video_task",
            AppAdminOperationLog.action == action,
        )
    ).all()
    expected = body.model_dump()
    for log in logs:
        details = json.loads(log.details_json)
        if details.get("idempotency_key") == body.idempotency_key:
            if details.get("request") != expected:
                raise HTTPException(
                    409, "Idempotency key belongs to a different operation"
                )
            return True
    return False


def _audit(
    session: SessionDep,
    admin: User,
    task: AppVideoTask,
    action: str,
    body: AdminVideoTaskAction,
) -> None:
    crud.create_app_admin_operation_log(
        session=session,
        admin_user=admin,
        action=action,
        target_type="video_task",
        target_id=task.id,
        summary=body.reason,
        details={
            "idempotency_key": body.idempotency_key,
            "request": body.model_dump(),
            "status": task.status,
            "coin_refunded": task.coin_refunded_at is not None,
            "provider_task_id": task.provider_task_id,
        },
    )


@router.get("", response_model=AdminVideoTasksPublic)
def read_video_tasks(
    session: SessionDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status: str | None = None,
    app_user_id: uuid.UUID | None = None,
    needs_review: bool = False,
) -> AdminVideoTasksPublic:
    statement = select(AppVideoTask)
    count_statement = select(func.count()).select_from(AppVideoTask)
    filters: list[ColumnElement[bool]] = []
    if status:
        filters.append(col(AppVideoTask.status) == status)
    if app_user_id:
        filters.append(col(AppVideoTask.app_user_id) == app_user_id)
    if needs_review:
        filters.append(_review_filter())
    rows = session.exec(
        statement.where(*filters)
        .order_by(col(AppVideoTask.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return AdminVideoTasksPublic(
        data=[_serialize(session, row) for row in rows],
        count=session.exec(count_statement.where(*filters)).one(),
    )


@router.get("/{task_id}", response_model=AdminVideoTaskPublic)
def read_video_task(session: SessionDep, task_id: uuid.UUID) -> AdminVideoTaskPublic:
    return _serialize(session, _get_task(session, task_id))


@router.post("/{task_id}/reconcile", response_model=AdminVideoTaskPublic)
async def reconcile_video_task(
    session: SessionDep,
    task_id: uuid.UUID,
    body: AdminVideoTaskAction,
    current_admin: User = Depends(get_current_active_superuser),
) -> AdminVideoTaskPublic:
    task = _get_task(session, task_id)
    if _duplicate(session, task_id, "video_task.reconcile", body):
        return _serialize(session, task)
    if not task.provider_task_id:
        raise HTTPException(
            409, "No prediction ID: obtain provider evidence; do not retry generation"
        )
    try:
        task = await reconcile_task(session=session, task_id=task_id)
    except VideoTaskStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    # A concurrent administrative retry can finish while the provider GET runs.
    if not _duplicate(session, task_id, "video_task.reconcile", body):
        _audit(session, current_admin, task, "video_task.reconcile", body)
    session.commit()
    return _serialize(session, task)


@router.post("/{task_id}/resolve", response_model=AdminVideoTaskPublic)
def resolve_video_task(
    session: SessionDep,
    task_id: uuid.UUID,
    body: AdminVideoTaskResolve,
    current_admin: User = Depends(get_current_active_superuser),
) -> AdminVideoTaskPublic:
    task = _get_task(session, task_id)
    if _duplicate(session, task_id, "video_task.resolve", body):
        return _serialize(session, task)
    historical_unknown = task.status == "expired" and task.completed_at is None
    if task.deleted_at is not None or (
        task.status not in (*PROVIDER_ACTIVE_STATUSES, "saving")
        and not historical_unknown
    ):
        raise HTTPException(
            409, "Task is already settled; it cannot be manually rewritten"
        )
    now = datetime.now(UTC)
    if (
        task.status == "submitting"
        and task.submission_attempted_at
        and task.submission_attempted_at > now - timedelta(minutes=2)
    ):
        raise HTTPException(
            409, "Submission is still in flight; verify it before resolving"
        )
    if task.worker_locked_at and task.worker_locked_at > now - timedelta(minutes=10):
        raise HTTPException(
            409, "Video persistence is in progress; reconcile before resolving"
        )
    if body.resolution == "not_submitted" and (
        task.provider_task_id or task.real_submission_counted_at
    ):
        raise HTTPException(
            409, "An accepted prediction cannot be classified as not submitted"
        )
    # Verify an actual debit before any compensation, not just a client amount.
    debit = session.exec(
        select(AppCoinLedger).where(
            AppCoinLedger.task_id == task.id,
            AppCoinLedger.entry_type == "generation_debit",
        )
    ).first()
    if task.coin_cost_snapshot and (
        debit is None or debit.delta != -task.coin_cost_snapshot
    ):
        raise HTTPException(
            409, "Original task debit must be verified before settlement"
        )
    if body.resolution != "not_submitted" and task.real_submission_counted_at is None:
        task.real_submission_counted_at = now
    task.status = "canceled" if body.resolution == "canceled" else "failed"
    task.error = "Confirmed manual resolution; see audited provider evidence"
    task.completed_at = now
    task.updated_at = now
    task.provider_next_check_at = None
    task.next_attempt_at = None
    task.provider_output_url = None
    refund_video_task(session=session, task=task)
    session.add(task)
    _audit(session, current_admin, task, "video_task.resolve", body)
    session.commit()
    return _serialize(session, task)
