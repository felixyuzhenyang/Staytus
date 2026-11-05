"""Offline generation must be model-backed, durable, deduplicated and private."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import login
from sqlalchemy import select

from app.assistant_update_models import AssistantUpdate, AssistantUpdateEvent
from app.assistant_updates import queue_updates, run_assistant_once
from app.chat import _grounding
from app.models import AuthSession, Profile, now
from app.notification_models import ReminderNotice
from app.notifications import preferences_for


class Model:
    config = SimpleNamespace(generation_model="synthetic-model-test-only")

    def __init__(self):
        self.calls = []
        self.callback = None
        self.fail = False

    def generate_assistant_update(self, context):
        self.calls.append(context)
        if self.callback:
            self.callback()
        if self.fail:
            raise RuntimeError("do-not-log-private-provider-secret")
        if context.get("language") == "zh":
            return {"title": "旅行准备提醒", "summary": "您保存的旅行资料核对准备日期即将到来，请确认相关日期。",
                "why_it_matters": "请根据个人情况与国际学生顾问核对适用的材料和流程。",
                "next_steps": ["联系顾问核对材料。"], "questions": []}
        return {"title": "Your travel preparation is approaching", "summary": "Your saved travel review target is approaching.",
            "why_it_matters": "As an F-1 student, confirm your documents and planned return with ISSS.",
            "next_steps": ["Review the saved dates with your adviser."], "questions": ["When do you intend to return?"]}


@pytest.fixture
def ready(env, monkeypatch):
    client, factory = env
    stamp = now()
    monkeypatch.setattr("app.retrieval.retrieve_for_profile", lambda *args, **kwargs: [])
    with factory() as db:
        profile = db.get(Profile, "mei-lin")
        profile.travel_date = stamp.date() + timedelta(days=33)
        profile.notification_frequency = "daily"
        pref = preferences_for(db, profile.account_id)
        pref.assistant_enabled = True
        db.commit()
    return client, factory, stamp, Model()


def run(ready, **kwargs):
    _, factory, stamp, model = ready
    return run_assistant_once(factory, provider=model, stamp=stamp, account_id="account-mei-lin", **kwargs)


def test_event_creates_model_message_without_user_question_and_deduplicates(ready, student):
    client, factory, stamp, model = ready
    assert run(ready)["generated"] == 1
    assert len(model.calls) == 1
    context = model.calls[0]
    assert context["profile"]["status_type"] == "F-1"
    assert context["profile"]["program_document"] == "I-20"
    assert "email" not in context["profile"] and "id" not in context["profile"]
    assert context["events"][0]["kind"] == "planning"
    history = client.get("/api/v1/chat/history", headers=student).json()
    assert history["messages"] == []  # No fictional user turn or provider thread.
    updates = client.get("/api/v1/assistant-updates", headers=student).json()["updates"]
    assert len(updates) == 1 and updates[0]["generated_by"] == "watsonx.ai"
    assert updates[0]["content"]["title"] == "Your travel preparation is approaching"
    assert run(ready)["generated"] == 0 and len(model.calls) == 1
    assert run_assistant_once(factory, provider=model, stamp=stamp + timedelta(days=1), account_id="account-mei-lin")["generated"] == 0
    with factory() as db:
        assert len(list(db.scalars(select(AssistantUpdateEvent)))) == 1


def test_read_and_preferences_are_owned(ready, student):
    client, _, _, _ = ready
    run(ready)
    item = client.get("/api/v1/assistant-updates", headers=student).json()["updates"][0]
    other = login(client, "sam-rivera")
    assert client.get("/api/v1/assistant-updates", headers=other).json()["updates"] == []
    assert client.post(f"/api/v1/assistant-updates/{item['id']}/read", headers=other).status_code == 404
    first = client.post(f"/api/v1/assistant-updates/{item['id']}/read", headers=student).json()
    second = client.post(f"/api/v1/assistant-updates/{item['id']}/read", headers=student).json()
    assert first["read_at"] == second["read_at"]
    assert client.get("/api/v1/assistant-updates").status_code == 401
    response = client.patch("/api/v1/assistant-updates/preferences", headers=student, json={"enabled": True, "language": "zh"})
    assert response.status_code == 200 and response.json()["language"] == "zh"
    assert client.patch("/api/v1/assistant-updates/preferences", headers=student, json={"enabled": True, "language": "zh", "account_id": "other"}).status_code == 422


@pytest.mark.parametrize("mode", ["disabled", "frequency_off", "no_event", "mail_only"])
def test_no_model_call_when_no_eligible_event(ready, mode):
    _, factory, stamp, model = ready
    with factory() as db:
        profile = db.get(Profile, "mei-lin")
        if mode == "disabled":
            preferences_for(db, profile.account_id).assistant_enabled = False
        elif mode == "frequency_off":
            profile.notification_frequency = "off"
        else:
            profile.travel_date = None
            if mode == "mail_only":
                db.add(ReminderNotice(account_id=profile.account_id, profile_id=profile.id, dedup_key="private-mail",
                    kind="mail_monitor", title="Private inbox", message="DO NOT SEND MAIL TO MODEL", data={"snippet": "PRIVATE"}, created_at=stamp))
        db.commit()
    assert run(ready)["generated"] == 0 and not model.calls


def test_failed_generation_has_retry_budget_and_no_template_fallback(ready, student):
    client, factory, stamp, model = ready
    model.fail = True
    assert run(ready)["failed"] == 1
    assert run(ready)["failed"] == 0  # Backoff.
    for hours in (7, 14):
        run_assistant_once(factory, provider=model, stamp=stamp + timedelta(hours=hours), account_id="account-mei-lin")
    with factory() as db:
        row = db.scalar(select(AssistantUpdate))
        assert row.state == "FAILED" and row.attempts == 3
        assert "secret" not in (row.error_code or "") and row.content == {}
    assert client.get("/api/v1/assistant-updates", headers=student).json()["updates"] == []


@pytest.mark.parametrize("change", ["profile", "disable", "supersede", "language", "lease"])
def test_changes_during_generation_do_not_publish_old_result(ready, change):
    _, factory, _, model = ready
    def alter():
        with factory() as db:
            profile = db.get(Profile, "mei-lin")
            if change == "profile":
                profile.version += 1
            elif change == "disable":
                preferences_for(db, profile.account_id).assistant_enabled = False
            elif change == "language":
                preferences_for(db, profile.account_id).assistant_language = "zh"
            elif change == "lease":
                db.scalar(select(AssistantUpdate)).lease_token = "new-worker-token"
            else:
                db.scalar(select(ReminderNotice).where(ReminderNotice.kind == "planning")).superseded_at = now()
            db.commit()
    model.callback = alter
    result = run(ready)
    assert result["generated"] == 0
    with factory() as db:
        assert db.scalar(select(AssistantUpdate)).state != "READY"


def test_expired_final_lease_is_not_retried_forever(ready):
    _, factory, stamp, model = ready
    with factory() as db:
        queue_updates(db, stamp=stamp, account_id="account-mei-lin")
        row = db.scalar(select(AssistantUpdate))
        row.state, row.attempts, row.claimed_at = "GENERATING", 3, stamp - timedelta(minutes=11)
        db.commit()
    run(ready)
    assert not model.calls
    with factory() as db:
        assert db.scalar(select(AssistantUpdate)).state == "FAILED"


def test_followup_grounding_includes_saved_proactive_message(ready, student):
    _, factory, _, _ = ready
    run(ready)
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.account_id == "account-mei-lin"))
        grounding, _, _, context = _grounding(db, session, "Explain your update")
        assert context["recent_assistant_updates"][0]["content"]["title"] == "Your travel preparation is approaching"
        assert "background messages" in grounding["content"]


def test_policy_change_compares_actual_versions_and_preserves_review_state(ready):
    from app.ingestion import store_candidate
    from app.models import PolicySource
    _, factory, _, model = ready
    with factory() as db:
        db.get(Profile, "mei-lin").travel_date = None
        source = db.get(PolicySource, "penn-isss")
        old = store_candidate(db, source, "Previous official office text: contact the adviser.", categories=["F-1"])
        new = store_candidate(db, source, "Updated official office text: review the revised checklist with the adviser.", categories=["F-1"])
        db.commit()
    # Source event was created just after the test stamp.
    ready = (ready[0], factory, now() + timedelta(seconds=1), model)
    assert run(ready)["generated"] == 1
    context = model.calls[0]
    evidence = context["official_evidence"][-1]
    assert "Previous official" in evidence["previous_excerpt"]
    assert "Updated official" in evidence["current_excerpt"]
    assert evidence["review_required"] and evidence["status"] == "detected_pending_review"
    assert context["events"][0]["data"]["policy_version_id"] == new["policy_version_id"]
    assert context["events"][0]["data"]["previous_version_id"] == old["policy_version_id"]


def test_schema_migration_preserves_existing_preferences(tmp_path):
    from alembic import command
    from sqlalchemy import MetaData, text

    from app.database_migrations import migration_config, schema_differences, upgrade_database
    from app.db import make_engine
    engine = make_engine(f"sqlite:///{tmp_path}/previous.db")
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "20261103_0002")
        old = MetaData()
        old.reflect(connection)
        connection.execute(old.tables["accounts"].insert().values(id="existing", email="existing@example.invalid",
            name="Synthetic existing account", password_hash="test-only", role="student", created_at=now()))
        connection.execute(old.tables["notification_preferences"].insert().values(account_id="existing", in_app_enabled=True,
            popup_enabled=False, email_enabled=False, timezone="America/New_York", digest_hour=8, digest_weekday=2,
            digest_monthday=12, scheduled_frequency="weekly", lead_days=9, updated_at=now()))
    upgrade_database(engine)
    with engine.connect() as connection:
        from alembic.script import ScriptDirectory
        assert connection.scalar(text("select version_num from alembic_version")) == ScriptDirectory.from_config(config).get_current_head()
        assert schema_differences(connection) == []
        saved = connection.execute(text("select assistant_enabled, assistant_language, digest_hour, lead_days, timezone, popup_enabled from notification_preferences where account_id='existing'")).one()
        assert tuple(saved) == (1, "en", 8, 9, "America/New_York", 0)
    engine.dispose()


def test_watsonx_background_transport_uses_real_chat_json_contract():
    import json

    import httpx

    from app.integrations.watsonx import WatsonxClient, WatsonxConfig
    requests = []
    def handler(request):
        if "identity/token" in request.url.path:
            return httpx.Response(200, json={"access_token": "synthetic-proactive-token", "expires_in": 3600})
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "title": "A new reminder", "summary": "Review it", "why_it_matters": "Your saved dates", "next_steps": ["Check sources"], "questions": []})}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        model = WatsonxClient(WatsonxConfig("https://ca-tor.ml.cloud.ibm.com", "proactive-only-test-key", "test-project", generation_model="test-model"), transport)
        assert model.generate_assistant_update({"language": "zh", "events": []})["title"] == "A new reminder"
    assert requests[0]["model_id"] == "test-model"
    assert "NOT asked" in requests[0]["messages"][0]["content"]
    assert "tools" not in requests[0] and requests[0]["max_completion_tokens"] == 1400


def test_authenticated_manual_check_uses_only_own_account_and_get_never_generates(ready, student, monkeypatch):
    from contextlib import contextmanager
    client, _, _, model = ready
    @contextmanager
    def configured():
        yield model
    monkeypatch.setattr("app.policy_pipeline.optional_policy_models", configured)
    assert client.get("/api/v1/assistant-updates", headers=student).status_code == 200
    assert not model.calls
    response = client.post("/api/v1/assistant-updates/check", headers=student, json={"account_id": "account-sam-rivera"})
    assert response.status_code == 200 and response.json()["generated"] == 1
    assert len(model.calls) == 1 and model.calls[0]["profile"]["status_type"] == "F-1"
    assert client.post("/api/v1/assistant-updates/check", headers=student).json()["generated"] == 0
    assert len(model.calls) == 1
    assert client.post("/api/v1/assistant-updates/check").status_code == 401


@pytest.mark.parametrize("message,rejected", [("Your ISSS document review is scheduled for today.", True),
    ("No appointment has been booked. Contact an adviser if you want a review.", False)])
def test_preparation_target_cannot_be_invented_as_an_appointment(message, rejected):
    from app.assistant_updates import validate_generated
    content = {"title": "Preparation reminder", "summary": message, "why_it_matters": "Review your saved facts.",
        "next_steps": ["Contact your adviser."], "questions": []}
    context = {"language": "en", "profile": {}, "preparation_targets": []}
    if rejected:
        with pytest.raises(ValueError, match="booked"):
            validate_generated(content, context)
    else:
        assert validate_generated(content, context)["summary"] == message


def test_invalid_draft_gets_one_model_correction_before_publication(ready):
    _, factory, _, model = ready
    original = model.generate_assistant_update
    def generate(context):
        draft = original(context)
        if len(model.calls) == 1:
            draft["summary"] = "Your appointment is scheduled for today."
        return draft
    model.generate_assistant_update = generate
    assert run(ready)["generated"] == 1
    assert len(model.calls) == 2
    assert "revision_request" in model.calls[-1]
    with factory() as db:
        assert "scheduled" not in db.scalar(select(AssistantUpdate)).content["summary"]


def test_unsupported_step_is_omitted_without_replacing_model_text():
    from app.assistant_updates import validate_generated
    value = {"language": "en", "title": "Travel preparation", "summary": "Your preparation target is approaching.",
        "why_it_matters": "Review the relevant requirements with your adviser.",
        "next_steps": ["Contact your adviser to review travel documents.", "Finish this within 24 hours."], "questions": []}
    result = validate_generated(value, {"language": "en", "profile": {}, "preparation_targets": []})
    assert result["next_steps"] == [value["next_steps"][0]]
    assert result["summary"] == value["summary"] and result["omitted_unverified_details"]
