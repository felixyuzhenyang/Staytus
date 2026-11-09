"""Synthetic tests: mailbox monitoring never calls a real mail service."""
from datetime import datetime, timedelta
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import mail_monitor as m
from app.integrations import connectors
from app.integrations.connection_models import MailAgentPermission, ProviderConnection
from app.auth import digest
from app.db import Base, get_db
from database_support import isolated_engine
from app.mail_monitor_models import MailMonitorPreference, MailMonitorSeen
from app.mail_analysis_models import MailMessageAnalysis
from app.models import Account, AuthSession, Profile, now
from app.notification_models import ReminderNotice
from test_connectors import oauth as connector_oauth, add_connection, HTTPX_CLIENT

oauth = connector_oauth

STAMP = datetime(2026, 11, 3, 12)


@pytest.fixture
def store(tmp_path, monkeypatch, request):
    engine = isolated_engine(tmp_path, "monitor", request)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        for name in ("a", "b"):
            db.add(Account(id=name, email=f"{name}@example.invalid", name=f"Synthetic{name}", password_hash="unusable"))
            db.flush()
            db.add(Profile(id="p"+name, account_id=name, name=f"Synthetic{name}", status_type="F-1",
                program_start=STAMP.date()-timedelta(days=100), program_end=STAMP.date()+timedelta(days=100), synthetic=True))
            db.flush()
            db.add(AuthSession(account_id=name, profile_id="p"+name, token_hash=digest("token-"+name),
                role="student", expires_at=now()+timedelta(days=1)))
        db.commit()
    identities = {name: {"email": f"verified-{name}@example.invalid", "provider": "google", "connection_id": "c-"+name}
        for name in ("a", "b")}
    monkeypatch.setattr(m, "_identity", lambda db, account_id, provider: identities.get(account_id) if provider=="google" else None)
    monkeypatch.setattr(m, "now", lambda: STAMP)
    yield factory, identities
    engine.dispose()


@pytest.fixture
def api(store):
    factory, _ = store
    app = FastAPI()
    app.include_router(m.router)
    def dependency():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        yield client


def headers(name="a"):
    return {"Authorization": "Bearer token-"+name}


def enable(factory, who="a", stamp=STAMP):
    with factory() as db:
        row=m.preference(db,who,"google")
        row.enabled, row.connection_id = True,"c-"+who
        row.next_check_at=stamp-timedelta(seconds=1)
        db.commit()


def reader(db, account_id, provider, **kwargs):
    assert provider=="google" and kwargs=={"limit":20,"for_agent":False,"inbox_only":True}
    return {"messages":[{"id":"private-message-id", "subject":"Synthetic ISSS reminder", "snippet":"Private body preview never persisted"}]}


def test_default_off_and_account_owned_state(api):
    value=api.get("/api/v1/mail-monitor/google",headers=headers()).json()
    assert value["enabled"] is False and value["connected"] is True
    assert value["mailbox"]=="verified-a@example.invalid"
    assert value["message_bodies_stored"] is False and value["model_sharing_enabled_by_monitor"] is False
    assert api.get("/api/v1/mail-monitor/google").status_code==401
    assert api.get("/api/v1/mail-monitor/google",headers=headers("b")).json()["mailbox"]=="verified-b@example.invalid"


def test_enable_requires_verified_link_and_strict_settings(api):
    assert api.patch("/api/v1/mail-monitor/microsoft",headers=headers(),json={"enabled":True}).status_code==409
    assert api.patch("/api/v1/mail-monitor/google",headers=headers(),json={"enabled":True,"account_id":"b"}).status_code==422
    assert api.patch("/api/v1/mail-monitor/google",headers=headers(),json={"enabled":True,"timezone":"Invalid/zone"}).status_code==422
    assert api.patch("/api/v1/mail-monitor/google",headers=headers(),json={"enabled":True,"check_hour":24}).status_code==422
    value=api.patch("/api/v1/mail-monitor/google",headers=headers(),json={"enabled":True,"timezone":"America/New_York","check_hour":9}).json()
    assert value["enabled"] and value["consent_current"] and value["next_check_at"]=="2026-11-03T14:00:00Z"
    disabled=api.patch("/api/v1/mail-monitor/google",headers=headers(),json={"enabled":False}).json()
    assert disabled["enabled"] is False and disabled["next_check_at"] is None


