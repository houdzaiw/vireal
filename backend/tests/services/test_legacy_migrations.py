from sqlalchemy import create_engine, text

from app.services.legacy_migrations import reconcile_legacy_replicate_revision


def test_reconcile_legacy_replicate_revision() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('a7b8c9d0e1f2')")
        )
        connection.execute(text("CREATE TABLE app_video_task (id TEXT)"))

        assert reconcile_legacy_replicate_revision(connection) is True
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "f6a7b8c9d0e1"


def test_reconcile_does_not_change_origin_main_schema() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('a7b8c9d0e1f2')")
        )
        connection.execute(text("CREATE TABLE app_generation (id TEXT)"))

        assert reconcile_legacy_replicate_revision(connection) is False
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "a7b8c9d0e1f2"
