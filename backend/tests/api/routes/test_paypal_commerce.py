import copy
import hashlib
import hmac
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, delete, select

from app.api.routes import app_paypal, paypal_webhooks
from app.core.config import settings
from app.core.db import engine
from app.models import (
    AppAdminOperationLog,
    AppCoinLedger,
    AppOrder,
    AppOrderEvent,
    AppPaymentCase,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
    User,
)
from app.services import paypal_orders
from app.services.coin_wallet import (
    CoinBalanceError,
    adjust_coin_balance,
    get_coin_balance,
)
from app.services.paypal_client import PRODUCTS, PayPalClient, PayPalError
from app.services.video_quota import global_real_count, quota_counts
from tests.utils.app_user import app_authentication_headers


class FakePayPal:
    """Unit tests only: never performs an external payment or generation."""

    def __init__(self):
        self.orders = {}
        self.valid_signature = True
        self.timeout_after_capture = False
        self.create_calls = 0

    def close(self):
        pass

    def create_order(self, order):
        self.create_calls += 1
        provider_id = "PAY-" + str(order.id)
        self.orders.setdefault(
            provider_id,
            {
                "id": provider_id,
                "intent": "CAPTURE",
                "status": "CREATED",
                "purchase_units": [
                    {
                        "custom_id": str(order.id),
                        "invoice_id": str(order.id),
                        "payee": {"merchant_id": "TEST-MERCHANT"},
                        "amount": {
                            "currency_code": "USD",
                            "value": f"{order.amount / 100:.2f}",
                        },
                    }
                ],
            },
        )
        return copy.deepcopy(self.orders[provider_id])

    def order_details(self, provider_id):
        return copy.deepcopy(self.orders[provider_id])

    def capture_order(self, order):
        data = self.orders[order.provider_order_id]
        data["status"] = "COMPLETED"
        data["purchase_units"][0]["payments"] = {
            "captures": [
                {
                    "id": "CAP-" + str(order.id),
                    "status": "COMPLETED",
                    "amount": data["purchase_units"][0]["amount"],
                }
            ]
        }
        if self.timeout_after_capture:
            raise PayPalError()
        return copy.deepcopy(data)

    def verify_webhook(self, raw, headers):
        return self.valid_signature

    def dispute_details(self, dispute_id):
        return {
            "status": "RESOLVED",
            "dispute_outcome": {"outcome_code": "RESOLVED_SELLER_FAVOUR"},
        }


