"""Opt-in real PostgreSQL suites use unique schemas in a dedicated test database."""
import os
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import make_engine


def isolated_engine(tmp_path, name, request):
    url = os.environ.get("STAYTUS_TEST_DATABASE_URL")
    if not url:
        engine = make_engine(f"sqlite:///{tmp_path}/{name}.db")
        request.addfinalizer(engine.dispose)
        return engine
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").startswith("staytus_test"):
        raise RuntimeError("Tests require a dedicated staytus_test* PostgreSQL database; application URLs are forbidden")
    control = make_engine(url)
    schema = "test_" + uuid4().hex
    with control.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Shadow any public migration table; introspection must not fall through
        # to the test database's public schema before this schema is migrated.
        connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
    engine = make_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
    engine = engine.execution_options(schema_translate_map={None: schema})
    engine._staytus_test_connect_args = {"options": f"-csearch_path={schema},public"}
    engine._staytus_test_schema = schema

    def cleanup():
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
    request.addfinalizer(cleanup)
    return engine