def test_no_background_read_without_optin(store):
    factory,_=store
    def forbidden(*args,**kwargs):
        pytest.fail("Reader must not run")
    assert m.run_mail_monitor_once(factory,stamp=STAMP,reader=forbidden)["checked"]==0


def test_manual_read_with_background_off_is_explicit_and_bounded(api,store,monkeypatch):
    factory,_=store
    monkeypatch.setattr(m,"read_recent_messages",reader)
    value=api.post("/api/v1/mail-monitor/google/check",headers=headers()).json()
    assert value["new_relevant_count"]==1 and len(value["messages"])==1 and value["untrusted_content"]
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        assert row.enabled is False and row.next_check_at is None
        notice=db.scalar(select(ReminderNotice))
        assert notice.account_id=="a" and notice.profile_id=="pa" and notice.data["policy_authority"] is False
        persisted=json.dumps({"title":notice.title,"message":notice.message,"data":notice.data})
        assert "Private body" not in persisted and "private-message-id" not in persisted and "Synthetic ISSS" not in persisted
        assert len(db.scalar(select(MailMonitorSeen)).message_hash)==64
    assert api.post("/api/v1/mail-monitor/google/check",headers=headers()).status_code==429


def test_daily_read_deduplicates_and_isolates(store):
    factory,_=store
    enable(factory)
    one=m.run_mail_monitor_once(factory,stamp=STAMP,reader=reader)
    assert one=={"checked":1,"failed":0,"new_relevant_count":1}
    assert m.run_mail_monitor_once(factory,stamp=STAMP+timedelta(minutes=1),reader=reader)["checked"]==0
    two=m.run_mail_monitor_once(factory,stamp=STAMP+timedelta(days=1),reader=reader)
    assert two["new_relevant_count"]==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReminderNotice))==1
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen))==1
        assert db.get(MailMonitorPreference,("b","google")) is None


def test_daily_read_generates_private_summary_only_with_separate_content_consent(store, monkeypatch):
    factory, identities = store
    enable(factory)
    with factory() as db:
        db.add(ProviderConnection(id="c-a", account_id="a", provider="google", encrypted_tokens="unused", scopes=[]))
        db.add(MailAgentPermission(account_id="a", provider="google", enabled=False,
            content_analysis_enabled=True, updated_at=STAMP))
        db.commit()
    identities["a"]["connection_id"] = "c-a"
    calls = []
    def analyze(db, account_id, profile, provider, **kwargs):
        calls.append((account_id, profile.id, provider, kwargs["previews"]))
        assert kwargs["consent_check"](db) is True
        return [{"id": "encrypted-summary-record"}]
    monkeypatch.setattr("app.mail_analysis.analyze_matching_messages", analyze)
    result = m.run_mail_monitor_once(factory, stamp=STAMP, reader=reader)
    assert result == {"checked": 1, "failed": 0, "new_relevant_count": 1}
    assert calls and calls[0][:3] == ("a", "pa", "google")
    with factory() as db:
        checked = m.check_mailbox(db, "a", "google", stamp=STAMP + timedelta(minutes=5), reader=lambda *a, **k: {"messages": []})
        assert "authorized to share matching body text" not in checked["notice"]
    with factory() as db:
        notice = db.scalar(select(ReminderNotice))
        assert notice.data["analysis_count"] == 1 and "private AI summary" in notice.message


