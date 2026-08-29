"""Add app generation

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-29 09:10:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_generation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "prompt",
            sqlmodel.sql.sqltypes.AutoString(length=2000),
            nullable=False,
        ),
        sa.Column("style", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column(
            "aspect_ratio",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("consistency", sa.Boolean(), nullable=False),
        sa.Column(
            "reference_image_url",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=True,
        ),
        sa.Column(
            "character_image_url",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=True,
        ),
        sa.Column(
            "output_url",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_generation_app_user_id"),
        "app_generation",
        ["app_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_generation_created_at"),
        "app_generation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_generation_kind"),
        "app_generation",
        ["kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_generation_status"),
        "app_generation",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_app_generation_status"), table_name="app_generation")
    op.drop_index(op.f("ix_app_generation_kind"), table_name="app_generation")
    op.drop_index(op.f("ix_app_generation_created_at"), table_name="app_generation")
    op.drop_index(op.f("ix_app_generation_app_user_id"), table_name="app_generation")
    op.drop_table("app_generation")
