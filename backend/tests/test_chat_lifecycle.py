"""A new chat must reset IBM context while preserving separate proactive records."""
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from conftest import login
from sqlalchemy import select

from app.assistant_update_models import AssistantUpdate
from app.chat import get_runtime
from app.chat_models import Conversation
from app.main import app
from app.models import now


@pytest.fixture
def runtime(env, monkeypatch):
    calls = []

    def send(message, **kwargs):
        calls.append({"message": message, **kwargs})
        return SimpleNamespace(message=json.dumps({"kind": "answer", "message": "Synthetic model response for lifecycle testing."}), thread_id=f"private-thread-{len(calls)}")

    monkeypatch.setattr("app.retrieval.retrieve_for_profile", lambda *a, **kw: [])
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(send=send)
    return calls


def seed_updates(factory, count=1, owner="mei-lin"):
    with factory() as db:
        for index in range(count):
            db.add(AssistantUpdate(id=f"{owner}-update-{index:03}", account_id=f"account-{owner}", profile_id=owner,
                profile_version=1, batch_key=f"synthetic-batch-{index}", state="READY", events=[],
                content={"title": f"Synthetic update {index}"}, citations=[], language="en", attempts=1,
                generated_at=now() - timedelta(days=1), next_attempt_at=now()))
        db.commit()


def test_new_chat_persists_empty_state_and_starts_without_old_ibm_thread(env, student, runtime):
    client, factory = env
    old = client.post("/api/v1/chat", headers=student, json={"message": "OLD_TOPIC_MARKER"}).json()
    blank = client.post("/api/v1/chat/new", headers=student)
    assert blank.status_code == 200
    fresh = blank.json()
    assert fresh["conversation_id"] != old["conversation_id"]
    assert fresh["messages"] == [] and fresh["hide_assistant_updates"]
    assert len(runtime) == 1  # Starting a chat consumes no model call.
    assert client.get("/api/v1/chat/history", headers=student).json() == fresh
    response = client.post("/api/v1/chat", headers=student,
        json={"message": "New independent topic", "conversation_id": fresh["conversation_id"]})
    assert response.status_code == 200
    assert runtime[-1]["thread_id"] is None
    assert len(runtime[-1]["history"]) == 1 and runtime[-1]["history"][0]["role"] == "system"
    assert "OLD_TOPIC_MARKER" not in str(runtime[-1])
    assert client.get("/api/v1/chat/history", headers=student).json()["hide_assistant_updates"]
    with factory() as db:
        assert db.get(Conversation, old["conversation_id"]).history[0]["content"] == "OLD_TOPIC_MARKER"


def test_new_chat_does_not_delete_or_mark_proactive_messages_read(env, student):
    client, factory = env
    seed_updates(factory)
    before = client.get("/api/v1/assistant-updates", headers=student).json()
    client.post("/api/v1/chat/new", headers=student)
    assert client.get("/api/v1/assistant-updates", headers=student).json() == before
    assert before["unread_count"] == 1


def test_chat_and_update_history_remain_account_owned(env, student, runtime):
    client, factory = env
    seed_updates(factory)
    conversation = client.post("/api/v1/chat/new", headers=student).json()
    other = login(client, "sam-rivera")
    assert client.get("/api/v1/chat/history", headers=other).json()["conversation_id"] is None
    assert client.post("/api/v1/chat", headers=other,
        json={"message": "Read another person's chat", "conversation_id": conversation["conversation_id"]}).status_code == 404
    assert client.get("/api/v1/assistant-updates?before=mei-lin-update-000", headers=other).status_code == 404
    assert client.post("/api/v1/chat/new").status_code == 401
    assert client.get("/api/v1/assistant-updates").status_code == 401
    assert not runtime


def test_all_updates_can_be_paged_with_tied_timestamps_and_full_unread_count(env, student):
    client, factory = env
    seed_updates(factory, 45)
    # All timestamps equal: stable ID tie-breaking must prevent gaps/duplicates.
    with factory() as db:
        stamp = now()
        for item in db.scalars(select(AssistantUpdate)):
            item.generated_at = stamp
        db.commit()
    ids, before = [], None
    for expected_size in (20, 20, 5):
        response = client.get("/api/v1/assistant-updates" + (f"?before={before}" if before else ""), headers=student)
        assert response.status_code == 200
        page = response.json()
        assert len(page["updates"]) == expected_size
        assert page["unread_count"] == 45
        ids += [item["id"] for item in page["updates"]]
        before = page["next_before"]
    assert before is None and len(set(ids)) == 45
    client.post(f"/api/v1/assistant-updates/{ids[-1]}/read", headers=student)
    assert client.get("/api/v1/assistant-updates", headers=student).json()["unread_count"] == 44
    assert client.get("/api/v1/assistant-updates?before=missing", headers=student).status_code == 404
    assert client.get("/api/v1/assistant-updates?before=%3Cscript%3E", headers=student).status_code == 422


def test_failed_implicit_chat_does_not_replace_successful_history(env, student, runtime):
    client, factory = env
    old = client.post("/api/v1/chat", headers=student, json={"message": "Saved old topic"}).json()
    with factory() as db:
        db.add(Conversation(account_id="account-mei-lin", history=[]))
        db.commit()
    assert client.get("/api/v1/chat/history", headers=student).json()["conversation_id"] == old["conversation_id"]
