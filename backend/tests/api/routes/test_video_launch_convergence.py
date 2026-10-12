"""Isolated/mocked release regressions. No payments, predictions or real media."""

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, delete, select

from app.api.routes import app_video_tasks
from app.core.config import settings
from app.core.db import engine
from app.models import (
    AppAdminOperationLog,
    AppCoinLedger,
    AppEffect,
    AppEffectCategory,
    AppEffectRecommendation,
    AppEffectVariant,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
)
from app.services import video_task_reconciliation as reconciliation
from app.services.coin_wallet import adjust_coin_balance, get_coin_balance
from app.services.storage import LocalImageStorage
from app.services.video_generation import VideoTaskResult, VideoTaskStatus
from app.services.video_quota import global_real_count
from app.workers import video_tasks as worker
from app.workers.video_tasks import cleanup_expired_media
from tests.utils.app_user import app_authentication_headers

MP4 = b"\x00\x00\x00\x18ftypmp42test-video"


@pytest.fixture(autouse=True)
def isolated_tasks(db, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_DEMO_ENABLED", False)
    monkeypatch.setattr(settings, "APP_LIVE_ACCEPTANCE_ENABLED", False)
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()
    yield
    db.rollback()
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()


def paid_task(client, db, status="submission_unknown", provider_id=None):
    headers, user = app_authentication_headers(client=client)
    user_id = uuid.UUID(user["app_user"]["id"])
    now = datetime.now(UTC)
    task = AppVideoTask(
        app_user_id=user_id,
        idempotency_key=str(uuid.uuid4()),
        template_id="dance-1",
        mode="effect",
        upload_ids_json="[]",
        model="wan-video/wan-2.7-r2v",
        status=status,
        duration=5,
        seed=123,
        coin_cost_snapshot=12,
        provider_task_id=provider_id,
        submission_attempted_at=now,
        expires_at=now - timedelta(minutes=1),
    )
    db.add(task)
    db.flush()
    adjust_coin_balance(
        session=db,
        app_user_id=user_id,
        delta=100,
        entry_type="admin_adjustment",
        idempotency_key=str(uuid.uuid4()),
        reason="isolated fixture",
    )
    adjust_coin_balance(
        session=db,
        app_user_id=user_id,
        delta=-12,
        entry_type="generation_debit",
        idempotency_key=f"video-task-debit:{task.id}",
        reason="isolated generation",
        task_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return headers, task


def refunds(db, task):
    return list(
        db.exec(
            select(AppCoinLedger).where(
                AppCoinLedger.task_id == task.id,
                AppCoinLedger.entry_type == "generation_refund",
            )
        ).all()
    )


class Provider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0
        self.closed = False

    async def get_task(self, _id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize(
    "status", ["submitting", "submission_unknown", "pending", "running", "saving"]
)
def test_cleanup_does_not_settle_active_paid_tasks(client, db, status):
    _, task = paid_task(client, db, status)

    class Storage:
        def delete_object(self, _key):
            pytest.fail("Active task output must not be deleted")

    cleanup_expired_media(storage=Storage())
    db.expire_all()
    current = db.get(AppVideoTask, task.id)
    assert current.status == status and current.coin_refunded_at is None
    assert get_coin_balance(session=db, app_user_id=task.app_user_id) == 88
    assert not refunds(db, task)


@pytest.mark.parametrize("status", list(VideoTaskStatus))
def test_provider_observation_is_monotonic_and_refunds_once(client, db, status):
    _, task = paid_task(client, db, provider_id="prediction-test")
    result = VideoTaskResult(
        "prediction-test",
        status,
        output_url="https://replicate.delivery/test.mp4",
        metrics={"unit_test": True},
    )
    for _ in range(2):
        current = reconciliation.lock_task(db, task.id)
        reconciliation.apply_provider_result(session=db, task=current, result=result)
        db.commit()
    db.refresh(task)
    assert task.provider_last_checked_at and task.real_submission_counted_at
    expected_refund = status in {VideoTaskStatus.FAILED, VideoTaskStatus.CANCELED}
    assert len(refunds(db, task)) == int(expected_refund)
    assert get_coin_balance(session=db, app_user_id=task.app_user_id) == (
        100 if expected_refund else 88
    )
    if status == VideoTaskStatus.SUCCEEDED:
        assert task.status == "saving" and task.next_attempt_at
        reconciliation.apply_provider_result(
            session=db,
            task=task,
            result=VideoTaskResult("prediction-test", VideoTaskStatus.RUNNING),
        )
        db.commit()
        assert task.status == "saving"


def test_missing_output_and_concurrent_failure_compensate_once(client, db):
    _, task = paid_task(client, db, provider_id="prediction-concurrent")

    def settle(_index):
        with Session(engine) as session:
            locked = reconciliation.lock_task(session, task.id)
            reconciliation.apply_provider_result(
                session=session,
                task=locked,
                result=VideoTaskResult(
                    "prediction-concurrent", VideoTaskStatus.SUCCEEDED
                ),
            )
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(settle, [0, 1]))
    db.expire_all()
    assert db.get(AppVideoTask, task.id).status == "failed"
    assert len(refunds(db, task)) == 1
    assert get_coin_balance(session=db, app_user_id=task.app_user_id) == 100


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("timeout"),
        reconciliation.ReplicateAPIError(message="not found", status_code=404),
        reconciliation.ReplicateConfigurationError("not configured"),
    ],
)
def test_provider_transport_errors_keep_debit_and_reservation(
    client, db, monkeypatch, error
):
    _, task = paid_task(client, db, provider_id="prediction-unknown")
    provider = Provider(error=error)
    monkeypatch.setattr(reconciliation, "get_replicate_video_client", lambda: provider)
    current = asyncio.run(reconciliation.reconcile_task(session=db, task_id=task.id))
    db.commit()
    assert current.status == "submission_unknown" and current.provider_next_check_at
    assert (
        not refunds(db, task)
        and get_coin_balance(session=db, app_user_id=task.app_user_id) == 88
    )
    assert global_real_count(session=db, now=datetime.now(UTC)) == 1
    assert provider.closed