@pytest.fixture(autouse=True)
def commerce_setup(db: Session, monkeypatch):
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()
    values = {
        "PAYPAL_ENABLED": True,
        "PAYPAL_ENVIRONMENT": "sandbox",
        "PAYPAL_CLIENT_ID": "test-public-client",
        "PAYPAL_CLIENT_SECRET": "test-secret-never-exposed",
        "PAYPAL_MERCHANT_ID": "TEST-MERCHANT",
        "PAYPAL_WEBHOOK_ID": "TEST-WEBHOOK",
        "APP_REGION_ENFORCEMENT_ENABLED": False,
        "APP_GLOBAL_DAILY_REAL_SUBMISSIONS": 30,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    fake = FakePayPal()
    for module in (app_paypal, paypal_webhooks, paypal_orders):
        monkeypatch.setattr(module, "get_paypal_client", lambda: fake)
    yield fake
    db.rollback()
    db.execute(delete(AppPaymentCase))
    db.execute(delete(AppOrderEvent).where(AppOrderEvent.provider == "paypal"))
    db.execute(delete(AppOrder).where(AppOrder.provider == "paypal"))
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()


def create(client, product="coins_100", headers=None, key=None):
    if headers is None:
        headers, _ = app_authentication_headers(client=client)
    response = client.post(
        "/api/v1/app/paypal/orders",
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
        json={"product_id": product},
    )
    assert response.status_code == 200, response.text
    return headers, response.json()


def approve(fake, order):
    fake.orders[order["provider_order_id"]]["status"] = "APPROVED"


def wallet(client, headers):
    return client.get("/api/v1/app/wallet", headers=headers).json()


def capture(client, headers, order):
    return client.post(
        f"/api/v1/app/paypal/orders/{order['id']}/capture", headers=headers
    )


@pytest.mark.parametrize("product", list(PRODUCTS))
def test_packages_and_duplicate_capture_credit_once(client, commerce_setup, product):
    headers, order = create(client, product)
    assert (order["coin_quantity"], order["amount"]) == PRODUCTS[product]
    assert wallet(client, headers)["balance"] == 0
    approve(commerce_setup, order)
    for _ in range(2):
        response = capture(client, headers, order)
        assert response.status_code == 200, response.text
        assert response.json()["fulfilled_at"]
    result = wallet(client, headers)
    assert result["balance"] == PRODUCTS[product][0]
    assert (
        len([x for x in result["ledger"] if x["entry_type"] == "recharge_credit"]) == 1
    )


def test_idempotency_and_client_amount_rejected(client, commerce_setup):
    key = str(uuid.uuid4())
    headers, order = create(client, key=key)
    _, repeated = create(client, headers=headers, key=key)
    assert repeated["id"] == order["id"] and commerce_setup.create_calls == 1
    assert (
        client.post(
            "/api/v1/app/paypal/orders",
            headers={**headers, "Idempotency-Key": key},
            json={"product_id": "coins_220"},
        ).status_code
        == 409
    )
    for field in ("amount", "currency", "coin_quantity"):
        assert (
            client.post(
                "/api/v1/app/paypal/orders",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"product_id": "coins_100", field: 1},
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "tampering", ["amount", "currency", "merchant", "invoice", "country"]
)
def test_capture_rejects_mismatch(client, commerce_setup, tampering):
    headers, order = create(client)
    approve(commerce_setup, order)
    data = commerce_setup.orders[order["provider_order_id"]]
    unit = data["purchase_units"][0]
    if tampering == "amount":
        unit["amount"]["value"] = "0.01"
    if tampering == "currency":
        unit["amount"]["currency_code"] = "EUR"
    if tampering == "merchant":
        unit["payee"]["merchant_id"] = "OTHER"
    if tampering == "invoice":
        unit["invoice_id"] = str(uuid.uuid4())
    if tampering == "country":
        data["payer"] = {"address": {"country_code": "CN"}}
    assert capture(client, headers, order).status_code == 409
    assert wallet(client, headers)["balance"] == 0


def test_unpaid_and_timeout_recovery(client, commerce_setup):
    headers, order = create(client)
    assert capture(client, headers, order).json()["fulfilled_at"] is None
    approve(commerce_setup, order)
    commerce_setup.timeout_after_capture = True
    assert capture(client, headers, order).json()["fulfilled_at"] is not None
    assert wallet(client, headers)["balance"] == 100


def test_foreign_order_inaccessible(client):
    _, order = create(client)
    headers, _ = app_authentication_headers(client=client)
    assert capture(client, headers, order).status_code == 404


def test_concurrent_confirmation_and_stale_state(client, commerce_setup):
    headers, public = create(client)
    approve(commerce_setup, public)
    oid = uuid.UUID(public["id"])
    with Session(engine) as session:
        commerce_setup.capture_order(session.get(AppOrder, oid))
    data = commerce_setup.order_details(public["provider_order_id"])

    def confirm(_):
        with Session(engine) as session:
            result = paypal_orders.apply_order_state(session, oid, data)
            session.commit()
            return result.fulfilled_at is not None

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(confirm, range(4)))
    stale = copy.deepcopy(data)
    stale["status"] = "CREATED"
    stale["purchase_units"][0].pop("payments")
    with Session(engine) as session:
        assert paypal_orders.apply_order_state(session, oid, stale).status == "paid"
        session.commit()
    assert wallet(client, headers)["balance"] == 100


def event_for(order, kind="PAYMENT.CAPTURE.COMPLETED"):
    return {
        "id": str(uuid.uuid4()),
        "event_type": kind,
        "resource": {
            "id": "CAP-" + order["id"],
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "5.99"},
            "supplementary_data": {
                "related_ids": {"order_id": order["provider_order_id"]}
            },
        },
    }


def test_webhook_signature_dedup_and_closed_gate(client, commerce_setup, monkeypatch):
    headers, order = create(client)
    approve(commerce_setup, order)
    with Session(engine) as session:
        commerce_setup.capture_order(session.get(AppOrder, uuid.UUID(order["id"])))
    event = event_for(order)
    commerce_setup.valid_signature = False
    assert (
        client.post("/api/v1/webhooks/payments/paypal", json=event).status_code == 403
    )
    assert wallet(client, headers)["balance"] == 0
    commerce_setup.valid_signature = True
    monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    for _ in range(2):
        assert (
            client.post("/api/v1/webhooks/payments/paypal", json=event).status_code
            == 204
        )
    assert (
        wallet(client, headers)["balance"] == 100
        and capture(client, headers, order).status_code == 200
    )


