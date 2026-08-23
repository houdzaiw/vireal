import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.app_user import app_authentication_headers


def _config_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4()}"


def test_admin_create_and_list_app_config(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    key = _config_key("startup.banner")
    response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={
            "key": f"  {key}  ",
            "value": "  hello  ",
            "description": "  Banner copy  ",
            "is_enabled": True,
        },
    )

    assert response.status_code == 200
    created_config = response.json()
    assert created_config["key"] == key
    assert created_config["value"] == "hello"
    assert created_config["description"] == "Banner copy"
    assert created_config["is_enabled"] is True

    list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
    )

    assert list_response.status_code == 200
    assert any(item["id"] == created_config["id"] for item in list_response.json()["data"])


def test_admin_create_app_config_rejects_duplicate_key(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    key = _config_key("paywall.enabled")
    payload = {"key": key, "value": "true", "is_enabled": True}

    first_response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json=payload,
    )
    second_response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Config key already exists"


def test_app_reads_only_enabled_configs(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    enabled_key = _config_key("feature.enabled")
    disabled_key = _config_key("feature.disabled")
    client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": enabled_key, "value": "on", "is_enabled": True},
    )
    client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": disabled_key, "value": "off", "is_enabled": False},
    )
    app_headers, _login_data = app_authentication_headers(client=client)

    response = client.get(
        f"{settings.API_V1_STR}/app/configs",
        headers=app_headers,
    )

    assert response.status_code == 200
    configs = response.json()["data"]
    assert configs[enabled_key] == "on"
    assert disabled_key not in configs


def test_admin_update_app_config_and_enabled_filter(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    key = _config_key("config.to.update")
    create_response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": key, "value": "old", "is_enabled": False},
    )
    config_id = create_response.json()["id"]

    update_response = client.patch(
        f"{settings.API_V1_STR}/admin/app/configs/{config_id}",
        headers=superuser_token_headers,
        json={"value": " new ", "is_enabled": True},
    )
    enabled_list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/configs?is_enabled=true",
        headers=superuser_token_headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["value"] == "new"
    assert update_response.json()["is_enabled"] is True
    assert any(item["id"] == config_id for item in enabled_list_response.json()["data"])


def test_admin_update_app_config_rejects_duplicate_key(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    first_key = _config_key("config.first")
    second_key = _config_key("config.second")
    first_response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": first_key, "value": "1", "is_enabled": True},
    )
    client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": second_key, "value": "2", "is_enabled": True},
    )

    response = client.patch(
        f"{settings.API_V1_STR}/admin/app/configs/{first_response.json()['id']}",
        headers=superuser_token_headers,
        json={"key": second_key},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Config key already exists"


def test_admin_app_config_rejects_empty_key(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": "   ", "value": "value", "is_enabled": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Config key cannot be empty"


def test_admin_app_config_missing_id(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.patch(
        f"{settings.API_V1_STR}/admin/app/configs/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json={"value": "new"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Config not found"


def test_admin_app_config_rejects_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
