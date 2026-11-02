"""Synthetic verification is explicit, isolated and cannot enable product chat."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select


@pytest.fixture
def probe(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("staytus_probe_test", scripts / "verify_orchestrate_context.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_default_has_no_configuration_read_or_network(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "environment", lambda *a: pytest.fail("Unexpected env-file read"))
    monkeypatch.setattr(probe, "execute", lambda *a: pytest.fail("Unexpected actual verification"))
    assert probe.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["network_called"] is False and result["product_readiness_changed"] is False


def test_live_needs_second_confirmation_before_configuration_read(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "environment", lambda *a: pytest.fail("Unexpected env-file read"))
    assert probe.main(["--live"]) == 2
    assert json.loads(capsys.readouterr().out)["network_called"] is False


def test_failed_rerun_invalidates_old_success_and_hides_unknown_error(probe, monkeypatch, tmp_path, capsys):
    path = tmp_path / "redacted-report.json"
    path.write_text('{"passed": true}')
    monkeypatch.setattr(probe, "environment", lambda *a: {})
    def fail(*args):
        raise RuntimeError("private-credential-must-not-appear")
    monkeypatch.setattr(probe, "execute", fail)
    assert probe.main(["--live", "--confirm-synthetic-test", "--report", str(path)]) == 2
    assert json.loads(path.read_text())["passed"] is False
    assert "private-credential-must-not-appear" not in capsys.readouterr().out


def test_environment_resolves_exact_uuid_and_never_guesses_literal(probe):
    agent, draft, live = str(uuid4()), str(uuid4()), str(uuid4())
    environments = [{"id": draft, "agent_id": agent, "name": "draft"},
                    {"id": live, "agent_id": agent, "name": "live"}]
    assert probe.draft_environment(environments, agent, "draft") == draft
    assert probe.draft_environment(environments, agent, "live") == live
    for invalid in ([], [{"id": "draft", "name": "draft"}], environments + [environments[0]]):
        with pytest.raises(probe.SetupError):
            probe.draft_environment(invalid, agent, "draft")


def test_cloud_configuration_must_keep_capability_out_of_prompt(probe):
    from uuid import uuid4
    tool_uuid = str(uuid4())
    manifest = {"agent_name": "StaytusContextProbe", "model_id": "tenant/model",
                "tool_names": ["get_student_profile"]}
    id_to_name = {tool_uuid: "get_student_profile"}
    agent = {"name": manifest["agent_name"], "llm": manifest["model_id"],
             "tools": [tool_uuid],
             "collaborators": [], "context_access_enabled": True, "context_variables": []}
    probe.validate_remote_agent(agent, manifest, id_to_name)
    probe.validate_remote_agent({**agent, "name": "staytus_context_probe_internal_slug",
                                 "display_name": "StaytusContextProbe"}, manifest, id_to_name)
    # Missing/disabled tool context and any model allowlist must fail.
    for changed in ({"context_access_enabled": False},
                    {"context_access_enabled": None},
                    {"context_variables": ["staytus_context"]},
                    {"llm": "different/model"},
                    {"name": "wrong_agent", "display_name": "wrong_display_name"}):
        with pytest.raises(probe.SetupError):
            probe.validate_remote_agent({**agent, **changed}, manifest, id_to_name)
    # Unknown UUID → rejected.
    with pytest.raises(probe.SetupError, match="not present in the tool inventory"):
        probe.validate_remote_agent({**agent, "tools": [str(uuid4())]}, manifest, id_to_name)
    # Duplicate UUID → rejected (resolves to same name twice).
    with pytest.raises(probe.SetupError):
        probe.validate_remote_agent({**agent, "tools": [tool_uuid, tool_uuid]}, manifest, id_to_name)


def test_live_release_pins_tool_identity_and_version_without_accepting_ambiguous_refs(probe):
    tool_id = str(uuid4())
    manifest = {"agent_name": "StaytusContextProbe", "model_id": "tenant/model", "tool_names": ["get_student_profile"]}
    agent = {"name": "StaytusContextProbe", "llm": "tenant/model", "collaborators": [],
        "context_access_enabled": True, "context_variables": [],
        "tools": [{"tool_id": tool_id, "version_label": 1}]}
    inventory = {tool_id: "get_student_profile"}
    probe.validate_remote_agent(agent, manifest, inventory, target="live")
    for references in ([tool_id], [{"tool_id": tool_id}],
            [{"tool_id": tool_id, "version_label": True}],
            [{"tool_id": tool_id, "version_label": 0}],
            [{"tool_id": tool_id, "version_label": 1, "unexpected": "value"}],
            [{"tool_id": str(uuid4()), "version_label": 1}],
            agent["tools"] * 2):
        with pytest.raises(probe.SetupError):
            probe.validate_remote_agent({**agent, "tools": references}, manifest, inventory, target="live")
    with pytest.raises(probe.SetupError):
        probe.validate_remote_agent(agent, manifest, inventory, target="draft")


@pytest.mark.parametrize("invalid", ["duplicate_id", "duplicate_name", "malformed", "denied"])
def test_unreadable_or_conflicting_tool_inventory_never_becomes_authority(probe, invalid):
    identity = str(uuid4())
    payload = [{"id": identity, "name": "get_student_profile"}]
    if invalid == "duplicate_id":
        payload.append({"id": identity, "name": "different_tool"})
    elif invalid == "duplicate_name":
        payload.append({"id": str(uuid4()), "name": "get_student_profile"})
    elif invalid == "malformed":
        payload = {"unexpected": "private-response-canary"}
    def transport(request):
        assert request.method == "GET" and request.url.params["include"] == "global"
        return httpx.Response(403 if invalid == "denied" else 200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(probe.SetupError) as error:
            probe.load_tool_inventory(client, "https://tenant.example.invalid", {"Authorization": "private-token-canary"})
    assert "private-response-canary" not in str(error.value)
    assert "private-token-canary" not in str(error.value)


def test_verified_uuid_inventory_allows_tool_order_changes(probe):
    ids = [str(uuid4()), str(uuid4())]
    names = ["get_student_profile", "list_action_tasks"]
    def transport(request):
        return httpx.Response(200, json=[{"id": value, "name": name} for value, name in zip(ids, names)])
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        inventory = probe.load_tool_inventory(client, "https://tenant.example.invalid", {})
    manifest = {"agent_name": "Staytus", "model_id": "tenant/model", "tool_names": names}
    agent = {"name": "Staytus", "llm": "tenant/model", "tools": list(reversed(ids)),
             "collaborators": [], "context_access_enabled": True, "context_variables": []}
    probe.validate_remote_agent(agent, manifest, inventory)


def test_draft_run_payload_passes_context_separately_and_checks_completion(probe):
    agent, draft, run, thread = [str(uuid4()) for _ in range(4)]
    requests = []
    def transport(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["environment_id"] == draft
            assert body["context"] == {"staytus_context": "synthetic-capability"}
            assert "synthetic-capability" not in body["message"]["content"]
            assert body["agent_id"] == agent and "thread_id" not in body
            return httpx.Response(200, json={"run_id": run, "thread_id": thread})
        if request.url.path == "/v1/orchestrate/runs/" + run:
            # A loosely typed run result can be empty or contain untrusted echo;
            # the verifier must fetch the actual assistant thread message.
            return httpx.Response(200, json={"status": "completed", "result": {"user_echo": "must-not-pass"}})
        assert request.url.path == "/v1/orchestrate/threads/" + thread + "/messages"
        return httpx.Response(200, json=[
            {"role": "assistant", "content": [{"response_type": "text", "text": "earlier assistant output"}]},
            {"role": "user", "content": [{"response_type": "text", "text": "must-not-pass"}]},
            {"role": "assistant", "content": [{"response_type": "text", "text": '{"profile_id":"synthetic-own"}'}]},
            {"role": "tool", "content": [{"response_type": "text", "text": "must-not-pass"}]},
        ])
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result, meta = probe.run_draft(client, "https://tenant.example.invalid", "synthetic-iam", agent, draft, "synthetic-capability")
    assert result == '{"profile_id":"synthetic-own"}' and meta["run_id"] == run
    assert len(requests) == 3


@pytest.mark.parametrize("payload", [
    [{"role": "user", "content": [{"response_type": "text", "text": "user echo"}]}],
    [{"role": "tool", "content": [{"response_type": "text", "text": "tool echo"}]}],
    {"data": {"messages": [{"role": "assistant", "content": "unsupported nested wrapper"}]}},
    [{"role": "assistant", "content": [{"response_type": "image", "text": "not assistant text"}]}],
])
def test_thread_result_rejects_user_echo_tool_output_and_unknown_wrappers(probe, payload):
    with pytest.raises(probe.SetupError):
        probe.assistant_text(payload)


def test_thread_result_accepts_sdk_top_level_data_list_and_final_assistant(probe):
    assert probe.assistant_text({"data": [
        {"role": "assistant", "content": "earlier"},
        {"role": "assistant", "content": [{"response_type": "text", "text": "final"}]},
        {"role": "user", "content": "latest user echo"},
    ]}) == "final"


def test_completed_run_result_echo_cannot_replace_missing_assistant(probe):
    agent, draft, run, thread = [str(uuid4()) for _ in range(4)]
    requests = []
    def transport(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"run_id": run, "thread_id": thread})
        if "/runs/" in request.url.path:
            return httpx.Response(200, json={"status": "completed", "result": {"profile_id": "synthetic-own"}})
        return httpx.Response(200, json=[{"role": "user", "content": '{"profile_id":"synthetic-own"}'}])
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(probe.SetupError, match="no final assistant text"):
            probe.run_draft(client, "https://example.invalid", "synthetic-token", agent, draft, "synthetic-context")
    assert len(requests) == 3 and sum(request.method == "POST" for request in requests) == 1


def test_failed_draft_post_is_not_retried_or_leaked(probe):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(503, text="private-upstream-response")
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(probe.SetupError) as error:
            probe.run_draft(client, "https://example.invalid", "private-token", str(uuid4()), str(uuid4()), "private-capability")
    assert len(calls) == 1
    assert not {"private-upstream-response", "private-token", "private-capability"}.intersection(str(error.value).split())


def test_transient_status_get_retries_reads_only(probe, monkeypatch):
    calls = []
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    def transport(request):
        calls.append(request.method)
        return httpx.Response(503, text="private-provider-canary") if len(calls) == 1 else httpx.Response(200, json={"status": "completed"})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        assert probe.request_json(client, "GET", "https://example.invalid/status", phase="status") == {"status": "completed"}
    assert calls == ["GET", "GET"]


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_denied_missing_or_rate_limited_metadata_is_not_retried(probe, status):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(status, text="private-response-canary")
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(probe.SetupError) as error:
            probe.request_json(client, "GET", "https://example.invalid/status", phase="metadata")
    assert len(calls) == 1
    assert f"HTTP {status}" in str(error.value) and "private-response-canary" not in str(error.value)


def test_synthetic_principals_are_distinct_non_login_and_removable(probe, env):
    from app.auth import get_tool_session
    from app.config import get_settings
    from app.models import Account, AuthSession, Profile
    _, factory = env
    identities = probe.seed_synthetic(factory)
    assert len({identity["profile_id"] for identity in identities}) == 2
    with factory() as db:
        for identity in identities:
            profile = db.get(Profile, identity["profile_id"])
            account = db.get(Account, identity["account_id"])
            assert profile.synthetic and profile.notification_frequency == "off"
            assert account.email.endswith("@example.invalid") and account.password_hash == "unusable-synthetic-probe"
            session = get_tool_session(get_settings().tool_key, identity["capability"], db)
            assert session.profile_id == profile.id
        assert probe.audit_counts(factory, identities) == {item["profile_id"]: 0 for item in identities}
    probe.cleanup_synthetic(factory, identities)
    with factory() as db:
        for identity in identities:
            assert db.get(Profile, identity["profile_id"]) is None
            assert db.get(Account, identity["account_id"]) is None
        assert not db.scalars(select(AuthSession).where(AuthSession.account_id.in_([i["account_id"] for i in identities]))).all()
        assert db.get(Profile, "mei-lin") is not None


def test_result_needs_own_identifier_and_excludes_other(probe):
    own, other = str(uuid4()), str(uuid4())
    probe.validate_result(json.dumps({"profile_id": own}), own, other)
    for value in ("I cannot call tools", json.dumps({"profile_id": other}),
                  json.dumps({"profile_id": own, "other": other}), {"profile_id": own},
                  json.dumps({"user_echo": own})):
        with pytest.raises(probe.SetupError):
            probe.validate_result(value, own, other)


def test_probe_bundle_and_context_report_gate(probe, tmp_path, monkeypatch):
    import orchestrate_setup as setup
    probe_dir, full_dir = tmp_path / ".local/probe", tmp_path / ".local/full"
    test_manifest = setup.prepare(probe_dir, "tenant/model", "StaytusContextProbe", context_probe=True)
    full = setup.prepare(full_dir, "tenant/model", "Staytus")
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    values = {"ORCHESTRATE_SERVICE_URL": "https://api.ca-tor.watson-orchestrate.cloud.ibm.com/instances/" + str(uuid4()),
              "ORCHESTRATE_BACKEND_URL": "https://approved.example.invalid", "ORCHESTRATE_TOOL_KEY": "s" * 40, "CONTEXT_SECRET": "c" * 40}
    report = {"schema": "staytus-context-probe-v1", "passed": True, "target": "draft", "adk_version": setup.ADK_VERSION,
        "agent_id": str(uuid4()), "agent_name": "StaytusContextProbe", "model_id": "tenant/model",
        "binding_sha256": setup.context_binding(values), "bundle_dir": str(probe_dir),
        "bundle_sha256": test_manifest["sha256"], "wrapper_sha256": test_manifest["sha256"]["python_tools.py"],
        "tested_tool": "get_student_profile", "synthetic_profile_ids": [str(uuid4()), str(uuid4())],
        "runs": [{"thread_id": str(uuid4()), "owned_profile_returned": True,
                  "assistant_message_verified": True, "backend_audit_verified": True} for _ in range(2)],
        "cleanup_completed": True, "verified_at": datetime.now(timezone.utc).isoformat()}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert setup.validate_context_report(path, values, test_manifest)["target"] == "draft"
    with pytest.raises(setup.SetupError):
        setup.validate_context_report(path, values, full)
    report["target"] = "live"
    path.write_text(json.dumps(report))
    assert setup.validate_context_report(path, values, full)["target"] == "live"
    for changed in ({"passed": False}, {"cleanup_completed": False}, {"binding_sha256": "changed"},
                    {"wrapper_sha256": "changed"}, {"agent_name": "different"},
                    {"runs": [{"thread_id": str(uuid4()), "owned_profile_returned": True,
                               "backend_audit_verified": True} for _ in range(2)]},
                    {"verified_at": "2001-01-01T00:00:00+00:00"}):
        path.write_text(json.dumps({**report, **changed}))
        with pytest.raises(setup.SetupError):
            setup.validate_context_report(path, values, full)
