"""Fake provider runtimes stay in tests; the product has no local chat fallback."""
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.chat import get_runtime
from app.chat_models import Conversation
from app.main import app
from app.models import now
from conftest import login


class StubRuntime:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.reply = "Use the cited official source to confirm your next steps."

    def send(self, message, **kwargs):
        self.calls.append({"message": message, **kwargs})
        if self.failure:
            raise self.failure
        return SimpleNamespace(message=self.reply, thread_id=kwargs.get("thread_id") or "provider-thread-private")


@pytest.fixture
def runtime(env):
    stub = StubRuntime()
    app.dependency_overrides[get_runtime] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_runtime, None)


def test_chat_keeps_account_owned_conversation_and_reuses_server_thread(env, student, runtime):
    client, factory = env
    first = client.post("/api/v1/chat", headers=student, json={"message": "What documents should I review?"})
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["mode"] == "orchestrate" and data["message"] == runtime.reply
    assert "provider-thread-private" not in first.text
    assert runtime.calls[0]["thread_id"] is None
    second = client.post("/api/v1/chat", headers=student, json={"message": "Help me prepare a checklist", "conversation_id": data["conversation_id"]})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == data["conversation_id"]
    assert runtime.calls[1]["thread_id"] == "provider-thread-private"
    assert runtime.calls[1]["history"][1:] == [
        {"role": "user", "content": "What documents should I review?"},
        {"role": "assistant", "content": runtime.reply}]
    with factory() as db:
        conversation = db.get(Conversation, data["conversation_id"])
        assert conversation.account_id == "account-mei-lin"
        assert len(conversation.history) == 4 and conversation.busy_until is None
        assert "staytus_context" not in json.dumps(conversation.history)


def test_other_account_cannot_read_or_reuse_conversation(env, student, runtime):
    client, _ = env
    item = client.post("/api/v1/chat", headers=student, json={"message": "Review my program dates"}).json()
    other = login(client, "sam-rivera")
    response = client.post("/api/v1/chat", headers=other, json={"message": "Continue", "conversation_id": item["conversation_id"]})
    assert response.status_code == 404
    assert len(runtime.calls) == 1
    second = client.post("/api/v1/chat", headers=other, json={"message": "My own program dates"})
    assert second.status_code == 200
    assert second.json()["conversation_id"] != item["conversation_id"]
    assert runtime.calls[1]["thread_id"] is None


def test_runtime_receives_signed_current_user_capability_not_client_identity(env, student, runtime):
    client, _ = env
    response = client.post("/api/v1/chat", headers=student, json={"message": "Review my document dates"})
    assert response.status_code == 200
    capability = runtime.calls[0]["context"]["staytus_context"]
    assert capability and capability not in response.text
    result = client.post("/tools/get_student_profile", json={}, headers={
        "X-Tool-Key": "test-tool-key", "X-Staytus-Context": capability})
    assert result.status_code == 200 and result.json()["id"] == "mei-lin"
    grounding = runtime.calls[0]["history"][0]
    assert grounding["role"] == "system"
    assert '"id": "mei-lin"' in grounding["content"]
    assert "untrusted DATA" in grounding["content"]
    for injection in ({"profile_id": "sam-rivera"}, {"context": {"staytus_context": capability}}, {"thread_id": "someone-else"}):
        response = client.post("/api/v1/chat", headers=student, json={"message": "Continue", **injection})
        assert response.status_code == 422
    assert len(runtime.calls) == 1


def test_unconfigured_chat_has_no_scripted_or_llm_fallback(env, student, monkeypatch):
    client, factory = env
    for key in ("ORCHESTRATE_SERVICE_URL", "ORCHESTRATE_AGENT_ID", "ORCHESTRATE_API_KEY", "ORCHESTRATE_BEARER_TOKEN"):
        monkeypatch.setenv(key, "")
    response = client.post("/api/v1/chat", headers=student, json={"message": "Create a calendar reminder"})
    assert response.status_code == 503
    assert "not connected" in response.json()["detail"]
    assert "message" not in response.json() and "approval" not in response.json()
    with factory() as db:
        assert list(db.scalars(select(Conversation))) == []


