"""Durable USD admission. Caller commits reservation with its new business row.

Existing settlement, provider reconciliation and delivery MUST NOT call admission.
Neither a task failure nor a coin refund is evidence of zero vendor expense.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models_operations import (
    AppBudgetWindow,
    AppCostObservation,
    AppCostReservation,
    AppOperationalAlert,
)

MICRO_USD = 1_000_000
WARN = 105 * MICRO_USD
PAUSE = 120 * MICRO_USD
TOTAL = 150 * MICRO_USD
CLOSING = 30 * MICRO_USD
SOURCES = frozenset(
    {
        "railway",
        "neon-production",
        "neon-staging",
        "replicate",
        "r2",
        "clerk",
        "cloudflare",
        "other",
    }
)


class BudgetEvidenceError(ValueError):
    """Safe category only; no provider payloads, credentials or customer records."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def budget_required() -> bool:
    # Opening old production flags alone cannot bypass the dollar gate.
    return settings.ENVIRONMENT == "production" or settings.APP_BUDGET_GUARD_ENABLED


def current_window(session: Session, *, lock: bool = False) -> AppBudgetWindow | None:
    query = select(AppBudgetWindow).where(col(AppBudgetWindow.is_current).is_(True))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return session.exec(query).first()


def alert_once(session: Session, window: AppBudgetWindow, key: str) -> None:
    # All callers hold the window lock; unique index also protects deduplication.
    existing = session.exec(
        select(AppOperationalAlert).where(
            AppOperationalAlert.window_id == window.id,
            AppOperationalAlert.event_key == key,
        )
    ).first()
    if existing is None:
        session.add(AppOperationalAlert(window_id=window.id, event_key=key))


def exposure(session: Session, window: AppBudgetWindow, now: datetime) -> int:
    observations = session.exec(
        select(AppCostObservation).where(AppCostObservation.window_id == window.id)
    ).all()
    by_source = {row.source: row for row in observations}
    if set(by_source) != SOURCES:
        raise BudgetEvidenceError("sources_incomplete")
    reservations = session.exec(
        select(AppCostReservation).where(AppCostReservation.window_id == window.id)
    ).all()
    by_id = {str(row.id): row for row in reservations}
    covered: set[str] = set()
    total = 0
    for source, observation in by_source.items():
        if not (
            window.starts_at
            <= observation.observed_at
            <= now
            < observation.valid_until
            <= window.ends_at
        ):
            raise BudgetEvidenceError("source_stale")
        if (
            not observation.evidence_reference
            or observation.spent_micros < 0
            or observation.unreported_bound_micros < 0
        ):
            raise BudgetEvidenceError("source_unbounded")
        ids = observation.covered_reservation_ids
        if len(set(ids)) != len(ids):
            raise BudgetEvidenceError("coverage_duplicate")
        covered_cost = 0
        for identifier in ids:
            row = by_id.get(identifier)
            if (
                row is None
                or row.source != source
                or row.actual_micros is None
                or not row.settlement_reference
            ):
                raise BudgetEvidenceError("coverage_unproved")
            if row.created_at > observation.observed_at:
                raise BudgetEvidenceError("coverage_future")
            covered_cost += row.actual_micros
        if covered_cost > observation.spent_micros:
            raise BudgetEvidenceError("coverage_exceeds_invoice")
        covered.update(ids)
        total += observation.spent_micros + observation.unreported_bound_micros
    total += sum(
        row.actual_micros if row.actual_micros is not None else row.bound_micros
        for row in reservations
        if str(row.id) not in covered
    )
    return total


def readiness(session: Session, window: AppBudgetWindow, now: datetime) -> int:
    if window.state != "active":
        raise BudgetEvidenceError("window_inactive")
    if not (
        window.starts_at
        <= now
        < window.ends_at
        <= window.starts_at + timedelta(hours=72)
    ):
        raise BudgetEvidenceError("window_expired")
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if not 9 <= local.hour < 23:
        raise BudgetEvidenceError("outside_staffed_hours")
    if (
        not window.owner_present_until
        or not now < window.owner_present_until <= now + timedelta(minutes=15)
    ):
        raise BudgetEvidenceError("owner_not_present")
    for deadline in (window.alerts_verified_until, window.backup_verified_until):
        if not deadline or now >= deadline:
            raise BudgetEvidenceError("operations_evidence_stale")
    if not window.worker_seen_at or not timedelta(
        0
    ) <= now - window.worker_seen_at <= timedelta(seconds=90):
        raise BudgetEvidenceError("worker_heartbeat_stale")
    if (
        window.closing_bound_micros is None
        or not window.closing_evidence
        or not 0 <= window.closing_bound_micros <= CLOSING
    ):
        raise BudgetEvidenceError("closing_cost_unbounded")
    return exposure(session, window, now)


