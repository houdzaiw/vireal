"""Synthetic PostgreSQL admission tests; no provider, storage or webhook HTTP."""

import asyncio
import multiprocessing
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, delete, select
from starlette.requests import Request

from app.api.routes import app_video_tasks as route
from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import (
    AppCoinLedger,
    AppEffect,
    AppEffectCategory,
    AppEffectVariant,
    AppUpload,
    AppUser,
    AppVideoTask,
    AppVideoTaskCreate,
    AppVideoTaskWebhookEvent,
)
from app.services.coin_wallet import adjust_coin_balance, get_coin_balance
from app.services.replicate_video import (
    MINIMAX_VIDEO_01_MODEL,
    SEEDANCE_R2V_MODEL,
    WAN_R2V_MODEL,
    ReplicateAPIError,
)
from app.services.video_generation import (
    VideoTaskResult,
    VideoTaskStatus,
    VideoTaskSubmission,
)
from app.services.video_quota import ACTIVE_REAL_STATUSES, global_active_real_count
from app.services.video_task_reconciliation import apply_provider_result, lock_task

MODELS = {
    "minimax": MINIMAX_VIDEO_01_MODEL,
    "wan": WAN_R2V_MODEL,
    "seedance": SEEDANCE_R2V_MODEL,
}
COST = 12


@dataclass(frozen=True)
class Case:
    user_id: uuid.UUID
    upload_id: uuid.UUID
    effect_id: uuid.UUID
    variant_id: uuid.UUID

    def body(self):
        return AppVideoTaskCreate(
            effect_id=self.effect_id,
            variant_id=self.variant_id,
            upload_ids=[self.upload_id],
        )


