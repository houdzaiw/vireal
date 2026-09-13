import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
)


@dataclass(frozen=True)
class StoredImage:
    url: str
    object_key: str
    content_type: str
    size: int


@dataclass(frozen=True)
class ReadImage:
    content: bytes
    content_type: str


@dataclass(frozen=True)
class StoredVideo:
    object_key: str
    content_type: str
    size: int


class ImageStorageError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ImageStorage(Protocol):
    def store_app_image(
        self,
        *,
        app_user_id: uuid.UUID,
        content: bytes,
        uploaded_content_type: str | None,
    ) -> StoredImage:
        """Store an App image and return the URL visible to API clients."""

    def create_read_url(self, url: str, *, expires_in: int) -> str:
        """Return a URL that can read one previously stored App image."""

    def read_app_image(self, url: str) -> ReadImage:
        """Read one private App image through the backend."""

    def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
        """Return a short-lived URL for one managed object key."""

    def store_video_file(
        self,
        *,
        app_user_id: uuid.UUID,
        task_id: uuid.UUID,
        file_path: Path,
        content_type: str,
    ) -> StoredVideo:
        """Store one generated video without loading it fully into memory."""

    def delete_object(self, object_key: str) -> None:
        """Delete one managed object if it exists."""


class S3ObjectClient(Protocol):
    def put_object(self, **kwargs: Any) -> Any: ...

    def get_object(self, **kwargs: Any) -> Any: ...

    def upload_fileobj(
        self, Fileobj: Any, Bucket: str, Key: str, **kwargs: Any
    ) -> Any: ...

    def delete_object(self, **kwargs: Any) -> Any: ...

    def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str: ...


def get_local_upload_root() -> Path:
    root = Path(settings.LOCAL_UPLOAD_DIR)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def detect_image_type(content: bytes) -> tuple[str, str] | None:
    for signature, content_type, extension in IMAGE_SIGNATURES:
        if content.startswith(signature):
            return content_type, extension
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def validate_image_upload(
    *,
    content: bytes,
    uploaded_content_type: str | None,
) -> tuple[str, str]:
    if len(content) > settings.MAX_UPLOAD_IMAGE_BYTES:
        raise ImageStorageError("Image is too large", status_code=413)

    detected = detect_image_type(content)
    if detected is None:
        raise ImageStorageError("File must be an image")

    if uploaded_content_type and not uploaded_content_type.startswith("image/"):
        raise ImageStorageError("File must be an image")

    return detected


class LocalImageStorage:
    def __init__(self, upload_root: Path | None = None) -> None:
        self.upload_root = upload_root or get_local_upload_root()

    def store_app_image(
        self,
        *,
        app_user_id: uuid.UUID,
        content: bytes,
        uploaded_content_type: str | None,
    ) -> StoredImage:
        content_type, extension = validate_image_upload(
            content=content,
            uploaded_content_type=uploaded_content_type,
        )
        image_dir = self.upload_root / "images" / str(app_user_id)
        image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}{extension}"
        object_key = f"images/{app_user_id}/{filename}"
        image_path = self.upload_root / object_key
        image_path.write_bytes(content)

        return StoredImage(
            url=f"/uploads/{object_key}",
            object_key=object_key,
            content_type=content_type,
            size=len(content),
        )

    def create_read_url(self, url: str, *, expires_in: int) -> str:
        del expires_in
        if not url.startswith("/uploads/images/"):
            raise ImageStorageError("Image URL is not managed by local storage")
        return url

    def read_app_image(self, url: str) -> ReadImage:
        if not url.startswith("/uploads/images/"):
            raise ImageStorageError("Image URL is not managed by local storage")
        relative_path = url.removeprefix("/uploads/")
        upload_root = self.upload_root.resolve()
        image_path = (upload_root / relative_path).resolve()
        if upload_root not in image_path.parents:
            raise ImageStorageError("Image URL is invalid")
        try:
            content = image_path.read_bytes()
        except FileNotFoundError as exc:
            raise ImageStorageError("Image not found", status_code=404) from exc
        detected = detect_image_type(content)
        if detected is None:
            raise ImageStorageError("Stored file is not a supported image")
        return ReadImage(content=content, content_type=detected[0])

    def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
        del expires_in
        self._object_path(object_key)
        return f"/uploads/{object_key}"

    def store_video_file(
        self,
        *,
        app_user_id: uuid.UUID,
        task_id: uuid.UUID,
        file_path: Path,
        content_type: str,
    ) -> StoredVideo:
        object_key = f"videos/{app_user_id}/{task_id}.mp4"
        target = self._object_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file_path, target)
        return StoredVideo(
            object_key=object_key,
            content_type=content_type,
            size=target.stat().st_size,
        )

    def delete_object(self, object_key: str) -> None:
        path = self._object_path(object_key)
        path.unlink(missing_ok=True)

    def _object_path(self, object_key: str) -> Path:
        upload_root = self.upload_root.resolve()
        object_path = (upload_root / object_key).resolve()
        if upload_root not in object_path.parents:
            raise ImageStorageError("Object key is invalid")
        return object_path