def evaluate(
    session: Session, window: AppBudgetWindow, now: datetime, bound: int = 0
) -> int:
    used = readiness(session, window, now)
    closing = window.closing_bound_micros
    assert closing is not None
    if used + bound >= PAUSE or used + bound + closing > TOTAL:
        raise BudgetEvidenceError("budget_pause_threshold")
    return used


def persist_pause(engine: Engine, window_id: uuid.UUID, reason: str) -> None:
    # The caller rolls back before this fresh transaction, so no unrelated order
    # or wallet changes can accidentally be committed by a rejected admission.
    with Session(engine) as evidence:
        window = evidence.exec(
            select(AppBudgetWindow)
            .where(AppBudgetWindow.id == window_id)
            .with_for_update()
        ).one()
        if window.state == "paused":
            # Repeated denied requests must not replace the original cause with
            # the generic inactive-period reason or create another notification.
            return
        if window.state != "closed":
            window.state = "paused"
            window.pause_reason = reason
            evidence.add(window)
            alert_once(evidence, window, "paused:" + reason)
            evidence.commit()


def deny(session: Session, window: AppBudgetWindow | None, reason: str) -> NoReturn:
    identifier = window.id if window else None
    engine = session.get_bind()
    session.rollback()
    if identifier is not None and isinstance(engine, Engine):
        persist_pause(engine, identifier, reason)
    raise HTTPException(503, "New business is temporarily paused / 新业务暂时关闭")


def require_budget(session: Session) -> None:
    if not budget_required():
        return
    window = current_window(session, lock=True)
    if window is None:
        deny(session, None, "window_missing")
    assert window is not None
    try:
        used = evaluate(session, window, utc_now())
    except BudgetEvidenceError as exc:
        deny(session, window, str(exc))
    if used >= WARN:
        alert_once(session, window, "budget_warning")


def reserve_cost(
    session: Session, *, key: str, source: str, price_key: str
) -> AppCostReservation | None:
    if not budget_required():
        return None
    window = current_window(session, lock=True)
    existing = session.exec(
        select(AppCostReservation).where(AppCostReservation.operation_key == key)
    ).first()
    if existing is not None:
        # A retry can observe its existing reservation; it must not submit again.
        if (
            window is None
            or existing.window_id != window.id
            or existing.source != source
        ):
            deny(session, window, "reservation_conflict")
        return existing
    if window is None:
        deny(session, None, "window_missing")
    assert window is not None
    now = utc_now()
    try:
        price = window.prices.get(price_key, {})
        bound = price.get("bound_micros")
        valid_text = price.get("valid_until")
        if (
            not isinstance(bound, int)
            or isinstance(bound, bool)
            or bound <= 0
            or not isinstance(valid_text, str)
            or not price.get("evidence")
        ):
            raise BudgetEvidenceError("price_unbounded")
        try:
            valid_until = datetime.fromisoformat(valid_text)
            valid = now < valid_until <= window.ends_at
        except ValueError, TypeError:
            valid = False
        if not valid:
            raise BudgetEvidenceError("price_stale")
        used = evaluate(session, window, now, bound)
    except BudgetEvidenceError as exc:
        deny(session, window, str(exc))
    row = AppCostReservation(
        window_id=window.id,
        operation_key=key,
        source=source,
        bound_micros=bound,
        created_at=now,
    )
    session.add(row)
    if used + bound >= WARN:
        alert_once(session, window, "budget_warning")
    return row


def new_business_available(session: Session) -> bool:
    if not budget_required():
        return True
    window = current_window(session)
    if window is None:
        return False
    try:
        evaluate(session, window, utc_now())
    except BudgetEvidenceError:
        return False
    return True


def settle_cost(
    session: Session, *, reservation_id: uuid.UUID, actual_micros: int, reference: str
) -> None:
    """Operator-verified USD only; record overspend instead of hiding it."""
    window = current_window(session, lock=True)
    row = session.get(AppCostReservation, reservation_id)
    if (
        window is None
        or row is None
        or row.window_id != window.id
        or actual_micros < 0
        or not reference.strip()
    ):
        raise BudgetEvidenceError("settlement_invalid")
    if row.actual_micros is not None:
        if row.actual_micros != actual_micros or row.settlement_reference != reference:
            raise BudgetEvidenceError("settlement_conflict")
        return
    row.actual_micros = actual_micros
    row.settlement_reference = reference
    session.add(row)
    session.flush()
    try:
        evaluate(session, window, utc_now())
    except BudgetEvidenceError as exc:
        window.state = "paused"
        window.pause_reason = str(exc)
        session.add(window)
        alert_once(session, window, "paused:" + str(exc))
