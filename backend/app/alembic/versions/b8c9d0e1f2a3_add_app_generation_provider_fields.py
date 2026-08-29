"""Add app generation provider fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-29 16:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_generation",
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=40),
            server_default="local",
            nullable=False,
        ),
    )
    op.add_column(
        "app_generation",
        sa.Column(
            "provider_task_id",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
    )
    op.alter_column("app_generation", "provider", server_default=None)
    op.create_index(
        op.f("ix_app_generation_provider"),
        "app_generation",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_generation_provider_task_id"),
        "app_generation",
        ["provider_task_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_app_generation_provider_task_id"),
        table_name="app_generation",
    )
    op.drop_index(op.f("ix_app_generation_provider"), table_name="app_generation")
    op.drop_column("app_generation", "provider_task_id")
    op.drop_column("app_generation", "provider")
