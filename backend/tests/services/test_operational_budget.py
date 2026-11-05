import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models_operations import (
    AppBudgetWindow,
    AppCostObservation,
    AppCostReservation,
    AppOperationalAlert,
)
from app.services import operational_budget as budget
from tests.utils.operations import staffed_now


def current(db: Session) -> AppBudgetWindow:
    return db.exec(select(AppBudgetWindow)).one()


def enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_BUDGET_GUARD_ENABLED", True)


def spent(db: Session, amount: int) -> None:
    row = db.exec(
        select(AppCostObservation).where(AppCostObservation.source == "railway")
    ).one()
    row.spent_micros = amount
    db.add(row)
    db.commit()


@pytest.mark.parametrize(
    "amount,allowed",
    [
        (104_000_000, True),
        (105_000_000, True),
        (119_999_999, True),
        (120_000_000, False),
        (150_000_000, False),
    ],
)
def test_strict_dollar_boundaries(
    db: Session, monkeypatch: pytest.MonkeyPatch, amount: int, allowed: bool
) -> None:
    enable(monkeypatch)
    spent(db, amount)
    if allowed:
        budget.require_budget(db)
        db.commit()
        assert len(db.exec(select(AppOperationalAlert)).all()) == (
            1 if amount >= budget.WARN else 0
        )
    else:
        with pytest.raises(HTTPException):
            budget.require_budget(db)
        assert current(db).state == "paused"
        spent(db, 0)
        with pytest.raises(HTTPException):
            budget.require_budget(db)  # sticky after spend falls
        assert current(db).pause_reason == "budget_pause_threshold"
        assert len(db.exec(select(AppOperationalAlert)).all()) == 1


