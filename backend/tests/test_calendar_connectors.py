"""Calendar and mailbox-identity checks use synthetic MockTransport providers."""
import json

import httpx
import pytest

from app.integrations import connectors
from app.integrations.connection_models import ProviderConnection
from app.models import Approval
from test_connectors import oauth as connector_oauth, add_connection, start, callback, HTTPX_CLIENT, READ, DRAFT

oauth = connector_oauth

CALENDAR = "https://www.googleapis.com/auth/calendar.events.owned"
MS_CALENDAR = "https://graph.microsoft.com/Calendars.ReadWrite"


@pytest.mark.parametrize("provider,calendar_scope", [("google", CALENDAR), ("microsoft", MS_CALENDAR)])
def test_calendar_consent_is_independent_and_never_requests_mail_by_default(env, student, oauth, provider, calendar_scope):
    client, _ = env
    _, query = start(client, student, "calendar_write", provider)
    scopes = set(query["scope"][0].split())
    assert calendar_scope in scopes
    assert not any("mail" in scope.lower() for scope in scopes)
    if provider == "google":
        assert query["include_granted_scopes"] == ["true"]


def test_incremental_calendar_preserves_mail_and_rejects_missing_grant(env, student, oauth):
    client, factory = env
    old_id = add_connection(factory, oauth)
    state, query = start(client, student, "calendar_write")
    assert {READ, DRAFT, CALENDAR} == set(query["scope"][0].split())
    assert callback(client, student, state).status_code == 502
    with factory() as db:
        connection = db.get(ProviderConnection, old_id)
        assert connection is not None and not connectors._can_calendar(connection)


def test_successful_incremental_grant_keeps_both_capabilities(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth)
    original = oauth["handler"]
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "calendar-access", "refresh_token": "calendar-refresh",
                "expires_in": 3600, "scope": " ".join([READ, DRAFT, CALENDAR])})
        return original(request)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    state, _ = start(client, student, "calendar_write")
    assert callback(client, student, state).status_code == 303
    row = client.get("/api/v1/connections", headers=student).json()["providers"][0]
    assert row["capabilities"] == {"mail_read": True, "mail_draft": True, "calendar_write": True}
    assert row["email_identity_verified"] is True


def test_microsoft_mail_authorization_resolves_only_signed_in_basic_identity(env, student, oauth):
    client, factory = env
    scopes = ["offline_access", "User.Read", "Mail.Read"]
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "ms-token", "refresh_token": "ms-refresh",
                "expires_in": 3600, "scope": " ".join(scopes)})
        assert request.url.host == "graph.microsoft.com" and request.url.path == "/v1.0/me"
        assert request.url.params["$select"] == "mail,userPrincipalName"
        assert request.headers["Authorization"] == "Bearer ms-token"
        return httpx.Response(200, json={"mail": "owned@example.invalid", "userPrincipalName": "owned@example.invalid"})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    state, query = start(client, student, provider="microsoft")
    assert "https://graph.microsoft.com/User.Read" in query["scope"][0].split()
    response = client.get("/api/v1/connections/microsoft/callback", headers=student,
        params={"state": state, "code": "synthetic-code"}, follow_redirects=False)
    assert response.status_code == 303
    with factory() as db:
        assert connectors.verified_connected_email(db, "account-mei-lin", "microsoft")["email"] == "owned@example.invalid"
    assert len(calls) == 2


def test_mailbox_identity_is_provider_owned_account_scoped_and_relink_bound(env, student, oauth):
    client, factory = env
    with factory() as db:
        assert connectors.verified_connected_email(db, "account-mei-lin") is None
    state, _ = start(client, student)
    assert callback(client, student, state).status_code == 303
    with factory() as db:
        identity = connectors.verified_connected_email(db, "account-mei-lin", "google")
        assert identity["email"] == "mailbox@example.invalid" and identity["provider"] == "google"
        assert connectors.verified_connected_email(db, "account-sam-rivera", "google") is None
        encrypted = db.get(ProviderConnection, identity["connection_id"]).encrypted_tokens
        assert "mailbox@example.invalid" not in encrypted and "secret-access" not in encrypted
    row = client.get("/api/v1/connections", headers=student).json()["providers"][0]
    assert row["email_identity_verified"] is True and row["calendar_write"] is False
    state, _ = start(client, student)
    assert callback(client, student, state).status_code == 303
    with factory() as db:
        relinked = connectors.verified_connected_email(db, "account-mei-lin", "google")
        assert relinked["email"] == identity["email"]
        assert relinked["connection_id"] != identity["connection_id"]
        assert db.get(ProviderConnection, identity["connection_id"]) is None
    client.delete("/api/v1/connections/google", headers=student)
    with factory() as db:
        assert connectors.verified_connected_email(db, "account-mei-lin", "google") is None


