"""Real DDL/data transfer and fail-closed startup, with isolated synthetic databases."""
import os

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect, select, text

from app.config import DatabaseSettings, Settings
from app.database_migrations import (BASELINE_REVISION, SchemaNotReady, adopt_sqlite_baseline,
                                     migration_config, require_current_schema, schema_differences, upgrade_database)
from app.db import make_engine
from app.schema import metadata
from database_support import isolated_engine


def test_sqlite_upgrade_is_versioned_idempotent_and_matches_models(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    with pytest.raises(SchemaNotReady):
        require_current_schema(engine)
    upgrade_database(engine)
    upgrade_database(engine)
    with engine.connect() as connection:
        from alembic.script import ScriptDirectory
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(migration_config()).get_current_head()
        assert schema_differences(connection) == []
    engine.dispose()


def test_legacy_adoption_is_explicit_and_preserves_data(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/legacy.db")
    metadata().create_all(engine)
    from sqlalchemy.orm import Session
    from support import seed_fixtures
    with Session(engine) as db:
        seed_fixtures(db)
    with pytest.raises(SchemaNotReady, match="Unversioned"):
        upgrade_database(engine)
    adopt_sqlite_baseline(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 3
    require_current_schema(engine)
    engine.dispose()


def test_adoption_refuses_schema_drift_without_stamping(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/drift.db")
    metadata().create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE accounts ADD COLUMN unexpected TEXT"))
    with pytest.raises(SchemaNotReady, match="differs"):
        adopt_sqlite_baseline(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()
    engine.dispose()


def test_empty_sqlite_can_downgrade_and_upgrade_in_isolation(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/rollback.db")
    upgrade_database(engine)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    upgrade_database(engine)
    engine.dispose()


def test_api_startup_does_not_bootstrap_an_unmigrated_database(tmp_path, monkeypatch):
    from app import main
    engine = make_engine(f"sqlite:///{tmp_path}/uninitialized.db")
    monkeypatch.setattr(main, "engine", engine)
    with pytest.raises(SchemaNotReady):
        with TestClient(main.app):
            pass
    assert inspect(engine).get_table_names() == []
    engine.dispose()


@pytest.mark.parametrize("changes", [
    {"database_url": "sqlite:///wrong.db"},
    {"database_url": "postgresql+psycopg://localhost/staytus?sslmode=require"},
    {"context_secret": "short"},
    {"context_secret": ""},
    {"tool_key": "s" * 48},
    {"cors_origins": "http://example.invalid"},
])
def test_production_rejects_unsafe_shared_settings(changes, monkeypatch):
    for name in ("DATABASE_URL", "APP_ENVIRONMENT", "CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    data = {"app_environment": "production", "database_url": "postgresql+psycopg://localhost/staytus?sslmode=verify-full",
            "context_secret": "s" * 48, "ORCHESTRATE_TOOL_KEY": "t" * 48, "cors_origins": "https://app.example.invalid"}
    if "tool_key" in changes:
        changes = {"ORCHESTRATE_TOOL_KEY": changes["tool_key"]}
    data.update(changes)
    with pytest.raises(ValueError):
        Settings(_env_file=None, **data)


def test_cli_failure_does_not_print_connection_password(tmp_path, capsys, monkeypatch):
    from app.database_cli import main
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = tmp_path / ".env"
    config.write_text("DATABASE_URL=invalid+driver://user:synthetic-secret-never-print@host/db\n")
    assert main(["--env-file", str(config), "check"]) == 1
    output = capsys.readouterr()
    assert "synthetic-secret-never-print" not in output.out + output.err


def test_migration_configuration_does_not_require_runtime_or_model_secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = DatabaseSettings(_env_file=None, app_environment="production",
                              database_url="postgresql+psycopg://localhost/staytus?sslmode=verify-full")
    assert config.app_environment == "production"
    assert "context_secret" not in config.model_fields_set


def test_legacy_compatibility_never_silently_discards_history(tmp_path):
    from app.database_transfer import source_compatibility
    engine = make_engine(f"sqlite:///{tmp_path}/history.db")
    metadata().create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE rule_change_proposals (id TEXT PRIMARY KEY)"))
        assert source_compatibility(connection) == ["empty_legacy_rule_change_proposals_retained_in_sqlite"]
        connection.execute(text("INSERT INTO rule_change_proposals VALUES ('synthetic-history')"))
        with pytest.raises(SchemaNotReady):
            source_compatibility(connection)
    engine.dispose()


@pytest.mark.skipif(not os.environ.get("STAYTUS_TEST_DATABASE_URL"), reason="Opt-in dedicated PostgreSQL test database")
def test_postgres_migration_transfer_and_shared_connections(tmp_path, request):
    from app.database_transfer import transfer_sqlite
    from app.models import PolicyChunk, Profile
    from sqlalchemy.orm import Session
    from support import seed_fixtures
    engine = isolated_engine(tmp_path, "pg-transfer", request)
    upgrade_database(engine)
    with engine.connect() as connection:
        assert schema_differences(connection) == []
    source_path = tmp_path / "synthetic.db"
    source = make_engine(f"sqlite:///{source_path}")
    metadata().create_all(source)
    with Session(source) as db:
        seed_fixtures(db)
        chunk = db.scalar(select(PolicyChunk))
        chunk.embedding = chunk.vector = [0.123456789, 0.9, -0.12]
        chunk.embedding_model = "synthetic-test-only"
        db.commit()
    result = transfer_sqlite(source_path, engine)
    assert result["values_verified"] and result["tables"]["accounts"] == 3
    second = make_engine(str(engine.url.render_as_string(hide_password=False)),
                         connect_args=engine._staytus_test_connect_args)
    second = second.execution_options(schema_translate_map={None: engine._staytus_test_schema})
    try:
        with Session(engine) as api_db:
            api_db.get(Profile, "mei-lin").name = "Synthetic shared update"
            api_db.commit()
        with Session(second) as gateway_db:
            assert gateway_db.get(Profile, "mei-lin").name == "Synthetic shared update"
            assert len(gateway_db.scalar(select(PolicyChunk)).vector) == 3
        with pytest.raises(SchemaNotReady, match="empty"):
            transfer_sqlite(source_path, engine)
    finally:
        second.dispose()
        source.dispose()


@pytest.mark.skipif(not os.environ.get("STAYTUS_TEST_DATABASE_URL"), reason="Opt-in dedicated PostgreSQL test database")
def test_postgres_to_postgres_preserves_snapshot_and_rolls_back_failed_copy(tmp_path, request, monkeypatch):
    from app import database_transfer
    from app.models import PolicyChunk, Profile
    from sqlalchemy.orm import Session
    from support import seed_fixtures
    source = isolated_engine(tmp_path, "pg-source", request)
    target = isolated_engine(tmp_path, "pg-target", request)
    failed_target = isolated_engine(tmp_path, "pg-failed-target", request)
    for engine in (source, target, failed_target):
        upgrade_database(engine)
    with Session(source) as db:
        seed_fixtures(db)
        db.get(Profile, "mei-lin").name = "SYNTHETIC CURRENT POSTGRES SNAPSHOT"
        chunk = db.scalar(select(PolicyChunk))
        chunk.embedding = chunk.vector = [0.123456789, -0.9, 0.42]
        chunk.embedding_model = "synthetic-only"
        chunk_id = chunk.id
        db.commit()
    result = database_transfer.transfer_postgres(source, target)
    assert result["source_snapshot"] == "repeatable_read_read_only"
    assert result["values_verified"] and result["tables"]["accounts"] == 3
    with Session(target) as db:
        assert db.get(Profile, "mei-lin").name == "SYNTHETIC CURRENT POSTGRES SNAPSHOT"
        assert len(db.get(PolicyChunk, chunk_id).vector) == 3
    with pytest.raises(SchemaNotReady, match="empty"):
        database_transfer.transfer_postgres(source, target)
    monkeypatch.setattr(database_transfer, "_same_value", lambda *_args: False)
    with pytest.raises(SchemaNotReady, match="rolled back"):
        database_transfer.transfer_postgres(source, failed_target)
    for engine, expected in ((source, 3), (target, 3), (failed_target, 0)):
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM accounts")) == expected
