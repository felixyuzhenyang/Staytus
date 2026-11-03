"""iCloud uses only encrypted app-specific credentials and approved bounded PUTs."""
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.auth import get_current_session
from app.db import get_db
from app.integrations import icloud_calendar as ic
from app.integrations.connection_models import ProviderConnection
from app.models import Profile

REAL_CLIENT = httpx.Client
PASSWORD = "abcd-efgh-ijkl-mnop"
PRINCIPAL = "https://p01-caldav.icloud.com/123/principal/"
HOME = "https://p01-caldav.icloud.com/123/calendars/"


def multistatus(properties, href="/"):
    return (f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            f'<d:response><d:href>{href}</d:href><d:propstat><d:prop>{properties}</d:prop>'
            '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>')


def collection(name="Personal", path="personal", owner=PRINCIPAL, permission="write"):
    return (f'<d:response><d:href>{HOME}{path}/</d:href><d:propstat><d:prop>'
            f'<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>{name}</d:displayname>'
            f'<d:owner><d:href>{owner}</d:href></d:owner><d:current-user-privilege-set>'
            f'<d:privilege><d:{permission}/></d:privilege></d:current-user-privilege-set>'
            '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
            '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')


@pytest.fixture
def cloud(env, monkeypatch):
    _, factory = env
    key = Fernet.generate_key().decode()
    calls, state = [], {"many": False, "failure": None}

    def handler(request):
        calls.append(request)
        if state.get("on_request"):
            state["on_request"](request)
        if request.method == "PUT":
            if state["failure"] == "timeout":
                raise httpx.ReadTimeout("synthetic timeout")
            return httpx.Response(state.get("put_status", 201))
        if state["failure"] == "redirect":
            return httpx.Response(301, headers={"location": "https://evil.example/principal"})
        if state["failure"] == "doctype":
            return httpx.Response(207, content=b'<!DOCTYPE x [<!ENTITY q "secret">]><x/>')
        if state["failure"] == "denied":
            return httpx.Response(401)
        if str(request.url) == ic.BASE:
            return httpx.Response(207, text=multistatus(f'<d:current-user-principal><d:href>{PRINCIPAL}</d:href></d:current-user-principal>'))
        if str(request.url) == PRINCIPAL:
            return httpx.Response(207, text=multistatus(f'<c:calendar-home-set><d:href>{HOME}</d:href></c:calendar-home-set>'))
        if str(request.url) == HOME:
            rows = collection() + collection("Read only", "read-only", permission="read") + collection("Shared", "shared", owner="https://p01-caldav.icloud.com/other/principal/")
            if state["many"]:
                rows += collection("Work", "work")
            return httpx.Response(207, text=f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">{rows}</d:multistatus>')
        raise AssertionError("Unexpected provider destination")

    monkeypatch.setattr(ic, "ConnectorSettings", lambda: SimpleNamespace(connector_token_key=key))
    app = FastAPI()
    app.include_router(ic.router)
    owner = {"id": "account-mei-lin"}
    app.dependency_overrides[get_current_session] = lambda: SimpleNamespace(account_id=owner["id"])

    def database():
        with factory() as db:
            yield db
            db.commit()

    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    monkeypatch.setattr(ic.httpx, "Client", lambda **kwargs: REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    return client, factory, calls, state, owner, key


def link(client):
    response = client.post("/api/v1/connections/icloud/link", json={"apple_id": "synthetic@example.invalid", "app_specific_password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def approval(db):
    profile = db.get(Profile, "mei-lin")
    return profile, SimpleNamespace(id="icloud-approved", kind="calendar", status="EXECUTING", profile_id=profile.id,
        payload={"provider": "icloud", "title": "准备文件", "date": "2030-01-02", "description": "Synthetic\nEND:VEVENT", "reminder_minutes": 1440,
                 "_connector_target": ic.approval_connector_target(db, profile)})


def test_link_encrypts_secret_lists_only_owned_writable_calendars(cloud):
    client, factory, calls, _, _, key = cloud
    result = link(client)
    assert len(result["calendars"]) == 1 and result["calendar_write"]
    assert result["capabilities"] == {"mail_read": False, "mail_draft": False, "calendar_write": True}
    assert PASSWORD not in json.dumps(result) and "principal_url" not in json.dumps(result)
    with factory() as db:
        connection = db.scalar(select(ProviderConnection).where(ProviderConnection.provider == "icloud"))
        assert PASSWORD not in connection.encrypted_tokens
        assert json.loads(Fernet(key.encode()).decrypt(connection.encrypted_tokens.encode()))["app_specific_password"] == PASSWORD
    assert len(calls) == 3 and all(request.method == "PROPFIND" for request in calls)


@pytest.mark.parametrize("password", ["PRIMARY-secret-password", "my-primary-unsafe-secret", 123456])
def test_primary_password_rejected_without_credential_echo_or_network(cloud, password):
    client, _, calls, *_ = cloud
    response = client.post("/api/v1/connections/icloud/link", json={"apple_id": "synthetic@example.invalid", "app_specific_password": password})
    assert response.status_code == 422 and str(password) not in response.text
    assert not calls


def test_invalid_body_never_echoes_extra_or_nested_credentials(cloud):
    client, _, calls, *_ = cloud
    secret = "arbitrary-primary-secret"
    for body in ({"apple_id": "synthetic@example.invalid", "app_specific_password": PASSWORD, "primary_password": secret},
                 [{"password": secret}]):
        response = client.post("/api/v1/connections/icloud/link", json=body)
        assert response.status_code == 422 and secret not in response.text
    assert not calls


@pytest.mark.parametrize("location", ["http://caldav.icloud.com/", "https://evil.example/", "https://caldav.icloud.com.evil.example/", "https://p01-caldav.icloud.com:8443/", "https://a:b@caldav.icloud.com/", "https://caldav.icloud.com/x?token=1", "https://caldav.icloud.com/%2e%2e/x"])
def test_discovery_target_gate(location):
    with pytest.raises(ValueError):
        ic._url(location)


@pytest.mark.parametrize("failure,status", [("redirect", 502), ("doctype", 502), ("denied", 409)])
def test_untrusted_discovery_cannot_link_or_forward_auth(cloud, failure, status):
    client, factory, calls, state, *_ = cloud
    state["failure"] = failure
    response = client.post("/api/v1/connections/icloud/link", json={"apple_id": "synthetic@example.invalid", "app_specific_password": PASSWORD})
    assert response.status_code == status and PASSWORD not in response.text
    assert len(calls) == 1
    with factory() as db:
        assert not db.scalar(select(ProviderConnection).where(ProviderConnection.provider == "icloud"))


def test_cross_account_status_and_selection_do_not_disclose_or_change(cloud):
    client, _, _, _, owner, _ = cloud
    result = link(client)
    owner["id"] = "account-aarav-shah"
    other = client.get("/api/v1/connections/icloud").json()
    assert not other["connected"] and not other["calendars"] and other["account_label"] is None
    response = client.patch("/api/v1/connections/icloud/calendar", json={"calendar_id": result["selected_calendar_id"]})
    assert response.status_code == 409


def test_multiple_calendars_require_selection_and_reselection_invalidates_target(cloud):
    client, factory, _, state, *_ = cloud
    state["many"] = True
    result = link(client)
    assert not result["calendar_write"] and result["selected_calendar_id"] is None
    response = client.patch("/api/v1/connections/icloud/calendar", json={"calendar_id": result["calendars"][0]["id"]})
    assert response.status_code == 200 and response.json()["calendar_write"]
    with factory() as db:
        profile, item = approval(db)
    assert client.patch("/api/v1/connections/icloud/calendar", json={"calendar_id": result["calendars"][1]["id"]}).status_code == 200
    with factory() as db:
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 409


def test_approved_event_write_is_single_conditional_put_without_invites(cloud):
    client, factory, calls, *_ = cloud
    link(client)
    with factory() as db:
        profile, item = approval(db)
        result = ic.execute_calendar(db, item, profile)
    puts = [request for request in calls if request.method == "PUT"]
    assert len(puts) == 1 and puts[0].headers["if-none-match"] == "*"
    text = puts[0].content.decode()
    assert text.count("\r\nBEGIN:VEVENT\r\n") == 1 and "ATTENDEE" not in text
    assert "TRIGGER:-PT1440M" in text and result["provider"] == "icloud" and not result["attendees_notified"]


def test_uncertain_put_is_not_retried(cloud):
    client, factory, calls, state, *_ = cloud
    link(client)
    state["failure"] = "timeout"
    with factory() as db:
        profile, item = approval(db)
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 502
    assert sum(request.method == "PUT" for request in calls) == 1


def test_unapproved_and_relinked_targets_never_write(cloud):
    client, factory, calls, *_ = cloud
    link(client)
    with factory() as db:
        profile, item = approval(db)
        item.status = "PROPOSED"
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 409
        item.status = "EXECUTING"
    link(client)
    with factory() as db:
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 409
    assert not any(request.method == "PUT" for request in calls)


def test_disconnect_removes_only_current_users_credential(cloud):
    client, factory, _, _, owner, _ = cloud
    link(client)
    owner["id"] = "account-aarav-shah"
    assert client.delete("/api/v1/connections/icloud").status_code == 200
    owner["id"] = "account-mei-lin"
    assert client.get("/api/v1/connections/icloud").json()["connected"]
    assert client.delete("/api/v1/connections/icloud").status_code == 200
    with factory() as db:
        assert not db.scalar(select(ProviderConnection).where(ProviderConnection.provider == "icloud"))


def fake_clock(monkeypatch):
    stamp = [0.0]
    monkeypatch.setattr(ic, "time", SimpleNamespace(monotonic=lambda: stamp[0]))
    return stamp


def test_link_shares_one_budget_and_leaves_existing_binding_intact(cloud, monkeypatch):
    client, factory, calls, state, *_ = cloud
    link(client)
    old_id = client.get("/api/v1/connections/icloud").json()["connection_id"]
    calls.clear()
    stamp = fake_clock(monkeypatch)
    state["on_request"] = lambda _: stamp.__setitem__(0, stamp[0] + 11)
    response = client.post("/api/v1/connections/icloud/link", json={"apple_id": "synthetic@example.invalid", "app_specific_password": PASSWORD})
    assert response.status_code == 409 and "timed out" in response.text
    assert len(calls) == 3 and not any(request.method == "PUT" for request in calls)
    with factory() as db:
        assert db.get(ProviderConnection, old_id) is not None


def test_approval_discovery_budget_exhaustion_is_safe_and_never_starts_put(cloud, monkeypatch):
    client, factory, calls, state, *_ = cloud
    link(client)
    calls.clear()
    stamp = fake_clock(monkeypatch)
    state["on_request"] = lambda _: stamp.__setitem__(0, stamp[0] + 11)
    with factory() as db:
        profile, item = approval(db)
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 409 and "before any calendar change" in failure.value.detail
    assert len(calls) == 3 and not any(request.method == "PUT" for request in calls)


def test_shared_budget_expiring_after_put_remains_uncertain_and_never_retries(cloud, monkeypatch):
    client, factory, calls, state, *_ = cloud
    link(client)
    calls.clear()
    stamp = fake_clock(monkeypatch)

    def advance(request):
        stamp[0] += 28 if request.method == "PUT" else 1

    state["on_request"] = advance
    with factory() as db:
        profile, item = approval(db)
        with pytest.raises(HTTPException) as failure:
            ic.execute_calendar(db, item, profile)
        assert failure.value.status_code == 502
    assert len(calls) == 4 and sum(request.method == "PUT" for request in calls) == 1


def test_stream_trickle_and_redirects_share_the_same_deadline(monkeypatch):
    stamp = fake_clock(monkeypatch)
    calls = []

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in (b"<d", b":multistatus/>"):
                stamp[0] += 3
                yield chunk

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            stamp[0] += 27
            return httpx.Response(301, headers={"location": PRINCIPAL})
        assert request.extensions["timeout"]["read"] == 0.75
        return httpx.Response(207, stream=SlowStream())

    with REAL_CLIENT(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.TimeoutException):
            ic._request(client, "PROPFIND", ic.BASE, deadline=30)
    assert len(calls) == 2
