"""Add Clerk-backed App identities.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-18 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_user",
        sa.Column(
            "account_type",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
            server_default="legacy_test",
        ),
    )
    op.create_index(
        op.f("ix_app_user_account_type"),
        "app_user",
        ["account_type"],
    )
    op.create_table(
        "app_user_identity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "issuer",
            sqlmodel.sql.sqltypes.AutoString(length=2048),
            nullable=False,
        ),
        sa.Column(
            "subject",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "primary_email",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("providers_json", sa.Text(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("login_count", sa.Integer(), nullable=False),
        sa.Column(
            "last_session_id_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_user_id"),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_app_user_identity_issuer_subject",
        ),
    )
    op.create_index(
        op.f("ix_app_user_identity_app_user_id"),
        "app_user_identity",
        ["app_user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_app_user_identity_primary_email"),
        "app_user_identity",
        ["primary_email"],
    )
    op.create_index(
        op.f("ix_app_user_identity_subject"),
        "app_user_identity",
        ["subject"],
    )
    op.create_index(
        op.f("ix_app_user_identity_last_login_at"),
        "app_user_identity",
        ["last_login_at"],
    )
    op.create_table(
        "app_user_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "session_id_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_user_session_app_user_id"),
        "app_user_session",
        ["app_user_id"],
    )
    op.create_index(
        op.f("ix_app_user_session_revoked_at"),
        "app_user_session",
        ["revoked_at"],
    )
    op.create_index(
        op.f("ix_app_user_session_session_id_hash"),
        "app_user_session",
        ["session_id_hash"],
        unique=True,
    )


def downgrade():
    # IF EXISTS keeps local environments recoverable when this unreleased
    # migration was previously applied before App session revocation was added.
    op.execute("DROP TABLE IF EXISTS app_user_session CASCADE")
    op.drop_index(
        op.f("ix_app_user_identity_last_login_at"),
        table_name="app_user_identity",
    )
    op.drop_index(
        op.f("ix_app_user_identity_subject"),
        table_name="app_user_identity",
    )
    op.drop_index(
        op.f("ix_app_user_identity_primary_email"),
        table_name="app_user_identity",
    )
    op.drop_index(
        op.f("ix_app_user_identity_app_user_id"),
        table_name="app_user_identity",
    )
    op.drop_table("app_user_identity")
    op.drop_index(op.f("ix_app_user_account_type"), table_name="app_user")
    op.drop_column("app_user", "account_type")
