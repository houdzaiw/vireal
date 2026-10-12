import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.api.deps import SessionDep
from app.models import AppVideoTask, AppVideoTaskWebhookEvent
from app.services.replicate_video import (
    ReplicateAPIError,
    parse_replicate_task_payload,
)
from app.services.replicate_webhook import (
    ReplicateWebhookVerificationError,
    verify_replicate_webhook,
)
from app.services.video_task_reconciliation import (
    PROVIDER_TERMINAL_STATUSES,
    VideoTaskStateError,
    apply_provider_result,
)

router = APIRouter(prefix="/webhooks/replicate", tags=["replicate webhooks"])
TERMINAL_PROVIDER_STATUSES = set(PROVIDER_TERMINAL_STATUSES)


@router.post("", status_code=204)
async def receive_replicate_webhook(
    *,
    request: Request,
    session: SessionDep,
    task_id: uuid.UUID,
) -> Response:
    raw_body = await request.body()
    try:
        webhook_id = verify_replicate_webhook(
            raw_body=raw_body,
            headers=request.headers,
        )
    except ReplicateWebhookVerificationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    duplicate = session.exec(
        select(AppVideoTaskWebhookEvent).where(
            AppVideoTaskWebhookEvent.webhook_id == webhook_id
        )
    ).first()
    if duplicate is not None:
        return Response(status_code=204)

    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail="Invalid Replicate webhook JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Replicate webhook payload")
    try:
        result = parse_replicate_task_payload(payload)
    except ReplicateAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = session.exec(
        select(AppVideoTask)
        .where(AppVideoTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    if task.provider_task_id and task.provider_task_id != result.provider_task_id:
        raise HTTPException(
            status_code=409, detail="Prediction does not match video task"
        )
    event = AppVideoTaskWebhookEvent(
        video_task_id=task.id,
        webhook_id=webhook_id,
        provider_task_id=result.provider_task_id,
        provider_status=result.status.value.lower(),
        payload_sha256=hashlib.sha256(raw_body).hexdigest(),
    )
    session.add(event)

    try:
        apply_provider_result(session=session, task=task, result=result)
    except VideoTaskStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return Response(status_code=204)
    return Response(status_code=204)
