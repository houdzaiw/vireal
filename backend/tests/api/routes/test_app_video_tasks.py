import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.api.routes import app_video_tasks as app_video_tasks_module
from app.core.config import settings
from app.models import AppUpload, AppVideoTask, AppVideoTaskWebhookEvent
from app.services.replicate_video import (
    ReplicateAPIError,
    ReplicateConfigurationError,
)
from app.services.storage import ImageStorageError, StoredVideo
from app.services.video_generation import VideoTaskStatus, VideoTaskSubmission
from app.workers.video_tasks import process_next_video_task
from tests.utils.app_user import app_authentication_headers

PNG_BYTES = b"\x89PNG\r\n\x1a\nvideo-task-test-image"
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


class FakeProvider:
    def __init__(
        self,
        *,
        timeout: bool = False,
        api_error: ReplicateAPIError | None = None,
    ) -> None:
        self.timeout = timeout
        self.api_error = api_error
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def submit_reference_to_video(self, **kwargs: Any) -> VideoTaskSubmission:
        self.calls.append(kwargs)
        if self.timeout:
            raise httpx.ReadTimeout(
                "submission timed out",
                request=httpx.Request(
                    "POST", "https://api.replicate.com/v1/predictions"
                ),
            )
        if self.api_error is not None:
            raise self.api_error
        return VideoTaskSubmission(
            provider_task_id=f"prediction-poc-{len(self.calls)}",
            status=VideoTaskStatus.PENDING,
        )

    async def aclose(self) -> None:
        self.closed = True


class RaisingProvider(FakeProvider):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def submit_reference_to_video(self, **kwargs: Any) -> VideoTaskSubmission:
        self.calls.append(kwargs)
        raise self.error


class FakeVideoStorage:
    def __init__(self) -> None:
        self.stored_content: bytes | None = None
        self.stored_object_key: str | None = None
        self.deleted: list[str] = []

    def store_video_file(
        self,
        *,
        app_user_id: Any,
        task_id: Any,
        file_path: Path,
        content_type: str,
    ) -> StoredVideo:
        assert content_type == "video/mp4"
        self.stored_content = file_path.read_bytes()
        self.stored_object_key = f"vireal/videos/{app_user_id}/{task_id}.mp4"
        return StoredVideo(
            object_key=self.stored_object_key,
            content_type=content_type,
            size=len(self.stored_content),
        )

    def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
        assert object_key == self.stored_object_key
        assert expires_in == settings.R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS
        return "https://private-r2.example/video.mp4?signed=1"

    def delete_object(self, object_key: str) -> None:
        self.deleted.append(object_key)


def _enable_mock_replicate(
    monkeypatch: pytest.MonkeyPatch,
    provider: FakeProvider,
) -> str:
    signing_key = base64.b64encode(b"integration-signing-key").decode().rstrip("=")
    secret = f"whsec_{signing_key}"
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "REPLICATE_WEBHOOK_URL",
        "https://api.example.com/api/v1/webhooks/replicate",
    )
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_SIGNING_SECRET", secret)
    monkeypatch.setattr(settings, "REPLICATE_POC_MAX_SUBMISSIONS", 100)
    monkeypatch.setattr(
        app_video_tasks_module,
        "get_replicate_video_client",
        lambda: provider,
    )
    return secret