def test_worker_reconciles_existing_id_only_and_identity_conflict(
    client, db, monkeypatch
):
    _, task = paid_task(client, db, provider_id="prediction-reconcile")
    provider = Provider(
        VideoTaskResult(
            "prediction-reconcile",
            VideoTaskStatus.SUCCEEDED,
            output_url="https://replicate.delivery/test.mp4",
        )
    )
    monkeypatch.setattr(reconciliation, "get_replicate_video_client", lambda: provider)
    assert reconciliation.reconcile_video_tasks() == 1
    db.expire_all()
    assert db.get(AppVideoTask, task.id).status == "saving" and provider.calls == 1
    _, unknown = paid_task(client, db)
    asyncio.run(reconciliation.reconcile_task(session=db, task_id=unknown.id))
    assert provider.calls == 1
    with pytest.raises(reconciliation.VideoTaskStateError):
        reconciliation.apply_provider_result(
            session=db,
            task=task,
            result=VideoTaskResult("other-prediction", VideoTaskStatus.FAILED),
        )
    with pytest.raises(reconciliation.VideoTaskStateError):
        asyncio.run(reconciliation.reconcile_task(session=db, task_id=uuid.uuid4()))


def test_unknown_previous_day_holds_capacity_until_evidence(client, db):
    _, task = paid_task(client, db)
    task.created_at = task.submission_attempted_at = datetime.now(UTC) - timedelta(
        days=2
    )
    db.add(task)
    db.commit()
    assert global_real_count(session=db, now=datetime.now(UTC)) == 1
    reconciliation.apply_provider_result(
        session=db,
        task=reconciliation.lock_task(db, task.id),
        result=VideoTaskResult("prediction-old", VideoTaskStatus.FAILED),
    )
    db.commit()
    assert global_real_count(session=db, now=datetime.now(UTC)) == 0
    assert len(refunds(db, task)) == 1


def test_owned_download_and_expired_links_fail_closed(
    client, db, monkeypatch, tmp_path
):
    headers, task = paid_task(client, db, status="succeeded")
    storage = LocalImageStorage(tmp_path)
    key = f"videos/{task.app_user_id}/{task.id}.mp4"
    path = tmp_path / key
    path.parent.mkdir(parents=True)
    path.write_bytes(MP4)
    task.output_object_key = key
    task.expires_at = datetime.now(UTC) + timedelta(seconds=40)
    db.add(task)
    db.commit()
    monkeypatch.setattr(app_video_tasks, "get_image_storage", lambda: storage)
    response = client.get(
        f"/api/v1/app/video-tasks/{task.id}/download", headers=headers
    )
    assert response.status_code == 200 and response.content == MP4
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "private, no-store"
    details = client.get(f"/api/v1/app/video-tasks/{task.id}", headers=headers).json()
    assert details["playback_url_expires_at"] <= details["expires_at"]
    other, _ = app_authentication_headers(client=client)
    assert (
        client.get(
            f"/api/v1/app/video-tasks/{task.id}/download", headers=other
        ).status_code
        == 404
    )
    task.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.add(task)
    db.commit()
    assert (
        client.get(
            f"/api/v1/app/video-tasks/{task.id}/download", headers=headers
        ).status_code
        == 410
    )
    details = client.get(f"/api/v1/app/video-tasks/{task.id}", headers=headers).json()
    assert details["status"] == "expired" and details["playback_url"] is None
    assert details["coin_refunded_at"] is None


