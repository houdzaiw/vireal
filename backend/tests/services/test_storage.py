import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.core.config import settings
from app.services import storage as storage_module
from app.services.storage import (
    ImageStorageError,
    LocalImageStorage,
    R2ImageStorage,
    build_r2_app_image_url,
    create_provider_read_url,
    detect_image_type,
    get_image_storage,
    is_supported_uploaded_image_url,
    parse_r2_app_image_url,
    validate_image_upload,
    validate_managed_asset,
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


class FailingR2Client(FakeR2Client):
    def _fail(self, operation: str) -> None:
        raise ClientError(
            {"Error": {"Code": "InternalError", "Message": "test failure"}},
            operation,
        )

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        del kwargs
        self._fail("PutObject")

    def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        del client_method, Params, ExpiresIn
        self._fail("GetObject")

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self._fail("GetObject")

    def upload_fileobj(
        self,
        Fileobj: Any,
        Bucket: str,
        Key: str,
        **kwargs: Any,
    ) -> dict[str, str]:
        del Fileobj, Bucket, Key, kwargs
        self._fail("PutObject")

    def delete_object(self, **kwargs: Any) -> dict[str, str]:
        del kwargs
        self._fail("DeleteObject")


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


def test_validate_image_upload_rejects_unknown_signature() -> None:
    with pytest.raises(ImageStorageError, match="File must be an image"):
        validate_image_upload(content=b"plain text", uploaded_content_type="image/png")


def test_validate_managed_asset_supports_catalogue_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert validate_managed_asset(
        kind="poster", content=PNG_BYTES, uploaded_content_type="image/png"
    ) == ("image/png", ".png")
    assert validate_managed_asset(
        kind="preview_video",
        content=b"\x00\x00\x00\x18ftypmp42video",
        uploaded_content_type="video/mp4",
    ) == ("video/mp4", ".mp4")
    assert validate_managed_asset(
        kind="preview_video",
        content=b"\x1a\x45\xdf\xa3webm-video",
        uploaded_content_type="video/webm",
    ) == ("video/webm", ".webm")

    with pytest.raises(ImageStorageError, match="Unsupported catalogue"):
        validate_managed_asset(
            kind="audio", content=b"audio", uploaded_content_type="audio/mpeg"
        )
    with pytest.raises(ImageStorageError, match="supported image"):
        validate_managed_asset(
            kind="poster", content=b"bad", uploaded_content_type="image/png"
        )
    with pytest.raises(ImageStorageError, match="MP4 or WebM"):
        validate_managed_asset(
            kind="preview_video", content=b"bad", uploaded_content_type="text/plain"
        )
    with pytest.raises(ImageStorageError, match="signature is invalid"):
        validate_managed_asset(
            kind="preview_video", content=b"bad", uploaded_content_type="video/mp4"
        )

    monkeypatch.setattr(settings, "MAX_CATALOG_IMAGE_BYTES", 1)
    with pytest.raises(ImageStorageError) as image_error:
        validate_managed_asset(
            kind="poster", content=PNG_BYTES, uploaded_content_type="image/png"
        )
    assert image_error.value.status_code == 413
    monkeypatch.setattr(settings, "MAX_CATALOG_VIDEO_BYTES", 1)
    with pytest.raises(ImageStorageError) as video_error:
        validate_managed_asset(
            kind="preview_video",
            content=b"\x00\x00\x00\x18ftypmp42video",
            uploaded_content_type="video/mp4",
        )
    assert video_error.value.status_code == 413


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


def test_local_storage_reads_and_manages_private_objects(tmp_path: Path) -> None:
    app_user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    storage = LocalImageStorage(upload_root=tmp_path)
    stored_image = storage.store_app_image(
        app_user_id=app_user_id,
        content=PNG_BYTES,
        uploaded_content_type="image/png",
    )
    assert storage.create_read_url(stored_image.url, expires_in=60) == stored_image.url
    assert storage.read_app_image(stored_image.url).content == PNG_BYTES

    source = tmp_path / "source.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42video")
    stored_video = storage.store_video_file(
        app_user_id=app_user_id,
        task_id=task_id,
        file_path=source,
        content_type="video/mp4",
    )
    assert (tmp_path / stored_video.object_key).read_bytes() == source.read_bytes()

    asset = storage.store_managed_asset(
        kind="poster",
        content=PNG_BYTES,
        uploaded_content_type="image/png",
    )
    assert storage.create_object_read_url(asset.object_key, expires_in=60).startswith(
        "/uploads/catalog/poster/"
    )
    storage.delete_object(asset.object_key)
    assert not (tmp_path / asset.object_key).exists()


