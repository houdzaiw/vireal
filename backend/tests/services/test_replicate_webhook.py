import base64
import hashlib
import hmac

import pytest

from app.core.config import settings
from app.services.replicate_webhook import (
    ReplicateWebhookVerificationError,
    verify_replicate_webhook,
)


def _signature(secret: str, webhook_id: str, timestamp: int, body: bytes) -> str:
    encoded_key = secret.removeprefix("whsec_")
    encoded_key += "=" * (-len(encoded_key) % 4)
    signing_key = base64.b64decode(encoded_key)
    signed = f"{webhook_id}.{timestamp}.".encode() + body
    digest = hmac.new(signing_key, signed, hashlib.sha256).digest()
    return f"v1,{base64.b64encode(digest).decode()}"


def test_verify_replicate_webhook_accepts_valid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = f"whsec_{base64.b64encode(b'test-signing-key').decode().rstrip('=')}"
    body = b'{"id":"prediction-1","status":"succeeded"}'
    timestamp = 1_800_000_000
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_SIGNING_SECRET", secret)

    webhook_id = verify_replicate_webhook(
        raw_body=body,
        headers={
            "webhook-id": "event-1",
            "webhook-timestamp": str(timestamp),
            "webhook-signature": _signature(secret, "event-1", timestamp, body),
        },
        now=timestamp,
    )

    assert webhook_id == "event-1"


def test_verify_replicate_webhook_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = f"whsec_{base64.b64encode(b'test-signing-key').decode().rstrip('=')}"
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_SIGNING_SECRET", secret)

    with pytest.raises(ReplicateWebhookVerificationError, match="Invalid"):
        verify_replicate_webhook(
            raw_body=b"{}",
            headers={
                "webhook-id": "event-1",
                "webhook-timestamp": "1800000000",
                "webhook-signature": "v1,invalid",
            },
            now=1_800_000_000,
        )


def test_verify_replicate_webhook_rejects_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = f"whsec_{base64.b64encode(b'test-signing-key').decode().rstrip('=')}"
    body = b"{}"
    timestamp = 1_800_000_000
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_SIGNING_SECRET", secret)

    with pytest.raises(ReplicateWebhookVerificationError, match="Expired"):
        verify_replicate_webhook(
            raw_body=body,
            headers={
                "webhook-id": "event-1",
                "webhook-timestamp": str(timestamp),
                "webhook-signature": _signature(secret, "event-1", timestamp, body),
            },
            now=timestamp + settings.REPLICATE_WEBHOOK_TOLERANCE_SECONDS + 1,
        )
