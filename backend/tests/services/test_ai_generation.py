import json
import uuid
from pathlib import Path

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
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_API_BASE_URL", "https://ark.example.com/api/v3")
    monkeypatch.setattr(settings, "ARK_SEEDANCE_MODEL", "seedance-test")
    monkeypatch.setattr(settings, "APP_PUBLIC_BASE_URL", None)
    monkeypatch.setattr(settings, "LOCAL_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_TIMEOUT_SECONDS", 1.0)
    first_image_path = tmp_path / "images" / "u" / "first.png"
    second_image_path = tmp_path / "images" / "u" / "second.png"
    first_image_path.parent.mkdir(parents=True)
    first_image_path.write_bytes(b"\x89PNG\r\n\x1a\nfirst")
    second_image_path.write_bytes(b"\x89PNG\r\n\x1a\nsecond")
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
            assert payload["content"][1] == {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgpmaXJzdA=="
                },
                "role": "reference_image",
            }
            assert payload["content"][2] == {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgpzZWNvbmQ="
                },
                "role": "reference_image",
            }
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
    result = provider.generate(
        make_generation(
            kind="video",
            reference_image_url="/uploads/images/u/first.png",
            character_image_url="/uploads/images/u/second.png",
        )
    )

    assert result.provider_task_id == "video-task-1"
    assert result.output_url == "https://result.example.com/video.mp4"


def test_ark_provider_uses_public_base_url_for_local_upload_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_API_BASE_URL", "https://ark.example.com/api/v3")
    monkeypatch.setattr(settings, "ARK_SEEDANCE_MODEL", "seedance-test")
    monkeypatch.setattr(settings, "APP_PUBLIC_BASE_URL", "https://app.example.com")
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "ARK_VIDEO_POLL_TIMEOUT_SECONDS", 1.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["content"][1] == {
                "type": "image_url",
                "image_url": {"url": "https://app.example.com/uploads/images/u/file.png"},
                "role": "reference_image",
            }
            return httpx.Response(200, json={"id": "video-task-1"})
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
    result = provider.generate(
        make_generation(
            kind="video",
            reference_image_url="/uploads/images/u/file.png",
        )
    )

    assert result.output_url == "https://result.example.com/video.mp4"


def test_ark_provider_rejects_missing_local_upload_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "APP_PUBLIC_BASE_URL", None)
    provider = ArkAIGenerationProvider()

    with pytest.raises(AIGenerationProviderError) as exc_info:
        provider.generate(
            make_generation(
                kind="image",
                reference_image_url="/uploads/images/u/missing.png",
            )
        )

    assert exc_info.value.detail == "Local uploaded image file does not exist"


def test_get_ai_generation_provider_selects_ark() -> None:
    assert isinstance(get_ai_generation_provider("ark"), ArkAIGenerationProvider)