def test_content_analysis_batches_leave_later_messages_for_the_next_check(store, monkeypatch):
    factory, identities = store
    enable(factory)
    with factory() as db:
        db.add(ProviderConnection(id="c-a", account_id="a", provider="google", encrypted_tokens="unused", scopes=[]))
        db.add(MailAgentPermission(account_id="a", provider="google", content_analysis_enabled=True))
        db.commit()
    identities["a"]["connection_id"] = "c-a"
    messages = [{"id": f"message-{index}", "subject": "Synthetic ISSS reminder"} for index in range(7)]
    def many(*args, **kwargs):
        return {"messages": messages}
    def analyze(db, account_id, profile, provider, **kwargs):
        assert kwargs["consent_check"](db) is True
        return [{"id": f"summary-{item['id']}"} for item in kwargs["previews"]]
    monkeypatch.setattr("app.mail_analysis.analyze_matching_messages", analyze)
    assert m.run_mail_monitor_once(factory, stamp=STAMP, reader=many)["new_relevant_count"] == 7
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen)) == 5
    assert m.run_mail_monitor_once(factory, stamp=STAMP + timedelta(days=1), reader=many)["new_relevant_count"] == 2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen)) == 7


def test_transient_analysis_failure_reuses_notice_without_poisoning_retry(store, monkeypatch):
    factory, identities = store
    enable(factory)
    with factory() as db:
        db.add(ProviderConnection(id="c-a", account_id="a", provider="google", encrypted_tokens="unused", scopes=[]))
        db.add(MailAgentPermission(account_id="a", provider="google", content_analysis_enabled=True))
        db.commit()
    identities["a"]["connection_id"] = "c-a"
    attempts = []
    def analyze(db, account_id, profile, provider, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise HTTPException(502, "synthetic temporary model failure")
        return [{"id": "summary-ready"}]
    monkeypatch.setattr("app.mail_analysis.analyze_matching_messages", analyze)
    assert m.run_mail_monitor_once(factory, stamp=STAMP, reader=reader) == {
        "checked": 1, "failed": 0, "new_relevant_count": 1}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReminderNotice)) == 1
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen)) == 0
    assert m.run_mail_monitor_once(factory, stamp=STAMP + timedelta(days=1), reader=reader) == {
        "checked": 1, "failed": 0, "new_relevant_count": 1}
    with factory() as db:
        notice = db.scalar(select(ReminderNotice))
        assert db.scalar(select(func.count()).select_from(ReminderNotice)) == 1
        assert notice.data["analysis_count"] == 1 and notice.read_at is None
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen)) == 1


def test_daily_job_physically_deletes_expired_encrypted_summaries(store):
    factory, _ = store
    with factory() as db:
        db.add(ProviderConnection(id="expired-connection", account_id="a", provider="google",
            encrypted_tokens="unused", scopes=[]))
        db.add(MailMessageAnalysis(account_id="a", profile_id="pa", profile_version=1,
            provider="google", connection_id="expired-connection", message_hash="b" * 64,
            encrypted_result="synthetic-encrypted-value", model_id="synthetic-model",
            generated_at=STAMP - timedelta(days=91), expires_at=STAMP - timedelta(seconds=1)))
        db.commit()
    assert m.run_mail_monitor_once(factory, stamp=STAMP, reader=reader)["checked"] == 0
    with factory() as db:
        assert db.scalar(select(MailMessageAnalysis)) is None


@pytest.mark.parametrize("mode",["relink","disconnect"])
def test_connection_change_stops_background_before_read(store,mode):
    factory,identities=store
    enable(factory)
    if mode=="relink": identities["a"]={**identities["a"],"connection_id":"new-link"}
    else: identities.pop("a")
    def forbidden(*args,**kwargs): pytest.fail("Stale binding must not read")
    assert m.run_mail_monitor_once(factory,stamp=STAMP,reader=forbidden)["checked"]==0
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        assert not row.enabled and row.next_check_at is None


def test_manual_after_relink_never_reenables_background(store):
    factory,identities=store
    enable(factory)
    identities["a"]={**identities["a"],"connection_id":"new-link"}
    with factory() as db:
        assert m.check_mailbox(db,"a","google",stamp=STAMP,reader=reader)["new_relevant_count"]==1
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        assert not row.enabled and row.connection_id=="new-link"


