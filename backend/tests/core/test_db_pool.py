"""Disconnect fault injection in the disposable local PostgreSQL cluster only."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.core.db import create_database_engine, engine


def terminate_checked_in_connection(pool: Engine) -> int:
    host = str(pool.url.query.get("host", pool.url.host or ""))
    assert settings.ENVIRONMENT == "local"
    if not host.startswith("/tmp/vireal-convergence-tests."):
        pytest.skip(
            "Disconnect injection requires the dedicated private Unix-socket test cluster"
        )
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
