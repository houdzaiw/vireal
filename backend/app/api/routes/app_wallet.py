from datetime import UTC, datetime

from fastapi import APIRouter
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.models import AppCoinLedger, AppCoinLedgerPublic, AppWalletPublic
from app.services.coin_wallet import get_coin_balance
from app.services.video_quota import build_video_quota

router = APIRouter(prefix="/app/wallet", tags=["app wallet"])


@router.get("", response_model=AppWalletPublic)
def read_wallet(
    *, session: SessionDep, current_app_user: CurrentAppUser
) -> AppWalletPublic:
    ledger = session.exec(
        select(AppCoinLedger)
        .where(AppCoinLedger.app_user_id == current_app_user.id)
        .order_by(col(AppCoinLedger.created_at).desc())
        .limit(50)
    ).all()
    quota = build_video_quota(
        session=session, app_user_id=current_app_user.id, now=datetime.now(UTC)
    )
    return AppWalletPublic(
        balance=get_coin_balance(session=session, app_user_id=current_app_user.id),
        daily_remaining=quota.user_real_remaining,
        concurrent_remaining=quota.concurrent_remaining,
        resets_at=quota.resets_at,
        ledger=[AppCoinLedgerPublic.model_validate(item) for item in ledger],
    )
