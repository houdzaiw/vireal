"""Self-contained SQLite tests; never load tests/conftest.py or a deployed DB."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.deps import get_db
from app.api.routes import admin_app
from app.core.config import settings
from app.models import AppCoinAccount, AppCoinLedger, AppUser, User


class SQLiteSession(Session):
    def get(self, entity, ident, **kwargs):
        # The existing PostgreSQL auth dependency accepts a JWT string UUID.
        # SQLite's UUID binder requires the equivalent UUID object instead.
        if entity is User and isinstance(ident, str):
            ident = uuid.UUID(ident)
        return super().get(entity, ident, **kwargs)


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with SQLiteSession(engine, expire_on_commit=False) as db:
        admin = User(
            email="wallet-admin@example.com",
            hashed_password="unused",
            is_superuser=True,
        )
        ordinary = User(email="wallet-ordinary@example.com", hashed_password="unused")
        user = AppUser(account_type="clerk")
        other = AppUser(account_type="clerk")
        db.add_all([admin, ordinary, user, other])
        db.commit()
        app = FastAPI()
        app.include_router(admin_app.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        def headers(principal=admin):
            token = jwt.encode(
                {
                    "sub": str(principal.id),
                    "exp": datetime.now(UTC) + timedelta(minutes=5),
                },
                settings.SECRET_KEY,
                algorithm="HS256",
            )
            return {"Authorization": "Bearer " + token}

        yield client, db, user, other, ordinary, headers, engine
    engine.dispose()


def path(user):
    return f"/api/v1/admin/app/users/{user.id}/wallet"


def test_wallet_read_is_select_only_and_does_not_initialize_account(fixture):
    client, db, user, _, _, headers, engine = fixture
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _c, _u, statement, *_args: statements.append(statement),
    )
    response = client.get(path(user), headers=headers())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "app_user_id": str(user.id),
        "balance": 0,
        "account_initialized": False,
        "ledger": [],
        "count": 0,
        "skip": 0,
        "limit": 25,
    }
    assert statements and all(
        statement.lstrip().upper().startswith("SELECT") for statement in statements
    )
    assert db.get(AppCoinAccount, user.id) is None
    assert not db.new and not db.dirty and not db.deleted


def test_current_balance_is_not_historical_balance_and_ledger_is_scoped(fixture):
    client, db, user, other, _, headers, _ = fixture
    created = datetime.now(UTC)
    db.add(AppCoinAccount(app_user_id=user.id, balance=72))
    for i, (delta, after) in enumerate([(100, 100), (-28, 72)]):
        db.add(
            AppCoinLedger(
                app_user_id=user.id,
                delta=delta,
                balance_after=after,
                entry_type="recharge_credit" if delta > 0 else "generation_debit",
                idempotency_key=f"wallet-test-{i}",
                reason="Synthetic local fixture",
                created_at=created + timedelta(seconds=i),
            )
        )
    db.add(
        AppCoinLedger(
            app_user_id=other.id,
            delta=999,
            balance_after=999,
            entry_type="admin_adjust",
            idempotency_key="private-other-wallet",
            reason="Must not leak",
        )
    )
    db.commit()
    first = client.get(path(user), headers=headers(), params={"limit": 1}).json()
    second = client.get(
        path(user), headers=headers(), params={"limit": 1, "skip": 1}
    ).json()
    assert first["balance"] == second["balance"] == 72
    assert first["count"] == second["count"] == 2
    assert first["account_initialized"] is True
    assert first["ledger"][0]["delta"] == -28
    assert second["ledger"][0]["delta"] == 100
    assert second["ledger"][0]["balance_after"] == 100
    assert first["ledger"][0]["id"] != second["ledger"][0]["id"]
    assert "private-other-wallet" not in str(first) + str(second)
    assert len(db.exec(select(AppCoinLedger)).all()) == 3


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"skip": -1}])
def test_pagination_is_bounded(fixture, params):
    client, _, user, _, _, headers, _ = fixture
    assert client.get(path(user), headers=headers(), params=params).status_code == 422


def test_wallet_requires_authenticated_active_superuser(fixture):
    client, _, user, _, ordinary, headers, _ = fixture
    assert client.get(path(user)).status_code in (401, 403)
    assert client.get(path(user), headers=headers(ordinary)).status_code == 403
    assert (
        client.get(path(user), headers={"Authorization": "Bearer invalid"}).status_code
        == 403
    )


def test_cloudflare_access_is_not_bypassed(fixture, monkeypatch):
    client, _, user, _, _, headers, _ = fixture
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", True)
    assert client.get(path(user), headers=headers()).status_code == 403


def test_inactive_administrator_is_denied(fixture):
    client, db, user, _, _, headers, _ = fixture
    admin = db.exec(select(User).where(User.is_superuser)).one()
    admin.is_active = False
    db.add(admin)
    db.commit()
    assert client.get(path(user), headers=headers()).status_code == 400


def test_missing_user_does_not_create_wallet(fixture):
    client, db, _, _, _, headers, _ = fixture
    response = client.get(
        f"/api/v1/admin/app/users/{uuid.uuid4()}/wallet", headers=headers()
    )
    assert response.status_code == 404
    assert db.exec(select(AppCoinAccount)).all() == []
