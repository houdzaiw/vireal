from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "SECRET_KEY": "test-secret-key-not-default",
        "PROJECT_NAME": "Vireal test",
        "DATABASE_URL": "postgresql://postgres:safe-password@localhost/vireal",
        "FIRST_SUPERUSER": "admin@example.com",
        "FIRST_SUPERUSER_PASSWORD": "safe-password",
        "FASTAPI_ENV": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_is_normalized_and_email_defaults_are_computed() -> None:
    configured = _settings(
        DATABASE_URL="postgres://postgres:safe-password@localhost/vireal",
        SMTP_HOST="smtp.example.com",
        EMAILS_FROM_EMAIL="hello@example.com",
    )
    assert str(configured.DATABASE_URL).startswith("postgresql+psycopg://")
    assert configured.EMAILS_FROM_NAME == "Vireal test"
    assert configured.emails_enabled is True
    already_normalized = _settings(
        DATABASE_URL=("postgresql+psycopg://postgres:safe-password@localhost/vireal")
    )
    assert str(already_normalized.DATABASE_URL).startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"REPLICATE_WEBHOOK_URL": "http://example.com/hook"}, "must use HTTPS"),
        (
            {"REPLICATE_WEBHOOK_SIGNING_SECRET": "invalid"},
            "must start with whsec_",
        ),
        ({"APP_IMAGE_STORAGE_BACKEND": "r2"}, "R2 storage requires"),
        (
            {
                "APP_IMAGE_STORAGE_BACKEND": "r2",
                "R2_ENDPOINT_URL": "http://account.r2.cloudflarestorage.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
            },
            "R2_ENDPOINT_URL must use HTTPS",
        ),
        (
            {
                "APP_IMAGE_STORAGE_BACKEND": "r2",
                "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_OBJECT_PREFIX": "/",
            },
            "R2_OBJECT_PREFIX must not be empty",
        ),
        (
            {
                "APP_IMAGE_STORAGE_BACKEND": "r2",
                "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_DOWNLOAD_URL_EXPIRE_SECONDS": 0,
            },
            "R2_DOWNLOAD_URL_EXPIRE_SECONDS",
        ),
        (
            {
                "APP_IMAGE_STORAGE_BACKEND": "r2",
                "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_REPLICATE_URL_EXPIRE_SECONDS": 604801,
            },
            "R2_REPLICATE_URL_EXPIRE_SECONDS",
        ),
        (
            {
                "APP_IMAGE_STORAGE_BACKEND": "r2",
                "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS": 0,
            },
            "R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS",
        ),
        ({"REPLICATE_ENABLED": True}, "video generation requires"),
        (
            {
                "APP_AUTH_MODE": "clerk",
                "CLERK_ISSUER_URL": "https://clerk.example.com",
            },
            "Clerk authentication requires",
        ),
        (
            {
                "CLOUDFLARE_ACCESS_REQUIRED": True,
                "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
            },
            "Cloudflare Access requires",
        ),
        ({"ADMIN_LOGIN_MAX_FAILURES": 0}, "MAX_FAILURES must be positive"),
        ({"ADMIN_LOGIN_WINDOW_SECONDS": 0}, "WINDOW_SECONDS must be positive"),
        ({"APP_MEDIA_RETENTION_HOURS": 0}, "RETENTION_HOURS must be positive"),
        ({"MAX_GENERATED_VIDEO_BYTES": 0}, "VIDEO_BYTES must be positive"),
        ({"VIDEO_WORKER_POLL_SECONDS": 0}, "POLL_SECONDS must be positive"),
        ({"VIDEO_WORKER_MAX_ATTEMPTS": 0}, "MAX_ATTEMPTS must be positive"),
        ({"VIDEO_CLEANUP_INTERVAL_SECONDS": 0}, "INTERVAL_SECONDS must be positive"),
        ({"APP_USER_DAILY_REAL_SUBMISSIONS": 0}, "SUBMISSIONS must be positive"),
        ({"APP_USER_MAX_CONCURRENT_VIDEO_TASKS": 0}, "TASKS must be positive"),
        ({"APP_WAN_DAILY_GLOBAL_SUBMISSIONS": 0}, "SUBMISSIONS must be positive"),
        ({"MAX_CATALOG_IMAGE_BYTES": 0}, "IMAGE_BYTES must be positive"),
        ({"MAX_CATALOG_VIDEO_BYTES": 0}, "VIDEO_BYTES must be positive"),
        ({"LOCAL_DEMO_FFMPEG_PATH": " "}, "FFMPEG_PATH must not be empty"),
        ({"LOCAL_DEMO_TIMEOUT_SECONDS": 0}, "TIMEOUT_SECONDS must be positive"),
        (
            {"PAYMENT_WEBHOOK_VERIFICATION_MODE": "shared_secret"},
            "PAYMENT_WEBHOOK_SHARED_SECRET is required",
        ),
    ],
)
def test_invalid_production_settings_are_rejected(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**overrides)