def _upload_image(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        f"{settings.API_V1_STR}/app/uploads/images",
        headers=headers,
        files={"file": ("person.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200
    return response.json()


def _webhook_headers(secret: str, body: bytes, webhook_id: str) -> dict[str, str]:
    timestamp = int(time.time())
    encoded_key = secret.removeprefix("whsec_")
    encoded_key += "=" * (-len(encoded_key) % 4)
    signed = f"{webhook_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(
        hmac.new(base64.b64decode(encoded_key), signed, hashlib.sha256).digest()
    ).decode()
    return {
        "Content-Type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": f"v1,{signature}",
    }


def _publish_effect(
    *,
    client: TestClient,
    admin_headers: dict[str, str],
    effect: dict[str, Any],
    input_image_count: int,
    model: str,
    duration_seconds: int,
    coin_cost: int,
) -> dict[str, Any]:
    update = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=admin_headers,
        json={
            "category_id": effect["category_id"],
            "slug": effect["slug"],
            "title_zh": effect["title_zh"],
            "title_en": effect["title_en"],
            "description": "End-to-end generation test effect",
            "input_image_count": input_image_count,
            "poster_asset_id": None,
            "preview_asset_id": None,
            "sort_order": effect["sort_order"],
            "is_enabled": True,
            "recommendation_label": None,
            "recommendation_ids": [],
        },
    )
    assert update.status_code == 200
    variant = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
        headers=admin_headers,
        json={
            "duration_seconds": duration_seconds,
            "coin_cost": coin_cost,
            "provider": "replicate",
            "model": model,
            "model_type": "reference-to-video",
            "prompt": "Create a safe natural cinematic moment.",
            "negative_prompt": "blur, distortion",
            "prompt_version": "test-v1",
            "is_default": True,
            "is_enabled": True,
        },
    )
    assert variant.status_code == 200
    published = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
        headers=admin_headers,
    )
    assert published.status_code == 200
    return {"effect": published.json(), "variant": variant.json()}


def _grant_coins(
    *,
    client: TestClient,
    admin_headers: dict[str, str],
    app_user_id: str,
    amount: int,
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=admin_headers,
        json={
            "app_user_id": app_user_id,
            "delta": amount,
            "reason": "Video task end-to-end test grant",
            "idempotency_key": f"video-test-grant-{uuid.uuid4()}",
        },
    )
    assert response.status_code == 200


def test_effect_task_double_image_debit_idempotency_concurrency_and_refund(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    superuser_token_headers: dict[str, str],
) -> None:
    provider = FakeProvider()
    secret = _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    monkeypatch.setattr(settings, "APP_USER_MAX_CONCURRENT_VIDEO_TASKS", 1)

    category_slug = f"task-flow-{uuid.uuid4().hex[:10]}"
    category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json={
            "slug": category_slug,
            "name_zh": "任务测试",
            "name_en": "TASK FLOW",
            "tones": ["#123456", "#345678", "#abcdef"],
            "sort_order": 999,
            "is_enabled": True,
        },
    )
    assert category.status_code == 200
    effects = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category.json()["id"]},
        headers=superuser_token_headers,
    ).json()["data"]
    configured = _publish_effect(
        client=client,
        admin_headers=superuser_token_headers,
        effect=effects[0],
        input_image_count=2,
        model="wan-video/wan-2.7-r2v",
        duration_seconds=5,
        coin_cost=12,
    )

    headers, login = app_authentication_headers(client=client)
    app_user_id = str(login["app_user"]["id"])
    _grant_coins(
        client=client,
        admin_headers=superuser_token_headers,
        app_user_id=app_user_id,
        amount=30,
    )
    first_upload = _upload_image(client, headers)
    second_upload = _upload_image(client, headers)
    body = {
        "effect_id": configured["effect"]["id"],
        "variant_id": configured["variant"]["id"],
        "upload_ids": [first_upload["id"], second_upload["id"]],
    }

    wrong_image_count = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "effect-wrong-image-count"},
        json={**body, "upload_ids": [first_upload["id"]]},
    )
    assert wrong_image_count.status_code == 422

    request_headers = {**headers, "Idempotency-Key": "effect-double-image-task"}
    created = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers=request_headers,
        json=body,
    )
    duplicate = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers=request_headers,
        json=body,
    )
    assert created.status_code == 202
    assert created.json()["coin_cost"] == 12
    assert created.json()["balance"] == 18
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == created.json()["id"]
    assert duplicate.json()["balance"] == 18
    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == "wan-video/wan-2.7-r2v"
    assert provider.calls[0]["reference_image_urls"] == [
        first_upload["url"],
        second_upload["url"],
    ]

    concurrent = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "effect-concurrent-task"},
        json=body,
    )
    assert concurrent.status_code == 409
    wallet_before_refund = client.get(
        f"{settings.API_V1_STR}/app/wallet", headers=headers
    ).json()
    assert wallet_before_refund["balance"] == 18

    webhook_body = json.dumps(
        {
            "id": "prediction-poc-1",
            "status": "failed",
            "output": None,
            "error": "provider generation failed",
        },
        separators=(",", ":"),
    ).encode()
    webhook_path = (
        f"{settings.API_V1_STR}/webhooks/replicate?task_id={created.json()['id']}"
    )
    for _ in range(2):
        response = client.post(
            webhook_path,
            content=webhook_body,
            headers=_webhook_headers(secret, webhook_body, "effect-failed-event"),
        )
        assert response.status_code == 204

    wallet_after_refund = client.get(
        f"{settings.API_V1_STR}/app/wallet", headers=headers
    ).json()
    assert wallet_after_refund["balance"] == 30
    assert [item["entry_type"] for item in wallet_after_refund["ledger"]].count(
        "generation_refund"
    ) == 1

    single_image = _publish_effect(
        client=client,
        admin_headers=superuser_token_headers,
        effect=effects[1],
        input_image_count=1,
        model="minimax/video-01",
        duration_seconds=5,
        coin_cost=7,
    )
    single_headers, single_login = app_authentication_headers(client=client)
    _grant_coins(
        client=client,
        admin_headers=superuser_token_headers,
        app_user_id=str(single_login["app_user"]["id"]),
        amount=20,
    )
    single_upload = _upload_image(client, single_headers)
    extra_upload = _upload_image(client, single_headers)
    single_body = {
        "effect_id": single_image["effect"]["id"],
        "variant_id": single_image["variant"]["id"],
        "upload_ids": [single_upload["id"]],
    }
    too_many_images = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**single_headers, "Idempotency-Key": "effect-too-many-images"},
        json={
            **single_body,
            "upload_ids": [single_upload["id"], extra_upload["id"]],
        },
    )
    single_created = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**single_headers, "Idempotency-Key": "effect-single-image-task"},
        json=single_body,
    )
    assert too_many_images.status_code == 422
    assert single_created.status_code == 202
    assert single_created.json()["coin_cost"] == 7
    assert single_created.json()["balance"] == 13
    assert len(provider.calls) == 2
    assert provider.calls[1]["model"] == "minimax/video-01"
    assert provider.calls[1]["reference_image_urls"] == [single_upload["url"]]

    disabled_category = client.put(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{category.json()['id']}",
        headers=superuser_token_headers,
        json={
            "slug": category_slug,
            "name_zh": "任务测试",
            "name_en": "TASK FLOW",
            "tones": ["#123456", "#345678", "#abcdef"],
            "sort_order": 999,
            "is_enabled": False,
        },
    )
    unavailable = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "effect-disabled-category"},
        json=body,
    )
    assert disabled_category.status_code == 200
    assert unavailable.status_code == 409


