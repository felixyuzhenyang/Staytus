"""Bootstrap a fresh DB. This is not an existing-database upgrade migration.

Run from backend: uv run python migrations/0001_initial.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db import Base, engine
from app import models, chat_models, policy_models  # noqa: F401 - Register tables.
from app.integrations import connection_models  # noqa: F401 - Register OAuth tables.

if __name__ == "__main__":
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    print("Initial schema created (existing tables were not modified).")
