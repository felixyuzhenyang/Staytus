"""Test shared form/chat planning, grounded dates, persistence and bounded repair."""
import json
from types import SimpleNamespace

import pytest

from app.chat import get_runtime
from app.integrations.orchestrate_runtime import OrchestrateRuntime
from app.main import app
from app.models import Profile
from app.planning_protocol import ChatEnvelope, request_from_envelope


@pytest.fixture
def timeline_runtime(env, monkeypatch):
    class Runtime:
        def __init__(self):
            self.calls = []
            self.envelope = {"kind": "plan", "workflow": "opt", "facts": []}
            self.invalid_narrative = False
            self.optional_nodes = []

        def send(self, message, **kwargs):
            self.calls.append({"message": message, **kwargs})
            if "STAYTUS RESPONSE CONTRACT" in message:
                output = self.envelope
            else:
                context = json.loads(kwargs["history"][0]["content"].split("\n")[-1])
                output = {"summary": "Plan your internship with your DSO. Your intended start is a goal; confirm the application dates and current requirements.",
                    "node_notes": [{"id": node["id"], "explanation": "Check the supplied dates and official references before taking this step."}
                        for node in context["guided_plan"]["timeline"]["nodes"]],
                    "optional_nodes": self.optional_nodes}
                if self.invalid_narrative:
                    output["node_notes"][0]["id"] = "model_invented_node"
            return SimpleNamespace(message=json.dumps(output), thread_id="synthetic-private-thread")
    runtime = Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    monkeypatch.setattr("app.retrieval.retrieve_for_profile", lambda *a, **kw: [])
    return runtime


def test_direct_goal_has_timeline_and_separate_goal_and_request_dates(env, student, timeline_runtime):
    client, _ = env
    message = "I am considering pre-completion OPT. I want to start an internship on May 20, 2027. Please help me plan."
    timeline_runtime.envelope["facts"] = [
        {"field": "goal_date", "value": "2027-05-20", "quote": "May 20, 2027"},
        {"field": "opt_stage", "value": "considering", "quote": "considering"},
        {"field": "opt_type", "value": "pre_completion", "quote": "pre-completion OPT"}]
    saved = client.get("/api/v1/profile", headers=student).json()
    response = client.post("/api/v1/chat", headers=student, json={"message": message})
    assert response.status_code == 200, response.text
    body = response.json()
    plan = body["planning"]
    assert plan["inputs"]["goal_date"] == "2027-05-20"
    assert "opt_requested_start" not in plan["inputs"]["planning_details"]
    nodes = {node["id"]: node for node in plan["timeline"]["nodes"]}
    assert nodes["goal"]["date"] == "2027-05-20" and nodes["goal"]["date_kind"] == "user_goal"
    assert nodes["prepare"]["date"] == "2027-03-21" and "60" in " ".join(nodes["prepare"]["basis"])
    assert nodes["filing"]["date"] is None and nodes["filing"]["date_kind"] == "to_confirm"
    assert nodes["filing"]["calendar_target"] is None
    assert all(node["explanation"] and node["sources"] for node in nodes.values())
    assert client.get("/api/v1/chat/history", headers=student).json()["messages"][-1]["planning"] == plan
    assert client.get("/api/v1/profile", headers=student).json() == saved
    assert len(timeline_runtime.calls) == 2


def test_form_and_chat_share_timeline_and_missing_travel_dates_remain_unknown(env, student, timeline_runtime):
    client, _ = env
    profile = client.get("/api/v1/profile", headers=student).json()
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my OPT", "planning_request": {
        "workflow": "opt", "profile_version": profile["version"], "goal_date": "2027-05-20",
        "planning_details": {"opt_stage": "considering", "opt_type": "pre_completion"}}})
    assert response.status_code == 200, response.text
    assert response.json()["planning"]["timeline"]["nodes"][1]["date"] == "2027-03-21"
    timeline_runtime.envelope = {"kind": "plan", "workflow": "travel", "facts": []}
    response = client.post("/api/v1/chat", headers=student, json={"message": "Help plan a trip; I don't know the dates yet."})
    assert response.status_code == 200, response.text
    nodes = {node["id"]: node for node in response.json()["planning"]["timeline"]["nodes"]}
    assert nodes["return"]["date"] is None
    assert nodes["return"]["date_kind"] == "to_confirm"


