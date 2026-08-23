import uuid

from fastapi.testclient import TestClient

from app.core.config import settings


def app_authentication_headers(
    *, client: TestClient, device_uuid: str | None = None
) -> tuple[dict[str, str], dict[str, object]]:
    payload = {
        "device_uuid": device_uuid or f"test-device-{uuid.uuid4()}",
        "platform": "ios",
    }
    response = client.post(
        f"{settings.API_V1_STR}/app/auth/device-login",
        json=payload,
    )
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data
