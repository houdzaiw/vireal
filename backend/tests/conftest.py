from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import (
    AppAdminOperationLog,
    AppConfig,
    AppContent,
    AppContentImage,
    AppDevice,
    AppGeneration,
    AppOrder,
    AppOrderEvent,
    AppUpload,
    AppUser,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
    Item,
    User,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def local_image_storage_for_tests() -> Generator[None]:
    """Keep API tests deterministic when a developer .env enables R2."""
    original_backend = settings.APP_IMAGE_STORAGE_BACKEND
    settings.APP_IMAGE_STORAGE_BACKEND = "local"  # type: ignore[assignment]
    yield
    settings.APP_IMAGE_STORAGE_BACKEND = original_backend


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    with Session(engine) as session:
        init_db(session)
        yield session
        statement = delete(AppOrderEvent)
        session.execute(statement)
        statement = delete(AppAdminOperationLog)
        session.execute(statement)
        statement = delete(AppOrder)
        session.execute(statement)
        statement = delete(AppConfig)
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
        statement = delete(AppUpload)
        session.execute(statement)
        statement = delete(AppDevice)
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