def test_mocked_upload_prediction_webhook_worker_and_playback_flow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    secret = _enable_mock_replicate(monkeypatch, provider)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    idempotency_key = "h5-integration-poc-1"

    create_response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 5,
        },
    )

    assert create_response.status_code == 202
    created = create_response.json()
    assert created["status"] == "pending"
    assert created["mode"] == "advanced"
    assert created["execution_type"] == "wan"
    assert created["is_demo"] is False
    assert created["resolution"] == "720p"
    assert created["aspect_ratio"] == "9:16"
    assert len(provider.calls) == 1
    assert provider.calls[0]["duration"] == 5
    assert provider.calls[0]["reference_image_urls"] == [upload["url"]]
    assert provider.calls[0]["webhook_url"].endswith(f"task_id={created['id']}")

    duplicate_response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 5,
        },
    )
    assert duplicate_response.status_code == 202
    assert duplicate_response.json()["id"] == created["id"]
    assert len(provider.calls) == 1
    conflicting_response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 10,
        },
    )
    assert conflicting_response.status_code == 409
    assert len(provider.calls) == 1

    webhook_body = json.dumps(
        {
            "id": "prediction-poc-1",
            "status": "succeeded",
            "output": "https://replicate.delivery/generated.mp4",
            "error": None,
            "metrics": {"predict_time": 12.5},
        },
        separators=(",", ":"),
    ).encode()
    webhook_path = f"{settings.API_V1_STR}/webhooks/replicate?task_id={created['id']}"
    webhook_response = client.post(
        webhook_path,
        content=webhook_body,
        headers=_webhook_headers(secret, webhook_body, "event-completed-1"),
    )
    duplicate_webhook_response = client.post(
        webhook_path,
        content=webhook_body,
        headers=_webhook_headers(secret, webhook_body, "event-completed-1"),
    )
    assert webhook_response.status_code == 204
    assert duplicate_webhook_response.status_code == 204

    late_running_body = json.dumps(
        {"id": "prediction-poc-1", "status": "processing"},
        separators=(",", ":"),
    ).encode()
    late_running_response = client.post(
        webhook_path,
        content=late_running_body,
        headers=_webhook_headers(secret, late_running_body, "event-late-running"),
    )
    assert late_running_response.status_code == 204
    saving_response = client.get(
        f"{settings.API_V1_STR}/app/video-tasks/{created['id']}",
        headers=headers,
    )
    assert saving_response.json()["status"] == "saving"

    storage = FakeVideoStorage()

    def output_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://replicate.delivery/generated.mp4"
        return httpx.Response(
            200,
            content=MP4_BYTES,
            headers={"Content-Type": "video/mp4"},
        )

    with httpx.Client(transport=httpx.MockTransport(output_handler)) as http_client:
        assert process_next_video_task(storage=storage, http_client=http_client) is True
    assert storage.stored_content == MP4_BYTES

    monkeypatch.setattr(app_video_tasks_module, "get_image_storage", lambda: storage)
    task_response = client.get(
        f"{settings.API_V1_STR}/app/video-tasks/{created['id']}",
        headers=headers,
    )
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "succeeded"
    assert task_response.json()["playback_url"].startswith(
        "https://private-r2.example/"
    )

    other_headers, _other_login = app_authentication_headers(client=client)
    forbidden_response = client.get(
        f"{settings.API_V1_STR}/app/video-tasks/{created['id']}",
        headers=other_headers,
    )
    assert forbidden_response.status_code == 404


