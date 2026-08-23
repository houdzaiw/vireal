import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import settings

IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
)


@dataclass(frozen=True)
class StoredImage:
    url: str
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
        image_path = image_dir / filename
        image_path.write_bytes(content)

        return StoredImage(
            url=f"/uploads/images/{app_user_id}/{filename}",
            content_type=content_type,
            size=len(content),
        )


def get_image_storage() -> ImageStorage:
    if settings.APP_IMAGE_STORAGE_BACKEND == "local":
        return LocalImageStorage()
    raise RuntimeError(
        f"Unsupported image storage backend: {settings.APP_IMAGE_STORAGE_BACKEND}"
    )


def is_supported_uploaded_image_url(url: str) -> bool:
    if settings.APP_IMAGE_STORAGE_BACKEND == "local":
        return url.startswith("/uploads/")
    return False
