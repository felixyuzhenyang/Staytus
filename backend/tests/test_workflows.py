from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Approval, AuthSession, PolicyVersion, RuleVersion, now
from app.auth import digest, mint_tool_context
from app.config import get_settings
from conftest import login


def create_calendar(client, headers):
    result = client.post("/api/v1/approvals", headers=headers, json={"kind": "calendar", "payload": {"title": "Prepare documents", "date": "2027-03-16", "description": "Internal reminder"}})
    assert result.status_code == 201, result.text
    return result.json()


def test_three_synthetic_profiles_and_reproducible_rules(env, student):
    client, _ = env
    assert client.get("/api/v1/profiles").status_code == 404
    a = client.get("/api/v1/dashboard", headers=student).json()
    b = client.get("/api/v1/dashboard", headers=student).json()
    assert a["deadlines"] == b["deadlines"]
    assert a["deadlines"][0]["date"] == "2027-03-16"
    assert all(d["is_planning_buffer"] for d in a["deadlines"])
    for pid in ("sam-rivera", "amina-ali"):
        headers = login(client, pid)
        response = client.get("/api/v1/dashboard", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["deadlines"]) == 2


def test_profile_change_persists_and_recalculates(env, student):
    client, _ = env
    assert client.patch("/api/v1/profile", headers=student, json={"program_end": "2027-06-15"}).status_code == 200
    result = client.get("/api/v1/dashboard", headers=student).json()
    assert result["profile"]["version"] == 2
    assert result["deadlines"][0]["date"] == "2027-04-16"
    assert client.patch("/api/v1/profile", headers=student, json={"program_end": "2020-01-01"}).status_code == 422
    assert client.patch("/api/v1/profile", headers=student, json={"id": "amina-ali"}).status_code == 422


def test_approval_requires_preview_hash_and_single_use(env, student):
    client, _ = env
    a = create_calendar(client, student)
    url = f"/api/v1/approvals/{a['id']}"
    assert client.post(url + "/approve", headers=student, json={"payload_hash": a["payload_hash"]}).status_code == 409
    assert client.post(url + "/preview", headers=student).json()["status"] == "PREVIEWED"
    assert client.post(url + "/approve", headers=student, json={"payload_hash": "0" * 64}).status_code == 409
    approved = client.post(url + "/approve", headers=student, json={"payload_hash": a["payload_hash"]})
    assert approved.status_code == 200
    assert approved.json()["status"] == "SUCCEEDED"
    assert approved.json()["receipt"]["mode"] == "file_export"
    assert client.post(url + "/approve", headers=student, json={"payload_hash": a["payload_hash"]}).status_code == 409
    assert "BEGIN:VCALENDAR" in client.get(url + "/calendar.ics", headers=student).text


def test_other_user_cannot_preview_execute_or_download_approval(env, student):
    client, _ = env
    a = create_calendar(client, student)
    other = login(client, "sam-rivera")
    url = f"/api/v1/approvals/{a['id']}"
    for suffix in ("preview", "reject"):
        assert client.post(url + "/" + suffix, headers=other).status_code == 404
    assert client.post(url + "/approve", headers=other, json={"payload_hash": a["payload_hash"]}).status_code == 404
    assert client.get(url + "/calendar.ics", headers=other).status_code == 404
    assert client.get("/api/v1/approvals", headers=other).json()["approvals"] == []


def test_expired_approval_cannot_execute(env, student):
    client, factory = env
    a = create_calendar(client, student)
    with factory() as db:
        record = db.get(Approval, a["id"])
        record.status = "PREVIEWED"
        record.expires_at = now() - timedelta(minutes=1)
        db.commit()
    assert client.post(f"/api/v1/approvals/{a['id']}/approve", headers=student, json={"payload_hash": a["payload_hash"]}).status_code == 409
    assert client.get("/api/v1/approvals", headers=student).json()["approvals"][0]["status"] == "EXPIRED"


def test_payload_mutation_invalidates_approval(env, student):
    client, factory = env
    a = create_calendar(client, student)
    client.post(f"/api/v1/approvals/{a['id']}/preview", headers=student)
    with factory() as db:
        record = db.get(Approval, a["id"])
        record.payload = {**record.payload, "date": "2030-01-01"}
        db.commit()
    assert client.post(f"/api/v1/approvals/{a['id']}/approve", headers=student, json={"payload_hash": a["payload_hash"]}).status_code == 409


