"""Add bounded replacement grants without changing any existing financial rows."""

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_paypal_replacement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "app_user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "original_order_id",
            sa.Uuid(),
            sa.ForeignKey("app_order.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("original_provider_order_id", sa.String(255), nullable=False),
        sa.Column(
            "replacement_order_id",
            sa.Uuid(),
            sa.ForeignKey("app_order.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column(
            "approved_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "replacement_order_id IS NULL OR replacement_order_id <> original_order_id"
        ),
        sa.CheckConstraint("(replacement_order_id IS NULL) = (consumed_at IS NULL)"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Preserve replacement/payment history; close feature gates instead"
    )
