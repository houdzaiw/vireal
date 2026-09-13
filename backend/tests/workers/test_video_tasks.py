import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
from app.services.storage import ImageStorageError, StoredVideo
from app.workers.video_tasks import cleanup_expired_media, process_next_video_task

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
