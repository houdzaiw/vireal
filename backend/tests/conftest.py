from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import (
    AppAdminOperationLog,
    AppCoinAccount,
    AppCoinLedger,
    AppConfig,
    AppContent,
    AppContentImage,
    AppDevice,
    AppEffect,
    AppEffectCategory,
    AppEffectRecommendation,
    AppEffectVariant,
    AppGeneration,
    AppManagedMediaAsset,
    AppOrder,
    AppOrderEvent,
    AppPayPalReplacement,
    AppUpload,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
    Item,
    User,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(autouse=True)
def isolated_email_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit/API tests must not deliver email to a real external SMTP service."""
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", "no-reply@example.com")
    monkeypatch.setattr(
        "emails.message.Message.send",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=250),
    )


@pytest.fixture(scope="session", autouse=True)
def local_image_storage_for_tests() -> Generator[None]:
    """Keep API tests deterministic when a developer .env enables R2."""
    original_backend = settings.APP_IMAGE_STORAGE_BACKEND
    settings.APP_IMAGE_STORAGE_BACKEND = "local"  # type: ignore[assignment]
    yield
    settings.APP_IMAGE_STORAGE_BACKEND = original_backend


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    # This fixture deletes every application table on teardown. Never permit
    # accidental execution against a deployed database loaded from a local .env.
    url = engine.url
    host = str(url.query.get("host", url.host or ""))
    local_hosts = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
    temporary_socket = host.startswith("/tmp/vireal-convergence-tests.")
    if settings.ENVIRONMENT == "production" or (
        host not in local_hosts and not temporary_socket
    ):
        raise RuntimeError("Destructive tests require an isolated local test database")
    with Session(engine) as session:
        init_db(session)
        yield session
        statement = delete(AppOrderEvent)
        session.execute(statement)
        session.execute(delete(AppPayPalReplacement))
        statement = delete(AppAdminOperationLog)
        session.execute(statement)
        statement = delete(AppOrder)
        session.execute(statement)
        statement = delete(AppConfig)
        session.execute(statement)
        statement = delete(AppEffectRecommendation)
        session.execute(statement)
        statement = delete(AppCoinLedger)
        session.execute(statement)
        statement = delete(AppGeneration)
        session.execute(statement)
        statement = delete(AppContentImage)
        session.execute(statement)
        statement = delete(AppContent)
        session.execute(statement)
        statement = delete(AppVideoTaskWebhookEvent)
        session.execute(statement)
        statement = delete(AppVideoTask)
        session.execute(statement)
        statement = delete(AppEffectVariant)
        session.execute(statement)
        statement = delete(AppEffect)
        session.execute(statement)
        statement = delete(AppEffectCategory)
        session.execute(statement)
        statement = delete(AppManagedMediaAsset)
        session.execute(statement)
        statement = delete(AppCoinAccount)
        session.execute(statement)
        statement = delete(AppUpload)
        session.execute(statement)
        statement = delete(AppDevice)
        session.execute(statement)
        statement = delete(AppUserSession)
        session.execute(statement)
        statement = delete(AppUserIdentity)
        session.execute(statement)
        statement = delete(AppUser)
        session.execute(statement)
        statement = delete(Item)
        session.execute(statement)
        statement = delete(User)
        session.execute(statement)
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )


@pytest.fixture(autouse=True)
def synthetic_operational_evidence(
    db: Session, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Generator[None]:
    """Legacy positive-production cases still satisfy the new, real USD gate.

    No gate is patched out. New operational tests explicitly vary these records.
    All data and clocks belong only to the guarded local test cluster.
    """
    from app.services import operational_budget
    from tests.utils.operations import clear_operations, seed_operations, staffed_now

    now = staffed_now()
    monkeypatch.setattr(operational_budget, "utc_now", lambda: now)
    seed_operations(db, now)
    from tests.utils.resources import SCOPE, clear_resources, seed_resources

    model = (
        "wan-video/wan-2.7-r2v"
        if request.path.name == "test_generation_acceptance.py"
        else "minimax/video-01"
    )
    seed_resources(db, model)
    monkeypatch.setattr(settings, "APP_RESOURCE_SCOPE", SCOPE)
    yield
    db.rollback()
    clear_operations(db)
    clear_resources(db)