def test_download_pending_missing_file_and_private_storage_failure(
    client, db, monkeypatch, tmp_path
):
    headers, task = paid_task(client, db, status="running")
    task.expires_at = datetime.now(UTC) + timedelta(hours=1)
    db.add(task)
    db.commit()
    url = f"/api/v1/app/video-tasks/{task.id}/download"
    assert client.get(url, headers=headers).status_code == 409
    task.status = "succeeded"
    task.output_object_key = "videos/missing.mp4"
    db.add(task)
    db.commit()
    monkeypatch.setattr(
        app_video_tasks, "get_image_storage", lambda: LocalImageStorage(tmp_path)
    )
    assert client.get(url, headers=headers).status_code == 404


def action_body(**overrides):
    return {
        "reason": "Confirmed supplier support evidence",
        "idempotency_key": str(uuid.uuid4()),
        **overrides,
    }


def test_admin_list_reconcile_resolve_and_retry_are_audited(
    client, db, superuser_token_headers
):
    _, task = paid_task(client, db)
    root = "/api/v1/admin/app/video-tasks"
    listed = client.get(root + "?needs_review=true", headers=superuser_token_headers)
    assert listed.status_code == 200 and listed.json()["count"] == 1
    details = client.get(f"{root}/{task.id}", headers=superuser_token_headers).json()
    assert details["needs_review"] and len(details["ledger"]) == 1
    assert "upload_ids_json" not in details and "provider_output_url" not in details
    assert (
        client.post(
            f"{root}/{task.id}/reconcile",
            headers=superuser_token_headers,
            json=action_body(),
        ).status_code
        == 409
    )
    body = action_body(
        resolution="not_submitted",
        evidence="Supplier support confirms no accepted prediction for this request",
        provider_confirmed=True,
    )
    for _ in range(2):
        response = client.post(
            f"{root}/{task.id}/resolve", headers=superuser_token_headers, json=body
        )
        assert response.status_code == 200, response.text
        assert (
            response.json()["status"] == "failed"
            and response.json()["coin_refunded_at"]
        )
    assert len(refunds(db, task)) == 1
    logs = db.exec(
        select(AppAdminOperationLog).where(
            AppAdminOperationLog.target_id == task.id,
            AppAdminOperationLog.action == "video_task.resolve",
        )
    ).all()
    assert (
        len(logs) == 1
        and json.loads(logs[0].details_json)["request"]["evidence"] == body["evidence"]
    )
    changed = {**body, "reason": "Different explanation"}
    assert (
        client.post(
            f"{root}/{task.id}/resolve", headers=superuser_token_headers, json=changed
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{root}/{task.id}/resolve",
            headers=superuser_token_headers,
            json={**body, "idempotency_key": str(uuid.uuid4())},
        ).status_code
        == 409
    )


def test_admin_reconciliation_checks_state_without_new_prediction(
    client, db, monkeypatch, superuser_token_headers
):
    _, task = paid_task(client, db, provider_id="prediction-admin")
    provider = Provider(VideoTaskResult("prediction-admin", VideoTaskStatus.FAILED))
    monkeypatch.setattr(reconciliation, "get_replicate_video_client", lambda: provider)
    body = action_body()
    for _ in range(2):
        response = client.post(
            f"/api/v1/admin/app/video-tasks/{task.id}/reconcile",
            headers=superuser_token_headers,
            json=body,
        )
        assert response.status_code == 200 and response.json()["status"] == "failed"
    assert provider.calls == 1 and len(refunds(db, task)) == 1


