"""Add inactive operational evidence; never rewrite orders, tasks or ledgers."""

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frozen DDL: importing future application models here would change history.
    op.create_table(
        "app_budget_window",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("pause_reason", sa.String()),
        sa.Column("closing_bound_micros", sa.BigInteger()),
        sa.Column("closing_evidence", sa.String()),
        sa.Column("owner_present_until", sa.DateTime(timezone=True)),
        sa.Column("alerts_verified_until", sa.DateTime(timezone=True)),
        sa.Column("backup_verified_until", sa.DateTime(timezone=True)),
        sa.Column("worker_seen_at", sa.DateTime(timezone=True)),
        sa.Column("prices", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_at > starts_at"),
        sa.CheckConstraint("ends_at <= starts_at + interval '72 hours'"),
        sa.CheckConstraint("closing_bound_micros IS NULL OR closing_bound_micros >= 0"),
        sa.CheckConstraint("state IN ('draft', 'active', 'paused', 'closed')"),
    )
    op.create_index(
        "uq_budget_current",
        "app_budget_window",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "app_cost_reservation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "window_id",
            sa.Uuid(),
            sa.ForeignKey("app_budget_window.id"),
            nullable=False,
        ),
        sa.Column("operation_key", sa.String(255), nullable=False, unique=True),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("bound_micros", sa.BigInteger(), nullable=False),
        sa.Column("actual_micros", sa.BigInteger()),
        sa.Column("settlement_reference", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "bound_micros >= 0 AND (actual_micros IS NULL OR actual_micros >= 0)"
        ),
    )
    op.create_index(
        "ix_app_cost_reservation_window_id", "app_cost_reservation", ["window_id"]
    )
    op.create_table(
        "app_cost_observation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "window_id",
            sa.Uuid(),
            sa.ForeignKey("app_budget_window.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("spent_micros", sa.BigInteger(), nullable=False),
        sa.Column("unreported_bound_micros", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_reference", sa.String(), nullable=False),
        sa.Column("covered_reservation_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("spent_micros >= 0 AND unreported_bound_micros >= 0"),
    )
    op.create_index(
        "ix_app_cost_observation_window_id", "app_cost_observation", ["window_id"]
    )
    op.create_index(
        "uq_budget_source", "app_cost_observation", ["window_id", "source"], unique=True
    )
    op.create_table(
        "app_operational_alert",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "window_id",
            sa.Uuid(),
            sa.ForeignKey("app_budget_window.id"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String()),
    )
    op.create_index(
        "ix_app_operational_alert_window_id", "app_operational_alert", ["window_id"]
    )
    op.create_index(
        "uq_budget_alert",
        "app_operational_alert",
        ["window_id", "event_key"],
        unique=True,
    )
    # Deliberately no data/period/prices/operator proofs or activation.


def downgrade() -> None:
    raise RuntimeError("Preserve cost evidence; pause new business instead")
