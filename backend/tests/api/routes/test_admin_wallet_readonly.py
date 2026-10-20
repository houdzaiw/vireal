"""Real PostgreSQL API regression, using only the suite's disposable local DB."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models import AppCoinAccount, AppCoinLedger, AppUser


def make_user(db: Session) -> AppUser:
    user = AppUser(account_type="clerk")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_wallet_read_does_not_create_an_account(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    user = make_user(db)
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/users/{user.id}/wallet",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["balance"] == 0
    assert response.json()["account_initialized"] is False
    assert response.json()["ledger"] == []
    assert db.get(AppCoinAccount, user.id) is None


def test_admin_wallet_postgres_balance_and_ledger_scope(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    user, other = make_user(db), make_user(db)
    db.add(AppCoinAccount(app_user_id=user.id, balance=72))
    for owner, delta, after in [(user, 100, 100), (user, -28, 72), (other, 999, 999)]:
        db.add(
            AppCoinLedger(
                app_user_id=owner.id,
                delta=delta,
                balance_after=after,
                entry_type="local_test",
                reason="Synthetic local PostgreSQL fixture",
                idempotency_key="admin-wallet-test:" + str(uuid.uuid4()),
            )
        )
    db.commit()
    path = f"{settings.API_V1_STR}/admin/app/users/{user.id}/wallet"
    first = client.get(
        path, headers=superuser_token_headers, params={"limit": 1}
    ).json()
    second = client.get(
        path, headers=superuser_token_headers, params={"limit": 1, "skip": 1}
    ).json()
    assert first["balance"] == second["balance"] == 72
    assert first["count"] == second["count"] == 2
    assert len(first["ledger"]) == len(second["ledger"]) == 1
    assert first["ledger"][0]["id"] != second["ledger"][0]["id"]
    assert {first["ledger"][0]["delta"], second["ledger"][0]["delta"]} == {100, -28}


def test_admin_wallet_postgres_permissions(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
) -> None:
    user = make_user(db)
    path = f"{settings.API_V1_STR}/admin/app/users/{user.id}/wallet"
    assert client.get(path).status_code in (401, 403)
    assert client.get(path, headers=normal_user_token_headers).status_code == 403


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "skip=-1"])
def test_admin_wallet_postgres_bounded_pagination(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str], query: str
) -> None:
    user = make_user(db)
    assert (
        client.get(
            f"{settings.API_V1_STR}/admin/app/users/{user.id}/wallet?{query}",
            headers=superuser_token_headers,
        ).status_code
        == 422
    )
