"""OAuth and provider execution tests use transport fakes, never real user accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from threading import Event
import time
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
import httpx
import pytest
from sqlalchemy import select

from app.auth import digest, mint_tool_context
from app.integrations import connectors
from app.integrations.connection_models import MailAgentPermission, OAuthAttempt, ProviderConnection
from app.mail_analysis_models import MailMessageAnalysis
from app.models import Approval, AuthSession, now
from conftest import login

HTTPX_CLIENT = httpx.Client
READ = "https://www.googleapis.com/auth/gmail.readonly"
DRAFT = "https://www.googleapis.com/auth/gmail.compose"


@pytest.fixture
def oauth(env, monkeypatch):
    key = Fernet.generate_key().decode()
    for name, value in {"CONNECTOR_TOKEN_KEY": key, "GOOGLE_CLIENT_ID": "test-client",
                        "GOOGLE_CLIENT_SECRET": "test-secret", "MICROSOFT_CLIENT_ID": "ms-client",
                        "MICROSOFT_CLIENT_SECRET": "ms-secret",
                        "OAUTH_CALLBACK_BASE": "http://testserver/api/backend",
                        "FRONTEND_URL": "https://app.example.edu"}.items():
        monkeypatch.setenv(name, value)
    # HTTPS is required except loopback; testserver is a local synthetic test host.
    monkeypatch.setenv("OAUTH_CALLBACK_BASE", "https://app.example.edu/api/backend")
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "secret-access", "refresh_token": "secret-refresh",
                "expires_in": 3600, "scope": READ + " " + DRAFT})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "mailbox@example.invalid"})
        if request.url.path.endswith("/drafts"):
            return httpx.Response(200, json={"id": "provider-draft-123"})
        raise AssertionError(f"Unexpected provider request: {request.method} {request.url}")
    monkeypatch.setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    return {"key": key, "calls": calls, "handler": handler, "monkeypatch": monkeypatch}


def start(client, headers, capability="mail_read", provider="google"):
    response = client.post(f"/api/v1/connections/{provider}/start", headers=headers,
                           json={"capability": capability})
    assert response.status_code == 200, response.text
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    return query["state"][0], query


def callback(client, headers, state, **extra):
    return client.get("/api/v1/connections/google/callback", headers=headers,
                      params={"state": state, "code": "authorization-code", **extra}, follow_redirects=False)


def add_connection(factory, oauth, account_id="account-mei-lin", scopes=None, provider="google"):
    with factory() as db:
        connection = ProviderConnection(account_id=account_id, provider=provider,
            scopes=scopes if scopes is not None else [READ, DRAFT])
        connectors._save_tokens(connection, {"access_token": "secret-access", "refresh_token": "secret-refresh",
            "expires_at": time.time() + 3600}, connectors.ConnectorSettings())
        db.add(connection)
        db.commit()
        return connection.id


def test_oauth_state_is_hashed_pkce_encrypted_and_callback_one_use(env, student, oauth):
    client, factory = env
    state, query = start(client, student)
    assert query["redirect_uri"] == ["https://app.example.edu/api/backend/connections/google/callback"]
    assert query["code_challenge_method"] == ["S256"]
    with factory() as db:
        attempt = db.get(OAuthAttempt, digest(state))
        assert attempt.account_id == "account-mei-lin"
        verifier = Fernet(oauth["key"].encode()).decrypt(attempt.verifier.encode()).decode()
        assert verifier not in attempt.verifier and state != attempt.id
        assert query["code_challenge"] == [base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")]
    response = callback(client, student, state)
    assert response.status_code == 303 and response.headers["location"].endswith("?connection=google")
    assert callback(client, student, state).status_code == 400
    assert [(r.method, r.url.path) for r in oauth["calls"]] == [("POST", "/token"), ("GET", "/gmail/v1/users/me/profile")]
    assert parse_qs(oauth["calls"][0].content.decode())["code_verifier"] == [verifier]
    with factory() as db:
        assert db.get(OAuthAttempt, digest(state)) is None
        connection = db.scalar(select(ProviderConnection).where(ProviderConnection.account_id == "account-mei-lin"))
        assert "secret-access" not in connection.encrypted_tokens
        assert connectors._tokens(connection, connectors.ConnectorSettings())["access_token"] == "secret-access"


def test_oauth_callback_requires_original_browser_session(env, student, oauth):
    client, factory = env
    state, _ = start(client, student)
    assert callback(client, {}, state).status_code == 401
    other = login(client, "sam-rivera")
    assert callback(client, other, state).status_code == 400
    assert not oauth["calls"]
    with factory() as db:
        assert db.get(OAuthAttempt, digest(state)) is not None
    assert callback(client, student, state).status_code == 303


def test_parallel_callbacks_claim_state_only_once(env, student, oauth):
    client, _ = env
    state, _ = start(client, student)
    entered, release = Event(), Event()
    original = oauth["handler"]
    def handler(request):
        entered.set()
        assert release.wait(timeout=5)
        return original(request)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(callback, client, student, state)
        assert entered.wait(timeout=5)
        try:
            second = pool.submit(callback, client, student, state).result(timeout=5)
            assert second.status_code == 400
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 303
    assert sum(r.url.path.endswith("/token") for r in oauth["calls"]) == 1
    assert sum(r.url.path.endswith("/profile") for r in oauth["calls"]) == 1


def test_expired_state_and_provider_mismatch_make_no_exchange(env, student, oauth):
    client, factory = env
    state, _ = start(client, student)
    mismatch = client.get("/api/v1/connections/microsoft/callback", headers=student,
                          params={"state": state, "code": "x"}, follow_redirects=False)
    assert mismatch.status_code == 400
    with factory() as db:
        db.get(OAuthAttempt, digest(state)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert callback(client, student, state).status_code == 400
    assert not oauth["calls"]


def test_cancel_and_failed_exchange_both_consume_state(env, student, oauth):
    client, _ = env
    state, _ = start(client, student)
    assert callback(client, student, state, error="access_denied").status_code == 303
    assert callback(client, student, state).status_code == 400
    assert not oauth["calls"]
    state, _ = start(client, student)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, text="private-provider-detail")), **kwargs))
    response = callback(client, student, state)
    assert response.status_code == 502 and "private-provider-detail" not in response.text
    assert callback(client, student, state).status_code == 400


def test_logout_login_rotation_and_disconnect_invalidate_pending_oauth(env, student, oauth):
    client, factory = env
    state, _ = start(client, student)
    replacement = login(client)
    assert callback(client, replacement, state).status_code == 400
    state, _ = start(client, replacement)
    assert client.delete("/api/v1/connections/google", headers=replacement).status_code == 200
    assert callback(client, replacement, state).status_code == 400
    state, _ = start(client, replacement)
    assert client.post("/api/v1/auth/logout", headers=replacement).status_code == 200
    with factory() as db:
        assert db.get(OAuthAttempt, digest(state)) is None


def test_connection_status_read_and_disconnect_are_account_scoped(env, student, oauth):
    client, factory = env
    cid = add_connection(factory, oauth)
    own = client.get("/api/v1/connections", headers=student)
    assert own.status_code == 200
    assert own.json()["providers"][0]["connected"] is True
    assert "secret-access" not in own.text and "encrypted_tokens" not in own.text
    other = login(client, "sam-rivera")
    assert client.get("/api/v1/connections", headers=other).json()["providers"][0]["connected"] is False
    assert client.get("/api/v1/connections/google/messages", headers=other).status_code == 409
    assert client.delete("/api/v1/connections/google", headers=other).status_code == 200
    with factory() as db:
        assert db.get(ProviderConnection, cid) is not None
    assert not oauth["calls"]


def test_mail_read_filters_candidates_and_checks_scope(env, student, oauth):
    client, factory = env
    cid = add_connection(factory, oauth, scopes=["unrelated"])
    assert client.get("/api/v1/connections/google/messages", headers=student).status_code == 409
    with factory() as db:
        db.get(ProviderConnection, cid).scopes = [READ]
        db.commit()
    def handler(request):
        assert request.headers["Authorization"] == "Bearer secret-access"
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "official"}, {"id": "other"}]})
        official = request.url.path.endswith("/official")
        return httpx.Response(200, json={"id": "official" if official else "other", "snippet": "Check your document dates",
            "payload": {"headers": [{"name": "From", "value": "ISSS <isss@upenn.edu>" if official else "Visa Offer <offer@attacker.example>"},
                                    {"name": "Subject", "value": "International student travel signature"}]}})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    response = client.get("/api/v1/connections/google/messages", headers=student)
    assert response.status_code == 200, response.text
    assert [m["id"] for m in response.json()["messages"]] == ["official"]
    assert "secret-access" not in response.text


def test_read_only_connection_cannot_create_approved_draft(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[READ])
    result = client.post("/api/v1/approvals", headers=student, json={"kind": "email", "payload": {
        "to": "adviser@example.edu", "subject": "Document question", "body": "Please review my documents."}})
    item = result.json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert not oauth["calls"]


def test_approved_draft_has_real_receipt_and_never_calls_send(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth)
    result = client.post("/api/v1/approvals", headers=student, json={"kind": "email", "payload": {
        "to": "adviser@example.edu", "subject": "Document question", "body": "Please review my documents."}})
    item = result.json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    response = client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]})
    assert response.status_code == 200, response.text
    assert response.json()["receipt"]["external_id"] == "provider-draft-123"
    assert response.json()["receipt"]["sent"] is False
    assert response.json()["status"] == "SUCCEEDED"
    assert len(oauth["calls"]) == 1
    assert oauth["calls"][0].url.path.endswith("/drafts")
    assert "/send" not in str(oauth["calls"][0].url)
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    with factory() as db:
        assert db.get(Approval, item["id"]).receipt["external_id"] == "provider-draft-123"


def test_unconfigured_oauth_and_invalid_capability_fail_without_fake_success(env, student, monkeypatch):
    client, _ = env
    monkeypatch.setenv("CONNECTOR_TOKEN_KEY", "")
    result = client.post("/api/v1/connections/google/start", headers=student, json={"capability": "mail_read"})
    assert result.status_code == 503
    assert client.post("/api/v1/connections/google/start", headers=student, json={"capability": "all_permissions"}).status_code == 422
    assert client.post("/api/v1/connections/google/start", headers=student, json={"capability": "mail_read", "account_id": "account-sam-rivera"}).status_code == 422


def test_uncertain_provider_write_is_terminal_and_cannot_duplicate_draft(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth)
    calls = []
    def timed_out(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-provider-detail", request=request)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(timed_out), **kwargs))
    item = client.post("/api/v1/approvals", headers=student, json={"kind": "email", "payload": {
        "to": "adviser@example.edu", "subject": "Document question", "body": "Please review my documents."}}).json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    response = client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]})
    assert response.status_code == 502 and "private-provider-detail" not in response.text
    with factory() as db:
        assert db.get(Approval, item["id"]).status == "FAILED_UNCONFIRMED"
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert len(calls) == 1
    events = client.get("/api/v1/audit", headers=student).json()["events"]
    assert any(event["action"] == "approval.unconfirmed" for event in events)


def tool_headers(factory, headers):
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(headers["Authorization"][7:])))
        return {"X-Tool-Key": "test-tool-key", "X-Staytus-Context": mint_tool_context(session)}


def gmail_reads(oauth, *, count=3):
    def handler(request):
        oauth["calls"].append(request)
        if request.url.path.endswith("/messages"):
            assert "newer_than:30d" in request.url.params["q"]
            return httpx.Response(200, json={"messages": [{"id": str(i)} for i in range(count)]})
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "snippet": "p" * 1200,
            "body": {"content": "private-full-body"}, "attachments": ["private-attachment"],
            "payload": {"headers": [{"name": "From", "value": "ISSS <isss@upenn.edu>"},
                                    {"name": "Subject", "value": "International student documents"}]}})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))


def test_setup_status_identifies_exact_callback_and_missing_settings_without_secrets(env, student, oauth, monkeypatch):
    client, _ = env
    row = client.get("/api/v1/connections", headers=student).json()["providers"][0]
    assert row["configured"] is True and row["agent_access"] is False
    assert row["setup"]["callback_uri"] == "https://app.example.edu/api/backend/connections/google/callback"
    assert row["setup"]["application_type"] == "Web / server application"
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    response = client.get("/api/v1/connections", headers=student)
    providers = {row["provider"]: row for row in response.json()["providers"]}
    google, microsoft = providers["google"], providers["microsoft"]
    assert "icloud" in providers and not providers["icloud"]["connected"]
    assert google["configured"] is False and google["setup"]["missing"] == ["GOOGLE_CLIENT_SECRET"]
    assert microsoft["configured"] is True
    assert "test-secret" not in response.text and "ms-secret" not in response.text


def test_bad_encryption_key_and_callback_report_not_configured(env, student, oauth, monkeypatch):
    client, _ = env
    monkeypatch.setenv("CONNECTOR_TOKEN_KEY", "not-a-fernet-key")
    monkeypatch.setenv("OAUTH_CALLBACK_BASE", "http://public.example/api/backend")
    providers = client.get("/api/v1/connections", headers=student).json()["providers"]
    assert all(not p["configured"] and p["setup"]["errors"] for p in providers)


def test_cross_origin_callback_configuration_is_rejected_before_consent(env, student, oauth, monkeypatch):
    client, _ = env
    monkeypatch.setenv("FRONTEND_URL", "https://different.example.edu")
    result = client.get("/api/v1/connections", headers=student).json()["providers"][0]
    assert result["configured"] is False
    assert "same origin" in ".".join(result["setup"]["errors"])
    assert client.post("/api/v1/connections/google/start", headers=student, json={"capability": "mail_read"}).status_code == 503
    assert not oauth["calls"]


@pytest.mark.parametrize("scope", ["https://evil.example/Mail.Read", "prefixhttps://www.googleapis.com/auth/gmail.readonly", "https://evil.example/gmail.readonly"])
def test_lookalike_read_scopes_are_not_accepted(env, student, oauth, scope):
    client, factory = env
    add_connection(factory, oauth, scopes=[scope])
    assert client.get("/api/v1/connections/google/messages", headers=student).status_code == 409
    assert not oauth["calls"]


def test_agent_tool_requires_separate_consent_then_returns_only_bounded_previews(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[READ])
    headers = tool_headers(factory, student)
    url = "/tools/read_recent_official_messages"
    assert client.post(url, json={"provider": "google"}, headers=headers).status_code == 403
    assert not oauth["calls"]
    gmail_reads(oauth)
    permission = client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": True})
    assert permission.status_code == 200
    response = client.post(url, json={"provider": "google", "limit": 2}, headers=headers)
    assert response.status_code == 200, response.text
    value = response.json()
    assert len(value["messages"]) == 2
    assert value["model_access_authorized"] is True and value["untrusted_content"] is True
    assert all(len(item["snippet"]) == 500 and "id" not in item for item in value["messages"])
    assert "private-full-body" not in response.text and "private-attachment" not in response.text
    assert "secret-access" not in response.text and "encrypted_tokens" not in response.text
    assert client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": False}).status_code == 200
    assert client.post(url, json={"provider": "google"}, headers=headers).status_code == 403
    assert client.get("/api/v1/connections/google/messages", headers=student).status_code == 200


def test_agent_mail_permission_and_signed_tool_principal_are_account_scoped(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[READ])
    assert client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": True}).status_code == 200
    other = login(client, "sam-rivera")
    assert client.patch("/api/v1/connections/google/agent-access", headers=other, json={"enabled": True}).status_code == 409
    assert client.post("/tools/read_recent_official_messages", json={"provider": "google"}, headers=tool_headers(factory, other)).status_code == 409
    assert client.post("/tools/read_recent_official_messages", json={"provider": "google", "account_id": "account-mei-lin"}, headers=tool_headers(factory, other)).status_code == 422
    assert client.post("/tools/read_recent_official_messages", json={"provider": "google"}).status_code == 401
    assert not oauth["calls"]


def test_agent_mail_limit_rejected_before_provider_network(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[READ])
    client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": True})
    for limit in [0, 11, 1000]:
        assert client.post("/tools/read_recent_official_messages", json={"provider": "google", "limit": limit}, headers=tool_headers(factory, student)).status_code == 422
    assert not oauth["calls"]


def test_relink_and_disconnect_reset_agent_sharing_permission(env, student, oauth):
    client, factory = env
    connection_id = add_connection(factory, oauth, scopes=[READ])
    client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": True})
    client.patch("/api/v1/connections/google/content-analysis", headers=student, json={"enabled": True})
    with factory() as db:
        db.add(MailMessageAnalysis(account_id="account-mei-lin", profile_id="mei-lin", profile_version=1,
            provider="google", connection_id=connection_id, message_hash="a" * 64,
            encrypted_result="synthetic-encrypted-value", model_id="synthetic-model",
            expires_at=now() + timedelta(days=1)))
        db.commit()
    state, _ = start(client, student)
    assert callback(client, student, state).status_code == 303
    status = client.get("/api/v1/connections", headers=student).json()["providers"][0]
    assert status["agent_access"] is False and status["content_analysis_enabled"] is False
    with factory() as db:
        assert db.scalar(select(MailMessageAnalysis)) is None
    client.patch("/api/v1/connections/google/agent-access", headers=student, json={"enabled": True})
    client.delete("/api/v1/connections/google", headers=student)
    with factory() as db:
        assert db.get(MailAgentPermission, ("account-mei-lin", "google")) is None


def test_mail_get_401_renews_once_and_keeps_new_token_encrypted(env, student, oauth):
    client, factory = env
    cid = add_connection(factory, oauth, scopes=[READ])
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "renewed-access", "expires_in": 3600, "scope": READ})
        if request.headers["Authorization"] == "Bearer secret-access":
            return httpx.Response(401, text="private-error")
        return httpx.Response(200, json={"messages": []})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    assert client.get("/api/v1/connections/google/messages", headers=student).status_code == 200
    assert len(calls) == 3
    with factory() as db:
        connection = db.get(ProviderConnection, cid)
        assert "renewed-access" not in connection.encrypted_tokens
        assert connectors._tokens(connection, connectors.ConnectorSettings())["access_token"] == "renewed-access"


def test_refresh_permission_downgrade_stops_before_mail_read(env, student, oauth):
    client, factory = env
    cid = add_connection(factory, oauth, scopes=[READ])
    with factory() as db:
        connection = db.get(ProviderConnection, cid)
        connectors._save_tokens(connection, {"access_token": "old", "refresh_token": "refresh", "expires_at": 0}, connectors.ConnectorSettings())
        db.commit()
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/token")
        return httpx.Response(200, json={"access_token": "new", "expires_in": 3600, "scope": DRAFT})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    assert client.get("/api/v1/connections/google/messages", headers=student).status_code == 409
    assert len(calls) == 1


def test_callback_rejects_missing_granted_scope_without_storing_connection(env, student, oauth):
    client, factory = env
    state, _ = start(client, student)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"access_token": "token", "expires_in": 3600, "scope": DRAFT})), **kwargs))
    response = callback(client, student, state)
    assert response.status_code == 502
    with factory() as db:
        assert db.scalar(select(ProviderConnection).where(ProviderConnection.account_id == "account-mei-lin")) is None


def test_microsoft_short_scopes_and_recent_official_preview_filter(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=["Mail.Read"], provider="microsoft")
    current = now().isoformat() + "Z"
    ancient = (now() - timedelta(days=90)).isoformat() + "Z"
    def handler(request):
        assert request.url.host == "graph.microsoft.com" and request.url.path == "/v1.0/me/messages"
        assert "$filter" in request.url.params and request.url.params["$top"] == "50"
        base = {"subject": "ISSS International student update", "from": {"emailAddress": {"address": "isss@upenn.edu"}}, "bodyPreview": "Recent short update", "body": {"content": "full-mail-body"}}
        return httpx.Response(200, json={"value": [{**base, "id": "recent", "receivedDateTime": current},
            {**base, "id": "old", "receivedDateTime": ancient},
            {**base, "id": "spoof", "receivedDateTime": current, "from": {"emailAddress": {"address": "isss@upenn.edu.evil.example"}}}]})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    response = client.get("/api/v1/connections/microsoft/messages", headers=student)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["messages"]] == ["recent"]
    assert "full-mail-body" not in response.text


def test_official_sender_check_parses_address_instead_of_display_name():
    assert not connectors._relevant('"isss@upenn.edu" <attacker@evil.example>', "International student update")
    assert connectors._relevant('Penn ISSS <isss@upenn.edu>', "Travel signature")
