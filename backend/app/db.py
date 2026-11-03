import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DatabaseSettings


class Base(DeclarativeBase):
    pass


def make_engine(url: str, *, connect_args=None):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    options.update(connect_args or {})
    cloud_options = {"poolclass": NullPool} if os.environ.get("VERCEL") == "1" and url.startswith("postgresql") else {}
    engine = create_engine(url, connect_args=options, pool_pre_ping=True, hide_parameters=True, **cloud_options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


engine = make_engine(DatabaseSettings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