def test_refund_insufficient_recovery_remains_frozen(client, db, commerce_setup):
    headers, order = create(client)
    approve(commerce_setup, order)
    capture(client, headers, order)
    uid = uuid.UUID(order["app_user_id"])
    adjust_coin_balance(
        session=db,
        app_user_id=uid,
        delta=-24,
        entry_type="generation_debit",
        idempotency_key=str(uuid.uuid4()),
        reason="unit test",
    )
    db.commit()
    event = event_for(order, "PAYMENT.CAPTURE.REFUNDED")
    event["resource"]["id"] = "REFUND-1"
    assert (
        client.post("/api/v1/webhooks/payments/paypal", json=event).status_code == 204
    )
    result = wallet(client, headers)
    assert result["balance"] == 76 and result["payment_hold"]
    assert (
        client.post(
            "/api/v1/app/paypal/orders",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"product_id": "coins_100"},
        ).status_code
        == 409
    )
    case = db.exec(
        select(AppPaymentCase).where(AppPaymentCase.app_user_id == uid)
    ).one()
    with pytest.raises(CoinBalanceError):
        paypal_orders.resolve_case(
            db,
            case.id,
            resolution="recover",
            reason="verified refund",
            admin_id=uuid.uuid4(),
            client=commerce_setup,
        )
    db.rollback()
    assert get_coin_balance(session=db, app_user_id=uid) == 76


def test_worker_finishes_without_browser(client, commerce_setup, monkeypatch):
    headers, order = create(client)
    approve(commerce_setup, order)
    monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    assert paypal_orders.reconcile_paypal_orders() == 1
    assert wallet(client, headers)["balance"] == 100


