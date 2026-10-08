"""Add PayPal payment snapshots and manual payment cases without rewriting history."""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "payment_hold", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    columns: list[sa.Column[Any]] = [
        sa.Column("payment_environment", sa.String(10)),
        sa.Column("payment_idempotency_key", sa.String(120)),
        sa.Column("provider_order_id", sa.String(255)),
        sa.Column("capture_id", sa.String(255)),
        sa.Column("coin_quantity", sa.Integer()),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True)),
    ]
    for column in columns:
        op.add_column("app_order", column)
    for name in ("provider_order_id", "next_reconcile_at"):
        op.create_index(f"ix_app_order_{name}", "app_order", [name])
    for suffix, fields in (
        ("provider_order", ["provider", "payment_environment", "provider_order_id"]),
        ("capture", ["provider", "payment_environment", "capture_id"]),
        ("idempotency", ["app_user_id", "payment_idempotency_key"]),
    ):
        op.create_unique_constraint(
            f"uq_app_order_paypal_{suffix}", "app_order", fields
        )
    op.create_check_constraint(
        "ck_app_order_paypal_snapshot",
        "app_order",
        "provider <> 'paypal' OR (amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND currency = 'USD' AND coin_quantity IS NOT NULL AND coin_quantity > 0 AND payment_environment IS NOT NULL AND payment_environment IN ('sandbox','live') AND payment_idempotency_key IS NOT NULL)",
    )
    op.add_column("app_coin_ledger", sa.Column("order_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_app_coin_ledger_order",
        "app_coin_ledger",
        "app_order",
        ["order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_app_coin_ledger_order_id", "app_coin_ledger", ["order_id"])
    op.create_table(
        "app_payment_case",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("app_order.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "app_user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("required_coins", sa.Integer(), nullable=False),
        sa.Column("recovered_coins", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("resolution", sa.String(20)),
        sa.Column(
            "resolved_by", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("order_id", "kind", "external_id"),
        sa.CheckConstraint("required_coins >= 0 AND recovered_coins >= 0"),
    )
    for name in ("order_id", "app_user_id", "status"):
        op.create_index(f"ix_app_payment_case_{name}", "app_payment_case", [name])


def downgrade() -> None:
    # Refuse destructive rollback of financial history. Roll back using feature flags.
    raise RuntimeError(
        "PayPal financial history must be preserved; disable feature gates instead"
    )
