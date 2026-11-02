"""A future HTTPS edge can expose tools without exposing the application API."""
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import tool_gateway
from app.auth import digest, mint_tool_context
from app.config import get_settings
from app.db import get_db
from app.main import app as main_app
from app.models import AuthSession


TOOL_KEY = "test-service-key-" + "s" * 40
CONTEXT_SECRET = "test-signing-key-" + "c" * 40


@pytest.fixture
def gateway_config(monkeypatch):
    # Never read the operator's actual .env in these tests.
    monkeypatch.setattr(tool_gateway, "read_explicit_gateway_secrets", lambda: tool_gateway.GatewaySecrets(_env_file=None))
    monkeypatch.setenv("ORCHESTRATE_TOOL_KEY", TOOL_KEY)
    monkeypatch.setenv("CONTEXT_SECRET", CONTEXT_SECRET)
    monkeypatch.setattr(get_settings(), "tool_key", TOOL_KEY)
    monkeypatch.setattr(get_settings(), "context_secret", CONTEXT_SECRET)


@pytest.fixture
def gateway(env, gateway_config):
    tool_gateway.app.dependency_overrides[get_db] = main_app.dependency_overrides[get_db]
    try:
        with TestClient(tool_gateway.app) as client:
            yield client
    finally:
        tool_gateway.app.dependency_overrides.clear()


def test_gateway_minimal_health_and_correlation(gateway):
    response = gateway.get("/health", headers={"X-Request-ID": "forged-request-id"})
    assert response.status_code == 200 and response.json()["service"] == "staytus-tool-gateway"
    UUID(response.headers["X-Request-ID"])
    assert response.headers["X-Request-ID"] != "forged-request-id"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert TOOL_KEY not in response.text and CONTEXT_SECRET not in response.text


@pytest.mark.parametrize("path,method", [
    ("/docs", "GET"), ("/redoc", "GET"), ("/openapi.json", "GET"),
    ("/api/v1/auth/register", "POST"), ("/api/v1/auth/login", "POST"),
    ("/api/v1/profile", "GET"), ("/api/v1/approvals", "GET"),
    ("/api/v1/approvals/example/approve", "POST"),
    ("/api/v1/connections", "GET"), ("/api/v1/connections/google/callback", "GET"),
    ("/api/v1/chat", "POST"), ("/api/v1/policies/refresh", "POST"),
    ("/tools/approve", "POST"), ("/tools/send_email", "POST"),
])
def test_application_and_final_write_routes_are_absent(gateway, path, method):
    assert gateway.request(method, path).status_code == 404


def test_tools_reject_missing_service_or_user_context(gateway):
    assert gateway.post("/tools/get_student_profile", json={}).status_code == 401
    assert gateway.post("/tools/get_student_profile", json={}, headers={"X-Tool-Key": TOOL_KEY}).status_code == 401


def test_valid_context_resolves_own_account_and_rejects_spoofing(gateway, env, student):
    with env[1]() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(student["Authorization"][7:])))
        capability = mint_tool_context(session)
    headers = {"X-Tool-Key": TOOL_KEY, "X-Staytus-Context": capability}
    response = gateway.post("/tools/get_student_profile", json={}, headers=headers)
    assert response.status_code == 200 and response.json()["id"] == "mei-lin"
    assert gateway.post("/tools/get_student_profile", json={"profile_id": "sam-rivera"}, headers=headers).status_code == 422
    invalid = {**headers, "X-Staytus-Context": capability + "tampered"}
    assert gateway.post("/tools/get_student_profile", json={}, headers=invalid).status_code == 401
    wrong_service = {**headers, "X-Tool-Key": "different-service-key"}
    assert gateway.post("/tools/get_student_profile", json={}, headers=wrong_service).status_code == 401


@pytest.mark.parametrize("service,signing", [(None, None), ("short-secret", CONTEXT_SECRET),
    (TOOL_KEY, ""), (" " * 50, CONTEXT_SECRET), (TOOL_KEY, TOOL_KEY)])
def test_startup_rejects_missing_weak_or_shared_raw_secrets(monkeypatch, service, signing):
    monkeypatch.setattr(tool_gateway, "read_explicit_gateway_secrets", lambda: tool_gateway.GatewaySecrets(_env_file=None))
    for name, value in (("ORCHESTRATE_TOOL_KEY", service), ("CONTEXT_SECRET", signing)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="explicitly configured") as error:
        with TestClient(tool_gateway.app):
            pass
    assert "short-secret" not in str(error.value)


def test_startup_rejects_cached_settings_mismatch(gateway_config, monkeypatch):
    monkeypatch.setattr(get_settings(), "context_secret", "different-cached-key-" + "x" * 40)
    with pytest.raises(RuntimeError, match="same explicit secrets"):
        with TestClient(tool_gateway.app):
            pass
