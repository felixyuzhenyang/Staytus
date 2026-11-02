"""Verifier regressions: actual trace, ownership and unexecuted proposal proof."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def verifier(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("staytus_business_verifier", root / "scripts/verify_orchestrate_tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_never_reads_configuration_or_calls_cloud(verifier, monkeypatch, capsys):
    monkeypatch.setattr(verifier, "environment", lambda *a: pytest.fail("Unexpected config read"))
    monkeypatch.setattr(verifier, "run", lambda *a: pytest.fail("Unexpected network"))
    assert verifier.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["network_called"] is False and result["maximum_model_calls"] == 4
    assert verifier.main(["--live"]) == 2


def test_failed_rerun_invalidates_previous_pass_and_hides_exception(verifier, tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"
    report.write_text('{"passed":true}')
    monkeypatch.setattr(verifier, "environment", lambda *a: {})
    def fail(*args):
        raise RuntimeError("sensitive-canary-never-echo")
    monkeypatch.setattr(verifier, "run", fail)
    assert verifier.main(["--live", "--confirm-synthetic-test", "--env-file", str(tmp_path / "env"),
        "--report", str(report)]) == 2
    assert json.loads(report.read_text())["passed"] is False
    assert "sensitive-canary" not in report.read_text() + capsys.readouterr().out


def test_explicit_independent_case_selection_deduplicates_model_call_budget(verifier, capsys):
    assert verifier.main(["--case", "mail_permission_denial", "--case", "mail_permission_denial"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cases"] == ["mail_permission_denial"]
    assert result["maximum_model_calls"] == 1 and result["network_called"] is False


def trace(name="get_school_adapter", args=None, result=None):
    return [{"role": "user", "content": "must never count as tool proof"},
        {"role": "assistant", "content": "I called all tools successfully", "step_history": [{"step_details": [
            {"type": "tool_calls", "tool_calls": [{"name": name, "args": args or {}}]},
            {"type": "tool_response", "name": name, "content": json.dumps(result or {"id": "penn", "supported": True})}]}]}]


def test_trace_needs_real_tool_events_and_rejects_model_identity(verifier):
    calls, results = verifier.tool_trace(trace())
    assert calls == [{"name": "get_school_adapter", "args": {}}]
    assert results["get_school_adapter"] == [{"id": "penn", "supported": True}]
    for field in ["context", "profile_id", "account_id", "staytus_context", "user_id"]:
        with pytest.raises(verifier.SetupError):
            verifier.tool_trace(trace(args={field: "untrusted"}))
    with pytest.raises(verifier.SetupError, match="model-supplied connector target"):
        verifier.tool_trace(trace(name="create_email_preview", args={"payload": {"_connector_target": None}}))
    calls, results = verifier.tool_trace([{"role": "assistant", "content": "all done"}])
    with pytest.raises(verifier.SetupError):
        verifier.validate_trace(calls, results, ["get_school_adapter"], {}, "read_tools")


def test_mail_tool_requires_explicit_permission_denial_not_generic_error(verifier):
    data = {"profile_id": "own", "other_profile_id": "other"}
    verifier.validate_tool("read_recent_official_messages", {"error": "tool_permission_required"}, data, "mail_permission_denial")
    for result in [{"error": "backend_tool_unavailable"}, {"messages": []},
            {"error": "tool_permission_required", "messages": []}]:
        with pytest.raises(verifier.SetupError):
            verifier.validate_tool("read_recent_official_messages", result, data, "mail_permission_denial")


def test_proposals_must_match_exact_content_and_remain_unexecuted(verifier):
    data = {"profile_id": "own-profile", "other_profile_id": "other-profile", "profile_version": 1}
    empty_target = {"provider": None, "connection_id": None, "account_label": None}
    payload = {**verifier.EMAIL, "_connector_target": empty_target}
    good = {"id": "proposal", "kind": "email", "status": "PROPOSED", "receipt": None,
        "payload": payload, "payload_hash": verifier.payload_digest(payload), "target_account": None, "profile_version": 1}
    verifier.validate_tool("create_email_preview", good, data, "proposal_tools")
    forged = {**payload, "_connector_target": {"provider": "google", "connection_id": "forged", "account_label": "forged@example.invalid"}}
    with pytest.raises(verifier.SetupError, match="server-owned account binding"):
        verifier.validate_tool("create_email_preview", {**good, "payload": forged,
            "payload_hash": verifier.payload_digest(forged), "target_account": "forged@example.invalid"}, data, "proposal_tools")
    for changed in [{"status": "SUCCEEDED"}, {"receipt": {"sent": True}},
            {"payload": {**payload, "to": "different@example.invalid"}},
            {"payload": {**payload, "_connector_target": {"connection_id": "forged"}}},
            {"payload": verifier.EMAIL}, {"payload_hash": "0" * 64}, {"target_account": "forged@example.invalid"},
            {"profile_version": 0}]:
        with pytest.raises(verifier.SetupError):
            verifier.validate_tool("create_email_preview", {**good, **changed}, data, "proposal_tools")


def test_connector_target_is_server_bound_not_optional_or_swappable(verifier):
    target = {"provider": "google", "connection_id": "synthetic-connection-a", "account_label": "a@example.invalid"}
    payload = {"provider": "google", "_connector_target": target}
    verifier.validate_connector_target("calendar", payload, target)
    empty = {"provider": None, "connection_id": None, "account_label": None}
    verifier.validate_connector_target("email", {"_connector_target": empty}, empty)
    for altered in [{"provider": "google"}, {"provider": "google", "_connector_target": None},
            {"provider": "google", "_connector_target": {**target, "connection_id": "synthetic-connection-b"}}]:
        with pytest.raises(verifier.SetupError):
            verifier.validate_connector_target("calendar", altered, target)
    with pytest.raises(verifier.SetupError):
        verifier.validate_connector_target("calendar", {"provider": "export", "_connector_target": target}, None)


def test_citation_and_review_provenance_cannot_be_replaced_by_model_prose(verifier):
    data = {"profile_id": "own-profile", "other_profile_id": "other-profile"}
    row = {"fixture": False, "citations": [{"source_url": "https://example.invalid"}],
        "captured_at": "2030-01-01", "review_required": True, "source_url": "https://example.invalid"}
    verifier.validate_tool("search_official_policy", {"policies": [row]}, data, "read_tools")
    for changed in [{"fixture": True}, {"citations": []}, {"review_required": None}, {"source_url": "http://example.invalid"}]:
        with pytest.raises(verifier.SetupError):
            verifier.validate_tool("search_official_policy", {"policies": [{**row, **changed}]}, data, "read_tools")


def test_duplicate_or_unrequested_tool_calls_fail(verifier):
    calls, responses = verifier.tool_trace(trace())
    data = {"profile_id": "own-profile", "other_profile_id": "other-profile"}
    assert verifier.validate_trace(calls, responses, ["get_school_adapter"], data, "read_tools") == {"get_school_adapter": 1}
    for invalid in [calls * 2, [{"name": "send_email", "args": {}}]]:
        with pytest.raises(verifier.SetupError):
            verifier.validate_trace(invalid, responses, ["get_school_adapter"], data, "read_tools")


def test_audit_and_proposal_ownership_require_actual_matching_rows(verifier):
    data = {"profile_id": "own", "other_profile_id": "other"}
    before = {key: {"audits": Counter(), "approvals": {}} for key in ("own", "other")}
    after = deepcopy(before)
    after["own"] = {"audits": Counter({"tool.create_email_preview": 1, "approval.proposed": 1}),
        "approvals": {"proposal": {"kind": "email", "payload": verifier.EMAIL}}}
    responses = {"create_email_preview": [{"id": "proposal", "kind": "email", "payload": verifier.EMAIL}]}
    verifier.validate_audits(before, after, {"create_email_preview": 1}, data, responses)
    bad = deepcopy(after)
    bad["other"]["audits"]["tool.get_student_profile"] += 1
    with pytest.raises(verifier.SetupError):
        verifier.validate_audits(before, bad, {"create_email_preview": 1}, data, responses)
    with pytest.raises(verifier.SetupError):
        verifier.validate_audits(before, after, {"create_email_preview": 1}, data,
            {"create_email_preview": [{**responses["create_email_preview"][0], "id": "invented"}]})


def test_cleanup_deletes_only_its_synthetic_owned_rows(verifier, env):
    from sqlalchemy import select
    from app.models import Account, Approval, AuditEvent, Notification, Profile, now
    from app.integrations.connection_models import ProviderConnection, MailAgentPermission
    from datetime import timedelta
    factory = env[1]
    with factory() as db:
        original = set(db.scalars(select(Account.id)))
    identities = verifier.seed_synthetic(factory)
    profile, account = identities[0]["profile_id"], identities[0]["account_id"]
    with factory() as db:
        db.add(Notification(profile_id=profile, title="SYNTHETIC", message="temporary"))
        db.add(Approval(profile_id=profile, kind="email", payload={}, payload_hash="h" * 64,
            expires_at=now() + timedelta(minutes=1)))
        db.add(AuditEvent(profile_id=profile, action="tool.create_email_preview", detail={}, correlation_id=str(uuid4())))
        db.add(ProviderConnection(account_id=account, provider="google", encrypted_tokens="unusable", scopes=[]))
        db.add(MailAgentPermission(account_id=account, provider="google", enabled=False))
        db.commit()
    verifier.cleanup(factory, identities)
    with factory() as db:
        assert set(db.scalars(select(Account.id))) == original
        assert db.get(Profile, profile) is None
        assert not db.scalars(select(Approval).where(Approval.profile_id == profile)).all()
