import json

import httpx
import pytest

from app.services.replicate_video import (
    MINIMAX_VIDEO_01_MODEL,
    SEEDANCE_R2V_MODEL,
    ReplicateAPIError,
    ReplicateVideoClient,
)
from app.services.video_generation import VideoTaskStatus


@pytest.mark.anyio
async def test_submit_two_image_wan_r2v_uses_async_prediction_api() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            201,
            json={"id": "prediction-r2v", "status": "starting"},
        )

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ReplicateVideoClient(
        api_token="test-token",
        webhook_url="https://api.example.com/webhooks/replicate",
        http_client=async_client,
    )

    submission = await client.submit_reference_to_video(
        reference_image_urls=[
            "https://private-oss.example/person-a.jpg?signature=one",
            "https://private-oss.example/person-b.jpg?signature=two",
        ],
        prompt="Image 1 and Image 2 step closer and share a natural warm hug.",
        duration=10,
        seed=123,
    )

    assert submission.provider_task_id == "prediction-r2v"
    assert submission.status == VideoTaskStatus.PENDING
    assert captured_request is not None
    assert captured_request.url.path == ("/v1/models/wan-video/wan-2.7-r2v/predictions")
    assert captured_request.headers["Authorization"] == "Bearer test-token"
    payload = json.loads(captured_request.content)
    assert payload == {
        "input": {
            "prompt": ("Image 1 and Image 2 step closer and share a natural warm hug."),
            "reference_images": [
                "https://private-oss.example/person-a.jpg?signature=one",
                "https://private-oss.example/person-b.jpg?signature=two",
            ],
            "reference_videos": [],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "shot_type": "single",
            "seed": 123,
        },
        "webhook": "https://api.example.com/webhooks/replicate",
        "webhook_events_filter": ["completed"],
    }
    await async_client.aclose()


@pytest.mark.anyio
async def test_wan_r2v_rejects_fifteen_seconds() -> None:
    async with httpx.AsyncClient() as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        with pytest.raises(ValueError, match="between 2 and 10"):
            await client.submit_reference_to_video(
                reference_image_urls=["https://private-oss.example/person.jpg"],
                prompt="The person walks forward.",
                duration=15,
            )


@pytest.mark.anyio
async def test_minimax_video_01_uses_uploaded_image_as_first_frame() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            201,
            json={"id": "prediction-minimax", "status": "starting"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        submission = await client.submit_reference_to_video(
            reference_image_urls=["https://private-r2.example/person.jpg?signed=1"],
            prompt="A single adult person performs a natural full-body dance.",
            duration=5,
            model=MINIMAX_VIDEO_01_MODEL,
        )

    assert submission.provider_task_id == "prediction-minimax"
    assert captured_request is not None
    assert captured_request.url.path == (
        "/v1/models/minimax/video-01/predictions"
    )
    assert json.loads(captured_request.content)["input"] == {
        "prompt": "A single adult person performs a natural full-body dance.",
        "prompt_optimizer": True,
        "first_frame_image": "https://private-r2.example/person.jpg?signed=1",
    }


@pytest.mark.anyio
async def test_minimax_video_01_rejects_ten_second_product_request() -> None:
    async with httpx.AsyncClient() as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        with pytest.raises(ValueError, match="five-second"):
            await client.submit_reference_to_video(
                reference_image_urls=["https://private-r2.example/person.jpg"],
                prompt="The person dances.",
                duration=10,
                model=MINIMAX_VIDEO_01_MODEL,
            )


@pytest.mark.anyio
async def test_seedance_candidate_accepts_two_images_and_fifteen_seconds() -> None:
    captured_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == ("/v1/models/bytedance/seedance-2.0/predictions")
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            201,
            json={"id": "prediction-seedance", "status": "starting"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        submission = await client.submit_reference_to_video(
            reference_image_urls=[
                "https://private-oss.example/person-a.jpg",
                "https://private-oss.example/person-b.jpg",
            ],
            prompt="[Image1] and [Image2] hold hands and walk toward the camera.",
            duration=15,
            model=SEEDANCE_R2V_MODEL,
        )

    assert submission.provider_task_id == "prediction-seedance"
    assert captured_payload["input"] == {
        "prompt": "[Image1] and [Image2] hold hands and walk toward the camera.",
        "reference_images": [
            "https://private-oss.example/person-a.jpg",
            "https://private-oss.example/person-b.jpg",
        ],
        "reference_videos": [],
        "reference_audios": [],
        "duration": 15,
        "resolution": "720p",
        "aspect_ratio": "9:16",
        "generate_audio": True,
    }


@pytest.mark.anyio
async def test_submit_image_to_motion_maps_template_video_and_audio() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            201,
            json={"id": "prediction-animate", "status": "processing"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        submission = await client.submit_image_to_motion(
            image_url="https://private-oss.example/person.jpg",
            action_video_url="https://private-oss.example/dance-10s.mp4",
            seed=456,
        )

    assert submission.status == VideoTaskStatus.RUNNING
    assert captured_request is not None
    assert captured_request.url.path == (
        "/v1/models/wan-video/wan-2.2-animate-animation/predictions"
    )
    assert json.loads(captured_request.content)["input"] == {
        "video": "https://private-oss.example/dance-10s.mp4",
        "character_image": "https://private-oss.example/person.jpg",
        "resolution": "720",
        "frames_per_second": 24,
        "merge_audio": True,
        "go_fast": True,
        "refert_num": 1,
        "seed": 456,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [
        ("starting", VideoTaskStatus.PENDING),
        ("processing", VideoTaskStatus.RUNNING),
        ("succeeded", VideoTaskStatus.SUCCEEDED),
        ("failed", VideoTaskStatus.FAILED),
        ("canceled", VideoTaskStatus.CANCELED),
        ("unexpected", VideoTaskStatus.UNKNOWN),
    ],
)
async def test_get_task_normalizes_prediction_statuses(
    provider_status: str,
    expected_status: VideoTaskStatus,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "prediction-result",
                "status": provider_status,
                "output": "https://replicate.delivery/output.mp4",
                "error": None,
                "metrics": {"predict_time": 12.5},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        result = await client.get_task("prediction-result")

    assert result.status == expected_status
    assert result.output_url == "https://replicate.delivery/output.mp4"
    assert result.metrics == {"predict_time": 12.5}


@pytest.mark.anyio
async def test_api_error_preserves_status_and_prediction_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "id": "prediction-error",
                "detail": "Input validation failed.",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        with pytest.raises(ReplicateAPIError) as exc_info:
            await client.get_task("prediction-error")

    assert exc_info.value.status_code == 422
    assert exc_info.value.prediction_id == "prediction-error"
    assert str(exc_info.value) == "Input validation failed."


@pytest.mark.anyio
async def test_cancel_task_uses_prediction_cancel_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/predictions/prediction-cancel/cancel"
        return httpx.Response(
            200,
            json={
                "id": "prediction-cancel",
                "status": "canceled",
                "output": None,
                "error": None,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        result = await client.cancel_task("prediction-cancel")

    assert result.status == VideoTaskStatus.CANCELED


@pytest.mark.anyio
async def test_local_relative_asset_url_is_rejected_before_paid_request() -> None:
    async with httpx.AsyncClient() as http_client:
        client = ReplicateVideoClient(
            api_token="test-token",
            http_client=http_client,
        )
        with pytest.raises(ValueError, match="provider-readable"):
            await client.submit_image_to_motion(
                image_url="/uploads/images/person.jpg",
                action_video_url="https://private-oss.example/dance.mp4",
            )
