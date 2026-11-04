"""Guided forms must reach the model with scoped evidence and retain approval gates."""
from types import SimpleNamespace

import pytest
from conftest import login
from sqlalchemy import select

from app.chat import get_runtime
from app.chat_models import Conversation
from app.main import app
from app.models import Approval, Profile


@pytest.fixture
def planning_runtime(env, monkeypatch):
    class Runtime:
        def __init__(self):
            self.calls = []
        def send(self, message, **kwargs):
            self.calls.append({"message": message, **kwargs})
            return SimpleNamespace(message="Your personalized plan: review the supplied source with ISSS before departure.", thread_id="private-planning-thread")
    runtime = Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    monkeypatch.setattr("app.retrieval.retrieve_for_profile", lambda *args, **kwargs: [{
        "title": "Official travel guidance", "source_url": "https://global.upenn.edu/isss/",
        "text": "Synthetic retrieved excerpt for test only.", "status": "detected_pending_review", "review_required": True}])
    yield runtime
    app.dependency_overrides.pop(get_runtime, None)


def travel_request(client, headers, **overrides):
    profile = client.get("/api/v1/profile", headers=headers).json()
    return {"workflow": "travel", "profile_version": profile["version"],
        "travel_date": "2027-01-10", "travel_signature_date": "2026-06-01",
        "planning_details": {"travel_destination": "Japan", "return_date": "2027-01-22",
            "passport_expiry": "2029-01-01", "visa_expiry": "2026-12-31"},
        "notes": "请用中文说明准备事项", **overrides}


def test_guided_plan_passes_scenario_evidence_and_checks_to_real_chat_path(env, student, planning_runtime):
    client, factory = env
    saved = client.get("/api/v1/profile", headers=student).json()
    request = travel_request(client, student)
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my trip", "planning_request": request})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["mode"] == "orchestrate"
    assert answer["planning"]["inputs"]["planning_details"]["travel_destination"] == "Japan"
    assert answer["planning"]["retrieved_source_count"] == 1
    assert answer["planning"]["calendar_targets"][0]["date"] == "2026-12-11"
    assert answer["planning"]["calendar_targets"][0]["is_planning_buffer"]
    assert any(row["id"] == "visa_expiry_before_return" for row in answer["planning"]["record_checks"])
    grounding = planning_runtime.calls[0]["history"][0]["content"]
    assert "Japan" in grounding and "2027-01-22" in grounding
    assert "Synthetic retrieved excerpt" in grounding
    assert "pending/unreviewed/stale" in grounding and "Do not save or change the profile" in grounding
    current_turn = planning_runtime.calls[0]["message"]
    assert "Japan" in current_turn and "2027-01-22" in current_turn
    assert "visa_expiry_before_return" in current_turn and "Synthetic retrieved excerpt" in current_turn
    assert len(current_turn) <= 8000
    assert client.get("/api/v1/profile", headers=student).json() == saved
    assert "staytus_context" not in response.text and "private-planning-thread" not in response.text
    with factory() as db:
        assert list(db.scalars(select(Approval))) == []


@pytest.mark.parametrize("override", [
    {"planning_details": {"travel_destination": "Japan", "return_date": "2026-01-01"}},
    {"planning_details": {"return_date": "2027-01-22"}},
    {"profile_version": 999},
    {"profile_id": "sam-rivera"},
    {"planning_details": {"travel_destination": "Japan", "return_date": "2027-01-22", "academic_training_stage": "active"}},
])
def test_invalid_scenarios_do_not_call_model_or_mutate_state(env, student, planning_runtime, override):
    client, factory = env
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan", "planning_request": travel_request(client, student, **override)})
    assert response.status_code in {409, 422}, response.text
    assert not planning_runtime.calls
    with factory() as db:
        assert list(db.scalars(select(Conversation))) == []


def test_history_restores_plan_and_followup_retains_temporary_scenario(env, student, planning_runtime):
    client, _ = env
    item = client.post("/api/v1/chat", headers=student, json={"message": "Trip to Japan", "planning_request": travel_request(client, student)}).json()
    history = client.get("/api/v1/chat/history", headers=student)
    assert history.status_code == 200
    assert history.json()["messages"][-1]["planning"] == item["planning"]
    assert "private-planning-thread" not in history.text and "staytus_context" not in history.text
    response = client.post("/api/v1/chat", headers=student, json={"message": "What should I ask my adviser?", "conversation_id": item["conversation_id"]})
    assert response.status_code == 200
    assert "Japan" in planning_runtime.calls[-1]["history"][0]["content"]
    assert all(set(row) == {"role", "content"} for row in planning_runtime.calls[-1]["history"])
    other = login(client, "sam-rivera")
    assert client.get("/api/v1/chat/history", headers=other).json()["messages"] == []
    assert client.post("/api/v1/chat", headers=other, json={"message": "Continue", "conversation_id": item["conversation_id"]}).status_code == 404