def test_profile_change_invalidates_old_preview(env, student):
    client, _ = env
    a = create_calendar(client, student)
    client.post(f"/api/v1/approvals/{a['id']}/preview", headers=student)
    client.patch("/api/v1/profile", headers=student, json={"program_end": "2027-06-30"})
    assert client.post(f"/api/v1/approvals/{a['id']}/approve", headers=student, json={"payload_hash": a["payload_hash"]}).status_code == 409


def test_rejected_approval_cannot_execute(env, student):
    client, _ = env
    a = create_calendar(client, student)
    assert client.post(f"/api/v1/approvals/{a['id']}/reject", headers=student).json()["status"] == "REJECTED"
    assert client.post(f"/api/v1/approvals/{a['id']}/preview", headers=student).status_code == 409


def test_demo_administration_routes_are_not_product_endpoints(env, student):
    client, _ = env
    assert client.get("/api/v1/admin/reviews", headers=student).status_code == 404
    assert client.post("/api/v1/admin/replay", headers=student).status_code == 404


def test_future_rule_cannot_activate(env, student):
    client, factory = env
    with factory() as db:
        db.add(RuleVersion(version=99, preparation_days=120, policy_version_id="demo-extension", reviewed_by="test", effective_from=now() + timedelta(days=30)))
        db.commit()
    result = client.get("/api/v1/dashboard", headers=student).json()
    assert result["deadlines"][0]["date"] == "2027-03-16"


def test_pending_and_enjoined_not_retrieved_as_effective(env, student):
    client, factory = env
    with factory() as db:
        db.add(PolicyVersion(id="enjoined", source_id="penn-isss", title="Suspended example", text="TEST", content_hash="1" * 64, status="postponed_or_enjoined", reviewed=True, fixture=True, visa_types=["F-1"]))
        db.commit()
    policies = client.get("/api/v1/policies?include_pending=false", headers=student).json()["policies"]
    assert not any(p["id"] == "enjoined" for p in policies)
    assert policies == []  # Synthetic policy fixtures are never product retrieval results.


def test_tool_key_requires_bound_user_context_and_rejects_identity_body(env, student):
    client, factory = env
    assert client.post("/tools/get_student_profile", json={}).status_code == 401
    assert client.post("/tools/get_student_profile", json={}, headers={"X-Tool-Key": "test-tool-key"}).status_code == 401
    token = student["Authorization"][7:]
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token)))
        context = mint_tool_context(session)
    headers = {"X-Tool-Key": "test-tool-key", "X-Staytus-Context": context}
    result = client.post("/tools/get_student_profile", json={}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["id"] == "mei-lin"
    assert client.post("/tools/get_student_profile", json={"profile_id": "sam-rivera"}, headers=headers).status_code == 422
    assert client.post("/tools/get_student_profile", json={}, headers={**headers, "X-Staytus-Context": context[:-1] + "x"}).status_code == 401
    assert client.post("/tools/confirm_profile_update", json={}, headers=headers).status_code == 404


def test_expired_tool_context_fails(env, student):
    client, factory = env
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(student["Authorization"][7:])))
        context = mint_tool_context(session, ttl=-1)
    assert client.post("/tools/get_student_profile", json={}, headers={"X-Tool-Key": "test-tool-key", "X-Staytus-Context": context}).status_code == 401


def test_demo_routes_removed_and_real_account_sessions_work(env, student):
    client, _ = env
    assert client.get("/api/v1/profiles").status_code == 404
    assert client.post("/api/v1/auth/demo", json={"profile_id": "mei-lin"}).status_code == 404
    assert client.get("/api/v1/dashboard", headers=student).status_code == 200


def test_audit_is_user_scoped(env, student):
    client, _ = env
    create_calendar(client, student)
    other = login(client, "sam-rivera")
    own = client.get("/api/v1/audit", headers=student).json()["events"]
    others = client.get("/api/v1/audit", headers=other).json()["events"]
    assert any(e["action"] == "approval.proposed" for e in own)
    assert not any(e["action"] == "approval.proposed" for e in others)
    assert all(e["correlation_id"] for e in own)


def test_request_and_audit_share_correlation_id(env, student):
    client, _ = env
    response = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {"title": "Reminder", "date": "2027-03-16"}})
    correlation = response.headers["X-Request-ID"]
    events = client.get("/api/v1/audit", headers=student).json()["events"]
    assert any(e["correlation_id"] == correlation and e["action"] == "approval.proposed" for e in events)
