import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.services import storage as storage_module
from app.services.storage import (
    ImageStorageError,
    LocalImageStorage,
    R2ImageStorage,
    build_r2_app_image_url,
    create_provider_read_url,
    detect_image_type,
    is_supported_uploaded_image_url,
    parse_r2_app_image_url,
    validate_image_upload,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\napp-test-image"


class FakeR2Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.presign_calls: list[dict[str, Any]] = []
        self.upload_fileobj_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        self.put_calls.append(kwargs)
        return {"ETag": "test-etag"}

    def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        self.presign_calls.append(
            {
                "client_method": client_method,
                "Params": Params,
                "ExpiresIn": ExpiresIn,
            }
        )
        return "https://bucket.account.r2.cloudflarestorage.com/signed-image"

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return {"Body": BytesIO(PNG_BYTES), "ContentType": "image/png"}

    def upload_fileobj(
        self,
        Fileobj: Any,
        Bucket: str,
        Key: str,
        **kwargs: Any,
    ) -> dict[str, str]:
        self.upload_fileobj_calls.append(
            {
                "content": Fileobj.read(),
                "Bucket": Bucket,
                "Key": Key,
                **kwargs,
            }
        )
        return {"ETag": "video-etag"}

    def delete_object(self, **kwargs: Any) -> dict[str, str]:
        self.delete_calls.append(kwargs)
        return {}


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
    assert stored_image.object_key == stored_image.url.removeprefix("/uploads/")

    stored_path = tmp_path / stored_image.url.removeprefix("/uploads/")
    assert stored_path.read_bytes() == PNG_BYTES


def test_uploaded_image_url_validation_uses_storage_backend() -> None:
    assert is_supported_uploaded_image_url("/uploads/images/user/file.png") is True
    assert is_supported_uploaded_image_url("https://example.com/file.png") is False


def test_r2_image_storage_uploads_private_object_and_returns_stable_url() -> None:
    app_user_id = uuid.uuid4()
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )

    stored_image = storage.store_app_image(
        app_user_id=app_user_id,
        content=PNG_BYTES,
        uploaded_content_type="image/png",
    )

    parsed_location = parse_r2_app_image_url(stored_image.url)
    assert parsed_location is not None
    parsed_user_id, filename = parsed_location
    assert parsed_user_id == app_user_id
    assert filename.endswith(".png")
    assert stored_image.object_key == f"vireal/images/{app_user_id}/{filename}"
    assert fake_client.put_calls == [
        {
            "Bucket": "vireal-media-test",
            "Key": f"vireal/images/{app_user_id}/{filename}",
            "Body": PNG_BYTES,
            "ContentLength": len(PNG_BYTES),
            "ContentType": "image/png",
            "CacheControl": "private, no-store",
            "Metadata": {"app-user-id": str(app_user_id)},
        }
    ]


def test_r2_image_storage_creates_short_lived_read_url() -> None:
    app_user_id = uuid.uuid4()
    filename = f"{uuid.uuid4()}.jpg"
    stable_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=filename,
    )
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )

    signed_url = storage.create_read_url(stable_url, expires_in=300)

    assert signed_url.startswith("https://")
    assert fake_client.presign_calls == [
        {
            "client_method": "get_object",
            "Params": {
                "Bucket": "vireal-media-test",
                "Key": f"vireal/images/{app_user_id}/{filename}",
            },
            "ExpiresIn": 300,
        }
    ]


def test_r2_image_storage_reads_private_object() -> None:
    app_user_id = uuid.uuid4()
    filename = f"{uuid.uuid4()}.png"
    stable_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=filename,
    )
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )

    image = storage.read_app_image(stable_url)

    assert image.content == PNG_BYTES
    assert image.content_type == "image/png"
    assert fake_client.get_calls == [
        {
            "Bucket": "vireal-media-test",
            "Key": f"vireal/images/{app_user_id}/{filename}",
        }
    ]


def test_r2_video_storage_streams_private_object(tmp_path: Path) -> None:
    app_user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    video_path = tmp_path / "result.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42video")
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )

    stored = storage.store_video_file(
        app_user_id=app_user_id,
        task_id=task_id,
        file_path=video_path,
        content_type="video/mp4",
    )

    expected_key = f"vireal/videos/{app_user_id}/{task_id}.mp4"
    assert stored.object_key == expected_key
    assert stored.size == video_path.stat().st_size
    assert fake_client.upload_fileobj_calls == [
        {
            "content": video_path.read_bytes(),
            "Bucket": "vireal-media-test",
            "Key": expected_key,
            "ExtraArgs": {
                "ContentType": "video/mp4",
                "CacheControl": "private, no-store",
                "Metadata": {
                    "app-user-id": str(app_user_id),
                    "video-task-id": str(task_id),
                },
            },
        }
    ]


def test_r2_storage_deletes_managed_object() -> None:
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )

    storage.delete_object("vireal/videos/user/task.mp4")

    assert fake_client.delete_calls == [
        {"Bucket": "vireal-media-test", "Key": "vireal/videos/user/task.mp4"}
    ]


def test_provider_url_resolver_signs_r2_managed_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_user_id = uuid.uuid4()
    stable_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=f"{uuid.uuid4()}.png",
    )
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
    )
    monkeypatch.setattr(settings, "APP_IMAGE_STORAGE_BACKEND", "r2")
    monkeypatch.setattr(storage_module, "get_image_storage", lambda: storage)

    provider_url = create_provider_read_url(stable_url)

    assert provider_url.startswith("https://")
    assert (
        fake_client.presign_calls[0]["ExpiresIn"]
        == settings.R2_REPLICATE_URL_EXPIRE_SECONDS
    )


def test_r2_uploaded_url_validation_rejects_external_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_user_id = uuid.uuid4()
    stable_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=f"{uuid.uuid4()}.webp",
    )
    monkeypatch.setattr(settings, "APP_IMAGE_STORAGE_BACKEND", "r2")

    assert is_supported_uploaded_image_url(stable_url) is True
    assert is_supported_uploaded_image_url(f"https://evil.example{stable_url}") is False
