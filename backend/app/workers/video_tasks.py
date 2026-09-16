import json
import logging
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.models import AppUpload, AppVideoTask
from app.services.storage import ImageStorage, ImageStorageError, get_image_storage

logger = logging.getLogger(__name__)
WORKER_LOCK_TIMEOUT = timedelta(minutes=10)
DOWNLOAD_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
LocalDemoRenderer = Callable[[Path, Path, int], None]
ProviderVideoNormalizer = Callable[[Path, Path, int], None]


class VideoOutputError(RuntimeError):
    pass


def _claim_video_task(session: Session) -> uuid.UUID | None:
    now = datetime.now(UTC)
    stale_before = now - WORKER_LOCK_TIMEOUT
    statement = (
        select(AppVideoTask)
        .where(
            or_(
                and_(
                    col(AppVideoTask.status) == "saving",
                    col(AppVideoTask.provider_output_url).is_not(None),
                ),
                col(AppVideoTask.status) == "rendering_demo",
            ),
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


def _validate_local_video(path: Path) -> None:
    try:
        size = path.stat().st_size
        with path.open("rb") as video_file:
            header = video_file.read(12)
    except OSError as exc:
        raise VideoOutputError("Local demo output could not be read") from exc
    if size < 12 or header[4:8] != b"ftyp":
        raise VideoOutputError("Local demo output is not a valid MP4 file")
    if size > settings.MAX_GENERATED_VIDEO_BYTES:
        raise VideoOutputError("Local demo output exceeds the size limit")


def _run_ffmpeg(command: list[str], *, operation: str) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=settings.LOCAL_DEMO_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise VideoOutputError("FFmpeg is not installed for local video rendering") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoOutputError(f"FFmpeg timed out while {operation}") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoOutputError(f"FFmpeg failed while {operation}") from exc


def render_local_demo(source: Path, output: Path, duration: int) -> None:
    motion_filter = (
        "scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "zoompan=z='min(zoom+0.0008,1.08)':"
        "x='iw/2-(iw/zoom/2)+sin(on/18)*4':"
        "y='ih/2-(ih/zoom/2)+cos(on/22)*4':"
        "d=1:s=720x1280:fps=25,format=yuv420p"
    )
    _run_ffmpeg(
        [
            settings.LOCAL_DEMO_FFMPEG_PATH,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-vf",
            motion_filter,
            "-t",
            str(duration),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            str(output),
        ],
        operation="rendering a local demo",
    )
    _validate_local_video(output)


def normalize_provider_video(source: Path, output: Path, duration: int) -> None:
    video_filter = (
        "scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,fps=25,format=yuv420p"
    )
    _run_ffmpeg(
        [
            settings.LOCAL_DEMO_FFMPEG_PATH,
            "-y",
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-t",
            str(duration),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            str(output),
        ],
        operation="normalizing a provider video",
    )
    _validate_local_video(output)


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
    local_demo_renderer: LocalDemoRenderer = render_local_demo,
    provider_video_normalizer: ProviderVideoNormalizer = normalize_provider_video,
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
    temp_paths: list[Path] = []
    try:
        with Session(engine) as session:
            task = session.get(AppVideoTask, task_id)
            if task is None:
                return True
            try:
                if task.status == "rendering_demo":
                    try:
                        upload_ids = json.loads(task.upload_ids_json)
                        upload_id = uuid.UUID(upload_ids[0])
                    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise VideoOutputError(
                            "Local demo task has an invalid source upload"
                        ) from exc
                    upload = session.get(AppUpload, upload_id)
                    if (
                        upload is None
                        or upload.app_user_id != task.app_user_id
                        or upload.status != "active"
                        or upload.expires_at <= datetime.now(UTC)
                    ):
                        raise VideoOutputError(
                            "Local demo source upload is unavailable"
                        )
                    source_image = media_storage.read_app_image(upload.url)
                    suffix = ".png" if source_image.content_type == "image/png" else ".jpg"
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix,
                        delete=False,
                    ) as source_file:
                        source_path = Path(source_file.name)
                        source_file.write(source_image.content)
                    temp_paths.append(source_path)
                    with tempfile.NamedTemporaryFile(
                        suffix=".mp4",
                        delete=False,
                    ) as output_file:
                        output_path = Path(output_file.name)
                    temp_paths.append(output_path)
                    local_demo_renderer(source_path, output_path, task.duration)
                    _validate_local_video(output_path)
                    content_type = "video/mp4"
                    video_path = output_path
                else:
                    if not task.provider_output_url:
                        raise VideoOutputError("Replicate output URL is missing")
                    with tempfile.NamedTemporaryFile(
                        suffix=".mp4",
                        delete=False,
                    ) as downloaded_file:
                        downloaded_path = Path(downloaded_file.name)
                    temp_paths.append(downloaded_path)
                    content_type = _download_video(
                        url=task.provider_output_url,
                        target=downloaded_path,
                        http_client=client,
                    )
                    video_path = downloaded_path
                    if task.mode == "standard":
                        with tempfile.NamedTemporaryFile(
                            suffix=".mp4",
                            delete=False,
                        ) as normalized_file:
                            normalized_path = Path(normalized_file.name)
                        temp_paths.append(normalized_path)
                        provider_video_normalizer(
                            downloaded_path,
                            normalized_path,
                            task.duration,
                        )
                        _validate_local_video(normalized_path)
                        video_path = normalized_path
                        content_type = "video/mp4"
                stored = media_storage.store_video_file(
                    app_user_id=task.app_user_id,
                    task_id=task.id,
                    file_path=video_path,
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
        for temp_path in temp_paths:
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
