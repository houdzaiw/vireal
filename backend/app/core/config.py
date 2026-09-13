import warnings
from typing import Literal, Self

from pydantic import (
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    # App device login is intentionally long-lived for the first mobile MVP.
    APP_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 3650
    APP_IMAGE_STORAGE_BACKEND: Literal["local", "r2"] = "local"
    LOCAL_UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_IMAGE_BYTES: int = 5 * 1024 * 1024
    APP_GENERATION_PROVIDER: Literal["local", "ark"] = "local"
    APP_GENERATION_LOCAL_DELAY_SECONDS: float = 1.5
    APP_PUBLIC_BASE_URL: str | None = None
    ARK_API_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    ARK_API_KEY: str | None = None
    ARK_SEEDANCE_MODEL: str = "doubao-seedance-2-0-260128"
    ARK_SEEDREAM_MODEL: str = "doubao-seedream-5-0-260128"
    ARK_VIDEO_RESOLUTION: str = "720p"
    ARK_VIDEO_POLL_INTERVAL_SECONDS: float = 5.0
    ARK_VIDEO_POLL_TIMEOUT_SECONDS: float = 600.0
    R2_ENDPOINT_URL: HttpUrl | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str | None = None
    R2_OBJECT_PREFIX: str = "vireal"
    R2_DOWNLOAD_URL_EXPIRE_SECONDS: int = 5 * 60
    R2_REPLICATE_URL_EXPIRE_SECONDS: int = 30 * 60
    R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS: int = 5 * 60
    APP_MEDIA_RETENTION_HOURS: int = 24
    MAX_GENERATED_VIDEO_BYTES: int = 250 * 1024 * 1024
    VIDEO_WORKER_POLL_SECONDS: float = 2.0
    VIDEO_WORKER_MAX_ATTEMPTS: int = 5
    VIDEO_CLEANUP_INTERVAL_SECONDS: float = 60.0
    REPLICATE_ENABLED: bool = False
    REPLICATE_API_TOKEN: str | None = None
    REPLICATE_R2V_MODEL: str = "wan-video/wan-2.7-r2v"
    REPLICATE_ANIMATE_MODEL: str = "wan-video/wan-2.2-animate-animation"
    REPLICATE_WEBHOOK_URL: HttpUrl | None = None
    REPLICATE_WEBHOOK_SIGNING_SECRET: str | None = None
    REPLICATE_REQUEST_TIMEOUT_SECONDS: float = 30.0
    REPLICATE_WEBHOOK_TOLERANCE_SECONDS: int = 5 * 60
    REPLICATE_POC_MAX_SUBMISSIONS: int = 0
    PAYMENT_WEBHOOK_VERIFICATION_MODE: Literal["local", "shared_secret"] = "local"
    PAYMENT_WEBHOOK_SHARED_SECRET: str | None = None
    FRONTEND_HOST: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: list[HttpUrl] = []
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    @field_validator("REPLICATE_WEBHOOK_URL")
    @classmethod
    def _require_https_replicate_webhook(
        cls,
        value: HttpUrl | None,
    ) -> HttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("REPLICATE_WEBHOOK_URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def _validate_r2_configuration(self) -> Self:
        if self.APP_IMAGE_STORAGE_BACKEND != "r2":
            return self

        required_values = {
            "R2_ENDPOINT_URL": self.R2_ENDPOINT_URL,
            "R2_ACCESS_KEY_ID": self.R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": self.R2_SECRET_ACCESS_KEY,
            "R2_BUCKET_NAME": self.R2_BUCKET_NAME,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError("Cloudflare R2 storage requires: " + ", ".join(missing))
        if self.R2_ENDPOINT_URL and self.R2_ENDPOINT_URL.scheme != "https":
            raise ValueError("R2_ENDPOINT_URL must use HTTPS")
        if not self.R2_OBJECT_PREFIX.strip("/"):
            raise ValueError("R2_OBJECT_PREFIX must not be empty")
        if not 1 <= self.R2_DOWNLOAD_URL_EXPIRE_SECONDS <= 604_800:
            raise ValueError(
                "R2_DOWNLOAD_URL_EXPIRE_SECONDS must be between 1 and 604800"
            )
        if not 1 <= self.R2_REPLICATE_URL_EXPIRE_SECONDS <= 604_800:
            raise ValueError(
                "R2_REPLICATE_URL_EXPIRE_SECONDS must be between 1 and 604800"
            )
        if not 1 <= self.R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS <= 604_800:
            raise ValueError(
                "R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS must be between 1 and 604800"
            )
        return self

    @model_validator(mode="after")
    def _validate_replicate_configuration(self) -> Self:
        if not self.REPLICATE_ENABLED:
            return self
        required_values = {
            "REPLICATE_API_TOKEN": self.REPLICATE_API_TOKEN,
            "REPLICATE_WEBHOOK_URL": self.REPLICATE_WEBHOOK_URL,
            "REPLICATE_WEBHOOK_SIGNING_SECRET": self.REPLICATE_WEBHOOK_SIGNING_SECRET,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError(
                "Replicate video generation requires: " + ", ".join(missing)
            )
        if self.APP_IMAGE_STORAGE_BACKEND != "r2":
            raise ValueError("Replicate video generation requires Cloudflare R2")
        if self.REPLICATE_POC_MAX_SUBMISSIONS < 1:
            raise ValueError("REPLICATE_POC_MAX_SUBMISSIONS must be at least 1")
        if self.REPLICATE_WEBHOOK_TOLERANCE_SECONDS < 1:
            raise ValueError("REPLICATE_WEBHOOK_TOLERANCE_SECONDS must be positive")
        return self

    @model_validator(mode="after")
    def _validate_media_worker_configuration(self) -> Self:
        if self.APP_MEDIA_RETENTION_HOURS < 1:
            raise ValueError("APP_MEDIA_RETENTION_HOURS must be positive")
        if self.MAX_GENERATED_VIDEO_BYTES < 1:
            raise ValueError("MAX_GENERATED_VIDEO_BYTES must be positive")
        if self.VIDEO_WORKER_POLL_SECONDS <= 0:
            raise ValueError("VIDEO_WORKER_POLL_SECONDS must be positive")
        if self.VIDEO_WORKER_MAX_ATTEMPTS < 1:
            raise ValueError("VIDEO_WORKER_MAX_ATTEMPTS must be positive")
        if self.VIDEO_CLEANUP_INTERVAL_SECONDS <= 0:
            raise ValueError("VIDEO_CLEANUP_INTERVAL_SECONDS must be positive")
        return self

    @field_validator("REPLICATE_WEBHOOK_SIGNING_SECRET")
    @classmethod
    def _validate_replicate_webhook_signing_secret(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.startswith("whsec_"):
            raise ValueError("REPLICATE_WEBHOOK_SIGNING_SECRET must start with whsec_")
        return value

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )
        if self.PAYMENT_WEBHOOK_SHARED_SECRET:
            self._check_default_secret(
                "PAYMENT_WEBHOOK_SHARED_SECRET", self.PAYMENT_WEBHOOK_SHARED_SECRET
            )
        if (
            self.PAYMENT_WEBHOOK_VERIFICATION_MODE == "shared_secret"
            and not self.PAYMENT_WEBHOOK_SHARED_SECRET
        ):
            raise ValueError(
                "PAYMENT_WEBHOOK_SHARED_SECRET is required when "
                'PAYMENT_WEBHOOK_VERIFICATION_MODE is "shared_secret"'
            )

        return self


settings = Settings()  # type: ignore
