import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import AppVideoTask, AppVideoTaskQuotaPublic

REAL_EXECUTION_TYPES = ("minimax", "wan", "seedance")
RESERVED_REAL_STATUSES = ("submitting", "submission_unknown")
ACTIVE_REAL_STATUSES = (
    "submitting",
    "pending",
    "running",
    "saving",
    "submission_unknown",
)


def utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def real_today_filter(now: datetime) -> ColumnElement[bool]:
    day_start, day_end = utc_day_bounds(now)
    # Charge attempts to the day on which the request was sent, even if its
    # response/webhook arrives after midnight. Unknown older attempts carry over.
    attempted_at = func.coalesce(
        AppVideoTask.submission_attempted_at,
        AppVideoTask.real_submission_counted_at,
        AppVideoTask.created_at,
    )
    counted = and_(
        col(AppVideoTask.real_submission_counted_at).is_not(None),
        attempted_at >= day_start,
        attempted_at < day_end,
    )
    reserved = and_(
        col(AppVideoTask.execution_type).in_(REAL_EXECUTION_TYPES),
        col(AppVideoTask.status).in_(RESERVED_REAL_STATUSES),
        col(AppVideoTask.created_at) < day_end,
    )
    return or_(counted, reserved)


def global_real_count(*, session: Session, now: datetime) -> int:
    return int(
        session.exec(
            select(func.count())
            .select_from(AppVideoTask)
            .where(
                col(AppVideoTask.execution_type).in_(REAL_EXECUTION_TYPES),
                real_today_filter(now),
            )
        ).one()
    )


def quota_counts(
    *, session: Session, app_user_id: uuid.UUID, now: datetime
) -> tuple[int, int, int, datetime]:
    _day_start, resets_at = utc_day_bounds(now)
    real_today = real_today_filter(now)
    user_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(AppVideoTask.app_user_id == app_user_id, real_today)
    ).one()
    wan_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(AppVideoTask.execution_type == "wan", real_today)
    ).one()
    active_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(
            AppVideoTask.app_user_id == app_user_id,
            col(AppVideoTask.execution_type).in_(REAL_EXECUTION_TYPES),
            col(AppVideoTask.status).in_(ACTIVE_REAL_STATUSES),
        )
    ).one()
    return int(user_count), int(wan_count), int(active_count), resets_at


def build_video_quota(
    *, session: Session, app_user_id: uuid.UUID, now: datetime | None = None
) -> AppVideoTaskQuotaPublic:
    user_count, wan_count, active_count, resets_at = quota_counts(
        session=session, app_user_id=app_user_id, now=now or datetime.now(UTC)
    )
    return AppVideoTaskQuotaPublic(
        user_real_limit=settings.APP_USER_DAILY_REAL_SUBMISSIONS,
        user_real_remaining=max(
            settings.APP_USER_DAILY_REAL_SUBMISSIONS - user_count, 0
        ),
        wan_global_limit=settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS,
        wan_global_remaining=max(
            settings.APP_WAN_DAILY_GLOBAL_SUBMISSIONS - wan_count, 0
        ),
        resets_at=resets_at,
        concurrent_limit=settings.APP_USER_MAX_CONCURRENT_VIDEO_TASKS,
        concurrent_remaining=max(
            settings.APP_USER_MAX_CONCURRENT_VIDEO_TASKS - active_count, 0
        ),
        global_real_limit=settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS,
        global_real_remaining=max(
            settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS
            - global_real_count(session=session, now=now or datetime.now(UTC)),
            0,
        ),
    )
