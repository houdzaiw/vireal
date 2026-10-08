import subprocess
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlmodel import Session, delete

from app.core.config import settings
from app.models import (
    AppUpload,
    AppUser,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
)
from app.services.storage import ImageStorageError, ReadImage, StoredVideo
from app.workers import video_tasks as worker_module
from app.workers.video_tasks import (
    VideoOutputError,
    _download_video,
    _run_ffmpeg,
    _validate_local_video,
    cleanup_expired_media,
    normalize_provider_video,
    process_next_video_task,
    render_local_demo,
)

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42generated-video"


@pytest.fixture(autouse=True)
def clean_video_task_tables(db: Session) -> Generator[None]:
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.execute(delete(AppUpload))
    db.commit()
    yield
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.execute(delete(AppUpload))
    db.commit()


class FailingStorage:
    def store_video_file(self, **_kwargs: Any) -> StoredVideo:
        raise ImageStorageError("R2 unavailable", status_code=502)


class CleanupStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_object(self, object_key: str) -> None:
        self.deleted.append(object_key)


class SelectiveFailingCleanupStorage(CleanupStorage):
    def __init__(self, failures: set[str]) -> None:
        super().__init__()
        self.failures = failures

    def delete_object(self, object_key: str) -> None:
        if object_key in self.failures:
            raise ImageStorageError("delete failed", status_code=502)
        super().delete_object(object_key)


class LocalDemoStorage:
    def __init__(self) -> None:
        self.stored_content: bytes | None = None

    def read_app_image(self, url: str) -> ReadImage:
        assert url.endswith("person.png")
        return ReadImage(content=b"\x89PNG\r\n\x1a\nsource", content_type="image/png")

    def store_video_file(
        self,
        *,
        app_user_id: uuid.UUID,
        task_id: uuid.UUID,
        file_path: Any,
        content_type: str,
    ) -> StoredVideo:
        assert content_type == "video/mp4"
        self.stored_content = file_path.read_bytes()
        return StoredVideo(
            object_key=f"vireal/videos/{app_user_id}/{task_id}.mp4",
            content_type=content_type,
            size=len(self.stored_content),
        )


