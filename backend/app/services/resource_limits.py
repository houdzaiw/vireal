"""Durable finite allocations. Unknown outcomes never release resource budget.

No administration API or automatic renewal. A separate reviewed allocation must
cover every database/environment plus external account consumers. These counters
cannot constrain a credential used by another service or an already issued URL.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models_resources import AppResourceAttempt, AppResourcePolicy

METRICS = frozenset(
    {
        "uploads",
        "upload_bytes",
        "delivery_bytes",
        "storage_bytes",
        "class_a_upload",
        "class_a_delivery",
        "reads",
        "read_bytes",
        "grants",
        "generations",
        "attempts",
        "attempts_delivery",
        "reads_delivery",
        "read_bytes_delivery",
        "grants_delivery",
    }
)


def enabled() -> bool:
    return settings.ENVIRONMENT == "production" or settings.APP_RESOURCE_GUARD_ENABLED


def unavailable() -> HTTPException:
    return HTTPException(503, "Resource allowance is unavailable / 资源额度暂不可用")


def locked_policy(session: Session, *, admission: bool) -> AppResourcePolicy:
    now = datetime.now(UTC)
    scope = settings.APP_RESOURCE_SCOPE
    if not scope:
        raise unavailable()
    row = session.exec(
        select(AppResourcePolicy)
        .where(AppResourcePolicy.scope == scope)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if row is None or not row.enabled or not row.evidence or not row.account_evidence:
        raise unavailable()
    if not (
        row.starts_at <= now < row.delivery_until
        and row.starts_at < row.admission_until <= row.delivery_until
        and row.admission_until <= row.starts_at + timedelta(hours=72)
        and row.direct_urls_expired_at <= now
    ):
        raise unavailable()
    if admission and now >= row.admission_until:
        raise unavailable()
    if not isinstance(row.caps, dict) or not isinstance(row.used, dict):
        raise unavailable()
    if set(row.caps) != METRICS or not set(row.used) <= METRICS:
        raise unavailable()
    if any(
        type(v) is not int or v < 0 for v in [*row.caps.values(), *row.used.values()]
    ):
        raise unavailable()
    if any(row.used.get(k, 0) > v for k, v in row.caps.items()):
        raise unavailable()
    if (
        type(row.initial_storage_bytes) is not int
        or row.initial_storage_bytes < 0
        or type(row.pending_tasks_at_start) is not int
        or row.pending_tasks_at_start < 0
    ):
        raise unavailable()
    if not (
        1 <= row.caps["attempts"]
        and 1 <= row.caps["attempts_delivery"]
        and row.caps["attempts"] + row.caps["attempts_delivery"] <= 40000
    ):
        raise unavailable()
    writes = (
        row.caps["generations"] + row.pending_tasks_at_start
    ) * settings.VIDEO_WORKER_MAX_ATTEMPTS
    if (
        row.caps["class_a_delivery"] < writes
        or row.caps["reads_delivery"] < writes * 3
        or row.caps["grants_delivery"] < writes * 3
        or row.caps["delivery_bytes"] < writes * settings.MAX_GENERATED_VIDEO_BYTES
        or row.caps["storage_bytes"]
        < row.initial_storage_bytes
        + row.caps["upload_bytes"]
        + row.caps["delivery_bytes"]
        or row.used.get("storage_bytes", 0) < row.initial_storage_bytes
    ):
        raise unavailable()
    return row


def charge(
    session: Session, policy: AppResourcePolicy, operation: str, units: dict[str, int]
) -> None:
    if (
        not units
        or not set(units) <= METRICS
        or any(type(v) is not int or v < 0 for v in units.values())
    ):
        raise unavailable()
    if {"attempts", "attempts_delivery"} & units.keys() or not any(units.values()):
        raise unavailable()
    delivery = any(
        k in units for k in ("class_a_delivery", "reads_delivery", "grants_delivery")
    )
    units = {**units, "attempts_delivery" if delivery else "attempts": 1}
    used = dict(policy.used)
    for key, value in units.items():
        used[key] = used.get(key, 0) + value
        if used[key] > policy.caps[key]:
            raise HTTPException(429, "Resource allowance reached / 资源额度已用尽")
    policy.used = used
    session.add(policy)
    session.add(
        AppResourceAttempt(scope=policy.scope, operation=operation, units=units)
    )


def consume(operation: str, units: dict[str, int], *, admission: bool = False) -> None:
    if not enabled():
        return
    try:
        with Session(engine) as session:
            policy = locked_policy(session, admission=admission)
            charge(session, policy, operation, units)
            session.commit()  # Before external I/O; survives caller rollback or crash.
    except SQLAlchemyError as exc:
        raise unavailable() from exc


def reserve_generation(model: str, duration: int) -> None:
    if not enabled():
        return
    try:
        with Session(engine) as session:
            policy = locked_policy(session, admission=True)
            if model != policy.model or duration != policy.duration:
                raise HTTPException(
                    403, "Model is outside the reviewed pilot allocation"
                )
            # Gross delivery capacity is checked at write time. The allocation
            # review must reserve all worker retries for every admitted slot.
            charge(session, policy, "generation", {"generations": 1})
            session.commit()
    except SQLAlchemyError as exc:
        raise unavailable() from exc


_delivery_reads: ContextVar[bool] = ContextVar("delivery_reads", default=False)


@contextmanager
def delivery_reads(delivery: bool = True):
    token = _delivery_reads.set(delivery)
    try:
        yield
    finally:
        _delivery_reads.reset(token)


def read_units(maximum_bytes: int) -> dict[str, int]:
    suffix = "_delivery" if _delivery_reads.get() else ""
    return {"reads" + suffix: 1, "read_bytes" + suffix: maximum_bytes}
