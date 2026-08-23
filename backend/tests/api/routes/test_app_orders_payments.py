import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.app_user import app_authentication_headers


def _create_order(
    *, client: TestClient, headers: dict[str, str], provider: str = "apple"
) -> dict[str, object]:
    response = client.post(
        f"{settings.API_V1_STR}/app/orders",
        headers=headers,
        json={
            "provider": provider,
            "product_id": "premium.monthly",
            "amount": 1999,
            "currency": "usd",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_app_create_list_and_read_order(client: TestClient) -> None:
    headers, login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers)

    assert order["app_user_id"] == login_data["app_user"]["id"]
    assert order["provider"] == "apple"
    assert order["product_id"] == "premium.monthly"
    assert order["status"] == "created"
    assert order["amount"] == 1999
    assert order["currency"] == "USD"

    list_response = client.get(
        f"{settings.API_V1_STR}/app/orders",
        headers=headers,
    )
    detail_response = client.get(
        f"{settings.API_V1_STR}/app/orders/{order['id']}",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert any(item["id"] == order["id"] for item in list_response.json()["data"])
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == order["id"]


def test_app_cannot_read_other_user_order(client: TestClient) -> None:
    owner_headers, _owner_login = app_authentication_headers(client=client)
    reader_headers, _reader_login = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=owner_headers)

    response = client.get(
        f"{settings.API_V1_STR}/app/orders/{order['id']}",
        headers=reader_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_apple_iap_callback_marks_order_paid_and_stores_event(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="apple")

    callback_response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/apple-iap",
        json={
            "order_id": order["id"],
            "event_id": f"apple-event-{uuid.uuid4()}",
            "event_type": "DID_RENEW",
            "status": "paid",
            "transaction_id": "apple-transaction-001",
            "raw_data": {"environment": "sandbox"},
        },
    )

    assert callback_response.status_code == 200
    callback_data = callback_response.json()
    assert callback_data["is_duplicate"] is False
    assert callback_data["message"] == "Payment event processed"
    assert callback_data["order"]["status"] == "paid"
    assert callback_data["order"]["transaction_id"] == "apple-transaction-001"
    assert callback_data["event"]["provider"] == "apple"

    app_order_response = client.get(
        f"{settings.API_V1_STR}/app/orders/{order['id']}",
        headers=headers,
    )
    admin_events_response = client.get(
        f"{settings.API_V1_STR}/admin/app/orders/{order['id']}/events",
        headers=superuser_token_headers,
    )

    assert app_order_response.json()["status"] == "paid"
    assert admin_events_response.status_code == 200
    assert admin_events_response.json()["count"] == 1


def test_google_play_callback_marks_order_paid(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="google")

    response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/google-play",
        json={
            "order_id": order["id"],
            "event_id": f"google-event-{uuid.uuid4()}",
            "event_type": "SUBSCRIPTION_PURCHASED",
            "status": "paid",
            "transaction_id": "google-token-001",
            "raw_data": {"package_name": "com.example.app"},
        },
    )

    assert response.status_code == 200
    assert response.json()["order"]["status"] == "paid"
    assert response.json()["event"]["provider"] == "google"


def test_payment_callback_is_idempotent(client: TestClient) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="apple")
    event_id = f"apple-event-{uuid.uuid4()}"
    payload = {
        "order_id": order["id"],
        "event_id": event_id,
        "event_type": "DID_RENEW",
        "status": "paid",
        "transaction_id": "apple-transaction-duplicate",
    }

    first_response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/apple-iap",
        json=payload,
    )
    duplicate_response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/apple-iap",
        json={**payload, "status": "failed"},
    )

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["is_duplicate"] is True
    assert duplicate_response.json()["message"] == "Duplicate event ignored"
    assert duplicate_response.json()["order"]["status"] == "paid"
    assert (
        first_response.json()["event"]["id"]
        == duplicate_response.json()["event"]["id"]
    )


def test_payment_callback_stores_unmatched_event(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/google-play",
        json={
            "order_id": str(uuid.uuid4()),
            "event_id": f"missing-order-event-{uuid.uuid4()}",
            "event_type": "SUBSCRIPTION_PURCHASED",
            "status": "paid",
            "transaction_id": "missing-order-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["order"] is None
    assert response.json()["event"]["order_id"] is None
    assert response.json()["message"] == "Order not found"


def test_payment_callback_shared_secret_mode_rejects_missing_header(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "shared_secret")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", "payment-secret")
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="apple")

    response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/apple-iap",
        json={
            "order_id": order["id"],
            "event_id": f"apple-event-{uuid.uuid4()}",
            "event_type": "DID_RENEW",
            "status": "paid",
            "transaction_id": "apple-transaction-rejected",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid payment webhook signature"

    detail_response = client.get(
        f"{settings.API_V1_STR}/app/orders/{order['id']}",
        headers=headers,
    )
    assert detail_response.json()["status"] == "created"


def test_payment_callback_shared_secret_mode_accepts_valid_header(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_VERIFICATION_MODE", "shared_secret")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", "payment-secret")
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="google")

    response = client.post(
        f"{settings.API_V1_STR}/webhooks/payments/google-play",
        headers={"X-App-Payment-Webhook-Secret": "payment-secret"},
        json={
            "order_id": order["id"],
            "event_id": f"google-event-{uuid.uuid4()}",
            "event_type": "SUBSCRIPTION_PURCHASED",
            "status": "paid",
            "transaction_id": "google-token-with-secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["order"]["status"] == "paid"
    assert response.json()["event"]["transaction_id"] == "google-token-with-secret"


def test_admin_list_and_read_orders(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    headers, _login_data = app_authentication_headers(client=client)
    order = _create_order(client=client, headers=headers, provider="google")

    list_response = client.get(
        f"{settings.API_V1_STR}/admin/app/orders?provider=google",
        headers=superuser_token_headers,
    )
    detail_response = client.get(
        f"{settings.API_V1_STR}/admin/app/orders/{order['id']}",
        headers=superuser_token_headers,
    )

    assert list_response.status_code == 200
    assert any(item["id"] == order["id"] for item in list_response.json()["data"])
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == order["id"]


def test_admin_order_routes_reject_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/orders",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


def test_admin_missing_order(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/orders/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
