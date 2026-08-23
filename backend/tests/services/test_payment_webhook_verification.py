import pytest

from app.core.config import settings
from app.services.payment_webhook_verification import (
    PAYMENT_WEBHOOK_SHARED_SECRET_HEADER,
    PaymentWebhookVerificationError,
    verify_payment_webhook,
)


def test_payment_webhook_local_mode_allows_missing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "local")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", None)

    verify_payment_webhook(provider="apple", headers={})


def test_payment_webhook_shared_secret_mode_rejects_missing_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "shared_secret")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", None)

    with pytest.raises(PaymentWebhookVerificationError) as exc_info:
        verify_payment_webhook(provider="apple", headers={})

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Payment webhook verification is not configured"


def test_payment_webhook_shared_secret_mode_rejects_invalid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "shared_secret")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", "expected-secret")

    with pytest.raises(PaymentWebhookVerificationError) as exc_info:
        verify_payment_webhook(
            provider="google",
            headers={PAYMENT_WEBHOOK_SHARED_SECRET_HEADER: "wrong-secret"},
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid payment webhook signature"


def test_payment_webhook_shared_secret_mode_accepts_valid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "shared_secret")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", "expected-secret")

    verify_payment_webhook(
        provider="google",
        headers={PAYMENT_WEBHOOK_SHARED_SECRET_HEADER: "expected-secret"},
    )
