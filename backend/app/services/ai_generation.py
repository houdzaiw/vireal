import base64
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import unquote

import httpx
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.db import engine
from app.models import AppGeneration
from app.services.storage import detect_image_type, get_local_upload_root


@dataclass(frozen=True)
class AIGenerationResult:
    output_url: str | None = None
    error_message: str | None = None
    provider_task_id: str | None = None


class AIGenerationProviderError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        provider_task_id: str | None = None,
    ) -> None:
        self.detail = detail
        self.provider_task_id = provider_task_id
        super().__init__(detail)


class AIGenerationProvider(Protocol):
    def generate(self, generation: AppGeneration) -> AIGenerationResult:
        """Run one provider generation job and return its visible result URL."""


class LocalAIGenerationProvider:
    def generate(self, generation: AppGeneration) -> AIGenerationResult:
        time.sleep(settings.APP_GENERATION_LOCAL_DELAY_SECONDS)
        if generation.kind == "video":
            return AIGenerationResult()
        return AIGenerationResult(
            output_url=(
                generation.reference_image_url or generation.character_image_url
            ),
        )


class ArkAIGenerationProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def generate(self, generation: AppGeneration) -> AIGenerationResult:
        if not settings.ARK_API_KEY:
            raise AIGenerationProviderError(
                "ARK_API_KEY is required when APP_GENERATION_PROVIDER=ark"
            )

        if generation.kind == "image":
            return self._generate_image(generation)
        if generation.kind == "video":
            return self._generate_video(generation)
        raise AIGenerationProviderError(f"Unsupported generation kind: {generation.kind}")

    def _generate_image(self, generation: AppGeneration) -> AIGenerationResult:
        payload: dict[str, Any] = {
            "model": settings.ARK_SEEDREAM_MODEL,
            "prompt": self._build_prompt(generation),
            "response_format": "url",
            "size": self._image_size(generation.aspect_ratio),
            "watermark": False,
        }
        image_urls = self._generation_image_urls(generation)
        if image_urls:
            payload["image"] = image_urls[0] if len(image_urls) == 1 else image_urls

        data = self._request_json(
            method="POST",
            path="/images/generations",
            json_payload=payload,
            timeout=120.0,
        )
        output_url = self._extract_image_output_url(data)
        if not output_url:
            raise AIGenerationProviderError("Seedream response did not include output URL")
        return AIGenerationResult(output_url=output_url)

    def _generate_video(self, generation: AppGeneration) -> AIGenerationResult:
        payload: dict[str, Any] = {
            "model": settings.ARK_SEEDANCE_MODEL,
            "content": self._build_video_content(generation),
            "duration": generation.duration_seconds or 5,
            "ratio": generation.aspect_ratio,
            "resolution": settings.ARK_VIDEO_RESOLUTION,
        }
        data = self._request_json(
            method="POST",
            path="/contents/generations/tasks",
            json_payload=payload,
            timeout=120.0,
        )
        task_id = self._extract_task_id(data)
        if not task_id:
            raise AIGenerationProviderError("Seedance response did not include task ID")

        deadline = time.monotonic() + settings.ARK_VIDEO_POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            task_data = self._request_json(
                method="GET",
                path=f"/contents/generations/tasks/{task_id}",
                timeout=60.0,
            )
            status = str(task_data.get("status") or "").lower()
            if status in {"succeeded", "success", "completed", "done"}:
                output_url = self._extract_video_output_url(task_data)
                if not output_url:
                    raise AIGenerationProviderError(
                        "Seedance task succeeded without output URL",
                        provider_task_id=task_id,
                    )
                return AIGenerationResult(
                    output_url=output_url,
                    provider_task_id=task_id,
                )
            if status in {"failed", "error", "cancelled", "canceled", "expired"}:
                raise AIGenerationProviderError(
                    self._extract_error_message(task_data),
                    provider_task_id=task_id,
                )
            time.sleep(settings.ARK_VIDEO_POLL_INTERVAL_SECONDS)

        raise AIGenerationProviderError(
            "Seedance task polling timed out",
            provider_task_id=task_id,
        )

    def _build_prompt(self, generation: AppGeneration) -> str:
        consistency_text = "开启" if generation.consistency else "关闭"
        return (
            f"{generation.prompt}\n"
            f"风格：{generation.style}\n"
            f"画面比例：{generation.aspect_ratio}\n"
            f"人物一致性：{consistency_text}"
        )

    def _build_video_content(self, generation: AppGeneration) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": self._build_prompt(generation)}
        ]
        for image_url in self._generation_image_urls(generation):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                    "role": "reference_image",
                }
            )
        return content

    def _generation_image_urls(self, generation: AppGeneration) -> list[str]:
        image_urls = [
            generation.reference_image_url,
            generation.character_image_url,
        ]
        return [
            absolute_url
            for image_url in image_urls
            if image_url
            for absolute_url in [self._absolute_url(image_url)]
        ]

    def _absolute_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("/uploads/") and settings.APP_PUBLIC_BASE_URL:
            return f"{settings.APP_PUBLIC_BASE_URL.rstrip('/')}{url}"
        if url.startswith("/uploads/"):
            return self._local_upload_data_url(url)
        raise AIGenerationProviderError(
            "APP_PUBLIC_BASE_URL is required for local upload references in ark mode"
        )

    @staticmethod
    def _local_upload_data_url(url: str) -> str:
        upload_root = get_local_upload_root().resolve()
        relative_upload_path = Path(unquote(url.removeprefix("/uploads/")))
        if relative_upload_path.is_absolute() or ".." in relative_upload_path.parts:
            raise AIGenerationProviderError("Invalid local upload URL")

        upload_path = (upload_root / relative_upload_path).resolve()
        try:
            upload_path.relative_to(upload_root)
        except ValueError as exc:
            raise AIGenerationProviderError("Invalid local upload URL") from exc
        if not upload_path.is_file():
            raise AIGenerationProviderError("Local uploaded image file does not exist")

        content = upload_path.read_bytes()
        detected = detect_image_type(content)
        if detected is None:
            raise AIGenerationProviderError("Local uploaded file must be an image")
        content_type, _extension = detected
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def _request_json(
        self,
        *,
        method: Literal["GET", "POST"],
        path: str,
        json_payload: dict[str, Any] | None = None,
        timeout: float,
    ) -> dict[str, Any]:
        client = self.client or httpx.Client(timeout=timeout)
        should_close_client = self.client is None
        try:
            response = client.request(
                method,
                f"{settings.ARK_API_BASE_URL.rstrip('/')}{path}",
                headers={
                    "Authorization": f"Bearer {settings.ARK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=json_payload,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise AIGenerationProviderError("Ark API response must be JSON") from exc
            if not isinstance(data, dict):
                raise AIGenerationProviderError("Ark API response must be an object")
            return data
        except httpx.HTTPStatusError as exc:
            raise AIGenerationProviderError(
                self._extract_response_error_message(exc.response)
            ) from exc
        except httpx.HTTPError as exc:
            raise AIGenerationProviderError(str(exc)) from exc
        finally:
            if should_close_client:
                client.close()

    @staticmethod
    def _image_size(aspect_ratio: str) -> str:
        sizes = {
            "1:1": "1024x1024",
            "9:16": "768x1365",
            "16:9": "1365x768",
            "3:4": "864x1152",
            "4:3": "1152x864",
        }
        return sizes.get(aspect_ratio, "1024x1024")

    @staticmethod
    def _extract_task_id(data: dict[str, Any]) -> str | None:
        raw_task_id = data.get("id") or data.get("task_id")
        return str(raw_task_id) if raw_task_id else None

    @staticmethod
    def _extract_image_output_url(data: dict[str, Any]) -> str | None:
        raw_items = data.get("data")
        if not isinstance(raw_items, list) or not raw_items:
            return None
        first_item = raw_items[0]
        if not isinstance(first_item, dict):
            return None
        raw_url = first_item.get("url")
        return str(raw_url) if raw_url else None

    @staticmethod
    def _extract_video_output_url(data: dict[str, Any]) -> str | None:
        raw_content = data.get("content")
        if isinstance(raw_content, dict):
            raw_video_url = raw_content.get("video_url") or raw_content.get("url")
            if raw_video_url:
                return str(raw_video_url)
        raw_video_url = data.get("video_url") or data.get("url")
        return str(raw_video_url) if raw_video_url else None

    @staticmethod
    def _extract_error_message(data: Any) -> str:
        if not isinstance(data, dict):
            return "Ark API request failed"
        raw_error = data.get("error")
        if isinstance(raw_error, dict):
            raw_message = raw_error.get("message") or raw_error.get("code")
            if raw_message:
                return str(raw_message)
        raw_message = data.get("message") or data.get("detail")
        return str(raw_message) if raw_message else "Ark API request failed"

    @classmethod
    def _extract_response_error_message(cls, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:500] or "Ark API request failed"
        return cls._extract_error_message(data)


def get_ai_generation_provider(provider_name: str | None = None) -> AIGenerationProvider:
    provider = provider_name or settings.APP_GENERATION_PROVIDER
    if provider == "ark":
        return ArkAIGenerationProvider()
    return LocalAIGenerationProvider()


def run_generation(
    generation_id: uuid.UUID,
    provider: AIGenerationProvider | None = None,
) -> None:
    with Session(engine) as session:
        generation = session.get(AppGeneration, generation_id)
        if not generation or generation.deleted_at is not None:
            return

        try:
            result = (provider or get_ai_generation_provider()).generate(generation)
        except Exception as exc:  # pragma: no cover - provider-specific fallback
            crud.update_app_generation_result(
                session=session,
                generation_id=generation_id,
                status="failed",
                error_message=getattr(exc, "detail", str(exc))[:500],
                provider_task_id=getattr(exc, "provider_task_id", None),
            )
            return

        if result.error_message:
            crud.update_app_generation_result(
                session=session,
                generation_id=generation_id,
                status="failed",
                error_message=result.error_message,
                provider_task_id=result.provider_task_id,
            )
            return

        crud.update_app_generation_result(
            session=session,
            generation_id=generation_id,
            status="succeeded",
            output_url=result.output_url,
            provider_task_id=result.provider_task_id,
        )


def enqueue_generation(generation_id: uuid.UUID) -> None:
    worker = threading.Thread(
        target=run_generation,
        args=(generation_id,),
        daemon=True,
        name=f"app-generation-{generation_id}",
    )
    worker.start()
