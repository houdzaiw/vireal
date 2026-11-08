"""Private, authenticated operator evidence. No customer financial permissions."""

import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import col, select

from app.api.deps import (
    SessionDep,
    get_current_active_superuser,
    require_cloudflare_access,
)
from app.core.config import settings
from app.models import AppAdminOperationLog, User
from app.models_operations import (
    AppBudgetWindow,
    AppCostObservation,
    AppCostReservation,
    AppOperationalAlert,
)
from app.services.operational_budget import (
    SOURCES,
    BudgetEvidenceError,
    alert_once,
    current_window,
    evaluate,
    new_business_available,
    settle_cost,
    utc_now,
)

router = APIRouter(prefix="/operations", tags=["operations"])


def require_operator(
    request: Request, user: Annotated[User, Depends(get_current_active_superuser)]
) -> User:
    require_cloudflare_access(request)
    return user


Operator = Annotated[User, Depends(require_operator)]


def audit(
    session: SessionDep, operator: User, action: str, window_id: uuid.UUID
) -> None:
    session.add(
        AppAdminOperationLog(
            admin_user_id=operator.id,
            admin_email=operator.email,
            action="operations." + action,
            target_type="app_budget_window",
            target_id=window_id,
            summary="Operator explicitly recorded operational evidence or state",
        )
    )


