"""Offline installed-package smoke: no workers, provider calls or runtime database."""
import json

from alembic.script import ScriptDirectory

from app.database_migrations import migration_config, schema_differences, upgrade_database
from app.db import make_engine
from app.schema import metadata
from app.source_registry import load_school, load_sources


def check_package():
    registered = metadata()
    required = {"accounts", "user_profiles", "conversations", "policy_sources", "policy_versions", "policy_chunks",
        "assistant_updates", "assistant_update_events"}
    missing = required - set(registered.tables)
    if missing:
        raise RuntimeError("Required packaged tables are missing: " + ", ".join(sorted(missing)))
    sources = load_sources()
    if not sources or load_school()["id"] != "penn":
        raise RuntimeError("Packaged source/school configuration is incomplete")
    head = ScriptDirectory.from_config(migration_config()).get_current_head()
    if not head:
        raise RuntimeError("Packaged migration head is missing")
    # Compare actual migrated DDL to the ORM, rather than freezing a table count
    # that fails whenever a feature legitimately adds a table. Never use the
    # configured production database for this packaging check.
    engine = make_engine("sqlite://")
    try:
        upgrade_database(engine)
        with engine.connect() as connection:
            if schema_differences(connection):
                raise RuntimeError("Packaged migrations and application models differ")
    finally:
        engine.dispose()
    return {"tables": len(registered.tables), "sources": len(sources), "migration_head": head,
        "migration_schema_matches": True, "school": "penn"}


if __name__ == "__main__":
    print(json.dumps(check_package(), sort_keys=True))