def test_submission_timeout_is_not_retried(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(timeout=True)
    _enable_mock_replicate(monkeypatch, provider)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    request_headers = {**headers, "Idempotency-Key": "h5-timeout-no-retry"}
    request_body = {
        "template_id": "dance",
        "upload_ids": [upload["id"]],
        "duration": 5,
    }

    first = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers=request_headers,
        json=request_body,
    )
    second = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers=request_headers,
        json=request_body,
    )

    assert first.status_code == 202
    assert first.json()["status"] == "submission_unknown"
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert len(provider.calls) == 1


def test_video_task_rejects_unowned_upload_and_fifteen_seconds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    owner_headers, _owner_login = app_authentication_headers(client=client)
    other_headers, _other_login = app_authentication_headers(client=client)
    upload = _upload_image(client, owner_headers)

    unowned = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**other_headers, "Idempotency-Key": "h5-unowned-upload"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 5,
        },
    )
    invalid_duration = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**owner_headers, "Idempotency-Key": "h5-invalid-duration"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 15,
        },
    )

    assert unowned.status_code == 400
    assert invalid_duration.status_code == 422
    assert provider.calls == []


def test_video_task_enforces_poc_submission_ceiling(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "REPLICATE_POC_MAX_SUBMISSIONS", 1)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)

    accepted = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-poc-budget-first"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 5,
        },
    )
    response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-poc-budget-limit"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "duration": 5,
        },
    )

    assert accepted.status_code == 202
    assert response.status_code == 202
    assert response.json()["status"] == "rendering_demo"
    assert response.json()["execution_type"] == "local_demo"
    assert response.json()["fallback_reason"] == "poc_submission_limit"
    assert len(provider.calls) == 1


def test_provider_rejection_without_prediction_does_not_consume_poc_budget(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(
        api_error=ReplicateAPIError(
            message="Insufficient credit",
            status_code=402,
        )
    )
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "REPLICATE_POC_MAX_SUBMISSIONS", 1)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    body = {
        "template_id": "dance",
        "upload_ids": [upload["id"]],
        "duration": 5,
    }

    rejected = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-credit-rejected"},
        json=body,
    )
    assert rejected.status_code == 202
    assert rejected.json()["status"] == "rendering_demo"
    assert rejected.json()["execution_type"] == "local_demo"
    assert rejected.json()["fallback_reason"] == "provider_insufficient_credit"

    provider.api_error = None
    accepted = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-after-credit-added"},
        json=body,
    )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "pending"
    assert len(provider.calls) == 2


