from collections.abc import Mapping
from hmac import compare_digest
from typing import Literal

from app.core.config import settings

PAYMENT_WEBHOOK_SHARED_SECRET_HEADER = "x-app-payment-webhook-secret"


class PaymentWebhookVerificationError(Exception):
    def __init__(self, detail: str, status_code: int = 403) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def verify_payment_webhook(
    *,
    provider: Literal["apple", "google"],
    headers: Mapping[str, str],
) -> None:
    if settings.PAYMENT_WEBHOOK_VERIFICATION_MODE == "local":
        return

    if settings.PAYMENT_WEBHOOK_VERIFICATION_MODE == "shared_secret":
        _verify_shared_secret(headers=headers)
        return

    raise PaymentWebhookVerificationError(
        f"Unsupported payment webhook verification mode for {provider}",
        status_code=500,
    )


def _verify_shared_secret(*, headers: Mapping[str, str]) -> None:
    expected_secret = settings.PAYMENT_WEBHOOK_SHARED_SECRET
    if not expected_secret:
        raise PaymentWebhookVerificationError(
            "Payment webhook verification is not configured",
            status_code=500,
        )

    provided_secret = headers.get(PAYMENT_WEBHOOK_SHARED_SECRET_HEADER)
    if not provided_secret or not compare_digest(provided_secret, expected_secret):
        raise PaymentWebhookVerificationError("Invalid payment webhook signature")
