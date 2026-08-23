import uuid

import pytest

from app.core.config import settings
from app.services.storage import (
    ImageStorageError,
    LocalImageStorage,
    detect_image_type,
    is_supported_uploaded_image_url,
    validate_image_upload,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\napp-test-image"


def test_detect_image_type_supports_common_formats() -> None:
    assert detect_image_type(b"\xff\xd8\xffimage") == ("image/jpeg", ".jpg")
    assert detect_image_type(PNG_BYTES) == ("image/png", ".png")
    assert detect_image_type(b"GIF87aimage") == ("image/gif", ".gif")
    assert detect_image_type(b"RIFFxxxxWEBPimage") == ("image/webp", ".webp")


def test_validate_image_upload_rejects_invalid_content_type() -> None:
    with pytest.raises(ImageStorageError) as exc_info:
        validate_image_upload(
            content=PNG_BYTES,
            uploaded_content_type="text/plain",
        )

    assert exc_info.value.detail == "File must be an image"
    assert exc_info.value.status_code == 400


def test_validate_image_upload_rejects_oversized_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_IMAGE_BYTES", 8)

    with pytest.raises(ImageStorageError) as exc_info:
        validate_image_upload(
            content=PNG_BYTES,
            uploaded_content_type="image/png",
        )

    assert exc_info.value.detail == "Image is too large"
    assert exc_info.value.status_code == 413


def test_local_image_storage_writes_user_scoped_file(tmp_path) -> None:
    app_user_id = uuid.uuid4()
    storage = LocalImageStorage(upload_root=tmp_path)

    stored_image = storage.store_app_image(
        app_user_id=app_user_id,
        content=PNG_BYTES,
        uploaded_content_type="image/png",
    )

    assert stored_image.content_type == "image/png"
    assert stored_image.size == len(PNG_BYTES)
    assert stored_image.url.startswith(f"/uploads/images/{app_user_id}/")
    assert stored_image.url.endswith(".png")

    stored_path = tmp_path / stored_image.url.removeprefix("/uploads/")
    assert stored_path.read_bytes() == PNG_BYTES


def test_uploaded_image_url_validation_uses_storage_backend() -> None:
    assert is_supported_uploaded_image_url("/uploads/images/user/file.png") is True
    assert is_supported_uploaded_image_url("https://example.com/file.png") is False