def _create_saving_task(db: Session) -> AppVideoTask:
    app_user = AppUser()
    db.add(app_user)
    db.commit()
    db.refresh(app_user)
    now = datetime.now(UTC)
    task = AppVideoTask(
        app_user_id=app_user.id,
        idempotency_key=f"worker-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json="[]",
        model="wan-video/wan-2.7-r2v",
        provider_task_id=f"prediction-{uuid.uuid4()}",
        status="saving",
        duration=5,
        seed=123,
        provider_output_url="https://replicate.delivery/generated.mp4",
        next_attempt_at=now,
        submission_attempted_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_worker_retries_persistence_without_creating_a_prediction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _create_saving_task(db)
    monkeypatch.setattr(settings, "VIDEO_WORKER_MAX_ATTEMPTS", 2)

    def output_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=MP4_BYTES,
            headers={"Content-Type": "video/mp4"},
        )

    with httpx.Client(transport=httpx.MockTransport(output_handler)) as http_client:
        assert (
            process_next_video_task(
                storage=FailingStorage(),
                http_client=http_client,
            )
            is True
        )
        db.expire_all()
        first_attempt = db.get(AppVideoTask, task.id)
        assert first_attempt is not None
        assert first_attempt.status == "saving"
        assert first_attempt.worker_attempts == 1
        first_attempt.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.add(first_attempt)
        db.commit()

        assert (
            process_next_video_task(
                storage=FailingStorage(),
                http_client=http_client,
            )
            is True
        )

    db.expire_all()
    failed = db.get(AppVideoTask, task.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.worker_attempts == 2
    assert "R2 unavailable" in (failed.error or "")
    assert failed.provider_task_id == task.provider_task_id


def test_cleanup_removes_expired_input_and_output_objects(db: Session) -> None:
    app_user = AppUser()
    db.add(app_user)
    db.commit()
    db.refresh(app_user)
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    upload = AppUpload(
        app_user_id=app_user.id,
        url=f"/uploads/images/{app_user.id}/person.png",
        object_key=f"vireal/images/{app_user.id}/person.png",
        content_type="image/png",
        size=123,
        expires_at=expired_at,
    )
    task = AppVideoTask(
        app_user_id=app_user.id,
        idempotency_key=f"cleanup-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json="[]",
        model="wan-video/wan-2.7-r2v",
        provider_task_id=f"prediction-{uuid.uuid4()}",
        status="succeeded",
        duration=5,
        seed=123,
        output_object_key=f"vireal/videos/{app_user.id}/result.mp4",
        submission_attempted_at=expired_at,
        completed_at=expired_at,
        expires_at=expired_at,
    )
    db.add(upload)
    db.add(task)
    db.commit()
    expected_object_keys = {upload.object_key, task.output_object_key}
    storage = CleanupStorage()

    cleaned = cleanup_expired_media(storage=storage)

    assert cleaned == 2
    assert set(storage.deleted) == expected_object_keys
    db.expire_all()
    cleaned_upload = db.get(AppUpload, upload.id)
    cleaned_task = db.get(AppVideoTask, task.id)
    assert cleaned_upload is not None
    assert cleaned_upload.status == "deleted"
    assert cleaned_task is not None
    assert cleaned_task.status == "expired"
    assert cleaned_task.output_object_key is None


def test_worker_renders_local_demo_from_owned_upload(
    db: Session,
) -> None:
    app_user = AppUser()
    db.add(app_user)
    db.commit()
    db.refresh(app_user)
    now = datetime.now(UTC)
    upload = AppUpload(
        app_user_id=app_user.id,
        url=f"/uploads/images/{app_user.id}/person.png",
        object_key=f"vireal/images/{app_user.id}/person.png",
        content_type="image/png",
        size=123,
        expires_at=now + timedelta(hours=24),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    task = AppVideoTask(
        app_user_id=app_user.id,
        idempotency_key=f"local-demo-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json=f'["{upload.id}"]',
        mode="standard",
        provider="local",
        model="local/ffmpeg",
        execution_type="local_demo",
        is_demo=True,
        fallback_reason="replicate_disabled",
        status="rendering_demo",
        duration=5,
        seed=123,
        next_attempt_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    storage = LocalDemoStorage()

    def fake_renderer(source: Any, output: Any, duration: int) -> None:
        assert source.read_bytes().startswith(b"\x89PNG")
        assert duration == 5
        output.write_bytes(MP4_BYTES)

    assert (
        process_next_video_task(
            storage=storage,
            local_demo_renderer=fake_renderer,
        )
        is True
    )

    db.expire_all()
    completed = db.get(AppVideoTask, task.id)
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.execution_type == "local_demo"
    assert completed.is_demo is True
    assert completed.fallback_reason == "replicate_disabled"
    assert storage.stored_content == MP4_BYTES


def test_download_video_validates_transport_metadata_and_mp4_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "download.mp4"
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200))
    ):
        with pytest.raises(VideoOutputError, match="must use HTTPS"):
            _download_video(
                url="http://example.com/video.mp4",
                target=target,
                http_client=httpx.Client(),
            )

    cases = [
        (
            {"Content-Type": "text/plain"},
            MP4_BYTES,
            "not a video",
        ),
        (
            {"Content-Type": "video/mp4", "Content-Length": "invalid"},
            MP4_BYTES,
            "size is invalid",
        ),
        (
            {"Content-Type": "video/mp4"},
            b"short",
            "video is empty",
        ),
        (
            {"Content-Type": "application/octet-stream"},
            b"0123456789abcdef",
            "not an MP4",
        ),
    ]
    for headers, content, message in cases:
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda _request, headers=headers, content=content: httpx.Response(
                    200, headers=headers, content=content
                )
            )
        ) as client:
            with pytest.raises(VideoOutputError, match=message):
                _download_video(
                    url="https://example.com/video.mp4",
                    target=target,
                    http_client=client,
                )

    monkeypatch.setattr(settings, "MAX_GENERATED_VIDEO_BYTES", len(MP4_BYTES) - 1)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Type": "video/mp4; charset=binary",
                    "Content-Length": str(len(MP4_BYTES)),
                },
                content=MP4_BYTES,
            )
        )
    ) as client:
        with pytest.raises(VideoOutputError, match="size limit"):
            _download_video(
                url="https://example.com/video.mp4",
                target=target,
                http_client=client,
            )
    monkeypatch.setattr(settings, "MAX_GENERATED_VIDEO_BYTES", 1024)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, headers={"Content-Type": "video/webm"}, content=MP4_BYTES
            )
        )
    ) as client:
        assert (
            _download_video(
                url="https://example.com/video.mp4",
                target=target,
                http_client=client,
            )
            == "video/webm"
        )
    assert target.read_bytes() == MP4_BYTES


