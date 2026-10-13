import json

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.services.paypal_client import PayPalError, get_paypal_client
from app.services.paypal_orders import process_webhook

router = APIRouter(prefix="/webhooks/payments", tags=["paypal webhooks"])


@router.post("/paypal", status_code=204)
async def paypal_webhook(request: Request, session: SessionDep) -> Response:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 256 * 1024:
            raise HTTPException(413, "Payment event is too large")
    try:
        event = json.loads(raw)
        if not isinstance(event, dict) or not isinstance(event.get("resource"), dict):
            raise ValueError()
    except ValueError, UnicodeDecodeError:
        raise HTTPException(422, "Invalid payment event") from None
    client = None
    try:
        client = get_paypal_client()
        valid = await run_in_threadpool(
            client.verify_webhook, bytes(raw), request.headers
        )
        if not valid:
            raise HTTPException(403, "Invalid PayPal webhook signature")
        await run_in_threadpool(process_webhook, session, event, client)
    except PayPalError as exc:
        session.rollback()
        # Genuine-but-unprocessed events must be retried by PayPal, not acknowledged.
        raise HTTPException(
            503, "Payment event processing temporarily unavailable"
        ) from exc
    finally:
        if client:
            client.close()
    return Response(status_code=204)
