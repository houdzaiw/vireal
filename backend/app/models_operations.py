"""Additive operational evidence; never substitute coins for vendor USD costs."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(UTC)


class AppBudgetWindow(SQLModel, table=True):
    __tablename__ = "app_budget_window"
    __table_args__ = (
        Index(
            "uq_budget_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current"),
        ),
        CheckConstraint("ends_at > starts_at"),
        CheckConstraint("ends_at <= starts_at + interval '72 hours'").ddl_if(
            dialect="postgresql"
        ),
        CheckConstraint("julianday(ends_at) - julianday(starts_at) <= 3").ddl_if(
            dialect="sqlite"
        ),
        CheckConstraint("closing_bound_micros IS NULL OR closing_bound_micros >= 0"),
        CheckConstraint("state IN ('draft', 'active', 'paused', 'closed')"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    is_current: bool = True
    starts_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    ends_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    state: str = "draft"
    pause_reason: str | None = None
    closing_bound_micros: int | None = Field(default=None, sa_type=BigInteger)
    closing_evidence: str | None = None
    owner_present_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    alerts_verified_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    backup_verified_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    worker_seen_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Explicit, reviewed upper bounds by exact operation/model/duration; no inferred prices.
    prices: dict[str, dict[str, str | int]] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AppCostReservation(SQLModel, table=True):
    __tablename__ = "app_cost_reservation"
    __table_args__ = (
        CheckConstraint(
            "bound_micros >= 0 AND (actual_micros IS NULL OR actual_micros >= 0)"
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    window_id: uuid.UUID = Field(foreign_key="app_budget_window.id", index=True)
    operation_key: str = Field(unique=True, max_length=255)
    source: str = Field(max_length=60)
    bound_micros: int = Field(sa_type=BigInteger)
    actual_micros: int | None = Field(default=None, sa_type=BigInteger)
    settlement_reference: str | None = None
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AppCostObservation(SQLModel, table=True):
    __tablename__ = "app_cost_observation"
    __table_args__ = (
        Index("uq_budget_source", "window_id", "source", unique=True),
        CheckConstraint("spent_micros >= 0 AND unreported_bound_micros >= 0"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    window_id: uuid.UUID = Field(foreign_key="app_budget_window.id", index=True)
    source: str = Field(max_length=60)
    spent_micros: int = Field(sa_type=BigInteger)
    unreported_bound_micros: int = Field(sa_type=BigInteger)
    observed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    valid_until: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    evidence_reference: str
    # Only settled reservations from this same source/window may be covered.
    covered_reservation_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )


class AppOperationalAlert(SQLModel, table=True):
    __tablename__ = "app_operational_alert"
    __table_args__ = (Index("uq_budget_alert", "window_id", "event_key", unique=True),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    window_id: uuid.UUID = Field(foreign_key="app_budget_window.id", index=True)
    event_key: str = Field(max_length=100)
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    delivered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    acknowledged_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    attempts: int = 0
    last_error_code: str | None = None
