import json
import re
from collections.abc import Sequence
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.services.storage import create_provider_read_url
from app.services.video_generation import (
    VideoTaskResult,
    VideoTaskStatus,
    VideoTaskSubmission,
)

REPLICATE_API_BASE_URL = "https://api.replicate.com/v1"
WAN_R2V_MODEL = "wan-video/wan-2.7-r2v"
MINIMAX_VIDEO_01_MODEL = "minimax/video-01"
SEEDANCE_R2V_MODEL = "bytedance/seedance-2.0"
WAN_ANIMATE_MODEL = "wan-video/wan-2.2-animate-animation"

_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_PREDICTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SUPPORTED_R2V_MODELS = frozenset(
    {WAN_R2V_MODEL, MINIMAX_VIDEO_01_MODEL, SEEDANCE_R2V_MODEL}
)
_SUPPORTED_ANIMATE_MODELS = frozenset({WAN_ANIMATE_MODEL})


class ReplicateConfigurationError(RuntimeError):
    pass


class ReplicateAPIError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        status_code: int | None = None,
        prediction_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.prediction_id = prediction_id
        super().__init__(message)


class ReplicateVideoClient:
    """HTTP adapter for asynchronous Replicate video predictions.

    Each submit call creates one potentially billable prediction. Callers must
    persist the returned provider task ID and poll that prediction instead of
    retrying creation after an ambiguous response.
    """

    def __init__(
        self,
        *,
        api_token: str,
        r2v_model: str = WAN_R2V_MODEL,
        animate_model: str = WAN_ANIMATE_MODEL,
        webhook_url: str | None = None,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_token:
            raise ReplicateConfigurationError("Replicate API token is required")
        _validate_model(r2v_model, supported=_SUPPORTED_R2V_MODELS, kind="R2V")
        _validate_model(
            animate_model,
            supported=_SUPPORTED_ANIMATE_MODELS,
            kind="animation",
        )
        if webhook_url is not None:
            _validate_webhook_url(webhook_url)

        self.r2v_model = r2v_model
        self.animate_model = animate_model
        self.webhook_url = webhook_url
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def __aenter__(self) -> ReplicateVideoClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

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
    ) -> VideoTaskSubmission:
        selected_model = model or self.r2v_model
        _validate_model(
            selected_model,
            supported=_SUPPORTED_R2V_MODELS,
            kind="R2V",
        )
        if not prompt.strip():
            raise ValueError("Reference-to-video prompt is required")
        provider_reference_image_urls = [
            create_provider_read_url(image_url) for image_url in reference_image_urls
        ]
        for image_url in provider_reference_image_urls:
            _validate_public_asset_url(image_url, field_name="reference image URL")
        _validate_seed(seed)
        if webhook_url is not None:
            _validate_webhook_url(webhook_url)

        if selected_model == WAN_R2V_MODEL:
            prediction_input = _build_wan_r2v_input(
                reference_image_urls=provider_reference_image_urls,
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                negative_prompt=negative_prompt,
                seed=seed,
            )
        elif selected_model == MINIMAX_VIDEO_01_MODEL:
            prediction_input = _build_minimax_video_01_input(
                reference_image_urls=provider_reference_image_urls,
                prompt=prompt,
                duration=duration,
            )
        else:
            prediction_input = _build_seedance_r2v_input(
                reference_image_urls=provider_reference_image_urls,
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                negative_prompt=negative_prompt,
                seed=seed,
            )

        payload = self._prediction_payload(
            prediction_input,
            webhook_url=webhook_url,
        )
        response_payload = await self._post_model_prediction(selected_model, payload)
        return _parse_submission(response_payload)

    async def submit_image_to_motion(
        self,
        *,
        image_url: str,
        action_video_url: str,
        resolution: Literal["480", "720"] = "720",
        frames_per_second: int = 24,
        merge_audio: bool = True,
        seed: int | None = None,
    ) -> VideoTaskSubmission:
        provider_image_url = create_provider_read_url(image_url)
        provider_action_video_url = create_provider_read_url(action_video_url)
        _validate_public_asset_url(provider_image_url, field_name="image URL")
        _validate_public_asset_url(
            provider_action_video_url,
            field_name="action video URL",
        )
        if not 5 <= frames_per_second <= 60:
            raise ValueError("Frames per second must be between 5 and 60")
        _validate_seed(seed)

        prediction_input: dict[str, Any] = {
            "video": provider_action_video_url,
            "character_image": provider_image_url,
            "resolution": resolution,
            "frames_per_second": frames_per_second,
            "merge_audio": merge_audio,
            "go_fast": True,
            "refert_num": 1,
        }
        if seed is not None:
            prediction_input["seed"] = seed

        payload = self._prediction_payload(prediction_input)
        response_payload = await self._post_model_prediction(
            self.animate_model,
            payload,
        )
        return _parse_submission(response_payload)

    async def get_task(self, provider_task_id: str) -> VideoTaskResult:
        _validate_prediction_id(provider_task_id)
        response = await self._http_client.get(
            f"{REPLICATE_API_BASE_URL}/predictions/{provider_task_id}",
            headers={"Authorization": self._headers["Authorization"]},
        )
        return _parse_task_result(_decode_response(response))

    async def cancel_task(self, provider_task_id: str) -> VideoTaskResult:
        _validate_prediction_id(provider_task_id)
        response = await self._http_client.post(
            f"{REPLICATE_API_BASE_URL}/predictions/{provider_task_id}/cancel",
            headers=self._headers,
        )
        return _parse_task_result(_decode_response(response))

    def _prediction_payload(
        self,
        prediction_input: dict[str, Any],
        *,
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"input": prediction_input}
        effective_webhook_url = webhook_url or self.webhook_url
        if effective_webhook_url:
            payload["webhook"] = effective_webhook_url
            payload["webhook_events_filter"] = ["completed"]
        return payload

    async def _post_model_prediction(
        self,
        model: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        owner, name = model.split("/", 1)
        response = await self._http_client.post(
            f"{REPLICATE_API_BASE_URL}/models/{owner}/{name}/predictions",
            headers=self._headers,
            json=payload,
        )
        return _decode_response(response)


def get_replicate_video_client() -> ReplicateVideoClient:
    if not settings.REPLICATE_ENABLED:
        raise ReplicateConfigurationError("Replicate integration is disabled")
    if not settings.REPLICATE_API_TOKEN:
        raise ReplicateConfigurationError("Replicate API token is required")
    return ReplicateVideoClient(
        api_token=settings.REPLICATE_API_TOKEN,
        r2v_model=settings.REPLICATE_ADVANCED_MODEL,
        animate_model=settings.REPLICATE_ANIMATE_MODEL,
        webhook_url=(
            str(settings.REPLICATE_WEBHOOK_URL)
            if settings.REPLICATE_WEBHOOK_URL is not None
            else None
        ),
        timeout_seconds=settings.REPLICATE_REQUEST_TIMEOUT_SECONDS,
    )


def _build_wan_r2v_input(
    *,
    reference_image_urls: Sequence[str],
    prompt: str,
    duration: int,
    aspect_ratio: str,
    resolution: str,
    negative_prompt: str | None,
    seed: int | None,
) -> dict[str, Any]:
    if not 1 <= len(reference_image_urls) <= 5:
        raise ValueError("Wan R2V requires 1 to 5 reference images")
    if not 2 <= duration <= 10:
        raise ValueError("Replicate Wan R2V duration must be between 2 and 10 seconds")

    prediction_input: dict[str, Any] = {
        "prompt": prompt.strip(),
        "reference_images": list(reference_image_urls),
        "reference_videos": [],
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "shot_type": "single",
    }
    if negative_prompt:
        prediction_input["negative_prompt"] = negative_prompt
    if seed is not None:
        prediction_input["seed"] = seed
    return prediction_input


def _build_seedance_r2v_input(
    *,
    reference_image_urls: Sequence[str],
    prompt: str,
    duration: int,
    aspect_ratio: str,
    resolution: str,
    negative_prompt: str | None,
    seed: int | None,
) -> dict[str, Any]:
    if not 1 <= len(reference_image_urls) <= 9:
        raise ValueError("Seedance R2V requires 1 to 9 reference images")
    if not 2 <= duration <= 15:
        raise ValueError("Replicate Seedance duration must be between 2 and 15 seconds")
    if resolution != "720p":
        raise ValueError("The configured Seedance integration currently supports 720p")
    if negative_prompt:
        raise ValueError(
            "The configured Seedance model does not accept negative_prompt"
        )

    prediction_input: dict[str, Any] = {
        "prompt": prompt.strip(),
        "reference_images": list(reference_image_urls),
        "reference_videos": [],
        "reference_audios": [],
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "generate_audio": True,
    }
    if seed is not None:
        prediction_input["seed"] = seed
    return prediction_input


def _build_minimax_video_01_input(
    *,
    reference_image_urls: Sequence[str],
    prompt: str,
    duration: int,
) -> dict[str, Any]:
    if len(reference_image_urls) != 1:
        raise ValueError("MiniMax Video-01 requires exactly one first-frame image")
    if duration != 5:
        raise ValueError("MiniMax standard mode only accepts a five-second request")
    return {
        "prompt": prompt.strip(),
        "prompt_optimizer": True,
        "first_frame_image": reference_image_urls[0],
    }


def _validate_model(model: str, *, supported: frozenset[str], kind: str) -> None:
    if not _MODEL_PATTERN.fullmatch(model):
        raise ReplicateConfigurationError(f"Invalid Replicate {kind} model identifier")
    if model not in supported:
        options = ", ".join(sorted(supported))
        raise ReplicateConfigurationError(
            f"Unsupported Replicate {kind} model {model!r}; supported: {options}"
        )


def _validate_webhook_url(value: str) -> None:
    url = httpx.URL(value)
    if url.scheme != "https" or not url.host:
        raise ReplicateConfigurationError(
            "Replicate webhook URL must be an absolute HTTPS URL"
        )


def _validate_public_asset_url(value: str, *, field_name: str) -> None:
    url = httpx.URL(value)
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError(f"{field_name} must be a provider-readable HTTP or HTTPS URL")


def _validate_prediction_id(value: str) -> None:
    if not _PREDICTION_ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid Replicate prediction ID")


def _validate_seed(value: int | None) -> None:
    if value is not None and not 0 <= value <= 2_147_483_647:
        raise ValueError("Seed must be between 0 and 2147483647")


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ReplicateAPIError(
            message="Replicate returned a non-JSON response",
            status_code=response.status_code,
        ) from exc

    if not isinstance(payload, dict):
        raise ReplicateAPIError(
            message="Replicate returned an invalid response",
            status_code=response.status_code,
        )
    if response.is_error:
        raise ReplicateAPIError(
            message=_error_message(payload),
            status_code=response.status_code,
            prediction_id=_optional_string(payload.get("id")),
        )
    return payload


def _parse_submission(payload: dict[str, Any]) -> VideoTaskSubmission:
    prediction_id = _optional_string(payload.get("id"))
    if prediction_id is None:
        raise ReplicateAPIError(message="Replicate response is missing prediction id")
    return VideoTaskSubmission(
        provider_task_id=prediction_id,
        status=_parse_status(payload.get("status")),
    )


def _parse_task_result(payload: dict[str, Any]) -> VideoTaskResult:
    prediction_id = _optional_string(payload.get("id"))
    if prediction_id is None:
        raise ReplicateAPIError(message="Replicate response is missing prediction id")

    metrics = payload.get("metrics")
    return VideoTaskResult(
        provider_task_id=prediction_id,
        status=_parse_status(payload.get("status")),
        output_url=_extract_output_url(payload.get("output")),
        error=_optional_error(payload.get("error")),
        metrics=metrics if isinstance(metrics, dict) else None,
    )


def parse_replicate_task_payload(payload: dict[str, Any]) -> VideoTaskResult:
    """Normalize a signed Replicate webhook payload without making an API call."""
    return _parse_task_result(payload)


def _parse_status(value: object) -> VideoTaskStatus:
    status_map = {
        "starting": VideoTaskStatus.PENDING,
        "processing": VideoTaskStatus.RUNNING,
        "succeeded": VideoTaskStatus.SUCCEEDED,
        "failed": VideoTaskStatus.FAILED,
        "canceled": VideoTaskStatus.CANCELED,
    }
    return status_map.get(str(value).lower(), VideoTaskStatus.UNKNOWN)


def _extract_output_url(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, str) and item), None)
    return None


def _error_message(payload: dict[str, Any]) -> str:
    value = payload.get("detail") or payload.get("error")
    if isinstance(value, str) and value:
        return value
    if value is not None:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "Replicate request failed"


def _optional_error(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _optional_string(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
