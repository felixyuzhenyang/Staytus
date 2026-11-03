"""Operator-only database commands. URLs come from private config, never CLI flags."""
import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy import inspect

from app.config import DatabaseSettings
from app.database_migrations import (SchemaNotReady, adopt_sqlite_baseline, current_revision,
                                     grant_runtime_access, require_current_schema, upgrade_database)
from app.db import make_engine


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("upgrade", help="Apply reviewed migrations; refuses unversioned existing tables")
    sub.add_parser("check", help="Read-only revision check")
    sub.add_parser("adopt-sqlite", help="Explicitly stamp a matching, backed-up legacy SQLite database")
    sql = sub.add_parser("sql", help="Emit reviewable SQL without connecting to the target")
    sql.add_argument("--dialect", choices=["postgresql", "sqlite"], default="postgresql")
    transfer = sub.add_parser("import-sqlite", help="Import into an empty, migrated PostgreSQL database")
    transfer.add_argument("--sqlite-path", type=Path, required=True)
    transfer.add_argument("--report", type=Path)
    pg_transfer = sub.add_parser("import-postgres", help="Copy the current PostgreSQL snapshot into an empty migrated target")
    pg_transfer.add_argument("--source-env-file", type=Path, required=True)
    pg_transfer.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    engine = None
    try:
        if args.command == "sql":
            from alembic import command
            from app.database_migrations import migration_config
            config = migration_config()
            config.attributes["database_url"] = "postgresql+psycopg://" if args.dialect == "postgresql" else "sqlite:///"
            command.upgrade(config, "head", sql=True)
            return 0
        settings = DatabaseSettings(_env_file=args.env_file)
        engine = make_engine(settings.database_url)
        if args.command == "upgrade":
            upgrade_database(engine)
            if os.environ.get("DATABASE_RUNTIME_ROLE"):
                grant_runtime_access(engine, os.environ["DATABASE_RUNTIME_ROLE"])
        elif args.command == "adopt-sqlite":
            adopt_sqlite_baseline(engine)
        elif args.command == "import-sqlite":
            from app.database_transfer import transfer_sqlite
            result = transfer_sqlite(args.sqlite_path, engine)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2) + "\n")
                args.report.chmod(0o600)
            print(json.dumps(result))
            return 0
        elif args.command == "import-postgres":
            from dotenv import dotenv_values
            from app.database_transfer import transfer_postgres
            # Source identity must come from this explicit file, not a process
            # DATABASE_URL that may select the destination for both engines.
            source_values = dotenv_values(args.source_env_file)
            if not source_values.get("DATABASE_URL"):
                raise SchemaNotReady("Source configuration must contain DATABASE_URL.")
            source_settings = DatabaseSettings(_env_file=None, database_url=source_values["DATABASE_URL"],
                                              app_environment=source_values.get("APP_ENVIRONMENT", "development"))
            source = make_engine(source_settings.database_url)
            try:
                result = transfer_postgres(source, engine)
            finally:
                source.dispose()
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as output:
                    output.write(json.dumps(result, indent=2) + "\n")
                args.report.chmod(0o600)
            print(json.dumps(result))
            return 0
        require_current_schema(engine)
        with engine.connect() as connection:
            result = {"dialect": engine.dialect.name, "revision": current_revision(connection),
                      "application_tables": len(set(inspect(connection).get_table_names()) - {"alembic_version"}),
                      "schema_current": True}
        print(json.dumps(result))
        return 0
    except SchemaNotReady as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("Database operation failed; no credentials or row contents were logged. Check private configuration and server status.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
