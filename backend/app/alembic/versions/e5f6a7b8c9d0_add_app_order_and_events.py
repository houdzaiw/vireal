"""Add app order and events

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-22 22:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_order",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=True),
        sa.Column(
            "transaction_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_order_app_user_id"),
        "app_order",
        ["app_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_provider"),
        "app_order",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_status"),
        "app_order",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_transaction_id"),
        "app_order",
        ["transaction_id"],
        unique=False,
    )

    op.create_table(
        "app_order_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["app_order.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "event_id",
            name="uq_app_order_event_provider_event_id",
        ),
    )
    op.create_index(
        op.f("ix_app_order_event_event_id"),
        "app_order_event",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_event_order_id"),
        "app_order_event",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_event_provider"),
        "app_order_event",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_order_event_status"),
        "app_order_event",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_app_order_event_status"), table_name="app_order_event")
    op.drop_index(op.f("ix_app_order_event_provider"), table_name="app_order_event")
    op.drop_index(op.f("ix_app_order_event_order_id"), table_name="app_order_event")
    op.drop_index(op.f("ix_app_order_event_event_id"), table_name="app_order_event")
    op.drop_table("app_order_event")
    op.drop_index(op.f("ix_app_order_transaction_id"), table_name="app_order")
    op.drop_index(op.f("ix_app_order_status"), table_name="app_order")
    op.drop_index(op.f("ix_app_order_provider"), table_name="app_order")
    op.drop_index(op.f("ix_app_order_app_user_id"), table_name="app_order")
    op.drop_table("app_order")