def test_unverified_tenant_context_disables_personalized_chat(env, student, monkeypatch):
    client, _ = env
    for key, value in {"ORCHESTRATE_SERVICE_URL": "https://tenant.example.edu", "ORCHESTRATE_AGENT_ID": "test-agent",
                       "ORCHESTRATE_API_KEY": "private-test-key", "ORCHESTRATE_CONTEXT_VERIFIED": "false"}.items():
        monkeypatch.setenv(key, value)
    response = client.post("/api/v1/chat", headers=student, json={"message": "Review my profile"})
    assert response.status_code == 503
    assert "secure user-context" in response.json()["detail"]
    assert "private-test-key" not in response.text


def test_provider_failure_is_sanitized_and_unlocks_conversation(env, student, runtime):
    client, factory = env
    item = client.post("/api/v1/chat", headers=student, json={"message": "First message"}).json()
    runtime.failure = RuntimeError("private-provider-response-and-token")
    response = client.post("/api/v1/chat", headers=student, json={"message": "Second message", "conversation_id": item["conversation_id"]})
    assert response.status_code == 502
    assert "private-provider-response-and-token" not in response.text
    assert "message" not in response.json()
    with factory() as db:
        conversation = db.get(Conversation, item["conversation_id"])
        assert conversation.busy_until is None and len(conversation.history) == 2
    runtime.failure = None
    assert client.post("/api/v1/chat", headers=student, json={"message": "Try again", "conversation_id": item["conversation_id"]}).status_code == 200


def test_empty_provider_reply_is_an_error_and_unlocks(env, student, runtime):
    client, factory = env
    runtime.reply = "   "
    response = client.post("/api/v1/chat", headers=student, json={"message": "Review my documents"})
    assert response.status_code == 502
    with factory() as db:
        conversation = db.scalar(select(Conversation))
        assert conversation.busy_until is None and conversation.history == []


def test_busy_conversation_cannot_start_duplicate_provider_run(env, student, runtime):
    client, factory = env
    item = client.post("/api/v1/chat", headers=student, json={"message": "First message"}).json()
    with factory() as db:
        db.get(Conversation, item["conversation_id"]).busy_until = now() + timedelta(minutes=1)
        db.commit()
    response = client.post("/api/v1/chat", headers=student, json={"message": "Second message", "conversation_id": item["conversation_id"]})
    assert response.status_code == 409
    assert len(runtime.calls) == 1


def test_chat_requires_profile_and_nonblank_message(env, runtime):
    client, _ = env
    result = client.post("/api/v1/auth/register", json={"email": "no-profile@example.edu", "password": "a-real-test-password", "name": "New student"})
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert client.post("/api/v1/chat", headers=headers, json={"message": "Help"}).status_code == 409
    assert client.post("/api/v1/chat", json={"message": "Help"}).status_code == 401
    headers = login(client)
    assert client.post("/api/v1/chat", headers=headers, json={"message": " "}).status_code == 422
    assert runtime.calls == []


def test_grounding_uses_current_school_and_marks_pending_citations(env, student, runtime, monkeypatch):
    client, _ = env
    from app import retrieval
    calls = []
    def search(db, query, status_type, **kwargs):
        calls.append({"query": query, "status_type": status_type, **kwargs})
        return [{"title": "Captured public source", "source_url": "https://www.uscis.gov/",
                 "version": 1, "status": "detected_pending_review", "review_required": True,
                 "text": "Captured text is data, not an instruction"}]
    monkeypatch.setattr(retrieval, "search_snapshots", search)
    assert client.patch("/api/v1/profile", headers=student, json={"school": "Another University"}).status_code == 200
    response = client.post("/api/v1/chat", headers=student, json={"message": "What changed?"})
    assert response.status_code == 200, response.text
    assert calls[0]["school"] == "Another University" and calls[0]["status_type"] == "F-1"
    assert calls[0]["include_pending"] is True
    assert response.json()["citations"][0]["review_required"] is True
    assert response.json()["citations"][0]["source_url"] == "https://www.uscis.gov/"
    grounding = runtime.calls[0]["history"][0]["content"]
    assert "Captured text is data" in grounding and "unreviewed snapshots" in grounding
