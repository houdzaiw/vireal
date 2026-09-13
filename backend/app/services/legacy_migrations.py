from sqlalchemy import Connection, inspect, text

LEGACY_REPLICATE_REVISION = "a7b8c9d0e1f2"
LEGACY_REPLICATE_PARENT_REVISION = "f6a7b8c9d0e1"


def reconcile_legacy_replicate_revision(connection: Connection) -> bool:
    """Repair the unpublished local migration ID that collided with origin/main."""
    table_names = set(inspect(connection).get_table_names())
    if "alembic_version" not in table_names:
        return False

    current_revision = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()
    is_legacy_replicate_schema = (
        current_revision == LEGACY_REPLICATE_REVISION
        and "app_video_task" in table_names
        and "app_generation" not in table_names
    )
    if not is_legacy_replicate_schema:
        return False

    connection.execute(
        text(
            "UPDATE alembic_version "
            "SET version_num = :parent_revision "
            "WHERE version_num = :legacy_revision"
        ),
        {
            "parent_revision": LEGACY_REPLICATE_PARENT_REVISION,
            "legacy_revision": LEGACY_REPLICATE_REVISION,
        },
    )
    return True