class Provider:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    async def submit_reference_to_video(self, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return VideoTaskSubmission(
            provider_task_id=f"synthetic-{uuid.uuid4()}",
            status=VideoTaskStatus.PENDING,
        )

    async def aclose(self):
        pass


def _configure_test_settings(set_value):
    assert settings.ENVIRONMENT == "local"
    for name, value in {
        "REPLICATE_ENABLED": True,
        "REPLICATE_WEBHOOK_URL": "https://api.example.invalid/never-called",
        "LOCAL_DEMO_ENABLED": False,
        "APP_VIDEO_SUBMISSIONS_ENABLED": True,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
        "APP_USER_DAILY_REAL_SUBMISSIONS": 100,
        "APP_USER_MAX_CONCURRENT_VIDEO_TASKS": 100,
        "APP_WAN_DAILY_GLOBAL_SUBMISSIONS": 100,
        "APP_GLOBAL_DAILY_REAL_SUBMISSIONS": 100,
        "REPLICATE_POC_MAX_SUBMISSIONS": 0,
        "APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS": 1,
    }.items():
        set_value(settings, name, value)


@pytest.fixture(autouse=True)
def isolated_admission(db, monkeypatch):
    _configure_test_settings(monkeypatch.setattr)
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()
    yield
    db.rollback()
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()


@pytest.fixture
def provider(monkeypatch):
    fake = Provider()
    monkeypatch.setattr(route, "get_replicate_video_client", lambda: fake)
    return fake


@pytest.fixture
def make_case(db):
    def make(*, model=MODELS["wan"], balance=100):
        user = AppUser()
        category = AppEffectCategory(
            slug=f"test-{uuid.uuid4()}", name_zh="隔离测试", name_en="Isolated"
        )
        db.add(user)
        db.add(category)
        db.flush()
        effect = AppEffect(
            category_id=category.id,
            slug=f"test-{uuid.uuid4()}",
            title_zh="隔离测试",
            title_en="Isolated",
            publish_status="published",
        )
        upload = AppUpload(
            app_user_id=user.id,
            url="https://media.example.invalid/synthetic.png",
            object_key="synthetic.png",
            content_type="image/png",
            size=10,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(effect)
        db.add(upload)
        db.flush()
        variant = AppEffectVariant(
            effect_id=effect.id,
            duration_seconds=5,
            coin_cost=COST,
            provider="replicate",
            model=model,
            model_type="test",
            prompt="A synthetic fixture, never sent to a vendor",
        )
        db.add(variant)
        if balance:
            adjust_coin_balance(
                session=db,
                app_user_id=user.id,
                delta=balance,
                entry_type="admin_adjustment",
                idempotency_key=str(uuid.uuid4()),
                reason="Synthetic test only",
            )
        db.commit()
        return Case(user.id, upload.id, effect.id, variant.id)

    return make


def submit(case, key=None):
    with Session(engine) as session:
        return asyncio.run(
            route.create_video_task(
                request=Request({"type": "http", "headers": []}),
                session=session,
                current_app_user=session.get(AppUser, case.user_id),
                body=case.body(),
                idempotency_key=key or str(uuid.uuid4()),
            )
        )


def seed_task(db, case, *, status, execution_type="wan", age_days=0, deleted=False):
    then = datetime.now(UTC) - timedelta(days=age_days)
    task = AppVideoTask(
        app_user_id=case.user_id,
        idempotency_key=str(uuid.uuid4()),
        template_id="synthetic",
        upload_ids_json="[]",
        model=MODELS.get(execution_type, "local/ffmpeg"),
        execution_type=execution_type,
        status=status,
        duration=5,
        seed=1,
        created_at=then,
        submission_attempted_at=then,
        deleted_at=then if deleted else None,
        expires_at=then + timedelta(hours=1),
    )
    db.add(task)
    db.commit()
    return task


def task_count(db):
    return db.exec(select(func.count()).select_from(AppVideoTask)).one()


def ledger_count(db, entry_type):
    return db.exec(
        select(func.count())
        .select_from(AppCoinLedger)
        .where(AppCoinLedger.entry_type == entry_type)
    ).one()


@pytest.mark.parametrize("execution_type", list(MODELS))
@pytest.mark.parametrize("status", ACTIVE_REAL_STATUSES)
def test_all_users_models_and_active_states_share_one_slot(
    db, make_case, provider, status, execution_type
):
    seed_task(db, make_case(), status=status, execution_type=execution_type)
    other = make_case()
    before_debits = ledger_count(db, "generation_debit")
    with pytest.raises(HTTPException) as error:
        submit(other)
    assert error.value.status_code == 409
    assert (
        error.value.detail == "Real video generation quota or provider is unavailable"
    )
    db.expire_all()
    assert task_count(db) == global_active_real_count(session=db) == 1
    assert ledger_count(db, "generation_debit") == before_debits
    assert get_coin_balance(session=db, app_user_id=other.user_id) == 100
    assert provider.calls == 0


@pytest.mark.parametrize("deleted", [False, True])
def test_old_unknown_reservation_is_not_released_by_midnight_expiry_or_deletion(
    db, make_case, provider, deleted
):
    seed_task(db, make_case(), status="submission_unknown", age_days=3, deleted=deleted)
    with pytest.raises(HTTPException) as error:
        submit(make_case())
    assert error.value.status_code == 409 and provider.calls == 0
    assert global_active_real_count(session=db) == 1


@pytest.mark.parametrize("status", ["succeeded", "failed", "canceled", "expired"])
def test_terminal_tasks_release_slot(db, make_case, provider, status):
    seed_task(db, make_case(), status=status)
    result = submit(make_case())
    assert result.status == "pending" and provider.calls == 1
    assert global_active_real_count(session=db) == 1


@pytest.mark.parametrize("model", list(MODELS.values()))
def test_each_real_model_admitted_when_slot_free(make_case, provider, model):
    result = submit(make_case(model=model))
    assert result.status == "pending" and result.execution_type in MODELS
    assert provider.calls == 1


def test_local_demo_does_not_consume_real_slot(db, make_case, provider):
    seed_task(db, make_case(), status="rendering_demo", execution_type="local_demo")
    result = submit(make_case())
    assert result.status == "pending" and provider.calls == 1
    assert global_active_real_count(session=db) == 1


def test_same_idempotency_returns_original_without_debit_or_provider_retry(
    db, make_case, provider
):
    case = make_case()
    key = str(uuid.uuid4())
    first = submit(case, key)
    before_debits = ledger_count(db, "generation_debit")
    repeated = submit(case, key)
    assert repeated.id == first.id and repeated.status == first.status
    db.expire_all()
    assert task_count(db) == provider.calls == 1
    assert ledger_count(db, "generation_debit") == before_debits
    assert get_coin_balance(session=db, app_user_id=case.user_id) == 100 - COST


@pytest.mark.parametrize("paused", [False, True])
def test_http_capacity_contract_and_emergency_pause(
    client, db, make_case, provider, monkeypatch, paused
):
    if not paused:
        seed_task(db, make_case(), status="running")
    case = make_case()
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", not paused)
    token = security.create_app_access_token(case.user_id, timedelta(minutes=1))
    before_count = task_count(db)
    before_debits = ledger_count(db, "generation_debit")
    response = client.post(
        "/api/v1/app/video-tasks",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json=case.body().model_dump(mode="json"),
    )
    assert response.status_code == (503 if paused else 409)
    assert response.json() == {
        "detail": (
            "New uploads and video submissions are temporarily paused"
            if paused
            else "Real video generation quota or provider is unavailable"
        )
    }
    db.expire_all()
    assert task_count(db) == before_count and provider.calls == 0
    assert ledger_count(db, "generation_debit") == before_debits
    assert get_coin_balance(session=db, app_user_id=case.user_id) == 100


def test_insufficient_balance_rolls_back_reservation_and_releases_lock(
    db, make_case, provider
):
    empty = make_case(balance=0)
    before_debits = ledger_count(db, "generation_debit")
    with pytest.raises(HTTPException, match="Insufficient coin balance"):
        submit(empty)
    assert task_count(db) == global_active_real_count(session=db) == 0
    assert provider.calls == 0
    assert ledger_count(db, "generation_debit") == before_debits
    assert submit(make_case()).status == "pending"
    assert provider.calls == 1


def test_unknown_provider_response_keeps_slot_and_debit(db, make_case, provider):
    case = make_case()
    key = str(uuid.uuid4())
    provider.error = httpx.ReadTimeout("synthetic timeout, no HTTP")
    task = submit(case, key)
    assert task.status == "submission_unknown"
    assert submit(case, key).id == task.id
    with pytest.raises(HTTPException) as error:
        submit(make_case())
    db.expire_all()
    assert error.value.status_code == 409 and provider.calls == 1
    assert get_coin_balance(session=db, app_user_id=case.user_id) == 100 - COST
    assert global_active_real_count(session=db) == 1


def test_definitive_submission_rejection_refunds_once_and_releases_slot(
    db, make_case, provider
):
    case = make_case()
    key = str(uuid.uuid4())
    provider.error = ReplicateAPIError(
        message="Synthetic rejected input", status_code=422
    )
    before_refunds = ledger_count(db, "generation_refund")
    first = submit(case, key)
    assert first.status == "failed"
    assert submit(case, key).id == first.id
    db.expire_all()
    assert get_coin_balance(session=db, app_user_id=case.user_id) == 100
    assert ledger_count(db, "generation_refund") == before_refunds + 1
    assert global_active_real_count(session=db) == 0 and provider.calls == 1
    provider.error = None
    assert submit(make_case()).status == "pending"
    assert provider.calls == 2


@pytest.mark.parametrize("status", [VideoTaskStatus.FAILED, VideoTaskStatus.CANCELED])
def test_existing_settlement_releases_slot_without_duplicate_refund(
    db, make_case, provider, status
):
    case = make_case()
    task = submit(case)
    before_refunds = ledger_count(db, "generation_refund")
    for _ in range(2):
        locked = lock_task(db, task.id)
        apply_provider_result(
            session=db,
            task=locked,
            result=VideoTaskResult(locked.provider_task_id, status),
        )
        db.commit()
    assert ledger_count(db, "generation_refund") == before_refunds + 1
    assert get_coin_balance(session=db, app_user_id=case.user_id) == 100
    assert submit(make_case()).status == "pending" and provider.calls == 2


def test_provider_success_does_not_release_slot_before_delivery(
    db, make_case, provider
):
    task = submit(make_case())
    locked = lock_task(db, task.id)
    apply_provider_result(
        session=db,
        task=locked,
        result=VideoTaskResult(
            locked.provider_task_id,
            VideoTaskStatus.SUCCEEDED,
            output_url="https://media.example.invalid/synthetic.mp4",
        ),
    )
    db.commit()
    with pytest.raises(HTTPException) as error:
        submit(make_case())
    assert error.value.status_code == 409
    assert db.get(AppVideoTask, task.id).status == "saving"
    assert global_active_real_count(session=db) == provider.calls == 1


@pytest.mark.parametrize(
    "quota",
    [
        "APP_USER_DAILY_REAL_SUBMISSIONS",
        "APP_GLOBAL_DAILY_REAL_SUBMISSIONS",
        "APP_WAN_DAILY_GLOBAL_SUBMISSIONS",
        "REPLICATE_POC_MAX_SUBMISSIONS",
    ],
)
def test_existing_daily_and_lifetime_budgets_remain_independent(
    db, make_case, provider, monkeypatch, quota
):
    case = make_case()
    task = seed_task(db, case, status="succeeded")
    task.real_submission_counted_at = datetime.now(UTC)
    db.add(task)
    db.commit()
    monkeypatch.setattr(settings, quota, 1)
    assert global_active_real_count(session=db) == 0
    with pytest.raises(HTTPException) as error:
        submit(case)
    assert error.value.status_code == 409 and provider.calls == 0


def test_global_setting_does_not_remove_per_user_limit(
    db, make_case, provider, monkeypatch
):
    case = make_case()
    seed_task(db, case, status="running")
    monkeypatch.setattr(settings, "APP_GLOBAL_MAX_CONCURRENT_VIDEO_TASKS", 2)
    monkeypatch.setattr(settings, "APP_USER_MAX_CONCURRENT_VIDEO_TASKS", 1)
    with pytest.raises(HTTPException) as error:
        submit(case)
    assert error.value.status_code == 409 and provider.calls == 0
    assert submit(make_case()).status == "pending" and provider.calls == 1


def _race_submit(case, key, barrier, release, messages):
    """Spawned interpreter = independent API process and database connection."""
    _configure_test_settings(setattr)

    class PausedProvider(Provider):
        async def submit_reference_to_video(self, **kwargs):
            messages.put(("provider", os.getpid()))
            if not await asyncio.to_thread(release.wait, 20):
                raise RuntimeError("Parent did not release synthetic provider")
            return await super().submit_reference_to_video(**kwargs)

    route.get_replicate_video_client = PausedProvider
    try:
        barrier.wait(timeout=20)
        result = submit(case, key)
        messages.put(("result", 202, str(result.id), os.getpid()))
    except HTTPException as error:
        messages.put(("result", error.status_code, None, os.getpid()))
    except Exception as error:
        messages.put(("unexpected", type(error).__name__, os.getpid()))
        raise
    finally:
        engine.dispose()


@pytest.mark.parametrize("same_idempotency", [False, True])
def test_two_api_processes_reserve_and_submit_at_most_once(
    db, make_case, same_idempotency
):
    cases = [make_case()]
    cases.append(cases[0] if same_idempotency else make_case())
    keys = [str(uuid.uuid4()), str(uuid.uuid4())]
    if same_idempotency:
        keys[1] = keys[0]
    before_debits = ledger_count(db, "generation_debit")
    db.commit()
    ctx = multiprocessing.get_context("spawn")
    barrier, release, messages = ctx.Barrier(2), ctx.Event(), ctx.Queue()
    processes = [
        ctx.Process(target=_race_submit, args=(case, key, barrier, release, messages))
        for case, key in zip(cases, keys, strict=True)
    ]
    observations = []
    try:
        for process in processes:
            process.start()
        # One request reserves then pauses at the mocked provider; the other
        # must reject (or return that reservation for an idempotent retry).
        observations.extend(messages.get(timeout=25) for _ in range(2))
        release.set()
        observations.append(messages.get(timeout=25))
        for process in processes:
            process.join(timeout=10)
        assert all(process.exitcode == 0 for process in processes), observations
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        messages.close()
        messages.join_thread()
    results = [row for row in observations if row[0] == "result"]
    assert len([row for row in observations if row[0] == "provider"]) == 1
    assert sorted(row[1] for row in results) == (
        [202, 202] if same_idempotency else [202, 409]
    )
    assert len({row[3] for row in results}) == 2
    if same_idempotency:
        assert results[0][2] == results[1][2]
    db.expire_all()
    assert task_count(db) == global_active_real_count(session=db) == 1
    assert ledger_count(db, "generation_debit") == before_debits + 1
    assert (
        sum(
            get_coin_balance(session=db, app_user_id=case.user_id)
            for case in {case.user_id: case for case in cases}.values()
        )
        == (100 if same_idempotency else 200) - COST
    )