def test_local_video_validation_and_ffmpeg_error_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.mp4"
    with pytest.raises(VideoOutputError, match="could not be read"):
        _validate_local_video(missing)
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"invalid")
    with pytest.raises(VideoOutputError, match="not a valid MP4"):
        _validate_local_video(invalid)
    valid = tmp_path / "valid.mp4"
    valid.write_bytes(MP4_BYTES)
    _validate_local_video(valid)
    monkeypatch.setattr(settings, "MAX_GENERATED_VIDEO_BYTES", 12)
    with pytest.raises(VideoOutputError, match="exceeds the size limit"):
        _validate_local_video(valid)

    exceptions = [
        (FileNotFoundError(), "not installed"),
        (subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1), "timed out"),
        (subprocess.CalledProcessError(1, "ffmpeg"), "failed"),
    ]
    for exception, message in exceptions:

        def fail(*_args: Any, exception: Exception = exception, **_kwargs: Any) -> None:
            raise exception

        monkeypatch.setattr(worker_module.subprocess, "run", fail)
        with pytest.raises(VideoOutputError, match=message):
            _run_ffmpeg(["ffmpeg"], operation="testing")


def test_renderer_and_normalizer_build_ffmpeg_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    commands: list[tuple[list[str], str]] = []

    def fake_ffmpeg(command: list[str], *, operation: str) -> None:
        commands.append((command, operation))
        Path(command[-1]).write_bytes(MP4_BYTES)

    monkeypatch.setattr(worker_module, "_run_ffmpeg", fake_ffmpeg)
    demo = tmp_path / "demo.mp4"
    normalized = tmp_path / "normalized.mp4"
    render_local_demo(source, demo, 5)
    normalize_provider_video(demo, normalized, 10)
    assert commands[0][1] == "rendering a local demo"
    assert "zoompan" in commands[0][0][commands[0][0].index("-vf") + 1]
    assert commands[1][1] == "normalizing a provider video"
    assert normalized.read_bytes() == MP4_BYTES


@pytest.mark.parametrize(
    ("mode", "execution_type"),
    [("standard", "wan"), ("effect", "minimax")],
)
def test_worker_normalizes_minimax_provider_output_and_handles_empty_queue(
    db: Session,
    mode: str,
    execution_type: str,
) -> None:
    task = _create_saving_task(db)
    task.mode = mode
    task.execution_type = execution_type
    db.add(task)
    db.commit()
    storage = LocalDemoStorage()
    normalized_durations: list[int] = []

    def normalizer(source: Path, output: Path, duration: int) -> None:
        assert source.read_bytes() == MP4_BYTES
        assert duration == 5
        normalized_durations.append(duration)
        output.write_bytes(MP4_BYTES)

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, content=MP4_BYTES, headers={"Content-Type": "video/mp4"}
            )
        )
    ) as client:
        assert process_next_video_task(
            storage=storage,
            http_client=client,
            provider_video_normalizer=normalizer,
        )
    assert storage.stored_content == MP4_BYTES
    assert normalized_durations == [5]
    assert process_next_video_task(storage=storage) is False


def test_worker_records_invalid_local_demo_source_as_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_user = AppUser()
    db.add(app_user)
    db.commit()
    db.refresh(app_user)
    now = datetime.now(UTC)
    task = AppVideoTask(
        app_user_id=app_user.id,
        idempotency_key=f"invalid-demo-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json="not-json",
        provider="local",
        model="local/ffmpeg",
        execution_type="local_demo",
        is_demo=True,
        status="rendering_demo",
        duration=5,
        seed=123,
        next_attempt_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(task)
    db.commit()
    monkeypatch.setattr(settings, "VIDEO_WORKER_MAX_ATTEMPTS", 1)
    assert process_next_video_task(storage=LocalDemoStorage()) is True
    db.expire_all()
    failed = db.get(AppVideoTask, task.id)
    assert failed is not None
    assert failed.status == "failed"
    assert "invalid source upload" in (failed.error or "")


def test_cleanup_skips_objects_that_storage_cannot_delete(db: Session) -> None:
    app_user = AppUser()
    db.add(app_user)
    db.commit()
    db.refresh(app_user)
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    upload = AppUpload(
        app_user_id=app_user.id,
        url=f"/uploads/images/{app_user.id}/failed.png",
        object_key=f"vireal/images/{app_user.id}/failed.png",
        content_type="image/png",
        size=10,
        expires_at=expired_at,
    )
    task = AppVideoTask(
        app_user_id=app_user.id,
        idempotency_key=f"cleanup-fail-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json="[]",
        model="minimax/video-01",
        status="succeeded",
        duration=5,
        seed=1,
        output_object_key=f"vireal/videos/{app_user.id}/failed.mp4",
        expires_at=expired_at,
    )
    db.add(upload)
    db.add(task)
    db.commit()
    failures = {upload.object_key, task.output_object_key}
    assert cleanup_expired_media(storage=SelectiveFailingCleanupStorage(failures)) == 0
    db.expire_all()
    assert db.get(AppUpload, upload.id).status == "active"  # type: ignore[union-attr]
    assert db.get(AppVideoTask, task.id).status == "succeeded"  # type: ignore[union-attr]