@pytest.mark.parametrize("problem", ["accepted", "saving", "no_debit", "deleted"])
def test_manual_resolution_safety_guards(client, db, superuser_token_headers, problem):
    _, task = paid_task(
        client, db, provider_id="prediction-guard" if problem == "accepted" else None
    )
    if problem == "saving":
        task.status = "saving"
        task.worker_locked_at = datetime.now(UTC)
    elif problem == "deleted":
        task.deleted_at = datetime.now(UTC)
    elif problem == "no_debit":
        db.execute(delete(AppCoinLedger).where(AppCoinLedger.task_id == task.id))
    db.add(task)
    db.commit()
    response = client.post(
        f"/api/v1/admin/app/video-tasks/{task.id}/resolve",
        headers=superuser_token_headers,
        json=action_body(
            resolution="not_submitted",
            evidence="Confirmed original supplier request investigation",
            provider_confirmed=True,
        ),
    )
    assert response.status_code == 409 and not refunds(db, task)


def test_historical_unknown_requires_evidence_and_admin_access(
    client, db, monkeypatch, superuser_token_headers, normal_user_token_headers
):
    _, task = paid_task(client, db, status="expired")
    url = f"/api/v1/admin/app/video-tasks/{task.id}/resolve"
    body = action_body(
        resolution="unavailable",
        evidence="Provider confirms the accepted output is irretrievably unavailable",
        provider_confirmed=True,
    )
    assert client.post(
        url, headers=normal_user_token_headers, json=body
    ).status_code in {400, 403}
    assert (
        client.post(
            url,
            headers=superuser_token_headers,
            json={**body, "provider_confirmed": False},
        ).status_code
        == 422
    )
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", True)
    assert (
        client.get(
            "/api/v1/admin/app/video-tasks", headers=superuser_token_headers
        ).status_code
        == 403
    )
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", False)
    assert (
        client.post(url, headers=superuser_token_headers, json=body).status_code == 200
    )
    assert len(refunds(db, task)) == 1


def test_selected_catalog_blocks_deep_links_recommendations_and_submission(
    client, db, monkeypatch
):
    category = AppEffectCategory(
        slug=str(uuid.uuid4()),
        name_zh="测试",
        name_en="Test",
        tones_json='["#111","#222","#333"]',
    )
    db.add(category)
    db.flush()
    effects = []
    for _ in range(3):
        effect = AppEffect(
            category_id=category.id,
            slug=f"launch-{uuid.uuid4()}",
            title_zh="Test",
            title_en="Test",
            publish_status="published",
        )
        db.add(effect)
        db.flush()
        db.add(
            AppEffectVariant(
                effect_id=effect.id,
                duration_seconds=5,
                coin_cost=12,
                provider="replicate",
                model="wan-video/wan-2.7-r2v",
                model_type="wan-video",
                prompt="one authorized adult",
            )
        )
        effects.append(effect)
    db.add(
        AppEffectRecommendation(
            effect_id=effects[0].id, recommended_effect_id=effects[2].id
        )
    )
    db.commit()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(
        settings, "APP_LAUNCH_EFFECT_SLUGS", [e.slug for e in effects[:2]]
    )
    data = client.get("/api/v1/app/effect-catalog").json()
    assert {e["slug"] for cat in data["categories"] for e in cat["effects"]} == {
        e.slug for e in effects[:2]
    }
    assert client.get(f"/api/v1/app/effects/{effects[2].slug}").status_code == 404
    assert (
        client.get(f"/api/v1/app/effects/{effects[0].slug}").json()["recommendations"]
        == []
    )
    headers, _ = app_authentication_headers(client=client)
    variant = db.exec(
        select(AppEffectVariant).where(AppEffectVariant.effect_id == effects[2].id)
    ).one()
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", True)
    response = client.post(
        "/api/v1/app/video-tasks",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "effect_id": str(effects[2].id),
            "variant_id": str(variant.id),
            "upload_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 409
    db.execute(
        delete(AppEffectRecommendation).where(
            AppEffectRecommendation.effect_id == effects[0].id
        )
    )
    db.execute(
        delete(AppEffectVariant).where(
            AppEffectVariant.effect_id.in_([e.id for e in effects])
        )
    )
    db.execute(delete(AppEffect).where(AppEffect.category_id == category.id))
    db.delete(category)
    db.commit()


def test_independent_reconciliation_loop_retries_without_sensitive_error(
    monkeypatch, caplog
):
    class Stop:
        stopped = False
        waits = []

        def is_set(self):
            return self.stopped

        def wait(self, delay):
            self.waits.append(delay)
            self.stopped = True

    stop = Stop()
    monkeypatch.setattr(worker.time, "monotonic", lambda: 10.0)

    def fail():
        raise RuntimeError("secret-provider-body-must-not-be-logged")

    worker._reconciliation_loop(stop, fail, 60, "Video")
    assert stop.waits == [60]
    assert "will retry" in caplog.text
    assert "secret-provider-body" not in caplog.text


def test_reconciliation_threads_start_before_slow_persistence(monkeypatch):
    starts = []
    stops = []

    class Thread:
        def __init__(self, *, target, args, name, daemon):
            assert target is worker._reconciliation_loop and daemon
            self.name = name
            stops.append(args[0])

        def start(self):
            starts.append(self.name)

    def interrupt_persistence():
        assert starts == ["payment-reconcile", "video-reconcile"]
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.threading, "Thread", Thread)
    monkeypatch.setattr(worker, "process_next_video_task", interrupt_persistence)
    with pytest.raises(KeyboardInterrupt):
        worker.run_worker()
    assert all(stop.is_set() for stop in stops)


