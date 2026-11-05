import asyncio
import hashlib
import json
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.config import settings
from app.models import AppVideoTask, AppVideoTaskWebhookEvent
from app.services.replicate_video import (
    ReplicateAPIError,
    ReplicateConfigurationError,
    get_replicate_video_client,
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
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 256 * 1024:
            raise HTTPException(413, "Webhook payload too large")
    raw_body = bytes(chunks)
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
    if settings.ENVIRONMENT != "local":
        # A valid callback signature alone must not bind an unknown submission
        # or settle a prediction from the callback body. Polling remains fallback.
        if not task.provider_task_id:
            raise HTTPException(409, "Prediction requires server-side reconciliation")
        provider_id = task.provider_task_id
        session.commit()  # Do not hold a database row lock across provider I/O.
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
        ) as exc:
            raise HTTPException(503, "Prediction verification unavailable") from exc
        finally:
            if client is not None:
                await client.aclose()
        task = session.exec(
            select(AppVideoTask)
            .where(AppVideoTask.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if (
            task is None
            or task.provider_task_id != provider_id
            or result.provider_task_id != provider_id
        ):
            raise HTTPException(409, "Prediction does not match video task")
        # Recheck under the lock after concurrent verification of the same event.
        if (
            session.exec(
                select(AppVideoTaskWebhookEvent).where(
                    AppVideoTaskWebhookEvent.webhook_id == webhook_id
                )
            ).first()
            is not None
        ):
            return Response(status_code=204)
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