def test_standard_mode_uses_minimax_and_rejects_ten_seconds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)

    created = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-standard-minimax"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "standard",
            "duration": 5,
        },
    )
    invalid = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-standard-invalid-duration"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "standard",
            "duration": 10,
        },
    )

    assert created.status_code == 202
    assert created.json()["mode"] == "standard"
    assert created.json()["execution_type"] == "minimax"
    assert created.json()["is_demo"] is False
    assert provider.calls[0]["model"] == settings.REPLICATE_STANDARD_MODEL
    assert invalid.status_code == 422
    assert len(provider.calls) == 1


def test_disabled_replicate_routes_to_local_demo_without_provider_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", False)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", True)
    monkeypatch.setattr(
        app_video_tasks_module,
        "get_replicate_video_client",
        lambda: pytest.fail("Replicate client must not be created for local demo"),
    )
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)

    response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-disabled-local-demo"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "standard",
            "duration": 5,
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "rendering_demo"
    assert response.json()["execution_type"] == "local_demo"
    assert response.json()["is_demo"] is True
    assert response.json()["fallback_reason"] == "replicate_disabled"


def test_user_daily_real_quota_is_shared_by_both_modes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "APP_USER_DAILY_REAL_SUBMISSIONS", 1)
    monkeypatch.setattr(settings, "APP_WAN_DAILY_GLOBAL_SUBMISSIONS", 10)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)

    first = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-user-quota-first"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "standard",
            "duration": 5,
        },
    )
    second = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-user-quota-second"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    )

    assert first.json()["execution_type"] == "minimax"
    assert second.json()["execution_type"] == "local_demo"
    assert second.json()["fallback_reason"] == "user_daily_quota"
    assert len(provider.calls) == 1


def test_wan_daily_global_quota_applies_across_users(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "APP_USER_DAILY_REAL_SUBMISSIONS", 5)
    monkeypatch.setattr(settings, "APP_WAN_DAILY_GLOBAL_SUBMISSIONS", 1)
    first_headers, _login = app_authentication_headers(client=client)
    second_headers, _other_login = app_authentication_headers(client=client)
    first_upload = _upload_image(client, first_headers)
    second_upload = _upload_image(client, second_headers)

    first = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**first_headers, "Idempotency-Key": "h5-wan-global-first"},
        json={
            "template_id": "dance",
            "upload_ids": [first_upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    )
    second = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**second_headers, "Idempotency-Key": "h5-wan-global-second"},
        json={
            "template_id": "dance",
            "upload_ids": [second_upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    )

    assert first.json()["execution_type"] == "wan"
    assert second.json()["execution_type"] == "local_demo"
    assert second.json()["fallback_reason"] == "wan_daily_global_quota"
    assert len(provider.calls) == 1


def test_failed_provider_webhook_routes_existing_task_to_local_demo(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    secret = _enable_mock_replicate(monkeypatch, provider)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    created = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "h5-webhook-fallback"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    ).json()
    webhook_body = json.dumps(
        {
            "id": "prediction-poc-1",
            "status": "failed",
            "output": None,
            "error": "provider capacity exhausted",
        },
        separators=(",", ":"),
    ).encode()

    webhook_response = client.post(
        f"{settings.API_V1_STR}/webhooks/replicate?task_id={created['id']}",
        content=webhook_body,
        headers=_webhook_headers(secret, webhook_body, "event-fallback-1"),
    )
    task_response = client.get(
        f"{settings.API_V1_STR}/app/video-tasks/{created['id']}",
        headers=headers,
    )

    assert webhook_response.status_code == 204
    assert task_response.json()["status"] == "rendering_demo"
    assert task_response.json()["execution_type"] == "local_demo"
    assert task_response.json()["is_demo"] is True
    assert task_response.json()["fallback_reason"] == "provider_failed"


def test_video_task_request_guards_list_and_delete_flow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    body = {
        "template_id": "dance",
        "upload_ids": [upload["id"]],
        "mode": "standard",
        "duration": 5,
    }
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", False)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    disabled = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "disabled-provider"},
        json=body,
    )
    assert disabled.status_code == 503

    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", True)
    invalid_key = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "short"},
        json=body,
    )
    assert invalid_key.status_code == 422
    created = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "local-list-delete"},
        json=body,
    )
    assert created.status_code == 202
    task_id = created.json()["id"]
    listing = client.get(
        f"{settings.API_V1_STR}/app/video-tasks?skip=0&limit=999",
        headers=headers,
    )
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["data"][0]["id"] == task_id
    active_delete = client.delete(
        f"{settings.API_V1_STR}/app/video-tasks/{task_id}", headers=headers
    )
    assert active_delete.status_code == 409

    task = db.get(AppVideoTask, uuid.UUID(task_id))
    assert task is not None
    task.status = "succeeded"
    task.output_object_key = f"vireal/videos/{task.app_user_id}/{task.id}.mp4"
    task.completed_at = datetime.now(UTC)
    db.add(task)
    db.commit()
    storage = FakeVideoStorage()
    storage.stored_object_key = task.output_object_key
    monkeypatch.setattr(app_video_tasks_module, "get_image_storage", lambda: storage)
    deleted = client.delete(
        f"{settings.API_V1_STR}/app/video-tasks/{task_id}", headers=headers
    )
    assert deleted.status_code == 200
    assert storage.deleted == [f"vireal/videos/{task.app_user_id}/{task.id}.mp4"]
    assert (
        client.get(f"{settings.API_V1_STR}/app/video-tasks", headers=headers).json()[
            "count"
        ]
        == 0
    )


