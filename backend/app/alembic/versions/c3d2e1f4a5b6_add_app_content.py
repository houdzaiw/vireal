"""Add app content

Revision ID: c3d2e1f4a5b6
Revises: b7c9a2d4e6f1
Create Date: 2026-08-22 21:10:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "c3d2e1f4a5b6"
down_revision = "b7c9a2d4e6f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_content",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_content_app_user_id"),
        "app_content",
        ["app_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_content_status"),
        "app_content",
        ["status"],
        unique=False,
    )
    op.create_table(
        "app_content_image",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["content_id"], ["app_content.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_content_image_content_id"),
        "app_content_image",
        ["content_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_app_content_image_content_id"),
        table_name="app_content_image",
    )
    op.drop_table("app_content_image")
    op.drop_index(op.f("ix_app_content_status"), table_name="app_content")
    op.drop_index(op.f("ix_app_content_app_user_id"), table_name="app_content")
    op.drop_table("app_content")
