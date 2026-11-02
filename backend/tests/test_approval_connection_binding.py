"""Provider targets and current DB identity are part of exact-content approval."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import services
from app.integrations.connection_models import ProviderConnection
from app.models import Approval, AuditEvent, Profile, uid
from test_connectors import oauth as connector_oauth, add_connection

oauth = connector_oauth
CALENDAR = "https://www.googleapis.com/auth/calendar.events.owned"


def proposal(client, headers, kind="calendar"):
    payload = ({"provider": "google", "title": "Synthetic reminder", "date": "2030-02-03"}
        if kind == "calendar" else {"to": "adviser@example.invalid", "subject": "Synthetic", "body": "Planning only"})
    response = client.post("/api/v1/approvals", headers=headers, json={"kind": kind, "payload": payload})
    assert response.status_code == 201, response.text
    item = response.json()
    assert client.post(f"/api/v1/approvals/{item['id']}/preview", headers=headers).status_code == 200
    return item


@pytest.mark.parametrize("kind", ["calendar", "email"])
def test_relink_cannot_redirect_an_already_previewed_write(env, student, oauth, kind):
    client, factory = env
    scopes = [CALENDAR] if kind == "calendar" else None
    old_id = add_connection(factory, oauth, scopes=scopes)
    item = proposal(client, student, kind)
    target = item["payload"]["_connector_target"]
    assert target["connection_id"] == old_id and item["target_account"] == target["account_label"]
    with factory() as db:
        connection = db.get(ProviderConnection, old_id)
        connection.id = uid()  # OAuth relink rotates this server-owned binding.
        db.commit()
    result = client.post(f"/api/v1/approvals/{item['id']}/approve", headers=student,
        json={"payload_hash": item["payload_hash"]})
    assert result.status_code == 409 and not oauth["calls"]
    with factory() as db:
        assert db.get(Approval, item["id"]).status == "PREVIEWED"


@pytest.mark.parametrize("kind", ["calendar", "email"])
def test_linking_after_preview_requires_a_fresh_proposal(env, student, oauth, kind):
    client, factory = env
    item = proposal(client, student, kind)
    assert item["payload"]["_connector_target"]["connection_id"] is None
    connection_id = add_connection(factory, oauth, scopes=[CALENDAR] if kind == "calendar" else None)
    assert client.post(f"/api/v1/approvals/{item['id']}/approve", headers=student,
        json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert not oauth["calls"]
    fresh = proposal(client, student, kind)
    assert fresh["payload"]["_connector_target"]["connection_id"] == connection_id


def test_calendar_only_link_never_masks_an_existing_mail_draft_target(env, student, oauth):
    client, factory = env
    mail_id = add_connection(factory, oauth)
    add_connection(factory, oauth, provider="microsoft", scopes=["Calendars.ReadWrite"])
    item = proposal(client, student, "email")
    assert item["payload"]["_connector_target"]["connection_id"] == mail_id
    assert item["payload"]["_connector_target"]["provider"] == "google"
    result = client.post(f"/api/v1/approvals/{item['id']}/approve", headers=student,
        json={"payload_hash": item["payload_hash"]})
    assert result.status_code == 200 and result.json()["receipt"]["provider"] == "google"
    assert len(oauth["calls"]) == 1 and oauth["calls"][0].url.path.endswith("/drafts")


def test_private_binding_is_server_generated_and_covered_by_payload_hash(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth)
    forged = client.post("/api/v1/approvals", headers=student, json={"kind": "email", "payload": {
        "subject": "Synthetic", "body": "Synthetic", "_connector_target": {"connection_id": "forged"}}})
    assert forged.status_code == 422
    item = proposal(client, student, "email")
    assert services.payload_hash(item["payload"]) == item["payload_hash"]
    assert services.payload_hash({k: v for k, v in item["payload"].items() if not k.startswith("_")}) != item["payload_hash"]
    with factory() as db:
        approval = db.get(Approval, item["id"])
        approval.payload = {**approval.payload, "_connector_target": {**approval.payload["_connector_target"], "connection_id": "forged"}}
        db.commit()
    assert client.post(f"/api/v1/approvals/{item['id']}/approve", headers=student,
        json={"payload_hash": item["payload_hash"]}).status_code == 409
    assert not oauth["calls"]


def test_legacy_remote_preview_without_binding_fails_closed(env, student, oauth):
    client, factory = env
    add_connection(factory, oauth)
    item = proposal(client, student, "email")
    with factory() as db:
        approval = db.get(Approval, item["id"])
        approval.payload = {k: v for k, v in approval.payload.items() if not k.startswith("_")}
        approval.payload_hash = services.payload_hash(approval.payload)
        legacy_hash = approval.payload_hash
        db.commit()
    assert client.post(f"/api/v1/approvals/{item['id']}/approve", headers=student,
        json={"payload_hash": legacy_hash}).status_code == 409
    assert not oauth["calls"]


@pytest.mark.parametrize("change", ["profile_version", "profile_owner", "approval_hash", "approval_owner"])
def test_claim_rechecks_current_database_state_despite_stale_session(env, student, change):
    client, factory = env
    response = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {
        "title": "Synthetic export", "date": "2030-02-03"}})
    item = response.json()
    client.post(f"/api/v1/approvals/{item['id']}/preview", headers=student)
    with factory() as stale, factory() as concurrent:
        profile = stale.get(Profile, "mei-lin")
        approval = stale.get(Approval, item["id"])
        if change == "profile_version":
            concurrent.get(Profile, profile.id).version += 1
        elif change == "profile_owner":
            concurrent.get(Profile, profile.id).account_id = None
        elif change == "approval_hash":
            concurrent.get(Approval, approval.id).payload_hash = "a" * 64
        else:
            concurrent.get(Approval, approval.id).profile_id = "sam-rivera"
        concurrent.commit()
        with pytest.raises(HTTPException) as error:
            services.execute(stale, profile, approval, item["payload_hash"])
        assert error.value.status_code == 409
        stale.rollback()
    with factory() as db:
        assert db.get(Approval, item["id"]).status == "PREVIEWED"
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "approval.approved")) is None
