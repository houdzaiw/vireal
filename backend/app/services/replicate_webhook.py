import base64
import binascii
import hashlib
import hmac
import time
from collections.abc import Mapping

from app.core.config import settings


class ReplicateWebhookVerificationError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 401) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def verify_replicate_webhook(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    now: int | None = None,
) -> str:
    webhook_id = headers.get("webhook-id")
    timestamp_text = headers.get("webhook-timestamp")
    signature_header = headers.get("webhook-signature")
    if not webhook_id or not timestamp_text or not signature_header:
        raise ReplicateWebhookVerificationError("Missing Replicate webhook headers")

    try:
        timestamp = int(timestamp_text)
    except ValueError as exc:
        raise ReplicateWebhookVerificationError(
            "Invalid Replicate webhook timestamp"
        ) from exc

    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp) > settings.REPLICATE_WEBHOOK_TOLERANCE_SECONDS:
        raise ReplicateWebhookVerificationError("Expired Replicate webhook")

    secret = settings.REPLICATE_WEBHOOK_SIGNING_SECRET
    if not secret:
        raise ReplicateWebhookVerificationError(
            "Replicate webhook verification is not configured",
            status_code=503,
        )
    encoded_key = secret.removeprefix("whsec_")
    encoded_key += "=" * (-len(encoded_key) % 4)
    try:
        signing_key = base64.b64decode(encoded_key, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReplicateWebhookVerificationError(
            "Invalid Replicate webhook signing secret",
            status_code=503,
        ) from exc

    signed_content = (
        webhook_id.encode() + b"." + timestamp_text.encode() + b"." + raw_body
    )
    expected = base64.b64encode(
        hmac.new(signing_key, signed_content, hashlib.sha256).digest()
    ).decode()
    signatures = [
        item.split(",", 1)[1]
        for item in signature_header.split()
        if item.startswith("v1,") and "," in item
    ]
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise ReplicateWebhookVerificationError("Invalid Replicate webhook signature")
    return webhook_id
