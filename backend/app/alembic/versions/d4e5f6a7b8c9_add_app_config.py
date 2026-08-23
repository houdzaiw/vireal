"""Add app config

Revision ID: d4e5f6a7b8c9
Revises: c3d2e1f4a5b6
Create Date: 2026-08-22 21:35:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d2e1f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_config",
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(length=5000), nullable=False),
        sa.Column(
            "description",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_config_is_enabled"),
        "app_config",
        ["is_enabled"],
        unique=False,
    )
    op.create_index(op.f("ix_app_config_key"), "app_config", ["key"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_app_config_key"), table_name="app_config")
    op.drop_index(op.f("ix_app_config_is_enabled"), table_name="app_config")
    op.drop_table("app_config")
