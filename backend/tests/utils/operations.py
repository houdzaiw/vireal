"""Synthetic operator evidence for isolated tests; never a runtime bypass."""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, delete

from app.models_operations import (
    AppBudgetWindow,
    AppCostObservation,
    AppCostReservation,
    AppOperationalAlert,
)
from app.services.operational_budget import SOURCES


def clear_operations(session: Session) -> None:
    for model in (
        AppOperationalAlert,
        AppCostObservation,
        AppCostReservation,
        AppBudgetWindow,
    ):
        session.exec(delete(model))
    session.commit()


def seed_operations(session: Session, now: datetime) -> AppBudgetWindow:
    clear_operations(session)
    end = now + timedelta(hours=72)
    prices = {
        key: {
            "bound_micros": 1_000_000,
            "valid_until": end.isoformat(),
            "evidence": "synthetic verified bound",
        }
        for key in ("registration", "upload", "payment")
    }
    for model in (
        "local/ffmpeg",
        "minimax/video-01",
        "wan-video/wan-2.7-r2v",
        "bytedance/seedance-2.0",
        "wan-video/wan-2.2-animate-animation",
    ):
        for duration in (5, 6, 10, 15):
            prices[f"video:{model}:{duration}:720p:image-only"] = {
                "bound_micros": 1_000_000,
                "valid_until": end.isoformat(),
                "evidence": "synthetic verified bound",
            }
    window = AppBudgetWindow(
        starts_at=now - timedelta(minutes=1),
        ends_at=end - timedelta(minutes=1),
        state="active",
        closing_bound_micros=30_000_000,
        closing_evidence="synthetic bounded close",
        owner_present_until=now + timedelta(minutes=10),
        alerts_verified_until=now + timedelta(hours=1),
        backup_verified_until=now + timedelta(hours=1),
        worker_seen_at=now,
        prices={
            k: {**v, "valid_until": (end - timedelta(minutes=1)).isoformat()}
            for k, v in prices.items()
        },
    )
    session.add(window)
    session.commit()
    for source in SOURCES:
        session.add(
            AppCostObservation(
                window_id=window.id,
                source=source,
                spent_micros=0,
                unreported_bound_micros=0,
                observed_at=now,
                valid_until=window.ends_at,
                evidence_reference="synthetic all-service invoice",
            )
        )
    session.commit()
    return window


def staffed_now() -> datetime:
    return datetime.now(UTC).replace(hour=2, minute=0, second=0, microsecond=0)
