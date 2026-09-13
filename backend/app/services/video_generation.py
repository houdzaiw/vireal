from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol


class VideoTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class VideoTaskSubmission:
    provider_task_id: str
    status: VideoTaskStatus


@dataclass(frozen=True)
class VideoTaskResult:
    provider_task_id: str
    status: VideoTaskStatus
    output_url: str | None = None
    error: str | None = None
    metrics: dict[str, Any] | None = None


class VideoGenerationProvider(Protocol):
    async def submit_reference_to_video(
        self,
        *,
        reference_image_urls: Sequence[str],
        prompt: str,
        duration: int,
        aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4"] = "9:16",
        resolution: Literal["720p", "1080p"] = "720p",
        negative_prompt: str | None = None,
        seed: int | None = None,
        model: str | None = None,
        webhook_url: str | None = None,
    ) -> VideoTaskSubmission: ...

    async def submit_image_to_motion(
        self,
        *,
        image_url: str,
        action_video_url: str,
        resolution: Literal["480", "720"] = "720",
        frames_per_second: int = 24,
        merge_audio: bool = True,
        seed: int | None = None,
    ) -> VideoTaskSubmission: ...

    async def get_task(self, provider_task_id: str) -> VideoTaskResult: ...

    async def aclose(self) -> None: ...
