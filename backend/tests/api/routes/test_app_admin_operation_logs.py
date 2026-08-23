import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.app_user import app_authentication_headers


def _get_operation_logs(
    client: TestClient,
    headers: dict[str, str],
    *,
    action: str | None = None,
    target_type: str | None = None,
) -> list[dict[str, object]]:
    params = {}
    if action:
        params["action"] = action
    if target_type:
        params["target_type"] = target_type
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/operation-logs",
        headers=headers,
        params=params,
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_admin_config_actions_create_operation_logs(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    key = f"audit.config.{uuid.uuid4()}"
    create_response = client.post(
        f"{settings.API_V1_STR}/admin/app/configs",
        headers=superuser_token_headers,
        json={"key": key, "value": "old", "is_enabled": True},
    )
    config_id = create_response.json()["id"]

    update_response = client.patch(
        f"{settings.API_V1_STR}/admin/app/configs/{config_id}",
        headers=superuser_token_headers,
        json={"value": "new", "is_enabled": False},
    )

    assert create_response.status_code == 200
    assert update_response.status_code == 200

    create_logs = _get_operation_logs(
        client,
        superuser_token_headers,
        action="app_config.create",
        target_type="app_config",
    )
    update_logs = _get_operation_logs(
        client,
        superuser_token_headers,
        action="app_config.update",
        target_type="app_config",
    )

    create_log = next(log for log in create_logs if log["target_id"] == config_id)
    update_log = next(log for log in update_logs if log["target_id"] == config_id)

    assert create_log["summary"] == f"Created App config {key}"
    assert create_log["details"]["key"] == key
    assert create_log["details"]["is_enabled"] is True
    assert update_log["summary"] == f"Updated App config {key}"
    assert update_log["details"]["previous"]["value"] == "old"
    assert update_log["details"]["updated"]["value"] == "new"
    assert update_log["details"]["updated"]["is_enabled"] is False


def test_admin_user_status_update_creates_operation_log(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    _app_headers, login_data = app_authentication_headers(client=client)
    app_user_id = login_data["app_user"]["id"]

    response = client.patch(
        f"{settings.API_V1_STR}/admin/app/users/{app_user_id}/status",
        headers=superuser_token_headers,
        json={"status": "disabled"},
    )

    assert response.status_code == 200

    logs = _get_operation_logs(
        client,
        superuser_token_headers,
        action="app_user.status_update",
        target_type="app_user",
    )
    log = next(item for item in logs if item["target_id"] == app_user_id)

    assert log["summary"] == "Set App user status to disabled"
    assert log["details"]["previous_status"] == "active"
    assert log["details"]["new_status"] == "disabled"


def test_admin_content_delete_creates_operation_log(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    app_headers, _login_data = app_authentication_headers(client=client)
    create_response = client.post(
        f"{settings.API_V1_STR}/app/contents/",
        headers=app_headers,
        json={"text": "audit content delete", "image_urls": []},
    )
    content_id = create_response.json()["id"]

    response = client.delete(
        f"{settings.API_V1_STR}/admin/app/contents/{content_id}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200

    logs = _get_operation_logs(
        client,
        superuser_token_headers,
        action="app_content.delete",
        target_type="app_content",
    )
    log = next(item for item in logs if item["target_id"] == content_id)

    assert log["summary"] == "Soft deleted App content"
    assert log["details"]["previous_status"] == "active"
    assert log["details"]["text_preview"] == "audit content delete"


def test_admin_operation_logs_reject_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/operation-logs",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
