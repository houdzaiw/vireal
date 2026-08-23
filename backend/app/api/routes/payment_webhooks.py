from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request

from app import crud
from app.api.deps import SessionDep
from app.models import (
    AppOrderEventPublic,
    AppOrderPublic,
    PaymentCallbackRequest,
    PaymentCallbackResponse,
)
from app.services.payment_webhook_verification import (
    PaymentWebhookVerificationError,
    verify_payment_webhook,
)

router = APIRouter(prefix="/webhooks/payments", tags=["payment webhooks"])


def _handle_payment_callback(
    *,
    session: SessionDep,
    provider: Literal["apple", "google"],
    callback: PaymentCallbackRequest,
    request: Request,
) -> PaymentCallbackResponse:
    try:
        verify_payment_webhook(provider=provider, headers=request.headers)
    except PaymentWebhookVerificationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    order, event, is_duplicate = crud.process_payment_callback(
        session=session,
        provider=provider,
        callback=callback,
    )
    if order is None:
        message = "Order not found"
    elif is_duplicate:
        message = "Duplicate event ignored"
    else:
        message = "Payment event processed"
    return PaymentCallbackResponse(
        order=AppOrderPublic.model_validate(order) if order else None,
        event=AppOrderEventPublic.model_validate(event),
        is_duplicate=is_duplicate,
        message=message,
    )


@router.post("/apple-iap", response_model=PaymentCallbackResponse)
def receive_apple_iap_callback(
    *,
    request: Request,
    session: SessionDep,
    callback: PaymentCallbackRequest,
) -> Any:
    """
    Receive a local Apple IAP callback simulation.
    """
    return _handle_payment_callback(
        session=session,
        provider="apple",
        callback=callback,
        request=request,
    )


@router.post("/google-play", response_model=PaymentCallbackResponse)
def receive_google_play_callback(
    *,
    request: Request,
    session: SessionDep,
    callback: PaymentCallbackRequest,
) -> Any:
    """
    Receive a local Google Play callback simulation.
    """
    return _handle_payment_callback(
        session=session,
        provider="google",
        callback=callback,
        request=request,
    )