def test_local_storage_rejects_unmanaged_missing_and_corrupt_images(
    tmp_path: Path,
) -> None:
    storage = LocalImageStorage(upload_root=tmp_path)
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.create_read_url("https://example.com/image.png", expires_in=60)
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.read_app_image("/elsewhere/image.png")
    with pytest.raises(ImageStorageError, match="invalid"):
        storage.read_app_image("/uploads/images/../../outside.png")
    with pytest.raises(ImageStorageError) as missing:
        storage.read_app_image("/uploads/images/user/missing.png")
    assert missing.value.status_code == 404
    corrupt = tmp_path / "images" / "user" / "corrupt.png"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_bytes(b"not an image")
    with pytest.raises(ImageStorageError, match="not a supported image"):
        storage.read_app_image("/uploads/images/user/corrupt.png")
    with pytest.raises(ImageStorageError, match="Object key is invalid"):
        storage.create_object_read_url("../outside", expires_in=60)


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


def test_r2_managed_asset_upload_and_url_validation() -> None:
    fake_client = FakeR2Client()
    storage = R2ImageStorage(
        client=fake_client,
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )
    asset = storage.store_managed_asset(
        kind="poster",
        content=PNG_BYTES,
        uploaded_content_type="image/png",
    )
    assert asset.object_key.startswith("vireal/catalog/poster/")
    assert fake_client.put_calls[0]["CacheControl"] == "private, max-age=300"
    assert storage.create_object_read_url(asset.object_key, expires_in=120).startswith(
        "https://"
    )
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.create_object_read_url("other/object.png", expires_in=120)
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.delete_object("vireal/../secret")

    invalid_url = f"{settings.API_V1_STR}/app/uploads/images/not-a-uuid/image.png"
    assert parse_r2_app_image_url(invalid_url) is None
    assert (
        parse_r2_app_image_url(
            f"{settings.API_V1_STR}/app/uploads/images/{uuid.uuid4()}/bad.txt"
        )
        is None
    )
    assert (
        parse_r2_app_image_url(
            f"{settings.API_V1_STR}/app/uploads/images/{uuid.uuid4()}/{uuid.uuid4()}.txt"
        )
        is None
    )
    assert (
        parse_r2_app_image_url(f"{settings.API_V1_STR}/app/uploads/images/short")
        is None
    )


def test_r2_failures_are_wrapped_as_storage_errors(tmp_path: Path) -> None:
    storage = R2ImageStorage(
        client=FailingR2Client(),
        bucket_name="vireal-media-test",
        object_prefix="vireal",
    )
    app_user_id = uuid.uuid4()
    filename = f"{uuid.uuid4()}.png"
    stable_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=filename,
    )
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42video")

    operations = [
        lambda: storage.store_app_image(
            app_user_id=app_user_id,
            content=PNG_BYTES,
            uploaded_content_type="image/png",
        ),
        lambda: storage.create_read_url(stable_url, expires_in=60),
        lambda: storage.read_app_image(stable_url),
        lambda: storage.store_video_file(
            app_user_id=app_user_id,
            task_id=uuid.uuid4(),
            file_path=video,
            content_type="video/mp4",
        ),
        lambda: storage.delete_object(f"vireal/videos/{uuid.uuid4()}.mp4"),
        lambda: storage.store_managed_asset(
            kind="poster",
            content=PNG_BYTES,
            uploaded_content_type="image/png",
        ),
    ]
    for operation in operations:
        with pytest.raises(ImageStorageError) as error:
            operation()
        assert error.value.status_code == 502


def test_storage_factory_and_provider_url_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_IMAGE_STORAGE_BACKEND", "local")
    assert isinstance(get_image_storage(), LocalImageStorage)
    assert create_provider_read_url("https://cdn.example.com/image.png").startswith(
        "https://"
    )
    with pytest.raises(ValueError, match="provider-readable"):
        create_provider_read_url("/uploads/images/user/image.png")

    monkeypatch.setattr(settings, "APP_IMAGE_STORAGE_BACKEND", "unsupported")
    assert is_supported_uploaded_image_url("/uploads/image.png") is False
    with pytest.raises(RuntimeError, match="Unsupported image storage backend"):
        get_image_storage()


def test_r2_constructor_and_unmanaged_image_urls_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "R2_BUCKET_NAME", None)
    with pytest.raises(RuntimeError, match="R2_BUCKET_NAME"):
        R2ImageStorage(client=FakeR2Client(), bucket_name="", object_prefix="vireal")
    with pytest.raises(RuntimeError, match="R2_OBJECT_PREFIX"):
        R2ImageStorage(client=FakeR2Client(), bucket_name="bucket", object_prefix="/")
    storage = R2ImageStorage(
        client=FakeR2Client(), bucket_name="bucket", object_prefix="vireal"
    )
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.create_read_url("https://example.com/image.png", expires_in=60)
    with pytest.raises(ImageStorageError, match="not managed"):
        storage.read_app_image("https://example.com/image.png")
