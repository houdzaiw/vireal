from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.db import engine
from app.models_operations import AppBudgetWindow, AppOperationalAlert
from app.services import operational_alerts as alerts


def pending(db, key="test"):
    window = db.exec(select(AppBudgetWindow)).one()
    row = AppOperationalAlert(window_id=window.id, event_key=key)
    db.add(row)
    db.commit()
    return row


def receipt(db, at, key):
    row = pending(db, alerts.RECEIPT_PREFIX + key)
    row.created_at = row.acknowledged_at = at
    row.attempts = 1
    db.add(row)
    db.commit()


@pytest.mark.parametrize("count,allowed", [(19, True), (20, False)])
def test_daily_limit_counts_attempts_not_deliveries(db, count, allowed):
    now = datetime(2026, 11, 8, 20, tzinfo=UTC)
    for i in range(count):
        receipt(db, now - timedelta(hours=1), str(i))
    pending(db)
    assert (alerts.claim_send(db, now) is not None) is allowed


def test_month_limit_and_utc_rollover(db):
    now = datetime(2026, 11, 8, tzinfo=UTC)
    for i in range(600):
        row = AppOperationalAlert(
            window_id=db.exec(select(AppBudgetWindow.id)).one(),
            event_key=alerts.RECEIPT_PREFIX + str(i),
            created_at=now - timedelta(days=1),
            acknowledged_at=now,
            attempts=1,
        )
        db.add(row)
    db.commit()
    pending(db)
    assert alerts.claim_send(db, now) is None
    db.rollback()
    assert alerts.claim_send(db, datetime(2026, 12, 1, tzinfo=UTC)) is not None


def test_flapping_cooldown_survives_new_rows_and_sessions(db):
    now = datetime(2026, 11, 8, 2, tzinfo=UTC)
    first = pending(db, "failure-1")
    assert alerts.claim_send(db, now).id == first.id
    pending(db, "failure-2")
    with Session(engine) as other:
        assert alerts.claim_send(other, now + timedelta(minutes=9, seconds=59)) is None
    with Session(engine) as other:
        assert alerts.claim_send(other, now + timedelta(minutes=10)) is not None


def test_concurrent_workers_only_claim_one_send(db):
    now = datetime(2026, 11, 8, 2, tzinfo=UTC)
    for i in range(5):
        pending(db, str(i))
    db.rollback()

    def claim(_):
        with Session(engine) as session:
            return alerts.claim_send(session, now) is not None

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(claim, range(5))) == 1


def test_receipts_are_not_incidents_or_retried_after_crash(db):
    now = datetime(2026, 11, 8, 2, tzinfo=UTC)
    row = pending(db)
    assert alerts.claim_send(db, now).id == row.id
    # The claim was committed, but the transport never returned.
    with Session(engine) as restarted:
        assert alerts.claim_send(restarted, now + timedelta(days=1)) is None
    receipts = db.exec(
        select(AppOperationalAlert).where(
            AppOperationalAlert.event_key.startswith(alerts.RECEIPT_PREFIX)
        )
    ).all()
    assert len(receipts) == 1 and receipts[0].acknowledged_at is not None