class R2ImageStorage:
    def __init__(
        self,
        *,
        client: S3ObjectClient | None = None,
        bucket_name: str | None = None,
        object_prefix: str | None = None,
    ) -> None:
        resolved_bucket_name = bucket_name or settings.R2_BUCKET_NAME
        if not resolved_bucket_name:
            raise RuntimeError("R2_BUCKET_NAME is required")
        self.bucket_name = resolved_bucket_name
        self.object_prefix = (
            object_prefix if object_prefix is not None else settings.R2_OBJECT_PREFIX
        ).strip("/")
        if not self.object_prefix:
            raise RuntimeError("R2_OBJECT_PREFIX must not be empty")
        self.client = client or _create_r2_client()

    def store_app_image(
        self,
        *,
        app_user_id: uuid.UUID,
        content: bytes,
        uploaded_content_type: str | None,
    ) -> StoredImage:
        content_type, extension = validate_image_upload(
            content=content,
            uploaded_content_type=uploaded_content_type,
        )
        filename = f"{uuid.uuid4()}{extension}"
        object_key = self._object_key(app_user_id=app_user_id, filename=filename)
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=content,
                ContentLength=len(content),
                ContentType=content_type,
                CacheControl="private, no-store",
                Metadata={"app-user-id": str(app_user_id)},
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception(
                "Cloudflare R2 put_object failed",
                extra={"bucket": self.bucket_name, "key": object_key},
            )
            raise ImageStorageError(
                "Unable to store image in Cloudflare R2",
                status_code=502,
            ) from exc

        return StoredImage(
            url=build_r2_app_image_url(
                app_user_id=app_user_id,
                filename=filename,
            ),
            object_key=object_key,
            content_type=content_type,
            size=len(content),
        )

    def create_read_url(self, url: str, *, expires_in: int) -> str:
        image_location = parse_r2_app_image_url(url)
        if image_location is None:
            raise ImageStorageError("Image URL is not managed by Cloudflare R2")
        app_user_id, filename = image_location
        object_key = self._object_key(app_user_id=app_user_id, filename=filename)
        return self.create_object_read_url(object_key, expires_in=expires_in)

    def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
        self._validate_object_key(object_key)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception(
                "Cloudflare R2 generate_presigned_url failed",
                extra={"bucket": self.bucket_name},
            )
            raise ImageStorageError(
                "Unable to create Cloudflare R2 read URL",
                status_code=502,
            ) from exc

    def read_app_image(self, url: str) -> ReadImage:
        image_location = parse_r2_app_image_url(url)
        if image_location is None:
            raise ImageStorageError("Image URL is not managed by Cloudflare R2")
        app_user_id, filename = image_location
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=self._object_key(
                    app_user_id=app_user_id,
                    filename=filename,
                ),
            )
            content = response["Body"].read()
            content_type = response.get("ContentType") or "application/octet-stream"
        except (BotoCoreError, ClientError, KeyError) as exc:
            logger.exception(
                "Cloudflare R2 get_object failed",
                extra={
                    "bucket": self.bucket_name,
                    "key": self._object_key(
                        app_user_id=app_user_id,
                        filename=filename,
                    ),
                },
            )
            raise ImageStorageError(
                "Unable to read image from Cloudflare R2",
                status_code=502,
            ) from exc
        return ReadImage(content=content, content_type=content_type)

    def store_video_file(
        self,
        *,
        app_user_id: uuid.UUID,
        task_id: uuid.UUID,
        file_path: Path,
        content_type: str,
    ) -> StoredVideo:
        object_key = f"{self.object_prefix}/videos/{app_user_id}/{task_id}.mp4"
        size = file_path.stat().st_size
        try:
            with file_path.open("rb") as video_file:
                self.client.upload_fileobj(
                    video_file,
                    self.bucket_name,
                    object_key,
                    ExtraArgs={
                        "ContentType": content_type,
                        "CacheControl": "private, no-store",
                        "Metadata": {
                            "app-user-id": str(app_user_id),
                            "video-task-id": str(task_id),
                        },
                    },
                )
        except (BotoCoreError, ClientError, OSError) as exc:
            logger.exception(
                "Cloudflare R2 video upload failed",
                extra={"bucket": self.bucket_name, "key": object_key},
            )
            raise ImageStorageError(
                "Unable to store generated video in Cloudflare R2",
                status_code=502,
            ) from exc
        return StoredVideo(
            object_key=object_key,
            content_type=content_type,
            size=size,
        )

    def delete_object(self, object_key: str) -> None:
        self._validate_object_key(object_key)
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            logger.exception(
                "Cloudflare R2 delete_object failed",
                extra={"bucket": self.bucket_name, "key": object_key},
            )
            raise ImageStorageError(
                "Unable to delete object from Cloudflare R2",
                status_code=502,
            ) from exc

    def _object_key(self, *, app_user_id: uuid.UUID, filename: str) -> str:
        return f"{self.object_prefix}/images/{app_user_id}/{filename}"

    def _validate_object_key(self, object_key: str) -> None:
        if (
            not object_key.startswith(f"{self.object_prefix}/")
            or ".." in Path(object_key).parts
        ):
            raise ImageStorageError("Object key is not managed by Cloudflare R2")