def test_model_can_select_only_server_approved_context_nodes(env, student, timeline_runtime):
    client, _ = env
    profile = client.get("/api/v1/profile", headers=student).json()
    timeline_runtime.optional_nodes = [{"id": "context_visa_expiry_before_return",
        "explanation": "Because the saved visa expires before the planned return, review renewal needs and exceptions with the adviser."}]
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my trip", "planning_request": {
        "workflow": "travel", "profile_version": profile["version"], "travel_date": "2027-01-10",
        "planning_details": {"travel_destination": "Japan", "return_date": "2027-01-22",
            "passport_expiry": "2029-01-01", "visa_expiry": "2026-12-31"}}})
    assert response.status_code == 200, response.text
    plan = response.json()["planning"]
    assert "context_visa_expiry_before_return" in timeline_runtime.calls[0]["message"]
    ids = [node["id"] for node in plan["timeline"]["nodes"]]
    assert ids.index("context_visa_expiry_before_return") == ids.index("documents") + 1
    selected = next(node for node in plan["timeline"]["nodes"] if node["id"] == "context_visa_expiry_before_return")
    assert selected["node_role"] == "contextual"
    assert selected["calendar_target"] is None and selected["sources"] == plan["sources"]
    assert selected["depends_on"] == ["documents"] and selected["selection_reason"]
    assert "timeline_candidates" not in plan
    assert client.get("/api/v1/chat/history", headers=student).json()["messages"][-1]["planning"] == plan


def test_invalid_optional_selection_is_discarded_without_losing_safe_core(env, student, timeline_runtime):
    client, _ = env
    profile = client.get("/api/v1/profile", headers=student).json()
    timeline_runtime.optional_nodes = [{"id": "model_invented_node",
        "explanation": "Use a model-created deadline and dependency."}]
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my OPT", "planning_request": {
        "workflow": "opt", "profile_version": profile["version"], "planning_details": {"opt_stage": "considering"}}})
    assert response.status_code == 200, response.text
    plan = response.json()["planning"]
    assert len(timeline_runtime.calls) == 2
    assert "model_invented_node" not in {node["id"] for node in plan["timeline"]["nodes"]}
    assert all(node["node_role"] == "core" for node in plan["timeline"]["nodes"])
    assert "timeline_candidates" not in plan


def test_combined_grounding_above_old_64000_limit_reaches_timeline_runtime(
        env, student, timeline_runtime, monkeypatch):
    client, _ = env
    monkeypatch.setattr("app.retrieval.retrieve_for_profile", lambda *a, **kw: [{
        "title": f"Synthetic official source {index}",
        "source_url": f"https://example.edu/policy/{index}",
        "text": "Synthetic official reference excerpt. " * 150,
        "status": "detected_pending_review", "review_required": True,
        "extra_metadata": "x" * 5000,
    } for index in range(5)])
    update = {"content": {
        "title": "Synthetic saved assistant update",
        "summary": "Saved synthetic update. " * 200,
        "why_it_matters": "Synthetic explanation. " * 100,
        "next_steps": ["Review the official source. " * 20],
    }, "created_at": "2026-11-08T12:00:00Z", "outdated": False}
    monkeypatch.setattr("app.assistant_updates.list_updates", lambda *a, **kw: [update, update])
    original_send = timeline_runtime.send
    grounding_sizes = []

    def checked_send(message, **kwargs):
        grounding_sizes.append(len(kwargs["history"][0]["content"]))
        OrchestrateRuntime._body(message, kwargs.get("history"), kwargs.get("context"))
        return original_send(message, **kwargs)

    monkeypatch.setattr(timeline_runtime, "send", checked_send)
    profile = client.get("/api/v1/profile", headers=student).json()
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my OPT", "planning_request": {
        "workflow": "opt", "profile_version": profile["version"], "goal_date": "2027-05-20",
        "planning_details": {"opt_stage": "considering", "opt_type": "pre_completion"}}})
    assert response.status_code == 200, response.text
    assert grounding_sizes and 64_000 < grounding_sizes[0] <= 100_000


@pytest.mark.parametrize("field,value,quote", [
    ("goal_date", "2027-02-19", "May 20, 2027"),
    ("opt_requested_start", "2027-05-20", "May 20, 2027"),
    ("school", "Another University", "May 20, 2027"),
    ("training_history_reviewed", "true", "May 20, 2027"),
    ("goal_date", "2027-05-20", "invented quotation"),
])
def test_model_cannot_invent_dates_or_promote_internship_goal(field, value, quote):
    envelope = ChatEnvelope(kind="plan", workflow="opt", facts=[{"field": field, "value": value, "quote": quote}])
    with pytest.raises(ValueError):
        request_from_envelope(envelope, "My intended internship starts May 20, 2027.", SimpleNamespace(version=1))


def test_invalid_node_structure_is_rejected_without_history(env, student, timeline_runtime):
    client, _ = env
    timeline_runtime.invalid_narrative = True
    response = client.post("/api/v1/chat", headers=student, json={"message": "Plan my OPT timeline"})
    assert response.status_code == 502 and len(timeline_runtime.calls) == 3
    assert client.get("/api/v1/chat/history", headers=student).json()["messages"] == []