def test_complete_external_service_configuration_is_accepted() -> None:
    configured = _settings(
        APP_IMAGE_STORAGE_BACKEND="r2",
        R2_ENDPOINT_URL="https://account.r2.cloudflarestorage.com",
        R2_ACCESS_KEY_ID="key",
        R2_SECRET_ACCESS_KEY="secret",
        R2_BUCKET_NAME="bucket",
        REPLICATE_ENABLED=True,
        REPLICATE_API_TOKEN="token",
        REPLICATE_WEBHOOK_URL="https://api.example.com/webhook",
        REPLICATE_WEBHOOK_SIGNING_SECRET="whsec_test",
        APP_AUTH_MODE="clerk",
        CLERK_ISSUER_URL="https://clerk.example.com",
        CLERK_JWKS_URL="https://clerk.example.com/.well-known/jwks.json",
        CLERK_AUDIENCE="vireal",
        CLERK_SECRET_KEY="sk_test",
        CLERK_AUTHORIZED_PARTIES=["https://app.example.com"],
        CLOUDFLARE_ACCESS_REQUIRED=True,
        CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://team.cloudflareaccess.com",
        CLOUDFLARE_ACCESS_AUD="audience",
        PAYMENT_WEBHOOK_VERIFICATION_MODE="shared_secret",
        PAYMENT_WEBHOOK_SHARED_SECRET="payment-secret",
    )
    assert configured.REPLICATE_ENABLED is True
    assert configured.APP_AUTH_MODE == "clerk"


def test_cross_service_configuration_guards() -> None:
    replicate = {
        "REPLICATE_ENABLED": True,
        "REPLICATE_API_TOKEN": "token",
        "REPLICATE_WEBHOOK_URL": "https://api.example.com/webhook",
        "REPLICATE_WEBHOOK_SIGNING_SECRET": "whsec_test",
    }
    r2 = {
        "APP_IMAGE_STORAGE_BACKEND": "r2",
        "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        "R2_ACCESS_KEY_ID": "key",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET_NAME": "bucket",
    }
    with pytest.raises(ValidationError, match="requires Cloudflare R2"):
        _settings(**replicate)
    with pytest.raises(ValidationError, match="must not be negative"):
        _settings(**r2, **replicate, REPLICATE_POC_MAX_SUBMISSIONS=-1)
    with pytest.raises(ValidationError, match="TOLERANCE_SECONDS must be positive"):
        _settings(**r2, **replicate, REPLICATE_WEBHOOK_TOLERANCE_SECONDS=0)
    with pytest.raises(ValidationError, match="CLERK_AUTHORIZED_PARTIES"):
        _settings(
            APP_AUTH_MODE="clerk",
            CLERK_ISSUER_URL="https://clerk.example.com",
            CLERK_JWKS_URL="https://clerk.example.com/.well-known/jwks.json",
            CLERK_AUDIENCE="vireal",
            CLERK_SECRET_KEY="sk_test",
        )
    with pytest.raises(ValidationError, match='value of SECRET_KEY is "changethis"'):
        _settings(SECRET_KEY="changethis")
