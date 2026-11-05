import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.routes import replicate_webhooks
from app.core.config import settings
from app.models import AppOrderEvent, AppUser, AppVideoTask, AppVideoTaskWebhookEvent
from app.models_operations import AppBudgetWindow, AppOperationalAlert
from app.services import operational_alerts, operational_budget
from app.services.video_generation import VideoTaskResult, VideoTaskStatus
from tests.utils.operations import clear_operations, staffed_now

PATH = "/api/v1/operations"


def test_private_ops_require_admin_and_access(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.get(PATH + "/status").status_code == 401
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", True)
    assert (
        client.get(PATH + "/status", headers=superuser_token_headers).status_code == 403
    )
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", False)
    assert (
        client.get(PATH + "/status", headers=superuser_token_headers).status_code == 200
    )


def test_explicit_pause_and_activation(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BUDGET_GUARD_ENABLED", True)
    monkeypatch.setattr("app.api.routes.operations.utc_now", staffed_now)
    response = client.post(PATH + "/pause", headers=superuser_token_headers)
    assert response.json() == {"state": "paused"}
    assert (
        client.get(PATH + "/status", headers=superuser_token_headers).json()[
            "new_business_available"
        ]
        is False
    )
    alert = db.exec(select(AppOperationalAlert)).one()
    assert (
        client.post(
            PATH + f"/alerts/{alert.id}/acknowledge", headers=superuser_token_headers
        ).json()["automatically_opened"]
        is False
    )
    assert client.post(PATH + "/activate", headers=superuser_token_headers).json() == {
        "state": "active"
    }
    db.expire_all()
    window = db.exec(select(AppBudgetWindow)).one()
    window.backup_verified_until = None
    db.add(window)
    db.commit()
    assert (
        client.post(PATH + "/activate", headers=superuser_token_headers).status_code
        == 409
    )


def test_period_cannot_reset_or_overlap(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.routes.operations.utc_now", staffed_now)
    now = staffed_now()
    body = {
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(hours=72)).isoformat(),
    }
    assert (
        client.post(
            PATH + "/period", headers=superuser_token_headers, json=body
        ).status_code
        == 409
    )
    clear_operations(db)
    assert (
        client.post(
            PATH + "/period", headers=superuser_token_headers, json=body
        ).json()["state"]
        == "draft"
    )
    assert (
        client.post(PATH + "/activate", headers=superuser_token_headers).status_code
        == 409
    )


def test_ops_facts_do_not_reopen(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = staffed_now()
    monkeypatch.setattr("app.api.routes.operations.utc_now", lambda: now)
    window = db.exec(select(AppBudgetWindow)).one()
    body = {
        "closing_bound_micros": 30_000_000,
        "closing_evidence": "synthetic close bound",
        "owner_present_until": (now + timedelta(minutes=10)).isoformat(),
        "alerts_verified_until": (now + timedelta(hours=1)).isoformat(),
        "backup_verified_until": (now + timedelta(minutes=59)).isoformat(),
        "prices": window.prices,
    }
    client.post(PATH + "/pause", headers=superuser_token_headers)
    assert (
        client.put(PATH + "/facts", headers=superuser_token_headers, json=body).json()[
            "automatically_opened"
        ]
        is False
    )
    assert (
        client.get(PATH + "/status", headers=superuser_token_headers).json()["state"]
        == "paused"
    )
    body["owner_present_until"] = (now + timedelta(minutes=16)).isoformat()
    assert (
        client.put(
            PATH + "/facts", headers=superuser_token_headers, json=body
        ).status_code
        == 422
    )


def test_monitor_token_has_no_write_authority(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPS_MONITOR_READ_TOKEN", "synthetic-monitor-only")
    headers = {"Authorization": "Bearer synthetic-monitor-only"}
    assert client.get(PATH + "/monitor").status_code == 403
    assert client.get(PATH + "/monitor", headers=headers).status_code == 200
    assert client.post(PATH + "/pause", headers=headers).status_code == 403
    assert (
        client.get(PATH + "/monitor", headers=superuser_token_headers).status_code
        == 403
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("provider", ["apple-iap", "google-play"])
def test_hosted_mobile_callbacks_never_write(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    provider: str,
) -> None:
    before = {row.id for row in db.exec(select(AppOrderEvent)).all()}
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    response = client.post(
        "/api/v1/webhooks/payments/" + provider,
        json={
            "order_id": str(uuid.uuid4()),
            "event_id": "synthetic-hosted-callback",
            "event_type": "payment.completed",
            "status": "paid",
        },
    )
    assert response.status_code == 410
    db.expire_all()
    assert {row.id for row in db.exec(select(AppOrderEvent)).all()} == before


def test_replica_callback_requires_canonical_get(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    secret = base64.b64encode(b"synthetic-signed-callback").decode()
    monkeypatch.setattr(settings, "REPLICATE_WEBHOOK_SIGNING_SECRET", "whsec_" + secret)
    user = AppUser(account_type="clerk")
    db.add(user)
    db.commit()
    task = AppVideoTask(
        app_user_id=user.id,
        idempotency_key=uuid.uuid4().hex,
        template_id="synthetic",
        upload_ids_json="[]",
        model="minimax/video-01",
        provider_task_id="synthetic-prediction",
        duration=5,
        seed=1,
        status="running",
        expires_at=staffed_now() + timedelta(days=1),
    )
    db.add(task)
    db.commit()
    calls = []

    class Provider:
        async def get_task(self, identifier: str) -> VideoTaskResult:
            calls.append(identifier)
            return VideoTaskResult(
                provider_task_id=identifier, status=VideoTaskStatus.RUNNING
            )

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(replicate_webhooks, "get_replicate_video_client", Provider)
    body = json.dumps(
        {
            "id": "synthetic-prediction",
            "status": "succeeded",
            "output": "https://untrusted.invalid/result.mp4",
        }
    ).encode()

    def post(event: str = "synthetic-event"):
        timestamp = str(int(time.time()))
        signature = base64.b64encode(
            hmac.new(
                base64.b64decode(secret),
                event.encode() + b"." + timestamp.encode() + b"." + body,
                hashlib.sha256,
            ).digest()
        ).decode()
        return client.post(
            f"/api/v1/webhooks/replicate?task_id={task.id}",
            content=body,
            headers={
                "webhook-id": event,
                "webhook-timestamp": timestamp,
                "webhook-signature": "v1," + signature,
            },
        )

    assert post().status_code == 204
    db.refresh(task)
    assert task.status == "running" and task.provider_output_url is None
    assert (
        post().status_code == 204 and len(calls) == 1
    )  # duplicate never invokes provider
    task.provider_task_id = None
    db.add(task)
    db.commit()
    assert post("unknown-provider-id").status_code == 409 and len(calls) == 1
    assert not db.exec(
        select(AppVideoTaskWebhookEvent).where(
            AppVideoTaskWebhookEvent.webhook_id == "unknown-provider-id"
        )
    ).all()


@pytest.mark.parametrize("send_status", [202, 500, 0])
def test_alert_opt_in_and_uncertain_send_never_retries(
    db: Session, monkeypatch: pytest.MonkeyPatch, send_status: int
) -> None:
    window = db.exec(select(AppBudgetWindow)).one()
    alert = AppOperationalAlert(window_id=window.id, event_key="synthetic-test")
    db.add(alert)
    db.commit()
    assert operational_alerts.send_one_alert() is False
    monkeypatch.setattr(settings, "APP_OPERATIONAL_ALERT_DELIVERY_ENABLED", True)
    monkeypatch.setattr(settings, "OPS_RESEND_API_KEY", "synthetic-resend")
    monkeypatch.setattr(settings, "OPS_ALERT_FROM", "ops@example.invalid")
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {
                "timeout": 10,
                "follow_redirects": False,
                "trust_env": False,
            }

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if not send_status:
                raise httpx.ReadTimeout("synthetic timeout")
            return SimpleNamespace(status_code=send_status)

    monkeypatch.setattr(operational_alerts.httpx, "Client", Client)
    assert operational_alerts.send_one_alert() is (send_status == 202)
    assert operational_alerts.send_one_alert() is False
    db.refresh(alert)
    assert alert.attempts == 1 and (alert.delivered_at is not None) == (
        send_status == 202
    )
    assert len(calls) == 1
    assert "synthetic-resend" not in calls[0][1]["json"]["text"]


def test_watchdog_pauses_without_stopping_delivery(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operational_alerts, "utc_now", staffed_now)
    monkeypatch.setattr(operational_budget, "utc_now", staffed_now)
    window = db.exec(select(AppBudgetWindow)).one()
    window.worker_seen_at = staffed_now() - timedelta(seconds=91)
    db.add(window)
    db.commit()
    operational_alerts.evaluate_operations()
    db.refresh(window)
    assert window.state == "paused"
    assert (
        db.exec(select(AppOperationalAlert)).one().event_key
        == "paused:worker_heartbeat_stale"
    )
    operational_alerts.evaluate_operations()
    assert len(db.exec(select(AppOperationalAlert)).all()) == 1


def test_cost_observation_and_settlement_require_consistent_evidence(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models_operations import AppCostObservation, AppCostReservation

    now = staffed_now()
    monkeypatch.setattr("app.api.routes.operations.utc_now", lambda: now)
    monkeypatch.setattr(settings, "APP_BUDGET_GUARD_ENABLED", True)
    reservation = operational_budget.reserve_cost(
        db, key="synthetic-settlement-api", source="r2", price_key="upload"
    )
    assert reservation is not None
    db.commit()
    endpoint = PATH + f"/reservations/{reservation.id}/settlement"
    settled = {
        "actual_micros": 500_000,
        "evidence_reference": "synthetic provider invoice line",
    }
    assert (
        client.post(endpoint, headers=superuser_token_headers, json=settled).status_code
        == 200
    )
    assert (
        client.post(endpoint, headers=superuser_token_headers, json=settled).status_code
        == 200
    )
    assert (
        client.post(
            endpoint,
            headers=superuser_token_headers,
            json={**settled, "actual_micros": 0},
        ).status_code
        == 409
    )
    db.expire_all()
    row = db.get(AppCostReservation, reservation.id)
    assert row is not None and row.actual_micros == 500_000
    observation = db.exec(
        select(AppCostObservation).where(AppCostObservation.source == "r2")
    ).one()
    body = {
        "source": "r2",
        "spent_micros": 500_000,
        "unreported_bound_micros": 0,
        "observed_at": now.isoformat(),
        "valid_until": observation.valid_until.isoformat(),
        "evidence_reference": "synthetic invoice",
        "covered_reservation_ids": [str(reservation.id)],
    }
    assert (
        client.put(
            PATH + "/observations", headers=superuser_token_headers, json=body
        ).status_code
        == 200
    )
    assert (
        operational_budget.exposure(db, db.exec(select(AppBudgetWindow)).one(), now)
        == 500_000
    )
    assert (
        client.put(
            PATH + "/observations",
            headers=superuser_token_headers,
            json={**body, "spent_micros": 400_000},
        ).status_code
        == 409
    )
    assert (
        client.put(
            PATH + "/observations",
            headers=superuser_token_headers,
            json={**body, "covered_reservation_ids": [str(uuid.uuid4())]},
        ).status_code
        == 422
    )
    assert (
        client.put(
            PATH + "/observations",
            headers=superuser_token_headers,
            json={**body, "source": "unknown-vendor"},
        ).status_code
        == 422
    )


def test_worker_progress_and_unacknowledged_alerts(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = staffed_now()
    monkeypatch.setattr(operational_alerts, "utc_now", lambda: now)
    window = db.exec(select(AppBudgetWindow)).one()
    window.worker_seen_at = None
    db.add(window)
    db.commit()
    operational_alerts.record_worker_progress()
    db.refresh(window)
    assert window.worker_seen_at == now
    row = AppOperationalAlert(
        window_id=window.id,
        event_key="synthetic-unhandled",
        created_at=now - timedelta(minutes=6),
    )
    db.add(row)
    db.commit()
    operational_alerts.evaluate_operations()
    db.refresh(window)
    assert window.state == "paused" and window.pause_reason == "alert_unacknowledged"
