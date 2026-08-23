"""Add app user and device

Revision ID: b7c9a2d4e6f1
Revises: fe56fa70289e
Create Date: 2026-08-22 20:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "b7c9a2d4e6f1"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_user",
        sa.Column("nickname", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column(
            "avatar_url",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=True,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_user_status"), "app_user", ["status"], unique=False)
    op.create_table(
        "app_device",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "device_uuid_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_device_app_user_id"),
        "app_device",
        ["app_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_device_device_uuid_hash"),
        "app_device",
        ["device_uuid_hash"],
        unique=True,
    )


def downgrade():
    op.drop_index(op.f("ix_app_device_device_uuid_hash"), table_name="app_device")
    op.drop_index(op.f("ix_app_device_app_user_id"), table_name="app_device")
    op.drop_table("app_device")
    op.drop_index(op.f("ix_app_user_status"), table_name="app_user")
    op.drop_table("app_user")