def test_refund_admin_recovery_is_atomic_audited_and_idempotent(
    client, db, commerce_setup, monkeypatch, superuser_token_headers
):
    from app.services import paypal_client

    monkeypatch.setattr(paypal_client, "get_paypal_client", lambda: commerce_setup)
    headers, order = create(client)
    approve(commerce_setup, order)
    capture(client, headers, order)
    event = event_for(order, "PAYMENT.CAPTURE.REFUNDED")
    event["resource"]["id"] = "REFUND-FULL"
    event["resource"]["payer"] = {"email_address": "must-not-be-retained@example.com"}
    event["resource"]["links"] = [{"href": "https://example.com/private-payer"}]
    assert (
        client.post("/api/v1/webhooks/payments/paypal", json=event).status_code == 204
    )
    cases = client.get(
        f"/api/v1/admin/app/orders/{order['id']}/payment-cases",
        headers=superuser_token_headers,
    )
    assert cases.status_code == 200, cases.text
    case_id = cases.json()[0]["id"]
    url = f"/api/v1/admin/app/payment-cases/{case_id}/resolve"
    assert (
        client.post(
            url,
            headers=superuser_token_headers,
            json={"resolution": "recover", "reason": "   "},
        ).status_code
        == 422
    )
    assert client.post(
        url,
        headers=headers,
        json={"resolution": "recover", "reason": "verified full refund"},
    ).status_code in (401, 403, 404)
    for _ in range(2):
        response = client.post(
            url,
            headers=superuser_token_headers,
            json={"resolution": "recover", "reason": "verified full refund"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["recovered_coins"] == 100
    assert wallet(client, headers)["balance"] == 0
    assert not wallet(client, headers)["payment_hold"]
    assert (
        len(
            db.exec(
                select(AppCoinLedger).where(
                    AppCoinLedger.order_id == uuid.UUID(order["id"]),
                    AppCoinLedger.entry_type == "recharge_recovery",
                )
            ).all()
        )
        == 1
    )
    assert db.exec(
        select(AppAdminOperationLog).where(
            AppAdminOperationLog.target_id == uuid.UUID(case_id)
        )
    ).first()
    recorded = db.exec(
        select(AppOrderEvent).where(AppOrderEvent.event_id == event["id"])
    ).one()
    assert (
        "private-payer" not in recorded.raw_payload
        and "email_address" not in recorded.raw_payload
    )
    assert (
        client.post(
            url,
            headers=superuser_token_headers,
            json={"resolution": "recover", "reason": "different decision"},
        ).status_code
        == 409
    )
    # Late capture/approval cannot restore refunded credits.
    assert capture(client, headers, order).json()["status"] == "refunded"
    assert wallet(client, headers)["balance"] == 0


@pytest.mark.parametrize("decision", ["seller", "buyer", "unresolved"])
def test_verified_dispute_resolution(client, db, commerce_setup, decision):
    headers, order = create(client)
    approve(commerce_setup, order)
    capture(client, headers, order)
    event = event_for(order, "CUSTOMER.DISPUTE.CREATED")
    event["resource"]["id"] = "DISPUTE-" + decision
    paypal_orders.process_webhook(db, event, commerce_setup)
    case = db.exec(
        select(AppPaymentCase).where(AppPaymentCase.order_id == uuid.UUID(order["id"]))
    ).one()
    admin = db.exec(select(User).where(User.is_superuser)).first()
    commerce_setup.dispute_details = lambda _: {
        "status": "UNDER_REVIEW" if decision == "unresolved" else "RESOLVED",
        "disputed_transactions": [{"seller_transaction_id": "CAP-" + order["id"]}],
        "dispute_outcome": {
            "outcome_code": "RESOLVED_SELLER_FAVOUR"
            if decision == "seller"
            else "RESOLVED_BUYER_FAVOUR",
            "amount_refunded": {"currency_code": "USD", "value": "2.00"},
        },
    }
    if decision == "unresolved":
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            paypal_orders.resolve_case(
                db,
                case.id,
                resolution="recover",
                reason="still unresolved",
                admin_id=admin.id,
                client=commerce_setup,
            )
        db.rollback()
        assert wallet(client, headers)["payment_hold"]
    else:
        result = paypal_orders.resolve_case(
            db,
            case.id,
            resolution="dismiss" if decision == "seller" else "recover",
            reason="verified PayPal outcome",
            admin_id=admin.id,
            client=commerce_setup,
        )
        db.commit()
        assert result.recovered_coins == (0 if decision == "seller" else 34)
        assert wallet(client, headers)["balance"] == (
            100 if decision == "seller" else 66
        )
        assert not wallet(client, headers)["payment_hold"]


def test_unassociated_event_replayed_after_create_recovers_payment(
    client, db, commerce_setup
):
    headers, order = create(client)
    approve(commerce_setup, order)
    row = db.get(AppOrder, uuid.UUID(order["id"]))
    commerce_setup.capture_order(row)
    provider_id = row.provider_order_id
    row.provider_order_id = None
    db.add(row)
    db.commit()
    event = event_for(order)
    paypal_orders.process_webhook(db, event, commerce_setup)
    assert (
        db.exec(select(AppOrderEvent).where(AppOrderEvent.event_id == event["id"]))
        .one()
        .order_id
        is None
    )
    row.provider_order_id = provider_id
    # Keep this order out of the regular poll to exercise the event replay.
    row.next_reconcile_at = datetime.now(UTC) + timedelta(hours=1)
    db.add(row)
    db.commit()
    paypal_orders.reconcile_paypal_orders()
    assert wallet(client, headers)["balance"] == 100
    assert (
        db.exec(select(AppOrderEvent).where(AppOrderEvent.event_id == event["id"]))
        .one()
        .order_id
        == row.id
    )


def test_payment_missing_configuration_and_bad_event_fail_cleanly(client, monkeypatch):
    headers, order = create(client)

    def unavailable():
        raise PayPalError("Payment service is not configured", 503)

    monkeypatch.setattr(app_paypal, "get_paypal_client", unavailable)
    monkeypatch.setattr(paypal_webhooks, "get_paypal_client", unavailable)
    assert capture(client, headers, order).status_code == 503
    assert (
        client.post(
            "/api/v1/webhooks/payments/paypal", json=event_for(order)
        ).status_code
        == 503
    )
    assert (
        client.post("/api/v1/webhooks/payments/paypal", content="not json").status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/webhooks/payments/paypal", content=b"x" * (256 * 1024 + 1)
        ).status_code
        == 413
    )
    assert wallet(client, headers)["balance"] == 0


def test_creation_rate_limit_and_existing_order_after_capacity_gate(
    client, monkeypatch
):
    headers, order = create(client)
    key = str(uuid.uuid4())
    _, existing = create(client, headers=headers, key=key)
    for _ in range(3):
        create(client, headers=headers)
    response = client.post(
        "/api/v1/app/paypal/orders",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"product_id": "coins_100"},
    )
    assert response.status_code == 429
    monkeypatch.setattr(settings, "PAYPAL_ENABLED", False)
    assert create(client, headers=headers, key=key)[1]["id"] == existing["id"]
    assert capture(client, headers, order).status_code == 200


