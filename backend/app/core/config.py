import re
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import (
    AliasChoices,
    AwareDatetime,
    EmailStr,
    Field,
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
    ENVIRONMENT: Literal["local", "staging", "production"] = Field(
        default="local",
        validation_alias=AliasChoices("ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME"),
    )
    SECRET_KEY: str
    # Keep production administrator sessions bounded to one working day.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8
    # App device login is intentionally long-lived for the first mobile MVP.
    APP_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 3650
    APP_AUTH_MODE: Literal["device", "dual", "clerk"] = "device"
    CLERK_ISSUER_URL: HttpUrl | None = None
    CLERK_JWKS_URL: HttpUrl | None = None
    CLERK_AUDIENCE: str | None = None
    CLERK_SECRET_KEY: str | None = None
    CLERK_AUTHORIZED_PARTIES: list[HttpUrl] = []
    CLERK_API_BASE_URL: HttpUrl = HttpUrl("https://api.clerk.com/v1")
    ADMIN_PUBLIC_SIGNUP_ENABLED: bool = False
    ADMIN_LOGIN_MAX_FAILURES: int = 5
    ADMIN_LOGIN_WINDOW_SECONDS: int = 15 * 60
    CLOUDFLARE_ACCESS_REQUIRED: bool = False
    CLOUDFLARE_ACCESS_TEAM_DOMAIN: HttpUrl | None = None
    CLOUDFLARE_ACCESS_AUD: str | None = None
    PUBLIC_API_DOCS_ENABLED: bool = False
    APP_IMAGE_STORAGE_BACKEND: Literal["local", "r2"] = "local"
    LOCAL_UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_IMAGE_BYTES: int = 5 * 1024 * 1024
    MAX_CATALOG_IMAGE_BYTES: int = 10 * 1024 * 1024
    MAX_CATALOG_VIDEO_BYTES: int = 100 * 1024 * 1024
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
    REPLICATE_STANDARD_MODEL: str = "minimax/video-01"
    REPLICATE_ADVANCED_MODEL: str = "wan-video/wan-2.7-r2v"
    # Retained for older deployments; new video tasks use the mode-specific fields.
    REPLICATE_R2V_MODEL: str = "wan-video/wan-2.7-r2v"
    REPLICATE_ANIMATE_MODEL: str = "wan-video/wan-2.2-animate-animation"
    REPLICATE_WEBHOOK_URL: HttpUrl | None = None
    REPLICATE_WEBHOOK_SIGNING_SECRET: str | None = None
    REPLICATE_REQUEST_TIMEOUT_SECONDS: float = 30.0
    REPLICATE_WEBHOOK_TOLERANCE_SECONDS: int = 5 * 60
    REPLICATE_POC_MAX_SUBMISSIONS: int = 0
    APP_USER_DAILY_REAL_SUBMISSIONS: int = 5
    APP_USER_MAX_CONCURRENT_VIDEO_TASKS: int = 1
    APP_WAN_DAILY_GLOBAL_SUBMISSIONS: int = 30
    APP_GLOBAL_DAILY_REAL_SUBMISSIONS: int = 30
    APP_PUBLIC_REGISTRATION_ENABLED: bool = False
    # A single verified email may initialize an account without enabling commerce.
    APP_CONTROLLED_REGISTRATION_ENABLED: bool = False
    APP_CONTROLLED_REGISTRATION_EMAIL: EmailStr | None = None
    # Separate, temporary account setup only; never enables mainland commerce.
    APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED: bool = False
    APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT: AwareDatetime | None = None
    # Existing identity only: signed CN upload/generation, never payment/signup.
    APP_INTERNAL_ACCEPTANCE_ENABLED: bool = False
    APP_INTERNAL_ACCEPTANCE_SUBJECT: str | None = None
    APP_LIVE_ACCEPTANCE_ENABLED: bool = False
    APP_LIVE_ACCEPTANCE_SUBJECTS: list[str] = []
    # Existing-account payment only; disabled until a separate release approval.
    APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED: bool = False
    APP_PAYMENT_ONLY_REPLACEMENT_ENABLED: bool = False
    APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT: str | None = None
    APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID: uuid.UUID | None = None
    APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT: AwareDatetime | None = None
    # Only these catalogue slugs can be browsed/submitted in production.
    APP_LAUNCH_EFFECT_SLUGS: list[str] = ["dance-1", "romance-1"]
    # Emergency pause affects new submissions, not provider queries/callbacks.
    APP_VIDEO_SUBMISSIONS_ENABLED: bool = True
    APP_COMMERCE_TERMS_APPROVED: bool = False
    APP_REGION_ENFORCEMENT_ENABLED: bool = False
    APP_EDGE_SIGNING_SECRET: str | None = None
    APP_EDGE_SIGNATURE_TOLERANCE_SECONDS: int = 60
    PAYPAL_ENABLED: bool = False
    PAYPAL_ENVIRONMENT: Literal["sandbox", "live"] = "sandbox"
    PAYPAL_CLIENT_ID: str | None = None
    PAYPAL_CLIENT_SECRET: str | None = None
    PAYPAL_MERCHANT_ID: str | None = None
    PAYPAL_WEBHOOK_ID: str | None = None
    PAYPAL_REQUEST_TIMEOUT_SECONDS: float = 20.0
    PAYPAL_RECONCILE_INTERVAL_SECONDS: float = 60.0
    APP_SUPPORT_EMAIL: EmailStr = "li522903183@gmail.com"
    # Release gate only: retain longer variants and historical task snapshots.
    APP_EFFECT_MAX_DURATION_SECONDS: Literal[5, 10, 15] = 10
    # Preserve compatibility in development; disable the unpriced legacy
    # submission path when releasing the paid effect catalog.
    APP_LEGACY_VIDEO_TASKS_ENABLED: bool = True
    LOCAL_DEMO_ENABLED: bool = True
    LOCAL_DEMO_FFMPEG_PATH: str = "/usr/bin/ffmpeg"
    LOCAL_DEMO_TIMEOUT_SECONDS: int = 180
    PAYMENT_WEBHOOK_VERIFICATION_MODE: Literal["local", "shared_secret"] = "local"
    PAYMENT_WEBHOOK_SHARED_SECRET: str | None = None
    FRONTEND_HOST: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: list[HttpUrl] = []
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn

    @field_validator("APP_EFFECT_MAX_DURATION_SECONDS", mode="before")
    @classmethod
    def _parse_effect_duration_release_gate(cls, value: int | str) -> int:
        return int(value)

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
        if self.REPLICATE_POC_MAX_SUBMISSIONS < 0:
            raise ValueError("REPLICATE_POC_MAX_SUBMISSIONS must not be negative")
        if self.REPLICATE_WEBHOOK_TOLERANCE_SECONDS < 1:
            raise ValueError("REPLICATE_WEBHOOK_TOLERANCE_SECONDS must be positive")
        return self

    @model_validator(mode="after")
    def _validate_clerk_configuration(self) -> Self:
        if self.APP_AUTH_MODE == "device":
            return self
        required_values = {
            "CLERK_ISSUER_URL": self.CLERK_ISSUER_URL,
            "CLERK_JWKS_URL": self.CLERK_JWKS_URL,
            "CLERK_AUDIENCE": self.CLERK_AUDIENCE,
            "CLERK_SECRET_KEY": self.CLERK_SECRET_KEY,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError("Clerk authentication requires: " + ", ".join(missing))
        if not self.CLERK_AUTHORIZED_PARTIES:
            raise ValueError("Clerk authentication requires CLERK_AUTHORIZED_PARTIES")
        return self

    @model_validator(mode="after")
    def _validate_cloudflare_access_configuration(self) -> Self:
        if not self.CLOUDFLARE_ACCESS_REQUIRED:
            return self
        if not self.CLOUDFLARE_ACCESS_TEAM_DOMAIN or not self.CLOUDFLARE_ACCESS_AUD:
            raise ValueError(
                "Cloudflare Access requires CLOUDFLARE_ACCESS_TEAM_DOMAIN and "
                "CLOUDFLARE_ACCESS_AUD"
            )
        return self

    @model_validator(mode="after")
    def _validate_admin_login_configuration(self) -> Self:
        if self.ADMIN_LOGIN_MAX_FAILURES < 1:
            raise ValueError("ADMIN_LOGIN_MAX_FAILURES must be positive")
        if self.ADMIN_LOGIN_WINDOW_SECONDS < 1:
            raise ValueError("ADMIN_LOGIN_WINDOW_SECONDS must be positive")
        return self

    @model_validator(mode="after")
    def _validate_commerce_configuration(self) -> Self:
        if self.APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED and (
            self.ENVIRONMENT != "production"
            or self.APP_AUTH_MODE != "clerk"
            or not self.APP_CONTROLLED_REGISTRATION_ENABLED
            or not self.APP_CONTROLLED_REGISTRATION_EMAIL
            or not self.APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT
            or self.APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT
            > datetime.now(UTC) + timedelta(hours=8)
            or not self.APP_REGION_ENFORCEMENT_ENABLED
            or self.APP_PUBLIC_REGISTRATION_ENABLED
            or self.PAYPAL_ENABLED
            or self.APP_COMMERCE_TERMS_APPROVED
            or self.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
            or self.APP_PAYMENT_ONLY_REPLACEMENT_ENABLED
            or self.APP_INTERNAL_ACCEPTANCE_ENABLED
            or self.APP_LIVE_ACCEPTANCE_ENABLED
            or self.APP_LIVE_ACCEPTANCE_SUBJECTS
            or self.APP_VIDEO_SUBMISSIONS_ENABLED
            or self.ADMIN_PUBLIC_SIGNUP_ENABLED
            or self.LOCAL_DEMO_ENABLED
            or self.APP_LEGACY_VIDEO_TASKS_ENABLED
        ):
            raise ValueError(
                "CN account setup requires production Clerk, one controlled email, "
                "a signed region and an aware expiry within 8 hours, with all "
                "public/commerce/generation/other acceptance gates closed"
            )
        if (
            self.APP_PAYMENT_ONLY_REPLACEMENT_ENABLED
            and not self.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
        ):
            raise ValueError(
                "Replacement requires the closed payment-only acceptance mode"
            )
        if self.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED and (
            self.ENVIRONMENT != "production"
            or self.APP_AUTH_MODE != "clerk"
            or not self.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT
            or not re.fullmatch(
                r"user_[A-Za-z0-9_-]+", self.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT
            )
            or not self.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID
            or not self.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
            or self.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
            > datetime.now(UTC) + timedelta(hours=24)
            or not self.APP_REGION_ENFORCEMENT_ENABLED
            or not self.PAYPAL_ENABLED
            or not self.APP_COMMERCE_TERMS_APPROVED
            or self.APP_PUBLIC_REGISTRATION_ENABLED
            or self.APP_CONTROLLED_REGISTRATION_ENABLED
            or self.APP_INTERNAL_ACCEPTANCE_ENABLED
            or self.APP_LIVE_ACCEPTANCE_ENABLED
            or self.APP_LIVE_ACCEPTANCE_SUBJECTS
            or self.APP_VIDEO_SUBMISSIONS_ENABLED
            or self.ADMIN_PUBLIC_SIGNUP_ENABLED
            or self.LOCAL_DEMO_ENABLED
            or self.APP_LEGACY_VIDEO_TASKS_ENABLED
        ):
            raise ValueError(
                "Payment-only acceptance requires production Clerk, an existing exact user/subject, an aware expiry within 24 hours, signed regions, live payments and terms, with registration, other acceptance modes and new generation closed"
            )
        if self.APP_INTERNAL_ACCEPTANCE_ENABLED and (
            self.ENVIRONMENT != "production"
            or self.APP_AUTH_MODE != "clerk"
            or not self.APP_INTERNAL_ACCEPTANCE_SUBJECT
            or not re.fullmatch(
                r"user_[A-Za-z0-9_-]+", self.APP_INTERNAL_ACCEPTANCE_SUBJECT
            )
            or not self.APP_REGION_ENFORCEMENT_ENABLED
            or self.APP_PUBLIC_REGISTRATION_ENABLED
            or self.PAYPAL_ENABLED
            or self.APP_LIVE_ACCEPTANCE_ENABLED
            or self.APP_COMMERCE_TERMS_APPROVED
            or self.ADMIN_PUBLIC_SIGNUP_ENABLED
            or self.LOCAL_DEMO_ENABLED
            or self.APP_LEGACY_VIDEO_TASKS_ENABLED
        ):
            raise ValueError(
                "Internal acceptance requires production Clerk, one exact subject, signed regions, real priced generation and closed registration, payments, Live acceptance, terms and administrator signup"
            )
        if self.APP_CONTROLLED_REGISTRATION_ENABLED and (
            self.ENVIRONMENT != "production"
            or self.APP_AUTH_MODE != "clerk"
            or not self.APP_CONTROLLED_REGISTRATION_EMAIL
            or not self.APP_REGION_ENFORCEMENT_ENABLED
            or self.APP_PUBLIC_REGISTRATION_ENABLED
            or self.PAYPAL_ENABLED
            or self.APP_LIVE_ACCEPTANCE_ENABLED
            or self.APP_COMMERCE_TERMS_APPROVED
            or self.ADMIN_PUBLIC_SIGNUP_ENABLED
        ):
            raise ValueError(
                "Controlled registration requires production Clerk, one email, signed regions and closed public registration, payments, Live acceptance, terms and administrator signup"
            )
        if self.APP_LIVE_ACCEPTANCE_ENABLED:
            if (
                self.ENVIRONMENT != "production"
                or not self.PAYPAL_ENABLED
                or not self.APP_LIVE_ACCEPTANCE_SUBJECTS
                or self.APP_PUBLIC_REGISTRATION_ENABLED
            ):
                raise ValueError(
                    "Live acceptance requires production, enabled live payments, a nonempty subject allowlist and closed public registration"
                )
        if any(
            not subject.strip() or subject != subject.strip()
            for subject in self.APP_LIVE_ACCEPTANCE_SUBJECTS
        ):
            raise ValueError(
                "Acceptance subjects must be nonempty exact Clerk identities"
            )
        if self.ENVIRONMENT == "production" and not self.APP_LAUNCH_EFFECT_SLUGS:
            raise ValueError(
                "Production must explicitly select a nonempty launch catalogue"
            )
        if self.APP_GLOBAL_DAILY_REAL_SUBMISSIONS < 1:
            raise ValueError("APP_GLOBAL_DAILY_REAL_SUBMISSIONS must be positive")
        if self.APP_EDGE_SIGNATURE_TOLERANCE_SECONDS < 1:
            raise ValueError("APP_EDGE_SIGNATURE_TOLERANCE_SECONDS must be positive")
        if self.APP_REGION_ENFORCEMENT_ENABLED and (
            not self.APP_EDGE_SIGNING_SECRET or len(self.APP_EDGE_SIGNING_SECRET) < 32
        ):
            raise ValueError("Region enforcement requires a 32-character edge secret")
        if (
            self.PAYPAL_REQUEST_TIMEOUT_SECONDS <= 0
            or self.PAYPAL_RECONCILE_INTERVAL_SECONDS <= 0
        ):
            raise ValueError("PayPal timeouts and reconcile interval must be positive")
        if self.PAYPAL_ENABLED:
            required = (
                self.PAYPAL_CLIENT_ID,
                self.PAYPAL_CLIENT_SECRET,
                self.PAYPAL_MERCHANT_ID,
                self.PAYPAL_WEBHOOK_ID,
            )
            if not all(required):
                raise ValueError(
                    "PayPal requires client ID, secret, merchant ID and webhook ID"
                )
        if self.ENVIRONMENT == "production" and (
            self.PAYPAL_ENABLED or self.APP_PUBLIC_REGISTRATION_ENABLED
        ):
            if not self.APP_COMMERCE_TERMS_APPROVED:
                raise ValueError(
                    "Public commerce requires confirmed merchant identity and terms"
                )
            if self.APP_AUTH_MODE != "clerk":
                raise ValueError(
                    "Public commerce requires verified Clerk authentication"
                )
            if self.ADMIN_PUBLIC_SIGNUP_ENABLED:
                raise ValueError("Public commerce must not enable administrator signup")
            if (
                self.PAYPAL_ENVIRONMENT != "live"
                or not self.APP_REGION_ENFORCEMENT_ENABLED
            ):
                raise ValueError(
                    "Public commerce requires live PayPal and signed region enforcement"
                )
            if self.APP_PUBLIC_REGISTRATION_ENABLED and not self.PAYPAL_ENABLED:
                raise ValueError(
                    "Public registration and live recharge must launch together"
                )
            if self.LOCAL_DEMO_ENABLED or self.APP_LEGACY_VIDEO_TASKS_ENABLED:
                raise ValueError(
                    "Public commerce requires real, priced generation only"
                )
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
        if self.APP_USER_DAILY_REAL_SUBMISSIONS < 1:
            raise ValueError("APP_USER_DAILY_REAL_SUBMISSIONS must be positive")
        if self.APP_USER_MAX_CONCURRENT_VIDEO_TASKS < 1:
            raise ValueError("APP_USER_MAX_CONCURRENT_VIDEO_TASKS must be positive")
        if self.APP_WAN_DAILY_GLOBAL_SUBMISSIONS < 1:
            raise ValueError("APP_WAN_DAILY_GLOBAL_SUBMISSIONS must be positive")
        if self.MAX_CATALOG_IMAGE_BYTES < 1:
            raise ValueError("MAX_CATALOG_IMAGE_BYTES must be positive")
        if self.MAX_CATALOG_VIDEO_BYTES < 1:
            raise ValueError("MAX_CATALOG_VIDEO_BYTES must be positive")
        if not self.LOCAL_DEMO_FFMPEG_PATH.strip():
            raise ValueError("LOCAL_DEMO_FFMPEG_PATH must not be empty")
        if self.LOCAL_DEMO_TIMEOUT_SECONDS < 1:
            raise ValueError("LOCAL_DEMO_TIMEOUT_SECONDS must be positive")
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
