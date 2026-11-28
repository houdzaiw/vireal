"""Finite synthetic allocations for existing positive production-mode tests.

No runtime checks are patched out. Dedicated resource tests explicitly vary the
policy and missing/effective allocation conditions.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import delete

from app.core.config import settings
from app.models_resources import (
    AppMediaReadGrant,
    AppResourceAttempt,
    AppResourcePolicy,
)
from app.services.resource_limits import METRICS

SCOPE = "synthetic-legacy-positive-tests"


def clear_resources(session):
    for model in (AppMediaReadGrant, AppResourceAttempt, AppResourcePolicy):
        session.exec(delete(model).where(model.scope == SCOPE))
    session.commit()


def seed_resources(session, model):
    clear_resources(session)
    now = datetime.now(UTC)
    caps = dict.fromkeys(METRICS, 1000)
    caps.update(
        generations=20,
        upload_bytes=100_000_000,
        delivery_bytes=100 * settings.MAX_GENERATED_VIDEO_BYTES,
        storage_bytes=100 * settings.MAX_GENERATED_VIDEO_BYTES + 100_000_000,
        read_bytes=1000 * settings.MAX_GENERATED_VIDEO_BYTES,
        read_bytes_delivery=1000 * settings.MAX_GENERATED_VIDEO_BYTES,
    )
    session.add(
        AppResourcePolicy(
            scope=SCOPE,
            enabled=True,
            starts_at=now - timedelta(minutes=1),
            admission_until=now + timedelta(hours=1),
            delivery_until=now + timedelta(hours=2),
            direct_urls_expired_at=now - timedelta(seconds=1),
            evidence="synthetic only, no live authority",
            account_evidence="synthetic only, all consumers isolated",
            initial_storage_bytes=0,
            pending_tasks_at_start=0,
            model=model,
            duration=5,
            caps=caps,
            used={},
        )
    )
    session.commit()