def _create_r2_client() -> S3ObjectClient:
    if not settings.R2_ENDPOINT_URL:
        raise RuntimeError("R2_ENDPOINT_URL is required")
    if not settings.R2_ACCESS_KEY_ID or not settings.R2_SECRET_ACCESS_KEY:
        raise RuntimeError("Cloudflare R2 S3 credentials are required")
    client = boto3.client(
        "s3",
        endpoint_url=str(settings.R2_ENDPOINT_URL).rstrip("/"),
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"mode": "standard", "max_attempts": 4},
            connect_timeout=10,
            read_timeout=60,
            max_pool_connections=20,
        ),
    )
    return cast(S3ObjectClient, client)


def build_r2_app_image_url(*, app_user_id: uuid.UUID, filename: str) -> str:
    return (
        f"{settings.API_V1_STR.rstrip('/')}/app/uploads/images/{app_user_id}/{filename}"
    )


def parse_r2_app_image_url(url: str) -> tuple[uuid.UUID, str] | None:
    parsed_url = urlsplit(url)
    path_prefix = f"{settings.API_V1_STR.rstrip('/')}/app/uploads/images/"
    if not parsed_url.path.startswith(path_prefix):
        return None
    path_parts = parsed_url.path.removeprefix(path_prefix).split("/")
    if len(path_parts) != 2:
        return None
    app_user_id_text, filename = path_parts
    try:
        app_user_id = uuid.UUID(app_user_id_text)
        uuid.UUID(Path(filename).stem)
    except ValueError:
        return None
    if Path(filename).suffix.lower() not in {".jpg", ".png", ".gif", ".webp"}:
        return None
    return app_user_id, filename


def get_image_storage() -> ImageStorage:
    if settings.APP_IMAGE_STORAGE_BACKEND == "local":
        return LocalImageStorage()
    if settings.APP_IMAGE_STORAGE_BACKEND == "r2":
        return R2ImageStorage()
    raise RuntimeError(
        f"Unsupported image storage backend: {settings.APP_IMAGE_STORAGE_BACKEND}"
    )


def is_supported_uploaded_image_url(url: str) -> bool:
    if settings.APP_IMAGE_STORAGE_BACKEND == "local":
        return url.startswith("/uploads/")
    if settings.APP_IMAGE_STORAGE_BACKEND == "r2":
        parsed_url = urlsplit(url)
        return (
            not parsed_url.scheme
            and not parsed_url.netloc
            and parse_r2_app_image_url(url) is not None
        )
    return False


def create_provider_read_url(url: str) -> str:
    """Resolve a stored App URL into a URL readable by an external provider."""
    parsed_url = urlsplit(url)
    if (
        settings.APP_IMAGE_STORAGE_BACKEND == "r2"
        and not parsed_url.scheme
        and not parsed_url.netloc
        and parse_r2_app_image_url(url) is not None
    ):
        return get_image_storage().create_read_url(
            url,
            expires_in=settings.R2_REPLICATE_URL_EXPIRE_SECONDS,
        )

    if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
        return url
    raise ValueError("Asset URL must be provider-readable or stored in Cloudflare R2")
