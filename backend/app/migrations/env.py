from alembic import context

from app.config import DatabaseSettings
from app.db import make_engine
from app.schema import metadata

config = context.config
target_metadata = metadata()


def configure(connection):
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=config.attributes.get("database_url") or DatabaseSettings().database_url,
                      target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    configure(config.attributes["connection"])
else:
    engine = make_engine(DatabaseSettings().database_url)
    with engine.connect() as connection:
        configure(connection)
    engine.dispose()
