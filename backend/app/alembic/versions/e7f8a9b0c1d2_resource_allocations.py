"""Add inactive resource accounting and expiring media grants.
Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_resource_policy",
        sa.Column("scope", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *[
            sa.Column(n, sa.DateTime(timezone=True), nullable=False)
            for n in [
                "starts_at",
                "admission_until",
                "delivery_until",
                "direct_urls_expired_at",
            ]
        ],
        sa.Column("evidence", sa.String(), nullable=False),
        sa.Column("account_evidence", sa.String(), nullable=False),
        sa.Column("initial_storage_bytes", sa.BigInteger(), nullable=False),
        sa.Column("pending_tasks_at_start", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("caps", sa.JSON(), nullable=False),
        sa.Column("used", sa.JSON(), nullable=False),
    )
    op.create_table(
        "app_resource_attempt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scope",
            sa.String(100),
            sa.ForeignKey("app_resource_policy.scope"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("units", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_resource_attempt_scope", "app_resource_attempt", ["scope"])
    op.create_table(
        "app_media_read_grant",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scope",
            sa.String(100),
            sa.ForeignKey("app_resource_policy.scope"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(2048), nullable=False),
        sa.Column("delivery", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_media_read_grant_scope", "app_media_read_grant", ["scope"])
    # No allowances, rows, credentials or business activation are seeded.


def downgrade():
    raise RuntimeError(
        "Preserve resource/unknown-outcome evidence; pause admissions instead"
    )