@pytest.mark.parametrize(
    "status", ["REFUNDED", "REVERSED", "PARTIALLY_REFUNDED", "PENDING", "DECLINED"]
)
def test_provider_capture_states_do_not_succeed_prematurely(
    client, db, commerce_setup, status
):
    headers, order = create(client)
    approve(commerce_setup, order)
    row = db.get(AppOrder, uuid.UUID(order["id"]))
    commerce_setup.capture_order(row)
    commerce_setup.orders[order["provider_order_id"]]["purchase_units"][0]["payments"][
        "captures"
    ][0]["status"] = status
    response = capture(client, headers, order)
    assert response.status_code == 200, response.text
    assert response.json()["fulfilled_at"] is None
    assert wallet(client, headers)["balance"] == 0
    assert wallet(client, headers)["payment_hold"] == (
        status in {"REFUNDED", "REVERSED", "PARTIALLY_REFUNDED"}
    )


def signed_headers(path, method="GET", country="US", timestamp=None):
    timestamp = timestamp or str(int(time.time()))
    message = "\n".join((method, path, timestamp, country))
    return {
        "x-vireal-edge-country": country,
        "x-vireal-edge-time": timestamp,
        "x-vireal-edge-signature": hmac.new(
            settings.APP_EDGE_SIGNING_SECRET.encode(), message.encode(), hashlib.sha256
        ).hexdigest(),
    }


def test_geo_signature_and_no_secrets(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "APP_EDGE_SIGNING_SECRET",
        "unit-test-edge-signing-key-over-32-characters",
    )
    path = "/api/v1/app/paypal/config"
    for headers in (
        {},
        {"CF-IPCountry": "US"},
        signed_headers(path, country="CN"),
        signed_headers(path, timestamp="1"),
        signed_headers("/other"),
    ):
        response = client.get(path, headers=headers)
        assert (
            not response.json()["region_allowed"]
            and not response.json()["recharge_enabled"]
        )
        assert "test-secret-never-exposed" not in response.text
    assert client.get(path, headers=signed_headers(path)).json()["recharge_enabled"]
    assert client.get(path).headers["cache-control"] == "no-store"


def test_region_gate_blocks_orders_uploads_and_new_generation(client, monkeypatch):
    headers, _ = app_authentication_headers(client=client)
    monkeypatch.setattr(settings, "APP_REGION_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "APP_EDGE_SIGNING_SECRET",
        "unit-test-edge-signing-key-over-32-characters",
    )
    for country in (None, "CN", "XX"):
        for path, kwargs in (
            ("/api/v1/app/paypal/orders", {"json": {"product_id": "coins_100"}}),
            (
                "/api/v1/app/uploads/images",
                {"files": {"file": ("test.png", b"unit-image", "image/png")}},
            ),
            (
                "/api/v1/app/video-tasks",
                {
                    "json": {
                        "template_id": "dance",
                        "upload_ids": [str(uuid.uuid4())],
                        "mode": "standard",
                        "duration": 5,
                    }
                },
            ),
        ):
            proof = (
                signed_headers(path, "POST", country)
                if country
                else {"CF-IPCountry": "US"}
            )
            response = client.post(
                path,
                headers={**headers, **proof, "Idempotency-Key": str(uuid.uuid4())},
                **kwargs,
            )
            assert response.status_code == 403, response.text
    assert client.get("/api/v1/utils/health-check/").status_code == 200
    assert client.get("/api/v1/app/effect-catalog").status_code == 200


