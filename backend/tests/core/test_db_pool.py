"""Pool exhaustion and disconnects in disposable local PostgreSQL only."""

from contextlib import ExitStack

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import settings
from app.core.db import create_database_engine, engine


def require_disposable_cluster(pool: Engine) -> None:
    host = str(pool.url.query.get("host", pool.url.host or ""))
    assert settings.ENVIRONMENT == "local"
    if not host.startswith("/tmp/vireal-convergence-tests."):
        pytest.skip(
            "Disconnect injection requires the dedicated private Unix-socket test cluster"
        )


def terminate_checked_in_connection(pool: Engine) -> int:
    require_disposable_cluster(pool)
    with pool.connect() as connection:
        pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    with engine.connect() as control:
        assert (
            control.execute(
                text("SELECT pg_terminate_backend(:pid, 1000)"), {"pid": pid}
            ).scalar_one()
            is True
        )
    return pid


def test_app_engine_checks_connection_liveness_before_checkout():
    assert engine.pool._pre_ping is True


@pytest.mark.parametrize("overflow", [0, 1])
def test_exhausted_pool_has_finite_connections_and_recovers_on_release(
    monkeypatch, overflow
):
    require_disposable_cluster(engine)
    monkeypatch.setattr(settings, "DATABASE_POOL_SIZE", 2)
    monkeypatch.setattr(settings, "DATABASE_POOL_MAX_OVERFLOW", overflow)
    monkeypatch.setattr(settings, "DATABASE_POOL_TIMEOUT_SECONDS", 0.1)
    pool = create_database_engine(str(settings.DATABASE_URL))
    try:
        with ExitStack() as held:
            connections = [
                held.enter_context(pool.connect()) for _ in range(2 + overflow)
            ]
            pids = {
                c.execute(text("SELECT pg_backend_pid()")).scalar_one()
                for c in connections
            }
            assert len(pids) == 2 + overflow
            with pytest.raises(PoolTimeoutError, match="QueuePool limit"):
                pool.connect()
            # A failed checkout must neither invalidate nor replay transactions
            # on the connections already in use.
            assert all(
                c.execute(text("SELECT 1")).scalar_one() == 1 for c in connections
            )
            assert pool.pool.checkedout() == 2 + overflow
        with pool.connect() as recovered:
            assert recovered.execute(text("SELECT 1")).scalar_one() == 1
        assert pool.pool.checkedout() == 0
    finally:
        pool.dispose()


def test_old_pool_configuration_reproduces_first_query_failure():
    pool = create_engine(
        str(settings.DATABASE_URL), pool_pre_ping=False, pool_size=1, max_overflow=0
    )
    try:
        terminate_checked_in_connection(pool)
        with pytest.raises(DBAPIError):
            with pool.connect() as connection:
                connection.execute(text("SELECT 1"))
    finally:
        pool.dispose()


def test_pre_ping_recovers_before_first_business_query():
    pool = create_database_engine(str(settings.DATABASE_URL))
    try:
        old_pid = terminate_checked_in_connection(pool)
        with pool.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert (
                connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
                != old_pid
            )
    finally:
        pool.dispose()


def test_inflight_disconnect_rolls_back_without_replaying_durable_allocation(
    monkeypatch,
):
    from app.services import resource_limits
    from tests.utils.resources import SCOPE

    pool = create_database_engine(str(settings.DATABASE_URL))
    try:
        require_disposable_cluster(pool)
        monkeypatch.setattr(settings, "APP_RESOURCE_GUARD_ENABLED", True)
        monkeypatch.setattr(settings, "APP_RESOURCE_SCOPE", SCOPE)
        resource_limits.consume("disconnect-proof", {"uploads": 1})
        with pool.connect() as connection:
            transaction = connection.begin()
            pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            connection.execute(
                text(
                    "UPDATE app_resource_policy SET evidence=:marker WHERE scope=:scope"
                ),
                {"marker": "uncommitted-write-must-not-replay", "scope": SCOPE},
            )
            with engine.connect() as control:
                assert (
                    control.execute(
                        text("SELECT pg_terminate_backend(:pid, 1000)"), {"pid": pid}
                    ).scalar_one()
                    is True
                )
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT 1"))
            transaction.rollback()
        with pool.connect() as recovered:
            assert (
                recovered.execute(text("SELECT pg_backend_pid()")).scalar_one() != pid
            )
            evidence, used = recovered.execute(
                text(
                    "SELECT evidence,used FROM app_resource_policy WHERE scope=:scope"
                ),
                {"scope": SCOPE},
            ).one()
            assert evidence == "synthetic only, no live authority"
            assert used["uploads"] == used["attempts"] == 1
            assert (
                recovered.execute(
                    text(
                        "SELECT count(*) FROM app_resource_attempt WHERE scope=:scope AND operation='disconnect-proof'"
                    ),
                    {"scope": SCOPE},
                ).scalar_one()
                == 1
            )
    finally:
        pool.dispose()
