"""Injected test databases must not activate production persistence/workers."""
from fastapi.testclient import TestClient

from app import main


def test_custom_database_lifespan_never_starts_operator_workers(env, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("An injected database must own initialization and workers")
    monkeypatch.setattr(main.Base.metadata, "create_all", forbidden)
    monkeypatch.setattr(main, "sync_source_registry", forbidden)
    monkeypatch.setattr(main, "Thread", forbidden)
    with TestClient(main.app) as client:
        assert client.get("/health").json()["service"] == "staytus-api"
