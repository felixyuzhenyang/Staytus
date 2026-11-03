"""Explicit schema upgrades; API and gateway startup only check the revision."""
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.schema import metadata

BASELINE_REVISION = "20261103_0001"


class SchemaNotReady(RuntimeError):
    pass


def migration_config():
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return config


def current_revision(connection):
    return MigrationContext.configure(connection).get_current_revision()


def require_current_schema(engine):
    expected = ScriptDirectory.from_config(migration_config()).get_current_head()
    with engine.connect() as connection:
        current = current_revision(connection)
    if not expected or current != expected:
        raise SchemaNotReady("Database schema is not current. Run `python -m app.database_cli upgrade` "
                             "with the migration credential before starting the API or gateway.")


def schema_differences(connection):
    return compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), metadata())


def upgrade_database(engine):
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(7823946134021)"))
        inspector = inspect(connection)
        tables = set(inspector.get_table_names(schema=inspector.default_schema_name)) - {"alembic_version"}
        if tables and current_revision(connection) is None:
            raise SchemaNotReady("Unversioned existing database. Back it up, then explicitly run "
                                 "`python -m app.database_cli adopt-sqlite` after schema review.")
        config = migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    require_current_schema(engine)


def adopt_sqlite_baseline(engine):
    """No table/data changes: stamp only an exactly matching legacy SQLite schema."""
    if engine.dialect.name != "sqlite":
        raise SchemaNotReady("Legacy adoption is restricted to the existing local SQLite database.")
    config = migration_config()
    if ScriptDirectory.from_config(config).get_current_head() != BASELINE_REVISION:
        raise SchemaNotReady("Legacy adoption needs an explicit historical-baseline upgrade path.")
    with engine.begin() as connection:
        if current_revision(connection) is not None:
            raise SchemaNotReady("Database already has a migration revision; use upgrade/check.")
        if schema_differences(connection):
            raise SchemaNotReady("Existing schema differs from the baseline; adoption refused without changing data.")
        config.attributes["connection"] = connection
        command.stamp(config, BASELINE_REVISION)
    require_current_schema(engine)


def grant_runtime_access(engine, role):
    """Explicit operator grant; application roles cannot write migration metadata."""
    if engine.dialect.name != "postgresql":
        raise SchemaNotReady("Runtime grants require PostgreSQL.")
    require_current_schema(engine)
    quote = engine.dialect.identifier_preparer.quote_identifier
    with engine.begin() as connection:
        exists = connection.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname=:role"), {"role": role}).first()
        if not exists or exists[0]:
            raise SchemaNotReady("Choose an existing non-superuser runtime role.")
        current = connection.scalar(text("SELECT current_user"))
        if role == current:
            raise SchemaNotReady("Migration and runtime roles must be different.")
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {quote(role)}")
        for table in inspect(connection).get_table_names():
            verbs = "SELECT" if table == "alembic_version" else "SELECT, INSERT, UPDATE, DELETE"
            connection.exec_driver_sql(f"GRANT {verbs} ON TABLE {quote(table)} TO {quote(role)}")
        connection.exec_driver_sql(f"REVOKE INSERT, UPDATE, DELETE ON TABLE alembic_version FROM {quote(role)}")
        connection.exec_driver_sql(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quote(role)}")
