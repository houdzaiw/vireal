"""Add dual-mode routing and quota metadata to video tasks.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-16 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_video_task",
        sa.Column(
            "mode",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
            server_default="advanced",
        ),
    )
    op.add_column(
        "app_video_task",
        sa.Column(
            "execution_type",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
            server_default="wan",
        ),
    )
    op.add_column(
        "app_video_task",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "app_video_task",
        sa.Column(
            "fallback_reason",
            sqlmodel.sql.sqltypes.AutoString(length=80),
            nullable=True,
        ),
    )
    op.add_column(
        "app_video_task",
        sa.Column("source_duration", sa.Integer(), nullable=True),
    )
    op.add_column(
        "app_video_task",
        sa.Column(
            "real_submission_counted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE app_video_task
        SET real_submission_counted_at = submission_attempted_at
        WHERE provider_task_id IS NOT NULL
          AND real_submission_counted_at IS NULL
        """
    )
    for column in (
        "mode",
        "execution_type",
        "is_demo",
        "fallback_reason",
        "real_submission_counted_at",
    ):
        op.create_index(
            op.f(f"ix_app_video_task_{column}"),
            "app_video_task",
            [column],
        )


def downgrade():
    for column in (
        "real_submission_counted_at",
        "fallback_reason",
        "is_demo",
        "execution_type",
        "mode",
    ):
        op.drop_index(
            op.f(f"ix_app_video_task_{column}"),
            table_name="app_video_task",
        )
    for column in (
        "real_submission_counted_at",
        "source_duration",
        "fallback_reason",
        "is_demo",
        "execution_type",
        "mode",
    ):
        op.drop_column("app_video_task", column)