def test_new_goal_recomputes_without_changing_profile(env, student, timeline_runtime):
    client, _ = env
    timeline_runtime.envelope["facts"] = [{"field": "goal_date", "value": "2027-05-20", "quote": "2027-05-20"}]
    first = client.post("/api/v1/chat", headers=student, json={"message": "Plan an internship from 2027-05-20"}).json()
    timeline_runtime.envelope.update(reuse_previous=True, facts=[{"field": "goal_date", "value": "2027-06-15", "quote": "2027-06-15"}])
    second = client.post("/api/v1/chat", headers=student, json={"message": "Change that goal to 2027-06-15", "conversation_id": first["conversation_id"]})
    assert second.status_code == 200, second.text
    assert second.json()["planning"]["calendar_targets"][0]["date"] == "2027-04-16"


def test_category_and_record_stage_change_timeline(env, student, timeline_runtime):
    client, factory = env
    with factory() as db:
        db.get(Profile, "mei-lin").status_type = "J-1 student"
        db.commit()
    timeline_runtime.envelope = {"kind": "plan", "workflow": "academic_training"}
    response = client.post("/api/v1/chat", headers=student, json={"message": "Help plan my training"})
    assert response.status_code == 200
    assert "authorization" in {node["id"] for node in response.json()["planning"]["timeline"]["nodes"]}
    timeline_runtime.envelope = {"kind": "plan", "workflow": "opt"}
    assert client.post("/api/v1/chat", headers=student, json={"message": "Plan OPT"}).status_code == 502


def test_timing_checks_keep_historical_calculations_and_reject_new_windows():
    from app.guided_planning import plan_text_issues
    context = {"profile": {"planning_details": {}}, "guided_plan": {"calendar_targets": [{"date": "2026-11-08",
        "trace": ["Original preparation target 2026-10-01 has passed; internal preparation buffer: 60 days."]}]}}
    assert not plan_text_issues("The original target was 2026-10-01; review on 2026-11-08.", context)
    assert plan_text_issues("File within a 90-day window.", context)
    assert plan_text_issues("Read https://invented-policy.example/", context)


def test_plan_cannot_claim_execution_or_promote_receipt_to_approval():
    from app.guided_planning import plan_text_issues
    context = {"profile": {"planning_details": {}}, "guided_plan": {"calendar_targets": []}}
    for text in ("Calendar reminder set for your preparation.", "Your reminder has been scheduled.",
                 "Verify approved employment dates once the receipt notice arrives.",
                 "This step is required before any preparation."):
        assert plan_text_issues(text, context), text
    assert not plan_text_issues("A reminder is suggested and requires approval. A receipt is not approval.", context)


def test_equivalent_id_keyed_model_notes_preserve_text_and_require_all_nodes():
    from app.planning_protocol import parse_narrative
    plan = {"timeline": {"nodes": [{"id": "adviser"}, {"id": "filing"}]}}
    data = {"summary": "Confirm the missing facts.", "node_notes": {"adviser": "Discuss your goal.", "filing": "Confirm the window."}}
    result = parse_narrative(json.dumps(data), plan)
    assert {note.id: note.explanation for note in result.node_notes} == data["node_notes"]
    data["node_notes"].pop("filing")
    with pytest.raises(ValueError):
        parse_narrative(json.dumps(data), plan)


def test_optional_node_cannot_define_server_owned_fields():
    from app.planning_protocol import parse_narrative
    plan = {"timeline": {"nodes": [{"id": "adviser"}]},
        "timeline_candidates": [{"id": "context_confirm_history"}]}
    base = {"summary": "Confirm the missing facts.",
        "node_notes": [{"id": "adviser", "explanation": "Discuss the plan with your adviser."}]}
    for extra in ({"date": "2027-01-01"}, {"depends_on": ["model_node"]}, {"title": "Model title"}):
        data = {**base, "optional_nodes": [{"id": "context_confirm_history",
            "explanation": "Confirm the relevant record before relying on this plan.", **extra}]}
        with pytest.raises(ValueError):
            parse_narrative(json.dumps(data), plan)


def test_internal_offset_cannot_be_reused_as_a_filing_rule(env, student, timeline_runtime):
    from app.planning_protocol import PlanNarrative, narrative_issues
    client, _ = env
    profile = client.get("/api/v1/profile", headers=student).json()
    plan = client.post("/api/v1/chat", headers=student, json={"message": "Plan OPT", "planning_request": {
        "workflow": "opt", "profile_version": profile["version"], "goal_date": "2027-05-20"}}).json()["planning"]
    narrative = PlanNarrative(summary="Review your goal with your DSO.", node_notes=[{"id": node["id"],
        "explanation": "File within 60 days of recommendation." if node["id"] == "filing" else "Review with your adviser."}
        for node in plan["timeline"]["nodes"]])
    assert any("filing:" in issue for issue in narrative_issues(narrative, {"profile": profile, "guided_plan": plan}))