def test_production_cannot_disable_guard(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APP_BUDGET_GUARD_ENABLED", False)
    current(db).state = "draft"
    db.commit()
    with pytest.raises(HTTPException):
        budget.require_budget(db)


@pytest.mark.parametrize(
    "fault",
    [
        "missing-source",
        "stale-source",
        "closing-unbounded",
        "closing-over",
        "no-owner",
        "no-backup",
        "no-alert",
        "no-worker",
        "expired",
        "outside-hours",
        "missing-price",
        "price-naive",
    ],
)
def test_missing_evidence_fails_closed(
    db: Session, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    enable(monkeypatch)
    window = current(db)
    now = staffed_now()
    if fault == "missing-source":
        db.delete(db.exec(select(AppCostObservation).limit(1)).one())
    elif fault == "stale-source":
        row = db.exec(select(AppCostObservation).limit(1)).one()
        row.valid_until = now
        db.add(row)
    elif fault == "closing-unbounded":
        window.closing_bound_micros = None
    elif fault == "closing-over":
        window.closing_bound_micros = 30_000_001
    elif fault == "no-owner":
        window.owner_present_until = now
    elif fault == "no-backup":
        window.backup_verified_until = None
    elif fault == "no-alert":
        window.alerts_verified_until = None
    elif fault == "no-worker":
        window.worker_seen_at = now - timedelta(seconds=91)
    elif fault == "expired":
        monkeypatch.setattr(budget, "utc_now", lambda: window.ends_at)
    elif fault == "outside-hours":
        monkeypatch.setattr(
            budget, "utc_now", lambda: now.replace(hour=15)
        )  # 23 Beijing
    elif fault == "missing-price":
        window.prices = {}
    elif fault == "price-naive":
        window.prices = {
            "upload": {
                "bound_micros": 1,
                "valid_until": "2026-12-01T00:00:00",
                "evidence": "synthetic",
            }
        }
    db.add(window)
    db.commit()
    with pytest.raises(HTTPException):
        budget.reserve_cost(db, key="upload:test", source="r2", price_key="upload")
    assert not db.exec(select(AppCostReservation)).all()
    assert current(db).state == "paused"


def test_atomic_reservation_and_rollback(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    row = budget.reserve_cost(
        db, key="video:synthetic", source="replicate", price_key="upload"
    )
    assert row
    db.rollback()
    assert not db.exec(select(AppCostReservation)).all()
    first = budget.reserve_cost(
        db, key="video:synthetic", source="replicate", price_key="upload"
    )
    db.commit()
    again = budget.reserve_cost(
        db, key="video:synthetic", source="replicate", price_key="upload"
    )
    db.commit()
    assert first and again and first.id == again.id
    assert len(db.exec(select(AppCostReservation)).all()) == 1


def test_multisession_row_lock_prevents_oversubscription(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    spent(db, 118_500_000)
    db.rollback()

    def request(index: int) -> bool:
        with Session(engine) as independent:
            try:
                budget.reserve_cost(
                    independent,
                    key=f"parallel:{index}",
                    source="r2",
                    price_key="upload",
                )
                independent.commit()
                return True
            except HTTPException:
                return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(request, range(6)))
    db.expire_all()
    assert sum(results) == 1
    assert len(db.exec(select(AppCostReservation)).all()) == 1
    assert current(db).state == "paused"


def test_unknown_submission_and_coin_refund_hold_usd(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    row = budget.reserve_cost(
        db, key="video:unknown", source="replicate", price_key="upload"
    )
    db.commit()
    assert row and row.actual_micros is None
    # Delivery, failure and coin refunds have no USD-settlement hook.
    assert budget.exposure(db, current(db), staffed_now()) == 1_000_000
    budget.settle_cost(
        db,
        reservation_id=row.id,
        actual_micros=700_000,
        reference="synthetic invoice item",
    )
    db.commit()
    assert budget.exposure(db, current(db), staffed_now()) == 700_000
    with pytest.raises(budget.BudgetEvidenceError):
        budget.settle_cost(
            db, reservation_id=row.id, actual_micros=0, reference="coin-refund"
        )
    db.rollback()


def test_invoice_coverage_removes_only_proved_double_count(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    row = budget.reserve_cost(
        db, key="video:covered", source="replicate", price_key="upload"
    )
    db.commit()
    assert row
    budget.settle_cost(
        db,
        reservation_id=row.id,
        actual_micros=600_000,
        reference="synthetic line item",
    )
    db.commit()
    obs = db.exec(
        select(AppCostObservation).where(AppCostObservation.source == "replicate")
    ).one()
    obs.observed_at = row.created_at + timedelta(seconds=1)
    # use consistent synthetic provider/report clock
    monkeypatch.setattr(budget, "utc_now", lambda: obs.observed_at)
    obs.spent_micros = 800_000
    obs.covered_reservation_ids = [str(row.id)]
    db.add(obs)
    db.commit()
    assert budget.exposure(db, current(db), obs.observed_at) == 800_000
    obs.covered_reservation_ids = [str(uuid.uuid4())]
    db.add(obs)
    db.commit()
    with pytest.raises(budget.BudgetEvidenceError, match="coverage_unproved"):
        budget.exposure(db, current(db), obs.observed_at)


def test_settlement_overrun_is_recorded_and_pauses(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    row = budget.reserve_cost(db, key="overrun", source="replicate", price_key="upload")
    db.commit()
    assert row
    budget.settle_cost(
        db,
        reservation_id=row.id,
        actual_micros=151_000_000,
        reference="synthetic overrun invoice",
    )
    db.commit()
    assert db.get(AppCostReservation, row.id).actual_micros == 151_000_000
    assert current(db).state == "paused"


def test_reads_do_not_create_or_reset_period(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    window = current(db)
    original = (window.id, window.starts_at, window.ends_at)
    for _ in range(3):
        assert budget.new_business_available(db)
    assert (window.id, window.starts_at, window.ends_at) == original


def _child_admission(database_url, index, frozen_now, queue):
    from datetime import datetime

    from sqlmodel import Session, create_engine

    from app.core.config import settings
    from app.services import operational_budget

    settings.APP_BUDGET_GUARD_ENABLED = True
    operational_budget.utc_now = lambda: datetime.fromisoformat(frozen_now)
    local_engine = create_engine(database_url)
    try:
        with Session(local_engine) as session:
            try:
                operational_budget.reserve_cost(
                    session, key=f"process:{index}", source="r2", price_key="upload"
                )
                session.commit()
                queue.put(True)
            except HTTPException:
                queue.put(False)
    finally:
        local_engine.dispose()


def test_cross_process_reservations_are_serialized(db: Session) -> None:
    import multiprocessing

    spent(db, 118_500_000)
    db.rollback()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(
            target=_child_admission,
            args=(str(engine.url), i, staffed_now().isoformat(), queue),
        )
        for i in range(3)
    ]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0
        assert sum(results) == 1
        db.expire_all()
        assert len(db.exec(select(AppCostReservation)).all()) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        queue.close()


def test_72_hours_can_span_four_utc_dates_without_reset(db: Session) -> None:
    window = current(db)
    original_id = window.id
    before = window.starts_at.replace(hour=23, minute=30)
    window.starts_at = before
    window.ends_at = before + timedelta(hours=72)
    db.add(window)
    db.commit()
    for days in range(4):
        observed = before + timedelta(days=days)
        assert current(db).id == original_id
        if days == 3:
            with pytest.raises(budget.BudgetEvidenceError, match="window_expired"):
                budget.readiness(db, window, observed)
