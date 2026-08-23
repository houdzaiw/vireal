from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import AppDevice, AppUser


def test_device_login_creates_app_user(client: TestClient, db: Session) -> None:
    payload = {"device_uuid": "ios-device-uuid-001", "platform": "ios"}

    response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json=payload,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["is_new_user"] is True
    assert data["app_user"]["status"] == "active"

    app_user = db.get(AppUser, data["app_user"]["id"])
    assert app_user

    statement = select(AppDevice).where(AppDevice.app_user_id == app_user.id)
    app_device = db.exec(statement).first()
    assert app_device
    assert app_device.platform == "ios"


def test_device_login_returns_same_app_user_for_same_device(
    client: TestClient,
) -> None:
    payload = {"device_uuid": "android-device-uuid-001", "platform": "android"}

    first_response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json=payload,
    )
    second_response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["is_new_user"] is True
    assert second_response.json()["is_new_user"] is False
    assert (
        first_response.json()["app_user"]["id"]
        == second_response.json()["app_user"]["id"]
    )


def test_device_login_creates_different_users_for_different_devices(
    client: TestClient,
) -> None:
    first_response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json={"device_uuid": "ios-device-uuid-002", "platform": "ios"},
    )
    second_response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json={"device_uuid": "ios-device-uuid-003", "platform": "ios"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert (
        first_response.json()["app_user"]["id"]
        != second_response.json()["app_user"]["id"]
    )


def test_device_login_rejects_invalid_platform(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json={"device_uuid": "ios-device-uuid-004", "platform": "web"},
    )

    assert response.status_code == 422


def test_app_token_can_read_current_app_user(client: TestClient) -> None:
    login_response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json={"device_uuid": "ios-device-uuid-005", "platform": "ios"},
    )
    token = login_response.json()["access_token"]

    response = client.post(
        f"{settings.API_V1_STR}/app/auth/test-token",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == login_response.json()["app_user"]["id"]


def test_app_token_rejects_admin_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/app/auth/test-token",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
