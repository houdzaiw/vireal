import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlmodel import Session, select

from app.models import AppCoinAccount, AppCoinLedger, AppVideoTask


class CoinBalanceError(ValueError):
    pass


def _validate_idempotent_adjustment(
    *,
    existing: AppCoinLedger,
    delta: int,
    entry_type: str,
    reason: str,
    task_id: uuid.UUID | None,
    admin_user_id: uuid.UUID | None,
) -> None:
    if (
        existing.delta != delta
        or existing.entry_type != entry_type
        or existing.reason != reason
        or existing.task_id != task_id
        or existing.admin_user_id != admin_user_id
    ):
        raise CoinBalanceError(
            "Idempotency key was already used for another adjustment"
        )


def get_coin_balance(*, session: Session, app_user_id: uuid.UUID) -> int:
    account = session.get(AppCoinAccount, app_user_id)
    return account.balance if account is not None else 0


def adjust_coin_balance(
    *,
    session: Session,
    app_user_id: uuid.UUID,
    delta: int,
    entry_type: str,
    idempotency_key: str,
    reason: str,
    task_id: uuid.UUID | None = None,
    admin_user_id: uuid.UUID | None = None,
) -> tuple[AppCoinAccount, AppCoinLedger, bool]:
    """Apply one idempotent wallet change inside the caller's transaction."""
    if delta == 0:
        raise CoinBalanceError("Coin adjustment must not be zero")
    existing = session.exec(
        select(AppCoinLedger).where(
            AppCoinLedger.app_user_id == app_user_id,
            AppCoinLedger.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        _validate_idempotent_adjustment(
            existing=existing,
            delta=delta,
            entry_type=entry_type,
            reason=reason,
            task_id=task_id,
            admin_user_id=admin_user_id,
        )
        account = session.get(AppCoinAccount, app_user_id)
        if account is None:
            raise RuntimeError("Wallet ledger exists without an account")
        return account, existing, False

    session.connection().execute(
        text(
            """
            INSERT INTO app_coin_account (app_user_id, balance, updated_at)
            VALUES (:app_user_id, 0, :updated_at)
            ON CONFLICT (app_user_id) DO NOTHING
            """
        ),
        {"app_user_id": app_user_id, "updated_at": datetime.now(UTC)},
    )
    account = session.exec(
        select(AppCoinAccount)
        .where(AppCoinAccount.app_user_id == app_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()

    # Check again after acquiring the account lock. A concurrent request may
    # have committed the same logical adjustment while this request waited.
    existing = session.exec(
        select(AppCoinLedger).where(
            AppCoinLedger.app_user_id == app_user_id,
            AppCoinLedger.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        _validate_idempotent_adjustment(
            existing=existing,
            delta=delta,
            entry_type=entry_type,
            reason=reason,
            task_id=task_id,
            admin_user_id=admin_user_id,
        )
        return account, existing, False

    next_balance = account.balance + delta
    if next_balance < 0:
        raise CoinBalanceError("Insufficient coin balance")
    account.balance = next_balance
    account.updated_at = datetime.now(UTC)
    ledger = AppCoinLedger(
        app_user_id=app_user_id,
        delta=delta,
        balance_after=next_balance,
        entry_type=entry_type,
        idempotency_key=idempotency_key,
        task_id=task_id,
        admin_user_id=admin_user_id,
        reason=reason,
    )
    session.add(account)
    session.add(ledger)
    session.flush()
    return account, ledger, True


def refund_video_task(*, session: Session, task: AppVideoTask) -> bool:
    if not task.coin_cost_snapshot or task.coin_refunded_at is not None:
        return False
    _account, _ledger, created = adjust_coin_balance(
        session=session,
        app_user_id=task.app_user_id,
        delta=task.coin_cost_snapshot,
        entry_type="generation_refund",
        idempotency_key=f"video-task-refund:{task.id}",
        task_id=task.id,
        reason="生成任务未成功，金币自动退回",
    )
    task.coin_refunded_at = datetime.now(UTC)
    session.add(task)
    return created