def test_changed_profile_invalidates_old_scenario_on_followup(env, student, planning_runtime):
    client, _ = env
    first = client.post("/api/v1/chat", headers=student, json={"message": "Plan", "planning_request": travel_request(client, student)}).json()
    assert client.patch("/api/v1/profile", headers=student, json={"nationality": "Not supplied"}).status_code == 200
    response = client.post("/api/v1/chat", headers=student, json={"message": "Review my current profile", "conversation_id": first["conversation_id"]})
    assert response.status_code == 200 and "planning" not in response.json()
    assert "guided_plan" not in planning_runtime.calls[-1]["history"][0]["content"]


@pytest.mark.parametrize("status,workflow,details", [
    ("F-1", "opt", {"opt_stage": "preparing", "opt_type": "post_completion", "academic_completion_date": "2027-05-15"}),
    ("F-1", "extension", {"extension_stage": "preparing", "extension_requested_end": "2028-05-15"}),
    ("J-1 student", "academic_training", {"academic_training_stage": "active", "academic_training_end": "2027-05-15"}),
    ("J-1 scholar", "scholar", {"j1_category": "research_scholar", "sponsor_name": "Example sponsor"}),
])
def test_category_workflows_and_reminders(env, student, planning_runtime, status, workflow, details):
    client, factory = env
    with factory() as db:
        profile = db.get(Profile, "mei-lin")
        profile.status_type = status
        profile.planning_details = {}
        db.commit()
    version = client.get("/api/v1/profile", headers=student).json()["version"]
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my next steps", "planning_request": {
        "workflow": workflow, "profile_version": version, "planning_details": details}})
    assert response.status_code == 200, response.text
    assert response.json()["planning"]["workflow"] == workflow
    assert response.json()["planning"]["calendar_targets"]
    assert all(item["legal_deadline"] is None for item in response.json()["planning"]["calendar_targets"])


def test_j1_cannot_request_opt_and_logged_out_cannot_read_plans(env, student, planning_runtime):
    client, _ = env
    other = login(client, "sam-rivera")
    response = client.post("/api/v1/chat", headers=other, json={"message": "Plan", "planning_request": travel_request(client, other, workflow="opt")})
    assert response.status_code == 422
    assert not planning_runtime.calls
    assert client.get("/api/v1/chat/history").status_code == 401


def test_profile_change_during_generation_rejects_stale_plan(env, student, planning_runtime, monkeypatch):
    client, factory = env
    original = planning_runtime.send
    def change_profile(*args, **kwargs):
        with factory() as db:
            db.get(Profile, "mei-lin").version += 1
            db.commit()
        return original(*args, **kwargs)
    monkeypatch.setattr(planning_runtime, "send", change_profile)
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan", "planning_request": travel_request(client, student)})
    assert response.status_code == 409
    assert client.get("/api/v1/chat/history", headers=student).json()["messages"] == []
    with factory() as db:
        assert db.scalar(select(Conversation)).busy_until is None


def test_unsupported_timing_is_repaired_before_plan_is_saved(env, student, planning_runtime, monkeypatch):
    client, _ = env
    original = planning_runtime.send
    def reply(message, **kwargs):
        result = original(message, **kwargs)
        if len(planning_runtime.calls) == 1:
            result.message = "Book by 2026-12-15 and check within 24 hours. 已设定日历。"
        return result
    monkeypatch.setattr(planning_runtime, "send", reply)
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan", "planning_request": travel_request(client, student)})
    assert response.status_code == 200
    assert len(planning_runtime.calls) == 2
    assert "Rewrite your previous plan" in planning_runtime.calls[-1]["message"]
    assert len(planning_runtime.calls[-1]["message"]) <= 8000
    assert "2026-12-15" not in client.get("/api/v1/chat/history", headers=student).text


def test_invalid_model_plan_has_no_saved_or_local_fallback(env, student, planning_runtime, monkeypatch):
    client, _ = env
    original = planning_runtime.send
    def reply(*args, **kwargs):
        result = original(*args, **kwargs)
        result.message = "Book by 2026-12-15."
        return result
    monkeypatch.setattr(planning_runtime, "send", reply)
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan", "planning_request": travel_request(client, student)})
    assert response.status_code == 502 and len(planning_runtime.calls) == 2
    assert client.get("/api/v1/chat/history", headers=student).json()["messages"] == []


@pytest.mark.parametrize("text", ["Book by 2026‑12‑15.", "请在2026年12月15日前预约。", "Within 24 hours.", "日历已创建。"])
def test_output_checks_cover_timing_and_execution_claims(text):
    from app.guided_planning import plan_text_issues
    context = {"profile": {"travel_date": "2027-01-10", "planning_details": {}}, "guided_plan": {"calendar_targets": []}}
    assert plan_text_issues(text, context)


def test_model_can_explain_the_supplied_internal_buffer():
    from app.guided_planning import plan_text_issues
    context = {"profile": {"planning_details": {}}, "guided_plan": {"calendar_targets": [
        {"date": "2026-12-11", "trace": ["Internal travel preparation buffer: 30 calendar days"]}]}}
    assert not plan_text_issues("出发前约30天，按2026-12-11这一天准备；日历尚未创建。", context)
    assert plan_text_issues("Create an appointment in 24 hours.", context)
