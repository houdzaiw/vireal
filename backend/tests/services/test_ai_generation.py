import json
import uuid

import httpx
import pytest

from app.core.config import settings
from app.models import AppGeneration
from app.services.ai_generation import (
    AIGenerationProviderError,
    ArkAIGenerationProvider,
    get_ai_generation_provider,
)


def make_generation(
    *,
    kind: str,
    reference_image_url: str | None = None,
    character_image_url: str | None = None,
) -> AppGeneration:
    return AppGeneration(
        app_user_id=uuid.uuid4(),
        kind=kind,
        model="Seed test",
        provider="ark",
        prompt="写实社交头像",
        style="写实",
        aspect_ratio="1:1",
        duration_seconds=5,
        consistency=True,
        reference_image_url=reference_image_url,
        character_image_url=character_image_url,
    )


def test_ark_image_generation_posts_seedream_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_API_BASE_URL", "https://ark.example.com/api/v3")
    monkeypatch.setattr(settings, "ARK_SEEDREAM_MODEL", "seedream-test")
    monkeypatch.setattr(settings, "APP_PUBLIC_BASE_URL", "https://app.example.com")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v3/images/generations"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "seedream-test"
        assert payload["response_format"] == "url"
        assert payload["size"] == "1024x1024"
        assert payload["image"] == "https://app.example.com/uploads/images/u/file.png"
        return httpx.Response(
            200,
            json={"data": [{"url": "https://result.example.com/image.png"}]},
        )

    provider = ArkAIGenerationProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        make_generation(
            kind="image",
            reference_image_url="/uploads/images/u/file.png",
        )
    )

    assert result.output_url == "https://result.example.com/image.png"


def test_ark_video_generation_creates_and_polls_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_API_BASE_URL", "https://ark.example.com/api/v3")
    monkeypatch.setattr(settings, "ARK_SEEDANCE_MODEL", "seedance-test")
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_TIMEOUT_SECONDS", 1.0)
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if request.method == "POST":
            assert request.url.path == "/api/v3/contents/generations/tasks"
            payload = json.loads(request.content)
            assert payload["model"] == "seedance-test"
            assert payload["duration"] == 5
            assert payload["ratio"] == "1:1"
            assert payload["content"][0]["type"] == "text"
            return httpx.Response(200, json={"id": "video-task-1"})

        poll_count += 1
        assert request.method == "GET"
        assert request.url.path == "/api/v3/contents/generations/tasks/video-task-1"
        if poll_count == 1:
            return httpx.Response(200, json={"status": "processing"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "content": {"video_url": "https://result.example.com/video.mp4"},
            },
        )

    provider = ArkAIGenerationProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(make_generation(kind="video"))

    assert result.provider_task_id == "video-task-1"
    assert result.output_url == "https://result.example.com/video.mp4"


def test_ark_provider_requires_public_base_url_for_local_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "APP_PUBLIC_BASE_URL", None)
    provider = ArkAIGenerationProvider()

    with pytest.raises(AIGenerationProviderError) as exc_info:
        provider.generate(
            make_generation(
                kind="image",
                reference_image_url="/uploads/images/u/file.png",
            )
        )

    assert (
        exc_info.value.detail
        == "APP_PUBLIC_BASE_URL is required for local upload references in ark mode"
    )


def test_get_ai_generation_provider_selects_ark() -> None:
    assert isinstance(get_ai_generation_provider("ark"), ArkAIGenerationProvider)