def test_video_task_delete_and_playback_surface_storage_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    headers, login = app_authentication_headers(client=client)
    now = datetime.now(UTC)
    task = AppVideoTask(
        app_user_id=uuid.UUID(login["app_user"]["id"]),
        idempotency_key=f"storage-error-{uuid.uuid4()}",
        template_id="dance",
        upload_ids_json="[]",
        mode="standard",
        provider="replicate",
        model="minimax/video-01",
        execution_type="minimax",
        status="succeeded",
        duration=5,
        seed=1,
        output_object_key="vireal/videos/storage-error.mp4",
        completed_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    class BrokenStorage:
        def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
            del object_key, expires_in
            raise ImageStorageError("R2 signing failed", status_code=502)

        def delete_object(self, object_key: str) -> None:
            del object_key
            raise ImageStorageError("R2 delete failed", status_code=502)

    monkeypatch.setattr(
        app_video_tasks_module, "get_image_storage", lambda: BrokenStorage()
    )
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/video-tasks/{task.id}", headers=headers
        ).status_code
        == 502
    )
    assert (
        client.delete(
            f"{settings.API_V1_STR}/app/video-tasks/{task.id}", headers=headers
        ).status_code
        == 502
    )


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (
            ReplicateAPIError(
                message="provider rejected input",
                status_code=400,
                prediction_id="rejected-prediction",
            ),
            "provider rejected input",
        ),
        (ReplicateConfigurationError("provider is misconfigured"), "misconfigured"),
        (ImageStorageError("unable to sign input", status_code=502), "sign input"),
        (ValueError("invalid provider input"), "invalid provider input"),
    ],
)
def test_provider_errors_become_terminal_without_demo_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_error: str,
) -> None:
    provider = RaisingProvider(error)
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": f"error-{uuid.uuid4()}"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert expected_error in response.json()["error"]
    assert provider.closed is True


