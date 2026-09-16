import base64
import hashlib
import hmac
import json
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.api.routes import app_video_tasks as app_video_tasks_module
from app.core.config import settings
from app.models import AppUpload, AppVideoTask, AppVideoTaskWebhookEvent
from app.services.replicate_video import ReplicateAPIError
from app.services.storage import StoredVideo
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


class FakeVideoStorage:
    def __init__(self) -> None:
        self.stored_content: bytes | None = None
        self.stored_object_key: str | None = None

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