def test_untrusted_provider_identity_never_verifies_registration_email(env, student, oauth):
    client, factory = env
    original = oauth["handler"]
    def handler(request):
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "Victim <victim@example.invalid>"})
        return original(request)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    state, _ = start(client, student)
    assert callback(client, student, state).status_code == 303
    with factory() as db:
        assert connectors.verified_connected_email(db, "account-mei-lin") is None
    assert client.get("/api/v1/connections", headers=student).json()["providers"][0]["email_identity_verified"] is False


def test_identity_survives_refresh_but_scope_downgrade_disables_binding(env, student, oauth):
    client, factory = env
    state, _ = start(client, student)
    assert callback(client, student, state).status_code == 303
    with factory() as db:
        identity = connectors.verified_connected_email(db, "account-mei-lin", "google")
        connection = db.get(ProviderConnection, identity["connection_id"])
        tokens = connectors._tokens(connection, connectors.ConnectorSettings())
        tokens["expires_at"] = 0
        connectors._save_tokens(connection, tokens, connectors.ConnectorSettings())
        with HTTPX_CLIENT(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "access_token": "refreshed", "expires_in": 3600, "scope": READ}))) as transport:
            connectors._access_token(connection, transport, connectors.ConnectorSettings())
        assert connectors.verified_connected_email(db, "account-mei-lin", "google") == identity
        connection.scopes = [DRAFT]
        assert connectors.verified_connected_email(db, "account-mei-lin", "google") is None


@pytest.mark.parametrize("provider,calendar_scope", [("google", CALENDAR), ("microsoft", MS_CALENDAR)])
def test_calendar_approval_creates_one_all_day_event_without_invites(env, student, oauth, provider, calendar_scope):
    client, factory = env
    add_connection(factory, oauth, scopes=[calendar_scope], provider=provider)
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer secret-access"
        event = json.loads(request.content)
        assert "attendees" not in event
        if provider == "google":
            assert request.url.path == "/calendar/v3/calendars/primary/events"
            assert request.url.params["sendUpdates"] == "none"
            assert event["start"] == {"date": "2030-02-03"}
            assert event["end"] == {"date": "2030-02-04"}
            assert event["reminders"]["overrides"] == [{"method": "popup", "minutes": 60}]
            assert len(event["id"]) == 64
        else:
            assert request.url.path == "/v1.0/me/events"
            assert event["isAllDay"] is True and event["reminderMinutesBeforeStart"] == 60
            assert event["start"] == {"dateTime": "2030-02-03T00:00:00", "timeZone": "UTC"}
            assert event["end"] == {"dateTime": "2030-02-04T00:00:00", "timeZone": "UTC"}
            assert event["transactionId"]
        return httpx.Response(201, json={"id": "calendar-event-synthetic"})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    item = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {
        "provider": provider, "title": "Synthetic document review", "date": "2030-02-03",
        "description": "Planning only", "reminder_minutes": 60}}).json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    result = client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]})
    assert result.status_code == 200, result.text
    assert result.json()["receipt"]["mode"] == "provider_calendar"
    assert result.json()["receipt"]["external_id"] == "calendar-event-synthetic"
    assert result.json()["receipt"]["attendees_notified"] is False
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert len(calls) == 1
    row = next(x for x in client.get("/api/v1/connections", headers=student).json()["providers"] if x["provider"] == provider)
    assert row["calendar_write"] is True and row["capabilities"]["mail_read"] is False
    assert client.get(f"/api/v1/connections/{provider}/messages", headers=student).status_code == 409


def test_calendar_denial_never_falls_back_to_other_account_or_mail_permission(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[CALENDAR], account_id="account-sam-rivera")
    add_connection(factory, oauth, scopes=[READ, DRAFT])
    item = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {
        "provider": "google", "title": "Synthetic", "date": "2030-02-03"}}).json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert not oauth["calls"]


def test_uncertain_calendar_write_is_terminal_and_not_retried(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth, scopes=[CALENDAR])
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-calendar-response", request=request)
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    item = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {
        "provider": "google", "title": "Synthetic", "date": "2030-02-03"}}).json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    result = client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]})
    assert result.status_code == 502 and "private-calendar-response" not in result.text
    with factory() as db:
        assert db.get(Approval, item["id"]).status == "FAILED_UNCONFIRMED"
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert len(calls) == 1


def test_calendar_refresh_downgrade_stops_before_provider_write(env, student, oauth):
    client, factory = env
    cid = add_connection(factory, oauth, scopes=[CALENDAR])
    with factory() as db:
        connection = db.get(ProviderConnection, cid)
        connectors._save_tokens(connection, {"access_token": "expired", "refresh_token": "refresh", "expires_at": 0},
            connectors.ConnectorSettings())
        db.commit()
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/token")
        return httpx.Response(200, json={"access_token": "read-only", "expires_in": 3600, "scope": READ})
    oauth["monkeypatch"].setattr(connectors.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))
    item = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {
        "provider": "google", "title": "Synthetic", "date": "2030-02-03"}}).json()
    url = "/api/v1/approvals/" + item["id"]
    client.post(url + "/preview", headers=student)
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert len(calls) == 1