def test_missing_webhook_configuration_routes_to_local_demo(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_URL", None)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", True)
    headers, _login = app_authentication_headers(client=client)
    upload = _upload_image(client, headers)
    response = client.post(
        f"{settings.API_V1_STR}/app/video-tasks",
        headers={**headers, "Idempotency-Key": "missing-webhook-fallback"},
        json={
            "template_id": "dance",
            "upload_ids": [upload["id"]],
            "mode": "advanced",
            "duration": 5,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "rendering_demo"
    assert response.json()["fallback_reason"] == "provider_configuration_error"
    assert provider.closed is True


def test_api_error_fallback_reason_classification() -> None:
    assert (
        app_video_tasks_module._fallback_reason_for_api_error(
            ReplicateAPIError(message="limited", status_code=429)
        )
        == "provider_rate_limited"
    )
    assert (
        app_video_tasks_module._fallback_reason_for_api_error(
            ReplicateAPIError(message="down", status_code=503)
        )
        == "provider_unavailable"
    )
    assert (
        app_video_tasks_module._fallback_reason_for_api_error(
            ReplicateAPIError(message="bad", status_code=400)
        )
        is None
    )


def test_replicate_webhook_rejects_invalid_requests(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = _enable_mock_replicate(monkeypatch, FakeProvider())
    valid_payload = json.dumps(
        {"id": "prediction-missing", "status": "processing"}
    ).encode()
    assert (
        client.post(
            f"{settings.API_V1_STR}/webhooks/replicate?task_id={uuid.uuid4()}",
            content=valid_payload,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 401
    )

    cases = [
        (b"not-json", "invalid-json"),
        (b"[]", "list-payload"),
        (json.dumps({"status": "unknown"}).encode(), "missing-prediction-id"),
    ]
    for body, event_id in cases:
        response = client.post(
            f"{settings.API_V1_STR}/webhooks/replicate?task_id={uuid.uuid4()}",
            content=body,
            headers=_webhook_headers(secret, body, event_id),
        )
        assert response.status_code == 400

    missing = client.post(
        f"{settings.API_V1_STR}/webhooks/replicate?task_id={uuid.uuid4()}",
        content=valid_payload,
        headers=_webhook_headers(secret, valid_payload, "missing-task"),
    )
    assert missing.status_code == 404


def test_replicate_webhook_maps_provider_statuses_and_prediction_conflicts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    secret = _enable_mock_replicate(monkeypatch, FakeProvider())
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    _headers, login = app_authentication_headers(client=client)
    app_user_id = uuid.UUID(login["app_user"]["id"])

    def create_task(
        *, provider_task_id: str | None, idempotency_key: str
    ) -> AppVideoTask:
        now = datetime.now(UTC)
        task = AppVideoTask(
            app_user_id=app_user_id,
            idempotency_key=idempotency_key,
            template_id="dance",
            upload_ids_json="[]",
            mode="advanced",
            provider="replicate",
            model="wan-video/wan-2.7-r2v",
            execution_type="wan",
            status="pending",
            duration=5,
            seed=1,
            provider_task_id=provider_task_id,
            submission_attempted_at=now,
            expires_at=now + timedelta(hours=24),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    states = [
        ("succeeded", None, "failed"),
        ("canceled", None, "canceled"),
        ("processing", None, "running"),
        ("starting", None, "pending"),
    ]
    for index, (provider_status, output, expected_status) in enumerate(states):
        prediction_id = f"prediction-status-{index}"
        task = create_task(
            provider_task_id=None,
            idempotency_key=f"webhook-status-{index}-{uuid.uuid4()}",
        )
        body = json.dumps(
            {
                "id": prediction_id,
                "status": provider_status,
                "output": output,
                "error": "provider canceled" if provider_status == "canceled" else None,
            },
            separators=(",", ":"),
        ).encode()
        response = client.post(
            f"{settings.API_V1_STR}/webhooks/replicate?task_id={task.id}",
            content=body,
            headers=_webhook_headers(secret, body, f"status-event-{index}"),
        )
        assert response.status_code == 204
        db.expire_all()
        updated = db.get(AppVideoTask, task.id)
        assert updated is not None
        assert updated.provider_task_id == prediction_id
        assert updated.status == expected_status

    conflicting = create_task(
        provider_task_id="expected-prediction",
        idempotency_key=f"webhook-conflict-{uuid.uuid4()}",
    )
    conflict_body = json.dumps(
        {"id": "different-prediction", "status": "processing"}
    ).encode()
    conflict = client.post(
        f"{settings.API_V1_STR}/webhooks/replicate?task_id={conflicting.id}",
        content=conflict_body,
        headers=_webhook_headers(secret, conflict_body, "prediction-conflict"),
    )
    assert conflict.status_code == 409
