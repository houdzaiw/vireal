import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.routes import app_uploads as app_uploads_module
from app.core.config import settings
from app.models import AppUpload
from app.services.storage import ReadImage, build_r2_app_image_url
from tests.utils.app_user import app_authentication_headers

PNG_BYTES = b"\x89PNG\r\n\x1a\napp-test-image"


def test_read_and_update_app_profile(client: TestClient) -> None:
    headers, login_data = app_authentication_headers(client=client)
    app_user = login_data["app_user"]

    read_response = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
    )

    assert read_response.status_code == 200
    assert read_response.json()["id"] == app_user["id"]

    update_response = client.patch(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
        json={"nickname": "  Alice  ", "avatar_url": "/uploads/images/avatar.png"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["nickname"] == "Alice"
    assert update_response.json()["avatar_url"] == "/uploads/images/avatar.png"


def test_update_app_profile_rejects_empty_nickname(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    response = client.patch(
        f"{settings.API_V1_STR}/app/users/me",
        headers=headers,
        json={"nickname": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Nickname cannot be empty"


def test_upload_app_image(client: TestClient) -> None:
    headers, login_data = app_authentication_headers(client=client)
    app_user = login_data["app_user"]

    response = client.post(
        f"{settings.API_V1_STR}/app/uploads/images",
        headers=headers,
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    content = response.json()
    assert uuid.UUID(content["id"])
    assert content["content_type"] == "image/png"
    assert content["size"] == len(PNG_BYTES)
    assert content["url"].startswith(f"/uploads/images/{app_user['id']}/")
    assert datetime.fromisoformat(content["expires_at"]) > datetime.now(UTC)


def test_upload_app_image_rejects_non_image(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    response = client.post(
        f"{settings.API_V1_STR}/app/uploads/images",
        headers=headers,
        files={"file": ("note.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File must be an image"


def test_upload_app_image_rejects_too_large_image(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    oversized_image = PNG_BYTES + b"x" * settings.MAX_UPLOAD_IMAGE_BYTES

    response = client.post(
        f"{settings.API_V1_STR}/app/uploads/images",
        headers=headers,
        files={"file": ("large.png", oversized_image, "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Image is too large"


def test_read_r2_image_redirects_to_short_lived_signed_url(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeImageStorage:
        def create_object_read_url(self, object_key: str, *, expires_in: int) -> str:
            assert object_key.startswith("vireal/images/")
            assert expires_in == settings.R2_DOWNLOAD_URL_EXPIRE_SECONDS
            return "https://bucket.account.r2.cloudflarestorage.com/signed-image"

    headers, login_data = app_authentication_headers(client=client)
    monkeypatch.setattr(
        app_uploads_module,
        "get_image_storage",
        lambda: FakeImageStorage(),
    )
    app_user_id = uuid.UUID(login_data["app_user"]["id"])
    filename = f"{uuid.uuid4()}.png"
    image_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=filename,
    )
    db.add(
        AppUpload(
            app_user_id=app_user_id,
            url=image_url,
            object_key=f"vireal/images/{app_user_id}/{filename}",
            content_type="image/png",
            size=len(PNG_BYTES),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/app/uploads/images/{app_user_id}/{filename}",
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")
    assert response.headers["cache-control"] == "private, no-store"


def test_read_image_content_uses_same_origin_private_proxy(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeImageStorage:
        def read_app_image(self, url: str) -> ReadImage:
            assert url.startswith("/uploads/images/")
            return ReadImage(content=b"proxy-image", content_type="image/png")

    headers, login_data = app_authentication_headers(client=client)
    monkeypatch.setattr(
        app_uploads_module,
        "get_image_storage",
        lambda: FakeImageStorage(),
    )
    app_user_id = uuid.UUID(login_data["app_user"]["id"])
    filename = f"{uuid.uuid4()}.png"
    db.add(
        AppUpload(
            app_user_id=app_user_id,
            url=f"/uploads/images/{app_user_id}/{filename}",
            object_key=f"images/{app_user_id}/{filename}",
            content_type="image/png",
            size=len(PNG_BYTES),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/app/uploads/images/{app_user_id}/{filename}/content",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.content == b"proxy-image"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"


def test_create_content_and_read_feed(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    upload_response = client.post(
        f"{settings.API_V1_STR}/app/uploads/images",
        headers=headers,
        files={"file": ("post.png", PNG_BYTES, "image/png")},
    )
    image_url = upload_response.json()["url"]

    create_response = client.post(
        f"{settings.API_V1_STR}/app/contents/",
        headers=headers,
        json={"text": "  first post  ", "image_urls": [image_url]},
    )

    assert create_response.status_code == 200
    created_content = create_response.json()
    assert created_content["text"] == "first post"
    assert created_content["images"][0]["url"] == image_url

    feed_response = client.get(
        f"{settings.API_V1_STR}/app/contents/feed",
        headers=headers,
    )

    assert feed_response.status_code == 200
    feed_data = feed_response.json()["data"]
    assert any(item["id"] == created_content["id"] for item in feed_data)

    detail_response = client.get(
        f"{settings.API_V1_STR}/app/contents/{created_content['id']}",
        headers=headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created_content["id"]


def test_create_content_rejects_empty_payload(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)

    response = client.post(
        f"{settings.API_V1_STR}/app/contents/",
        headers=headers,
        json={"text": "   ", "image_urls": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Text or images are required"


def test_admin_delete_content_hides_it_from_app_feed(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    app_headers, _login_data = app_authentication_headers(client=client)
    create_response = client.post(
        f"{settings.API_V1_STR}/app/contents/",
        headers=app_headers,
        json={"text": "post to delete", "image_urls": []},
    )
    content_id = create_response.json()["id"]

    admin_delete_response = client.delete(
        f"{settings.API_V1_STR}/admin/app/contents/{content_id}",
        headers=superuser_token_headers,
    )

    assert admin_delete_response.status_code == 200
    assert admin_delete_response.json()["message"] == "Content deleted successfully"

    feed_response = client.get(
        f"{settings.API_V1_STR}/app/contents/feed",
        headers=app_headers,
    )
    detail_response = client.get(
        f"{settings.API_V1_STR}/app/contents/{content_id}",
        headers=app_headers,
    )

    assert all(item["id"] != content_id for item in feed_response.json()["data"])
    assert detail_response.status_code == 404


def test_admin_disable_app_user_blocks_token_and_hides_contents(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    disabled_headers, disabled_login_data = app_authentication_headers(client=client)
    reader_headers, _reader_login_data = app_authentication_headers(client=client)
    app_user = disabled_login_data["app_user"]
    create_response = client.post(
        f"{settings.API_V1_STR}/app/contents/",
        headers=disabled_headers,
        json={"text": "hidden after disable", "image_urls": []},
    )
    content_id = create_response.json()["id"]

    admin_update_response = client.patch(
        f"{settings.API_V1_STR}/admin/app/users/{app_user['id']}/status",
        headers=superuser_token_headers,
        json={"status": "disabled"},
    )

    assert admin_update_response.status_code == 200
    assert admin_update_response.json()["status"] == "disabled"

    profile_response = client.get(
        f"{settings.API_V1_STR}/app/users/me",
        headers=disabled_headers,
    )
    feed_response = client.get(
        f"{settings.API_V1_STR}/app/contents/feed",
        headers=reader_headers,
    )

    assert profile_response.status_code == 403
    assert all(item["id"] != content_id for item in feed_response.json()["data"])


def test_admin_list_and_soft_delete_app_user(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    _headers, login_data = app_authentication_headers(client=client)
    app_user = login_data["app_user"]

    list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers=superuser_token_headers,
    )

    assert list_response.status_code == 200
    assert any(item["id"] == app_user["id"] for item in list_response.json()["data"])

    delete_response = client.delete(
        f"{settings.API_V1_STR}/admin/app/users/{app_user['id']}",
        headers=superuser_token_headers,
    )
    default_list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers=superuser_token_headers,
    )
    deleted_list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/users?status=deleted",
        headers=superuser_token_headers,
    )

    assert delete_response.status_code == 200
    assert all(
        item["id"] != app_user["id"] for item in default_list_response.json()["data"]
    )
    assert any(
        item["id"] == app_user["id"] for item in deleted_list_response.json()["data"]
    )


def test_admin_routes_reject_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


def test_admin_delete_missing_content(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.delete(
        f"{settings.API_V1_STR}/admin/app/contents/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"
