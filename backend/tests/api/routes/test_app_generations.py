import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import AppGeneration
from app.services import ai_generation
from tests.utils.app_user import app_authentication_headers


@pytest.fixture(autouse=True)
def pause_generation_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    def skip_enqueue(_generation_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(ai_generation, "enqueue_generation", skip_enqueue)


class ImmediateProvider:
    @staticmethod
    def generate(generation: AppGeneration) -> ai_generation.AIGenerationResult:
        return ai_generation.AIGenerationResult(
            output_url=generation.reference_image_url
            or generation.character_image_url,
        )


def test_create_video_generation_and_read_quota(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    create_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json={
            "kind": "video",
            "prompt": "  写实社交头像短片  ",
            "style": " 写实 ",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
            "consistency": True,
        },
    )

    assert create_response.status_code == 200
    generation = create_response.json()
    assert generation["kind"] == "video"
    assert generation["model"] == "Seedance 2.0"
    assert generation["status"] == "processing"
    assert generation["prompt"] == "写实社交头像短片"
    assert generation["duration_seconds"] == 10

    quota_response = client.get(
        f"{settings.API_V1_STR}/app/generations/quota",
        headers=headers,
    )

    assert quota_response.status_code == 200
    assert quota_response.json()["video_used"] == 1
    assert quota_response.json()["video_remaining"] == 1
    assert quota_response.json()["image_used"] == 0
    assert quota_response.json()["image_remaining"] == 2


def test_generation_worker_marks_task_succeeded(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    create_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json={
            "kind": "image",
            "prompt": "写实头像",
            "style": "写实",
            "aspect_ratio": "1:1",
            "consistency": True,
            "reference_image_url": "/uploads/images/user/file.png",
        },
    )
    generation_id = uuid.UUID(create_response.json()["id"])

    ai_generation.run_generation(
        generation_id=generation_id,
        provider=ImmediateProvider(),
    )
    detail_response = client.get(
        f"{settings.API_V1_STR}/app/generations/{generation_id}",
        headers=headers,
    )

    assert detail_response.status_code == 200
    generation = detail_response.json()
    assert generation["status"] == "succeeded"
    assert generation["output_url"] == "/uploads/images/user/file.png"


def test_image_and_video_generation_quota_are_separate(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    image_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json={
            "kind": "image",
            "prompt": "写实头像",
            "style": "写实",
            "aspect_ratio": "1:1",
            "duration_seconds": 15,
            "consistency": True,
        },
    )

    assert image_response.status_code == 200
    assert image_response.json()["kind"] == "image"
    assert image_response.json()["model"] == "Seedream"
    assert image_response.json()["duration_seconds"] is None

    quota_response = client.get(
        f"{settings.API_V1_STR}/app/generations/quota",
        headers=headers,
    )

    assert quota_response.status_code == 200
    assert quota_response.json()["video_remaining"] == 2
    assert quota_response.json()["image_remaining"] == 1


def test_generation_rejects_exhausted_free_quota(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    payload = {
        "kind": "video",
        "prompt": "写实短片",
        "style": "写实",
        "aspect_ratio": "9:16",
        "duration_seconds": 5,
        "consistency": True,
    }

    first_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json=payload,
    )
    second_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json=payload,
    )
    third_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 402
    assert third_response.json()["detail"] == "Free generation quota exhausted"


def test_read_generations_and_delete_hides_without_restoring_quota(
    client: TestClient,
) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    create_response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json={
            "kind": "image",
            "prompt": "写实头像",
            "style": "写实",
            "aspect_ratio": "1:1",
            "consistency": True,
        },
    )
    generation_id = create_response.json()["id"]

    list_response = client.get(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
    )
    delete_response = client.delete(
        f"{settings.API_V1_STR}/app/generations/{generation_id}",
        headers=headers,
    )
    hidden_list_response = client.get(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
    )
    quota_response = client.get(
        f"{settings.API_V1_STR}/app/generations/quota",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert any(item["id"] == generation_id for item in list_response.json()["data"])
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Generation deleted successfully"
    assert all(
        item["id"] != generation_id for item in hidden_list_response.json()["data"]
    )
    assert quota_response.json()["image_used"] == 1
    assert quota_response.json()["image_remaining"] == 1


def test_generation_rejects_non_upload_image_url(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    response = client.post(
        f"{settings.API_V1_STR}/app/generations/",
        headers=headers,
        json={
            "kind": "image",
            "prompt": "写实头像",
            "style": "写实",
            "aspect_ratio": "1:1",
            "consistency": True,
            "reference_image_url": "https://example.com/image.png",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Image URL must be local upload URL"