def test_revocation_during_provider_request_discards_results(store):
    factory,_=store
    enable(factory)
    def revoke(db,account_id,provider,**kwargs):
        with factory() as other:
            row=other.get(MailMonitorPreference,(account_id,provider))
            row.enabled=False
            row.revision+=1
            other.commit()
        return reader(db,account_id,provider,**kwargs)
    value=m.run_mail_monitor_once(factory,stamp=STAMP,reader=revoke)
    assert value["failed"]==1 and value["checked"]==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReminderNotice))==0
        assert db.scalar(select(func.count()).select_from(MailMonitorSeen))==0


def test_relink_during_provider_request_discards_results(store):
    factory,identities=store
    enable(factory)
    def relink(db,account_id,provider,**kwargs):
        identities["a"]={**identities["a"],"connection_id":"replacement"}
        return reader(db,account_id,provider,**kwargs)
    assert m.run_mail_monitor_once(factory,stamp=STAMP,reader=relink)["failed"]==1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReminderNotice))==0


@pytest.mark.parametrize("status",[401,403,409])
def test_reauth_errors_disable_with_safe_details(store,status):
    factory,_=store
    enable(factory)
    def fail(*args,**kwargs): raise HTTPException(status,"private bearer-token must never leave")
    assert m.run_mail_monitor_once(factory,stamp=STAMP,reader=fail)["failed"]==1
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        assert not row.enabled and row.last_error_code=="mailbox_reauthorization_required"
        assert "bearer" not in row.last_error_code


def test_transient_failure_backs_off_without_repeat_within_hour(store):
    factory,_=store
    enable(factory)
    def fail(*args,**kwargs): raise HTTPException(502,"private token")
    m.run_mail_monitor_once(factory,stamp=STAMP,reader=fail)
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        assert row.enabled and row.next_check_at==STAMP+timedelta(hours=1) and row.failure_count==1
    assert m.run_mail_monitor_once(factory,stamp=STAMP+timedelta(minutes=30),reader=fail)["failed"]==0


def test_active_lease_prevents_duplicate_read(store):
    factory,_=store
    enable(factory)
    with factory() as db:
        row=db.get(MailMonitorPreference,("a","google"))
        row.lease_token="other-worker"
        row.lease_until=STAMP+timedelta(minutes=1)
        db.commit()
    def forbidden(*args,**kwargs): pytest.fail("Lease already held")
    assert m.run_mail_monitor_once(factory,stamp=STAMP,reader=forbidden)["checked"]==0


def test_daily_timezone_and_dst_schedule():
    assert m.next_daily_check(datetime(2026,3,7,15),"America/New_York",9)==datetime(2026,3,8,13)
    assert m.next_daily_check(datetime(2026,10,31,14),"America/New_York",9)==datetime(2026,11,1,14)
    assert m.next_daily_check(datetime(2026,11,3,14),"America/New_York",9)==datetime(2026,11,4,14)


@pytest.mark.parametrize("provider",["google","microsoft"])
def test_monitor_provider_transport_selects_only_inbox(env,student,oauth,provider):
    _,factory=env
    add_connection(factory,oauth,provider=provider,
        scopes=None if provider=="google" else ["Mail.Read","User.Read"])
    calls=[]
    def transport(request):
        calls.append(request)
        assert request.method=="GET"
        if provider=="google":
            assert request.url.path=="/gmail/v1/users/me/messages"
            assert request.url.params["q"].startswith("in:inbox newer_than:30d ")
            assert request.url.params["maxResults"]=="20"
            return httpx.Response(200,json={"messages":[]})
        assert request.url.path=="/v1.0/me/mailFolders/inbox/messages"
        assert request.url.params["$top"]=="50"
        assert "receivedDateTime ge " in request.url.params["$filter"]
        return httpx.Response(200,json={"value":[]})
    oauth["monkeypatch"].setattr(connectors.httpx,"Client",lambda **kwargs:HTTPX_CLIENT(
        transport=httpx.MockTransport(transport),**kwargs))
    with factory() as db:
        assert connectors.read_recent_messages(db,"account-mei-lin",provider,inbox_only=True)["messages"]==[]
    assert len(calls)==1
