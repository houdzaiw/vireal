"""Persisted alerts and opt-in transport. Delivery != human acknowledgement.

A timed-out send may already have delivered: no automatic resend of an uncertain
attempt. An independent monitor and a real delivery test remain release gates.
"""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, text
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.models_operations import AppOperationalAlert
from app.services.operational_budget import (
    BudgetEvidenceError,
    alert_once,
    current_window,
    evaluate,
    utc_now,
)

# Persist quota receipts in the existing outbox. They are acknowledged internal
# records, never customer incidents; no fifth table or historical DDL change.
RECEIPT_PREFIX = "send-receipt:"
DAILY_SEND_LIMIT = 20
MONTHLY_SEND_LIMIT = 600
SEND_COOLDOWN = timedelta(minutes=10)


def claim_send(session: Session, now: datetime) -> AppOperationalAlert | None:
    # One account-wide lock, including across worker processes/budget windows.
    # Hosted operation uses PostgreSQL; fail closed for unsupported databases.
    if session.get_bind().dialect.name != "postgresql":
        return None
    session.connection().execute(text("SELECT pg_advisory_xact_lock(914731062)"))
    prefix = col(AppOperationalAlert.event_key).startswith(RECEIPT_PREFIX)
    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    for beginning, limit in ((day, DAILY_SEND_LIMIT), (month, MONTHLY_SEND_LIMIT)):
        count = session.exec(
            select(func.count())
            .select_from(AppOperationalAlert)
            .where(
                prefix,
                AppOperationalAlert.created_at >= beginning,
            )
        ).one()
        if count >= limit:
            return None
    latest = session.exec(
        select(AppOperationalAlert)
        .where(prefix)
        .order_by(col(AppOperationalAlert.created_at).desc())
        .limit(1)
    ).first()
    if latest is not None and now - latest.created_at < SEND_COOLDOWN:
        return None
    row = session.exec(
        select(AppOperationalAlert)
        .where(
            AppOperationalAlert.delivered_at == None,  # noqa: E711
            AppOperationalAlert.attempts == 0,
            ~prefix,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    ).first()
    if row is None:
        return None
    row.attempts = 1
    row.last_error_code = "send_outcome_unknown"
    session.add(row)
    session.add(
        AppOperationalAlert(
            window_id=row.window_id,
            event_key=RECEIPT_PREFIX + row.id.hex,
            created_at=now,
            acknowledged_at=now,
            attempts=1,
        )
    )
    session.commit()  # Claim/count before I/O; timeouts and crashes count too.
    return row


def record_worker_progress() -> None:
    with Session(engine) as session:
        window = current_window(session, lock=True)
        if window:
            window.worker_seen_at = utc_now()
            session.add(window)
            session.commit()


def evaluate_operations() -> None:
    with Session(engine) as session:
        window = current_window(session, lock=True)
        if window is None or window.state == "closed":
            return
        if window.state == "active":
            try:
                used = evaluate(session, window, utc_now())
                if used >= 105_000_000:
                    alert_once(session, window, "budget_warning")
            except BudgetEvidenceError as exc:
                window.state = "paused"
                window.pause_reason = str(exc)
                session.add(window)
                alert_once(session, window, "paused:" + str(exc))
        pending = session.exec(
            select(AppOperationalAlert).where(
                AppOperationalAlert.window_id == window.id,
                AppOperationalAlert.acknowledged_at == None,  # noqa: E711
            )
        ).all()
        # Missing acknowledgement cannot be treated as delivered/handled.
        if any(utc_now() - row.created_at > timedelta(minutes=5) for row in pending):
            window.state = "paused"
            window.pause_reason = "alert_unacknowledged"
            session.add(window)
        session.commit()


def send_one_alert() -> bool:
    if not settings.APP_OPERATIONAL_ALERT_DELIVERY_ENABLED:
        return False
    if not settings.OPS_RESEND_API_KEY or not settings.OPS_ALERT_FROM:
        return False
    now = utc_now()
    quota_until = settings.OPS_EMAIL_QUOTA_VERIFIED_UNTIL
    tomorrow = now.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    if quota_until is None or not now < quota_until <= tomorrow:
        return False
    with Session(engine) as session:
        row = claim_send(session, now)
        if row is None:
            return False
        identifier, event_key = row.id, row.event_key
    succeeded = False
    try:
        with httpx.Client(
            timeout=10, follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": "Bearer " + settings.OPS_RESEND_API_KEY,
                    "Idempotency-Key": "ops-" + str(identifier),
                },
                json={
                    "from": settings.OPS_ALERT_FROM,
                    "to": [str(settings.APP_SUPPORT_EMAIL)],
                    "subject": "Vireal operational alert",
                    "text": "Operational event: "
                    + event_key
                    + ". Review the private operations console; acknowledge after handling.",
                },
            )
            succeeded = response.status_code in {200, 201, 202}
    except httpx.HTTPError:
        pass  # Do not log bodies, tokens, URLs or recipient data.
    with Session(engine) as session:
        row = session.get(AppOperationalAlert, identifier)
        assert row is not None
        if succeeded:
            row.delivered_at = utc_now()
            row.last_error_code = None
        session.add(row)
        session.commit()
    return succeeded


def operational_tick() -> None:
    evaluate_operations()
    send_one_alert()
