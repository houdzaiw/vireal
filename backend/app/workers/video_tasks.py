import logging
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.models import AppUpload, AppVideoTask
from app.services.storage import ImageStorage, ImageStorageError, get_image_storage

logger = logging.getLogger(__name__)
WORKER_LOCK_TIMEOUT = timedelta(minutes=10)
DOWNLOAD_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class VideoOutputError(RuntimeError):
    pass


def _claim_video_task(session: Session) -> uuid.UUID | None:
    now = datetime.now(UTC)
    stale_before = now - WORKER_LOCK_TIMEOUT
    statement = (
        select(AppVideoTask)
        .where(
            AppVideoTask.status == "saving",
            col(AppVideoTask.provider_output_url).is_not(None),
            or_(
                col(AppVideoTask.next_attempt_at).is_(None),
                col(AppVideoTask.next_attempt_at) <= now,
            ),
            or_(
                col(AppVideoTask.worker_locked_at).is_(None),
                col(AppVideoTask.worker_locked_at) < stale_before,
            ),
        )
        .order_by(col(AppVideoTask.next_attempt_at).asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    task = session.exec(statement).first()
    if task is None:
        return None
    task.worker_locked_at = now
    task.worker_attempts += 1
    task.updated_at = now
    session.add(task)
    session.commit()
    return task.id


def _download_video(
    *,
    url: str,
    target: Path,
    http_client: httpx.Client,
) -> str:
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or not parsed.host:
        raise VideoOutputError("Replicate output URL must use HTTPS")

    total = 0
    content_type = "video/mp4"
    with http_client.stream("GET", url) as response:
        response.raise_for_status()
        if response.url.scheme != "https":
            raise VideoOutputError("Replicate output redirect must use HTTPS")
        response_type = response.headers.get("content-type", "").split(";", 1)[0]
        if response_type and not (
            response_type.startswith("video/")
            or response_type == "application/octet-stream"
        ):
            raise VideoOutputError("Replicate output is not a video")
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise VideoOutputError("Replicate output size is invalid") from exc
            if declared_size > settings.MAX_GENERATED_VIDEO_BYTES:
                raise VideoOutputError("Generated video exceeds the size limit")
        if response_type.startswith("video/"):
            content_type = response_type
        with target.open("wb") as output:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                total += len(chunk)
                if total > settings.MAX_GENERATED_VIDEO_BYTES:
                    raise VideoOutputError("Generated video exceeds the size limit")
                output.write(chunk)

    if total < 12:
        raise VideoOutputError("Generated video is empty")
    with target.open("rb") as downloaded:
        header = downloaded.read(12)
    if header[4:8] != b"ftyp":
        raise VideoOutputError("Generated output is not an MP4 file")
    return content_type


def _record_worker_failure(
    session: Session, task: AppVideoTask, exc: Exception
) -> None:
    now = datetime.now(UTC)
    task.worker_locked_at = None
    task.updated_at = now
    if task.worker_attempts >= settings.VIDEO_WORKER_MAX_ATTEMPTS:
        task.status = "failed"
        task.error = f"Unable to persist generated video: {exc}"
        task.completed_at = now
        task.next_attempt_at = None
    else:
        delay_seconds = min(15 * (2 ** (task.worker_attempts - 1)), 300)
        task.next_attempt_at = now + timedelta(seconds=delay_seconds)
    session.add(task)
    session.commit()


def process_next_video_task(
    *,
    storage: ImageStorage | None = None,
    http_client: httpx.Client | None = None,
) -> bool:
    with Session(engine) as session:
        task_id = _claim_video_task(session)
    if task_id is None:
        return False

    owns_http_client = http_client is None
    client = http_client or httpx.Client(
        timeout=DOWNLOAD_TIMEOUT,
        follow_redirects=True,
    )
    media_storage = storage or get_image_storage()
    temp_path: Path | None = None
    try:
        with Session(engine) as session:
            task = session.get(AppVideoTask, task_id)
            if task is None:
                return True
            if not task.provider_output_url:
                task.status = "failed"
                task.error = "Replicate output URL is missing"
                task.worker_locked_at = None
                task.completed_at = datetime.now(UTC)
                task.updated_at = task.completed_at
                session.add(task)
                session.commit()
                return True
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                content_type = _download_video(
                    url=task.provider_output_url,
                    target=temp_path,
                    http_client=client,
                )
                stored = media_storage.store_video_file(
                    app_user_id=task.app_user_id,
                    task_id=task.id,
                    file_path=temp_path,
                    content_type=content_type,
                )
            except (
                httpx.HTTPError,
                OSError,
                ImageStorageError,
                VideoOutputError,
            ) as exc:
                logger.warning(
                    "Generated video persistence failed",
                    extra={
                        "video_task_id": str(task.id),
                        "attempt": task.worker_attempts,
                    },
                )
                _record_worker_failure(session, task, exc)
                return True

            now = datetime.now(UTC)
            task.status = "succeeded"
            task.output_object_key = stored.object_key
            task.provider_output_url = None
            task.error = None
            task.worker_locked_at = None
            task.next_attempt_at = None
            task.completed_at = now
            task.expires_at = now + timedelta(hours=settings.APP_MEDIA_RETENTION_HOURS)
            task.updated_at = now
            session.add(task)
            session.commit()
            return True
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if owns_http_client:
            client.close()


def cleanup_expired_media(*, storage: ImageStorage | None = None) -> int:
    media_storage = storage or get_image_storage()
    now = datetime.now(UTC)
    cleaned = 0
    with Session(engine) as session:
        uploads = list(
            session.exec(
                select(AppUpload)
                .where(
                    AppUpload.status == "active",
                    AppUpload.expires_at <= now,
                )
                .limit(100)
            ).all()
        )
        for upload in uploads:
            try:
                media_storage.delete_object(upload.object_key)
            except ImageStorageError:
                logger.exception(
                    "Expired upload deletion failed",
                    extra={"app_upload_id": str(upload.id)},
                )
                continue
            upload.status = "deleted"
            upload.deleted_at = now
            session.add(upload)
            cleaned += 1

        tasks = list(
            session.exec(
                select(AppVideoTask)
                .where(
                    AppVideoTask.status != "expired",
                    AppVideoTask.expires_at <= now,
                )
                .limit(100)
            ).all()
        )
        for task in tasks:
            if task.output_object_key:
                try:
                    media_storage.delete_object(task.output_object_key)
                except ImageStorageError:
                    logger.exception(
                        "Expired video deletion failed",
                        extra={"video_task_id": str(task.id)},
                    )
                    continue
            task.status = "expired"
            task.output_object_key = None
            task.provider_output_url = None
            task.updated_at = now
            session.add(task)
            cleaned += 1
        session.commit()
    return cleaned


def run_worker() -> None:
    logger.info("Video task worker started")
    next_cleanup_at = 0.0
    while True:
        processed = process_next_video_task()
        monotonic_now = time.monotonic()
        if monotonic_now >= next_cleanup_at:
            cleanup_expired_media()
            next_cleanup_at = monotonic_now + settings.VIDEO_CLEANUP_INTERVAL_SECONDS
        if not processed:
            time.sleep(settings.VIDEO_WORKER_POLL_SECONDS)


if __name__ == "__main__":
    run_worker()