class Period(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class Facts(BaseModel):
    closing_bound_micros: int = Field(ge=0, le=30_000_000)
    closing_evidence: str = Field(min_length=1, max_length=500)
    owner_present_until: AwareDatetime
    alerts_verified_until: AwareDatetime
    backup_verified_until: AwareDatetime
    prices: dict[str, dict[str, str | int]]


class Observation(BaseModel):
    source: str
    spent_micros: int = Field(ge=0)
    unreported_bound_micros: int = Field(ge=0)
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    evidence_reference: str = Field(min_length=1, max_length=500)
    covered_reservation_ids: list[uuid.UUID] = []


class Settlement(BaseModel):
    actual_micros: int = Field(ge=0)
    evidence_reference: str = Field(min_length=1, max_length=500)


def locked_window(session: SessionDep) -> AppBudgetWindow:
    row = current_window(session, lock=True)
    if row is None:
        raise HTTPException(409, "No current operational period")
    return row


@router.post("/period", include_in_schema=False)
def create_period(
    body: Period, session: SessionDep, _operator: Operator
) -> dict[str, str]:
    # Serialize period creation, including when no current row exists yet.
    from sqlalchemy import text

    session.connection().execute(text("SELECT pg_advisory_xact_lock(682951107)"))
    now = utc_now()
    if not (
        now - timedelta(minutes=5) <= body.starts_at <= now
        and body.starts_at < body.ends_at <= body.starts_at + timedelta(hours=72)
    ):
        raise HTTPException(422, "Period must start now and last at most 72 hours")
    previous = current_window(session, lock=True)
    if previous:
        if session.exec(
            select(AppCostReservation)
            .where(col(AppCostReservation.actual_micros).is_(None))
            .limit(1)
        ).first():
            raise HTTPException(
                409, "Unsettled exposure cannot reset with a new period"
            )
        if body.starts_at < previous.ends_at:
            raise HTTPException(
                409, "Cannot reset or overlap an existing budget period"
            )
        previous.is_current = False
        previous.state = "closed"
        session.add(previous)
        session.flush()
    row = AppBudgetWindow(starts_at=body.starts_at, ends_at=body.ends_at)
    session.add(row)
    audit(session, _operator, "period.create", row.id)
    session.commit()
    return {"id": str(row.id), "state": row.state}


@router.put("/facts", include_in_schema=False)
def record_facts(
    body: Facts, session: SessionDep, _operator: Operator
) -> dict[str, bool]:
    row = locked_window(session)
    now = utc_now()
    if (
        not now
        < body.owner_present_until
        <= min(now + timedelta(minutes=15), row.ends_at)
    ):
        raise HTTPException(422, "Presence expires within 15 minutes")
    if not now < body.alerts_verified_until <= min(
        now + timedelta(hours=24), row.ends_at
    ) or not now < body.backup_verified_until <= min(
        now + timedelta(hours=1), row.ends_at
    ):
        raise HTTPException(
            422, "Fresh alert delivery and hourly backup evidence required"
        )
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    session.add(row)
    audit(session, _operator, "evidence.update", locked_window(session).id)
    session.commit()
    return {"recorded": True, "automatically_opened": False}


@router.put("/observations", include_in_schema=False)
def record_observation(
    body: Observation, session: SessionDep, _operator: Operator
) -> dict[str, bool]:
    window = locked_window(session)
    if (
        body.source not in SOURCES
        or not window.starts_at
        <= body.observed_at
        <= utc_now()
        < body.valid_until
        <= window.ends_at
    ):
        raise HTTPException(422, "Source or cost coverage is invalid")
    row = session.exec(
        select(AppCostObservation).where(
            AppCostObservation.window_id == window.id,
            AppCostObservation.source == body.source,
        )
    ).first()
    if row is not None and (
        body.observed_at < row.observed_at or body.spent_micros < row.spent_micros
    ):
        raise HTTPException(409, "Cumulative observations cannot move backwards")
    data = body.model_dump()
    data["covered_reservation_ids"] = [
        str(value) for value in body.covered_reservation_ids
    ]
    if row is None:
        row = AppCostObservation(window_id=window.id, **data)
    else:
        for name, value in data.items():
            setattr(row, name, value)
    session.add(row)
    # Validate coverage even while paused; do not reopen the budget.
    session.flush()
    from app.services.operational_budget import exposure

    try:
        exposure(session, window, utc_now())
    except BudgetEvidenceError as exc:
        if str(exc) != "sources_incomplete":
            session.rollback()
            raise HTTPException(422, str(exc)) from exc
    audit(session, _operator, "evidence.update", locked_window(session).id)
    session.commit()
    return {"recorded": True, "automatically_opened": False}


@router.post("/activate", include_in_schema=False)
def activate(session: SessionDep, _operator: Operator) -> dict[str, str]:
    window = locked_window(session)
    if window.state == "closed":
        raise HTTPException(409, "Period is closed")
    old_state = window.state
    window.state = "active"
    try:
        evaluate(session, window, utc_now())
    except BudgetEvidenceError as exc:
        window.state = old_state
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
    window.pause_reason = None
    session.add(window)
    audit(session, _operator, "activate", window.id)
    session.commit()
    return {"state": "active"}


@router.post("/pause", include_in_schema=False)
def pause(session: SessionDep, _operator: Operator) -> dict[str, str]:
    window = locked_window(session)
    window.state = "paused"
    window.pause_reason = "operator_pause"
    session.add(window)
    alert_once(session, window, "paused:operator_pause")
    audit(session, _operator, "pause", window.id)
    session.commit()
    return {"state": "paused"}


@router.post("/reservations/{identifier}/settlement", include_in_schema=False)
def settlement(
    identifier: uuid.UUID, body: Settlement, session: SessionDep, _operator: Operator
) -> dict[str, bool]:
    try:
        settle_cost(
            session,
            reservation_id=identifier,
            actual_micros=body.actual_micros,
            reference=body.evidence_reference,
        )
    except BudgetEvidenceError as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
    audit(session, _operator, "cost.settle", locked_window(session).id)
    session.commit()
    return {"recorded": True}


@router.get("/status", include_in_schema=False)
def status(session: SessionDep, _operator: Operator) -> dict[str, Any]:
    window = current_window(session)
    alerts = session.exec(
        select(AppOperationalAlert).where(
            col(AppOperationalAlert.acknowledged_at).is_(None)
        )
    ).all()
    return {
        "new_business_available": new_business_available(session),
        "state": window.state if window else "missing",
        "pause_reason": window.pause_reason if window else "window_missing",
        "pending_alerts": [
            {
                "id": str(row.id),
                "code": row.event_key,
                "delivered": row.delivered_at is not None,
            }
            for row in alerts
        ],
    }


@router.post("/alerts/{identifier}/acknowledge", include_in_schema=False)
def acknowledge(
    identifier: uuid.UUID, session: SessionDep, _operator: Operator
) -> dict[str, bool]:
    row = session.get(AppOperationalAlert, identifier)
    if row is None:
        raise HTTPException(404, "Alert not found")
    row.acknowledged_at = utc_now()
    session.add(row)
    audit(session, _operator, "alert.acknowledge", row.window_id)
    session.commit()
    return {"acknowledged": True, "automatically_opened": False}


@router.get("/monitor", include_in_schema=False)
def monitor(
    request: Request, response: Response, session: SessionDep
) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    supplied = request.headers.get("authorization", "")
    token = settings.OPS_MONITOR_READ_TOKEN
    if not token or not hmac.compare_digest(
        supplied.encode(), ("Bearer " + token).encode()
    ):
        raise HTTPException(403, "Monitor access denied")
    window = current_window(session)
    now = datetime.now(UTC)
    return {
        "database_available": True,
        "monitoring_required": bool(
            window
            and window.state in {"active", "paused"}
            and window.starts_at <= now < window.ends_at
        ),
        "new_business_available": new_business_available(session),
        "worker_recent": bool(
            window
            and window.worker_seen_at
            and timedelta(0) <= now - window.worker_seen_at <= timedelta(seconds=90)
        ),
        "backup_recent": bool(
            window
            and window.backup_verified_until
            and now < window.backup_verified_until
        ),
    }
