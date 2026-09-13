"""Add tracked uploads and Replicate video tasks.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-12 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    managed_tables = {
        "app_upload",
        "app_video_task",
        "app_video_task_webhook_event",
    }
    existing_managed_tables = managed_tables.intersection(
        sa.inspect(op.get_bind()).get_table_names()
    )
    if existing_managed_tables:
        if existing_managed_tables == managed_tables:
            # A local pre-integration build used the remote app-generation
            # revision ID for these exact tables. The Alembic environment moves
            # that marker back to the common parent before this migration runs.
            return
        raise RuntimeError(
            "Replicate migration found a partial legacy schema: "
            + ", ".join(sorted(existing_managed_tables))
        )

    op.create_table(
        "app_upload",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "object_key",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=False,
        ),
        sa.Column(
            "content_type",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_upload_app_user_id"), "app_upload", ["app_user_id"])
    op.create_index(op.f("ix_app_upload_expires_at"), "app_upload", ["expires_at"])
    op.create_index(op.f("ix_app_upload_status"), "app_upload", ["status"])

    op.create_table(
        "app_video_task",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "idempotency_key",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sqlmodel.sql.sqltypes.AutoString(length=50),
            nullable=False,
        ),
        sa.Column("upload_ids_json", sa.Text(), nullable=False),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
        ),
        sa.Column(
            "model",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "provider_task_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
        ),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column(
            "resolution",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "aspect_ratio",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("provider_output_url", sa.Text(), nullable=True),
        sa.Column(
            "output_object_key",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("submission_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_attempts", sa.Integer(), nullable=False),
        sa.Column("worker_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "app_user_id",
            "idempotency_key",
            name="uq_app_video_task_user_idempotency_key",
        ),
    )
    for column in (
        "app_user_id",
        "status",
        "submission_attempted_at",
        "worker_locked_at",
        "next_attempt_at",
        "expires_at",
    ):
        op.create_index(op.f(f"ix_app_video_task_{column}"), "app_video_task", [column])
    op.create_index(
        op.f("ix_app_video_task_provider_task_id"),
        "app_video_task",
        ["provider_task_id"],
        unique=True,
    )

    op.create_table(
        "app_video_task_webhook_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_task_id", sa.Uuid(), nullable=False),
        sa.Column(
            "webhook_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "provider_task_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "provider_status",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
        ),
        sa.Column(
            "payload_sha256",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_task_id"], ["app_video_task.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_video_task_webhook_event_video_task_id"),
        "app_video_task_webhook_event",
        ["video_task_id"],
    )
    op.create_index(
        op.f("ix_app_video_task_webhook_event_webhook_id"),
        "app_video_task_webhook_event",
        ["webhook_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_app_video_task_webhook_event_provider_task_id"),
        "app_video_task_webhook_event",
        ["provider_task_id"],
    )


def downgrade():
    for column in ("provider_task_id", "webhook_id", "video_task_id"):
        op.drop_index(
            op.f(f"ix_app_video_task_webhook_event_{column}"),
            table_name="app_video_task_webhook_event",
        )
    op.drop_table("app_video_task_webhook_event")
    for column in (
        "expires_at",
        "next_attempt_at",
        "worker_locked_at",
        "submission_attempted_at",
        "status",
        "provider_task_id",
        "app_user_id",
    ):
        op.drop_index(
            op.f(f"ix_app_video_task_{column}"), table_name="app_video_task"
        )
    op.drop_table("app_video_task")
    op.drop_index(op.f("ix_app_upload_status"), table_name="app_upload")
    op.drop_index(op.f("ix_app_upload_expires_at"), table_name="app_upload")
    op.drop_index(op.f("ix_app_upload_app_user_id"), table_name="app_upload")
    op.drop_table("app_upload")
