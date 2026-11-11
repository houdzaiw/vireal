"""Account allocations prepared offline; no seeded policies or activation."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


class AppResourcePolicy(SQLModel, table=True):
    __tablename__ = "app_resource_policy"
    scope: str = Field(primary_key=True, max_length=100)
    enabled: bool = False
    starts_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    admission_until: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    delivery_until: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    evidence: str
    # Account/bucket allocation proof must cover other deployments and consumers.
    account_evidence: str
    # Last possible expiry of previously issued direct R2 URLs, after reviewed
    # revocation or expiry. New proxy receipts cannot revoke an old R2 URL.
    direct_urls_expired_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    initial_storage_bytes: int
    pending_tasks_at_start: int
    model: str
    duration: int
    caps: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    used: dict[str, int] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class AppResourceAttempt(SQLModel, table=True):
    __tablename__ = "app_resource_attempt"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    scope: str = Field(foreign_key="app_resource_policy.scope", index=True)
    operation: str = Field(max_length=40)
    units: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AppMediaReadGrant(SQLModel, table=True):
    __tablename__ = "app_media_read_grant"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    scope: str = Field(foreign_key="app_resource_policy.scope", index=True)
    object_key: str = Field(max_length=2048)
    delivery: bool = False
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
