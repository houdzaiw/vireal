"""Add app admin operation log

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-22 23:10:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_admin_operation_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "admin_email",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "action",
            sqlmodel.sql.sqltypes.AutoString(length=120),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sqlmodel.sql.sqltypes.AutoString(length=80),
            nullable=False,
        ),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "summary",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_action"),
        "app_admin_operation_log",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_admin_email"),
        "app_admin_operation_log",
        ["admin_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_admin_user_id"),
        "app_admin_operation_log",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_created_at"),
        "app_admin_operation_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_target_id"),
        "app_admin_operation_log",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_admin_operation_log_target_type"),
        "app_admin_operation_log",
        ["target_type"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_app_admin_operation_log_target_type"),
        table_name="app_admin_operation_log",
    )
    op.drop_index(
        op.f("ix_app_admin_operation_log_target_id"),
        table_name="app_admin_operation_log",
    )
    op.drop_index(
        op.f("ix_app_admin_operation_log_created_at"),
        table_name="app_admin_operation_log",
    )
    op.drop_index(
        op.f("ix_app_admin_operation_log_admin_user_id"),
        table_name="app_admin_operation_log",
    )
    op.drop_index(
        op.f("ix_app_admin_operation_log_admin_email"),
        table_name="app_admin_operation_log",
    )
    op.drop_index(
        op.f("ix_app_admin_operation_log_action"),
        table_name="app_admin_operation_log",
    )
    op.drop_table("app_admin_operation_log")