def test_global_all_models_and_midnight_unknown(client, db, commerce_setup):
    headers, existing = create(client)
    uid = uuid.UUID(existing["app_user_id"])
    now = datetime.now(UTC)
    for index in range(30):
        db.add(
            AppVideoTask(
                app_user_id=uid,
                idempotency_key=str(uuid.uuid4()),
                template_id="dance",
                model="unit-test/model",
                duration=5,
                seed=1,
                expires_at=now + timedelta(hours=24),
                upload_ids_json="[]",
                status="failed",
                execution_type=("minimax", "wan", "seedance")[index % 3],
                submission_attempted_at=now,
                real_submission_counted_at=now,
            )
        )
    db.commit()
    assert global_real_count(session=db, now=now) == 30
    config = client.get("/api/v1/app/paypal/config").json()
    assert config["global_real_remaining"] == 0 and not config["recharge_enabled"]
    assert (
        client.post(
            "/api/v1/app/paypal/orders",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"product_id": "coins_100"},
        ).status_code
        == 409
    )
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    approve(commerce_setup, existing)
    assert capture(client, headers, existing).json()["fulfilled_at"]
    assert wallet(client, headers)["balance"] == 100
    assert global_real_count(session=db, now=tomorrow) == 0
    db.add(
        AppVideoTask(
            app_user_id=uid,
            idempotency_key=str(uuid.uuid4()),
            template_id="dance",
            model="unit-test/model",
            duration=5,
            seed=1,
            expires_at=now + timedelta(hours=24),
            upload_ids_json="[]",
            status="submission_unknown",
            execution_type="minimax",
            created_at=now,
            submission_attempted_at=now,
        )
    )
    db.commit()
    assert (
        global_real_count(session=db, now=tomorrow) == 1
        and quota_counts(session=db, app_user_id=uid, now=tomorrow)[0] == 1
    )


def test_concurrent_cross_model_reservation_rejects_31st(client, db, monkeypatch):
    from tests.api.routes.test_app_video_tasks import (
        FakeProvider,
        _enable_mock_replicate,
        _upload_image,
    )

    provider = FakeProvider()
    _enable_mock_replicate(monkeypatch, provider)
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    _, base = app_authentication_headers(client=client)
    now = datetime.now(UTC)
    for index in range(29):
        db.add(
            AppVideoTask(
                app_user_id=uuid.UUID(base["app_user"]["id"]),
                idempotency_key=str(uuid.uuid4()),
                template_id="dance",
                model="unit-test/model",
                duration=5,
                seed=1,
                expires_at=now + timedelta(hours=24),
                upload_ids_json="[]",
                status="failed",
                execution_type=("minimax", "wan", "seedance")[index % 3],
                submission_attempted_at=now,
                real_submission_counted_at=now,
            )
        )
    db.commit()
    requests = []
    for mode in ("standard", "advanced"):
        headers, _ = app_authentication_headers(client=client)
        upload = _upload_image(client, headers)
        requests.append((headers, upload, mode))

    def submit(item):
        headers, upload, mode = item
        return client.post(
            "/api/v1/app/video-tasks",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "template_id": "dance",
                "upload_ids": [upload["id"]],
                "mode": mode,
                "duration": 5,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, requests))
    assert sorted(response.status_code for response in results) == [202, 409]
    assert len(provider.calls) == 1
    assert global_real_count(session=db, now=now) == 30


@pytest.mark.parametrize("fault", ["token", "decline", "bad_json", "network"])
def test_paypal_rest_errors_are_sanitized(fault):
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(
                401 if fault == "token" else 200,
                json={
                    "access_token": "test-token",
                    "expires_in": 300,
                    "private_secret": "DO-NOT-EXPOSE",
                },
            )
        if fault == "network":
            raise httpx.ReadTimeout("DO-NOT-EXPOSE")
        return httpx.Response(
            422 if fault == "decline" else 200, content=b"DO-NOT-EXPOSE"
        )

    rest = PayPalClient(httpx.MockTransport(handler))
    with pytest.raises(PayPalError) as caught:
        rest.order_details("safe-order")
    assert "DO-NOT-EXPOSE" not in str(caught.value)
    assert caught.value.status_code == (409 if fault == "decline" else 502)
    rest.close()


def test_rest_signature_preserves_raw_body_and_fixed_host():
    raw = b'{  "id" : "unit-event", "resource" : {} }'

    def handler(request):
        assert request.url.host == "api-m.sandbox.paypal.com"
        if request.url.path.endswith("token"):
            return httpx.Response(
                200, json={"access_token": "unit-access-token", "expires_in": 300}
            )
        assert b'"webhook_event": ' + raw in request.content
        return httpx.Response(200, json={"verification_status": "SUCCESS"})

    client = PayPalClient(transport=httpx.MockTransport(handler))
    headers = dict.fromkeys(
        (
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
            "paypal-transmission-sig",
        ),
        "unit-value",
    )
    try:
        assert client.verify_webhook(raw, headers) and not client.verify_webhook(
            raw, {}
        )
    finally:
        client.close()
