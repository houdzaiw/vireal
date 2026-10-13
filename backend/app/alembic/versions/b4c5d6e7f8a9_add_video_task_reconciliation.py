"""Add nullable provider reconciliation clocks without changing financial history."""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("provider_last_checked_at", "provider_next_check_at"):
        op.add_column("app_video_task", sa.Column(name, sa.DateTime(timezone=True)))
        op.create_index(f"ix_app_video_task_{name}", "app_video_task", [name])


def downgrade() -> None:
    raise RuntimeError("Preserve reconciliation history; roll back using feature gates")