def test_fresh_inflight_submission_cannot_be_manually_refunded(
    client, db, superuser_token_headers
):
    _, task = paid_task(client, db, status="submitting")
    response = client.post(
        f"/api/v1/admin/app/video-tasks/{task.id}/resolve",
        headers=superuser_token_headers,
        json=action_body(
            resolution="not_submitted",
            evidence="Supplier investigation evidence, but request is still in flight",
            provider_confirmed=True,
        ),
    )
    assert response.status_code == 409 and not refunds(db, task)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("timeout"),
        httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "https://replicate.delivery/missing"),
            response=httpx.Response(404),
        ),
        worker.VideoProcessingUnavailable("FFmpeg unavailable"),
    ],
)
def test_delivery_transport_failure_keeps_debit_and_enters_review(
    client, db, monkeypatch, superuser_token_headers, failure
):
    _, task = paid_task(client, db, status="saving", provider_id="prediction-delivery")
    monkeypatch.setattr(settings, "VIDEO_WORKER_MAX_ATTEMPTS", 2)
    task.worker_attempts = 2
    worker._record_worker_failure(db, task, failure)
    db.refresh(task)
    assert (
        task.status == "saving" and task.next_attempt_at and not task.coin_refunded_at
    )
    assert get_coin_balance(session=db, app_user_id=task.app_user_id) == 88
    queue = client.get(
        "/api/v1/admin/app/video-tasks?needs_review=true",
        headers=superuser_token_headers,
    ).json()
    assert any(row["id"] == str(task.id) for row in queue["data"])
    assert not refunds(db, task)


def test_confirmed_invalid_output_refunds_once_without_resubmission(
    client, db, monkeypatch
):
    _, task = paid_task(client, db, status="saving", provider_id="prediction-invalid")
    monkeypatch.setattr(settings, "VIDEO_WORKER_MAX_ATTEMPTS", 2)
    task.worker_attempts = 2
    for _ in range(2):
        worker._record_worker_failure(
            db, task, worker.VideoOutputError("Verified output is not MP4")
        )
    db.refresh(task)
    assert task.status == "failed" and len(refunds(db, task)) == 1
    assert task.provider_task_id == "prediction-invalid"


def test_emergency_generation_pause_preserves_existing_task_reads(
    client, db, monkeypatch
):
    headers, task = paid_task(client, db)
    monkeypatch.setattr(settings, "REPLICATE_ENABLED", True)
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", False)
    response = client.post(
        "/api/v1/app/video-tasks",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "effect_id": str(uuid.uuid4()),
            "variant_id": str(uuid.uuid4()),
            "upload_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 503
    assert (
        client.get(f"/api/v1/app/video-tasks/{task.id}", headers=headers).status_code
        == 200
    )
    db.refresh(task)
    assert task.status == "submission_unknown" and not refunds(db, task)


def test_production_old_free_generation_is_closed_even_during_controlled_acceptance(
    client, monkeypatch
):
    headers, _ = app_authentication_headers(client=client)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APP_PUBLIC_REGISTRATION_ENABLED", False)
    response = client.post(
        "/api/v1/app/generations/",
        headers=headers,
        json={
            "kind": "video",
            "prompt": "No free or alternate model allowed in production",
        },
    )
    assert response.status_code == 410
    assert client.get("/api/v1/app/generations/", headers=headers).status_code == 200
