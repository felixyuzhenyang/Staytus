"""Bounded synthetic Live business-tool validation; offline by default.

No final approval, provider write, real mailbox or real student account is used.
Raw provider messages/context/credentials are never persisted in the report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx

from orchestrate_setup import ROOT, SetupError, backend_url, environment, service_url, validate_bundle
from verify_orchestrate_context import (canonical_uuid, draft_environment, load_tool_inventory,
    request_json, seed_synthetic, validate_remote_agent)

READ_TOOLS = ["get_school_adapter", "search_official_policy", "get_policy_version_and_status",
    "calculate_deadline", "list_action_tasks", "get_policy_changes_for_profile",
    "escalate_to_isss", "build_action_plan"]
PROPOSAL_TOOLS = ["propose_profile_update", "create_email_preview", "create_calendar_preview"]
CASE_NAMES = ("read_tools", "proposal_tools", "mail_permission_denial", "multistep_workflow")
EMAIL = {"to": "advisor@example.invalid", "subject": "SYNTHETIC tool validation",
    "body": "This is a synthetic preview only. No email is to be sent."}
CALENDAR = {"title": "SYNTHETIC tool validation", "date": "2030-01-01", "description": "Synthetic preview only.",
    "provider": "export", "reminder_minutes": 1440}
PROFILE_UPDATE = {"nationality": "Synthetic proposal only"}


def tool_trace(payload: object) -> tuple[list[dict], dict[str, list[object]]]:
    """Parse actual assistant step history, never user echoes or final claims."""
    messages = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        raise SetupError("Unexpected cloud thread message shape")
    calls, results = [], {}
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for step in message.get("step_history") or []:
            for detail in step.get("step_details") or []:
                for call in detail.get("tool_calls") or []:
                    name, args = call.get("name"), call.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            raise SetupError("Unexpected cloud tool argument encoding") from None
                    if not isinstance(name, str) or not isinstance(args, dict):
                        raise SetupError("Unexpected cloud tool call shape")
                    if {"context", "staytus_context", "profile_id", "account_id", "user_id"}.intersection(args):
                        raise SetupError("A model-supplied identity/context argument was observed")
                    if isinstance(args.get("payload"), dict) and "_connector_target" in args["payload"]:
                        raise SetupError("A model-supplied connector target was observed")
                    calls.append({"name": name, "args": args})
                if detail.get("type") == "tool_response":
                    name, content = detail.get("name"), detail.get("content")
                    if not isinstance(name, str):
                        raise SetupError("Unexpected tool response identity")
                    if isinstance(content, str):
                        try:
                            content = json.loads(content)
                        except ValueError:
                            pass
                    results.setdefault(name, []).append(content)
    return calls, results


def case_spec(name: str, policy_id: str, planned_date: str) -> tuple[list[str], str]:
    if name == "read_tools":
        expected = READ_TOOLS
        detail = ("get_school_adapter(); search_official_policy(query=\"\", include_pending=true); "
            f"get_policy_version_and_status(policy_version_id={json.dumps(policy_id)}); "
            "calculate_deadline(workflow=\"program_extension\"); list_action_tasks(); "
            "get_policy_changes_for_profile(); escalate_to_isss(reason=\"SYNTHETIC integration handoff only\"); "
            "build_action_plan().")
    elif name == "proposal_tools":
        expected = PROPOSAL_TOOLS
        detail = (f"propose_profile_update(payload={json.dumps(PROFILE_UPDATE)}); "
            f"create_email_preview(payload={json.dumps(EMAIL)}); create_calendar_preview(payload={json.dumps(CALENDAR)}). "
            "Create proposals only. Do not approve, execute, send, update the profile, or write a calendar.")
    elif name == "mail_permission_denial":
        expected = ["read_recent_official_messages"]
        detail = ("read_recent_official_messages(provider=\"google\", limit=1). This synthetic account has not "
            "enabled assistant mailbox access. Report the permission denial; never bypass it or retry.")
    elif name == "multistep_workflow":
        expected = ["get_student_profile", "search_official_policy", "calculate_deadline", "create_calendar_preview"]
        calendar = {"title": "SYNTHETIC preparation reminder", "date": planned_date,
            "description": "Staytus internal preparation buffer, not a government filing deadline. Synthetic preview only.",
            "provider": "export", "reminder_minutes": 1440}
        detail = ("In this exact order: get_student_profile(); search_official_policy(query=\"\", include_pending=true); "
            "calculate_deadline(workflow=\"program_extension\"); then create_calendar_preview with payload "
            f"{json.dumps(calendar)}. Check that its date equals the returned program_extension planning date. "
            "Preserve pending-review labels. Do not approve or execute the calendar preview.")
    else:
        raise SetupError("Unknown reviewed synthetic case")
    prompt = ("Run this bounded SYNTHETIC integration check for the current authenticated account. "
        "Call each requested tool exactly once, never retry a failed tool. No other tools except "
        "get_student_profile once if required by your instructions. Never request or expose identity credentials "
        "or runtime context. Do not make a status/eligibility determination. " + detail +
        ' Finish with only concise JSON {"completed_tools":[names],"errors":[short errors]}; '
        "do not repeat policy text, profile identifiers, context or credentials in your final answer.")
    return expected, prompt


def _require(condition: bool, reason: str):
    if not condition:
        raise SetupError(reason)


def payload_digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_connector_target(kind: str, payload: dict, expected_target):
    """A target is trusted only when derived from this synthetic account's DB.

    Missing connection has explicit null identity fields, never a wildcard that may
    silently select a mailbox/calendar connected after the user saw a preview.
    """
    remote = kind == "email" or (kind == "calendar" and payload.get("provider", "export") != "export")
    if remote:
        _require(isinstance(expected_target, dict)
            and set(expected_target) == {"provider", "connection_id", "account_label"},
            "Expected connector identity was not derived in the reviewed server shape")
        _require("_connector_target" in payload and payload["_connector_target"] == expected_target,
            "Proposal connector target differs from the server-owned account binding")
    else:
        _require("_connector_target" not in payload, "Local/export proposal unexpectedly contains a connector target")


def validate_tool(name: str, value: object, data: dict, case: str):
    _require(isinstance(value, dict), f"{name}: tool did not return a structured backend response")
    if name == "read_recent_official_messages":
        _require(value.get("error") == "tool_permission_required" and "messages" not in value,
            "Mailbox tool did not explicitly deny missing assistant permission")
        return
    _require("error" not in value, f"{name}: backend tool returned an error")
    own, other = data["profile_id"], data["other_profile_id"]
    _require(other not in json.dumps(value), f"{name}: other-account identifier in tool output")
    if name == "get_student_profile":
        _require(value.get("id") == own and value.get("synthetic") is True, "Wrong owned profile returned")
    elif name == "get_school_adapter":
        _require(value.get("id") == "penn" and value.get("supported") is True, "School adapter result mismatch")
    elif name == "search_official_policy":
        rows = value.get("policies")
        _require(isinstance(rows, list) and bool(rows), "No real policy evidence returned")
        _require(all(row.get("fixture") is False and row.get("citations") and row.get("captured_at")
            and isinstance(row.get("review_required"), bool) and row.get("source_url", "").startswith("https://")
            for row in rows), "Policy result lacks actual citation/review provenance")
    elif name == "get_policy_version_and_status":
        _require(value.get("policy_version_id") == data["policy_id"] and value.get("fixture") is False
            and value.get("citations") and isinstance(value.get("review_required"), bool), "Policy-version result mismatch")
    elif name in {"calculate_deadline", "build_action_plan"}:
        rows = value.get("deadlines")
        _require(isinstance(rows, list) and any(row.get("workflow") == "program_extension"
            and row.get("date") == data["planned_date"] and row.get("is_planning_buffer") is True for row in rows),
            "Planning result differs from deterministic internal target")
        _require(all(row.get("id", "").startswith(own + "-") for row in rows), "Planning result ownership mismatch")
        if name == "build_action_plan":
            _require(bool(value.get("tasks")), "Action plan has no tasks")
    elif name == "list_action_tasks":
        _require(bool(value.get("tasks")) and all(row.get("id", "").startswith(own + "-")
            for row in value["tasks"]), "Task ownership/result mismatch")
    elif name == "get_policy_changes_for_profile":
        rows = value.get("changes")
        _require(isinstance(rows, list) and len(rows) == 1 and rows[0].get("id") == data["notification_id"],
            "Profile change notification isolation mismatch")
    elif name == "escalate_to_isss":
        _require(value.get("reason") == "SYNTHETIC integration handoff only"
            and "no message sent" in value.get("action", ""), "Adviser handoff result mismatch")
    elif name in PROPOSAL_TOOLS:
        kind = {"propose_profile_update": "profile_update", "create_email_preview": "email", "create_calendar_preview": "calendar"}[name]
        _require(value.get("kind") == kind and value.get("status") == "PROPOSED" and value.get("receipt") is None,
            "Proposal was missing or unexpectedly executed")
        _require(value.get("profile_version") == data["profile_version"],
            "Proposal is not bound to the current synthetic profile version")
        expected = {"profile_update": PROFILE_UPDATE, "email": EMAIL, "calendar": CALENDAR}[kind]
        if name == "create_calendar_preview" and case == "multistep_workflow":
            expected = {"title": "SYNTHETIC preparation reminder", "date": data["planned_date"],
                "description": "Staytus internal preparation buffer, not a government filing deadline. Synthetic preview only.",
                "provider": "export", "reminder_minutes": 1440}
        payload = value.get("payload")
        _require(isinstance(payload, dict), "Proposal payload is not structured")
        expected_target = data.get("connector_targets", {}).get(kind,
            {"provider": None if kind == "email" else payload.get("provider"),
             "connection_id": None, "account_label": None})
        validate_connector_target(kind, payload, expected_target)
        if kind == "email" or (kind == "calendar" and payload.get("provider", "export") != "export"):
            _require("target_account" in value and value["target_account"] == expected_target["account_label"],
                "Displayed target account differs from the hashed server binding")
        business = {key: item for key, item in payload.items() if key != "_connector_target"}
        _require(business == expected, "Proposal content differs from exact reviewed synthetic payload")
        _require(value.get("payload_hash") == payload_digest(payload), "Proposal hash does not bind full content and connector target")


def validate_trace(calls: list[dict], responses: dict, expected: list[str], data: dict, case: str):
    names = [call["name"] for call in calls]
    allowed = set(expected) | {"get_student_profile"}
    _require(set(names).issubset(allowed), "Unrequested tool call observed")
    counts = Counter(names)
    _require(all(counts[name] == 1 for name in expected), "Requested tool missing or repeated")
    _require(counts["get_student_profile"] <= 1, "Profile tool repeated")
    if case == "multistep_workflow":
        _require(names == expected, "Multistep tool order did not match the reviewed workflow")
    for name in counts:
        _require(len(responses.get(name, [])) == counts[name], "Actual tool response missing from cloud trace")
        for result in responses[name]:
            validate_tool(name, result, data, case)
    return dict(counts)


def seed_case_data(factory, identities):
    from sqlalchemy import select
    from app.models import AuthSession, Notification, PolicyChunk, PolicyVersion, Profile, now
    from app.rules import adapter_for
    from app.services import active_rule
    data = []
    with factory() as db:
        rows = db.scalars(select(PolicyVersion).join(PolicyChunk).where(PolicyVersion.fixture.is_(False),
            PolicyChunk.superseded.is_(False))).unique().all()
        policy = next((row for row in rows if "F-1" in row.visa_types), None)
        _require(policy is not None, "The check needs an existing real F-1 public-source policy capture")
        for index, identity in enumerate(identities):
            profile = db.get(Profile, identity["profile_id"])
            profile.travel_date = date(2030, 2, 1)
            session = db.scalar(select(AuthSession).where(AuthSession.account_id == identity["account_id"]))
            session.expires_at = now() + timedelta(minutes=30)
            notification = Notification(profile_id=profile.id, title="SYNTHETIC tool validation",
                message="Synthetic private notification for integration isolation only.",
                data={"synthetic": True, "test_marker": str(uuid4())})
            db.add(notification)
            db.flush()
            targets = adapter_for(profile).deadlines(profile, active_rule(db, include_fixtures=True))
            target = next(row["date"] for row in targets if row["workflow"] == "program_extension")
            data.append({**identity, "other_profile_id": identities[1 - index]["profile_id"],
                "notification_id": notification.id, "policy_id": policy.id, "planned_date": target,
                "profile_version": profile.version, "nationality": profile.nationality})
        db.commit()
    return data


def prepare_mail_denial(factory, identity):
    # Added only immediately before the denial case. Earlier email proposals
    # therefore have a genuinely absent provider target bound as explicit null.
    from app.integrations.connection_models import MailAgentPermission, ProviderConnection
    with factory() as db:
        db.add(ProviderConnection(account_id=identity["account_id"], provider="google",
            encrypted_tokens="UNUSABLE_SYNTHETIC_DENIAL_TEST_ONLY",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"]))
        db.add(MailAgentPermission(account_id=identity["account_id"], provider="google", enabled=False))
        db.commit()


def owned_state(factory, data):
    from sqlalchemy import select
    from app.models import Approval, AuditEvent, Profile
    with factory() as db:
        result = {}
        for identity in data:
            profile = db.get(Profile, identity["profile_id"])
            audits = db.scalars(select(AuditEvent).where(AuditEvent.profile_id == profile.id)).all()
            approvals = db.scalars(select(Approval).where(Approval.profile_id == profile.id)).all()
            _require(profile.version == identity["profile_version"] and profile.nationality == identity["nationality"],
                "A synthetic profile was changed instead of merely proposed")
            _require(all(row.status == "PROPOSED" and row.receipt is None for row in approvals),
                "A synthetic approval was unexpectedly executed")
            _require(all(row.profile_version == identity["profile_version"]
                and row.payload_hash == payload_digest(row.payload) for row in approvals),
                "Owned proposal lost its full content/target/profile-version binding")
            _require(all(row.action.startswith("tool.") or row.action == "approval.proposed" for row in audits),
                "Unexpected synthetic-account mutation in audit")
            result[profile.id] = {"audits": Counter(row.action for row in audits),
                "approvals": {row.id: {"kind": row.kind, "payload": row.payload} for row in approvals}}
        return result


def validate_audits(before: dict, after: dict, counts: dict, data: dict, responses: dict):
    own, other = data["profile_id"], data["other_profile_id"]
    _require(after[other] == before[other], "Other synthetic account changed during this call")
    delta = after[own]["audits"] - before[own]["audits"]
    expected = Counter({"tool." + name: count for name, count in counts.items()
        if name != "read_recent_official_messages"})
    proposals = sum(counts.get(name, 0) for name in PROPOSAL_TOOLS)
    if proposals:
        expected["approval.proposed"] = proposals
    _require(delta == expected, "Backend audits do not match the actual cloud tool calls")
    _require(len(after[own]["approvals"]) - len(before[own]["approvals"]) == proposals,
        "Proposal record count mismatch")
    returned = {value["id"]: {"kind": value["kind"], "payload": value["payload"]}
        for name in PROPOSAL_TOOLS for value in responses.get(name, [])}
    created = {key: value for key, value in after[own]["approvals"].items()
        if key not in before[own]["approvals"]}
    _require(returned == created, "Returned proposals differ from owned database records")


def cleanup(factory, identities):
    from sqlalchemy import delete, select
    from app.models import Account, Approval, AuditEvent, AuthSession, DeadlineResult, Notification, Profile
    from app.chat_models import Conversation
    from app.integrations.connection_models import MailAgentPermission, OAuthAttempt, ProviderConnection
    profiles, accounts = [row["profile_id"] for row in identities], [row["account_id"] for row in identities]
    with factory() as db:
        actual = db.scalars(select(Profile).where(Profile.id.in_(profiles))).all()
        _require(len(actual) == len(profiles) and all(row.synthetic and row.account_id in accounts for row in actual),
            "Refuse cleanup of unverified synthetic ownership")
        for model in [Approval, DeadlineResult, Notification, AuditEvent]:
            db.execute(delete(model).where(model.profile_id.in_(profiles)))
        for model in [Conversation, MailAgentPermission, OAuthAttempt, ProviderConnection, AuthSession]:
            db.execute(delete(model).where(model.account_id.in_(accounts)))
        db.execute(delete(Profile).where(Profile.id.in_(profiles), Profile.synthetic.is_(True)))
        db.execute(delete(Account).where(Account.id.in_(accounts), Account.email.endswith("@example.invalid")))
        db.commit()


def run(values: dict, bundle: Path, agent_id: str, report: dict, save, cases=CASE_NAMES):
    manifest = validate_bundle(bundle)
    _require(set(manifest["tool_names"]) == set(READ_TOOLS + PROPOSAL_TOOLS +
        ["get_student_profile", "read_recent_official_messages"]), "Unexpected reviewed business tool surface")
    base, edge = service_url(values.get("ORCHESTRATE_SERVICE_URL", "")), backend_url(values.get("ORCHESTRATE_BACKEND_URL", ""))
    agent_id = canonical_uuid(agent_id)
    _require(agent_id == values.get("ORCHESTRATE_AGENT_ID"), "Explicit main Agent differs from server configuration")
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT / "backend")
    os.environ.update(values)
    from app.auth import mint_tool_context
    from app.db import SessionLocal
    from app.models import AuthSession
    from sqlalchemy import select
    from app.integrations.orchestrate_runtime import OrchestrateRuntime, OrchestrateSettings
    identities = []
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        runtime = OrchestrateRuntime(OrchestrateSettings(service_url=base, agent_id=agent_id,
            api_key=values.get("ORCHESTRATE_API_KEY", ""), timeout=150), client=client)
        headers = {"Authorization": "Bearer " + runtime._token(), "Accept": "application/json"}
        envs = request_json(client, "GET", base + f"/v1/orchestrate/agents/{agent_id}/environment",
            phase="business Live environment", headers=headers)
        live_id = draft_environment(envs, agent_id, "live")
        live = next(row for row in envs if row.get("id") == live_id)
        _require(type(live.get("current_version")) is int, "Main Agent has no published version")
        remote = request_json(client, "GET", base + f"/v1/orchestrate/agents/{agent_id}/releases/{live['current_version']}",
            phase="business Live release", headers=headers)
        validate_remote_agent(remote, manifest, load_tool_inventory(client, base, headers), target="live")
        health = request_json(client, "GET", edge + "/health", phase="business tool gateway")
        _require(health.get("service") == "staytus-tool-gateway", "Approved callback is not the narrow gateway")
        report.update(cloud_configuration_verified=True, agent_id=agent_id, live_version=live["current_version"])
        save()
        try:
            identities = seed_synthetic(SessionLocal)
            report["temporary_records_created"] = True
            data = seed_case_data(SessionLocal, identities)
            report["synthetic_profile_ids"] = [row["profile_id"] for row in data]
            for name in cases:
                identity = data[1 if name == "multistep_workflow" else 0]
                if name == "mail_permission_denial":
                    prepare_mail_denial(SessionLocal, identity)
                expected, prompt = case_spec(name, identity["policy_id"], identity["planned_date"])
                case = {"case": name, "passed": False, "expected_tools": expected, "phase": "prepared"}
                report["cases"].append(case)
                before = owned_state(SessionLocal, data)
                with SessionLocal() as db:
                    session = db.scalar(select(AuthSession).where(AuthSession.account_id == identity["account_id"]))
                    capability = mint_tool_context(session, ttl=300)
                case["phase"] = "inference_submitting"
                report["model_calls_submitted"] += 1
                save()
                # No retry of inference/actions, including on uncertain failures.
                reply = runtime.send(prompt, context={"staytus_context": capability})
                case.update(thread_id=canonical_uuid(reply.thread_id), phase="response_received")
                save()
                messages = request_json(client, "GET", base + f"/v1/orchestrate/threads/{reply.thread_id}/messages",
                    phase="business tool trace", headers=headers)
                _require(capability not in reply.message and capability not in json.dumps(
                    [m.get("step_history") for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]),
                    "Runtime capability appeared in model/tool-visible trace")
                calls, results = tool_trace(messages)
                case["observed_tool_calls"] = dict(Counter(call["name"] for call in calls))
                case["tool_checks"] = {}
                for tool in expected:
                    try:
                        _require(case["observed_tool_calls"].get(tool) == 1 and len(results.get(tool, [])) == 1,
                            "Requested tool missing/repeated or response missing")
                        validate_tool(tool, results[tool][0], identity, name)
                        case["tool_checks"][tool] = {"result_semantics_verified": True}
                    except SetupError as error:
                        case["tool_checks"][tool] = {"result_semantics_verified": False, "reason": str(error)}
                save()
                counts = validate_trace(calls, results, expected, identity, name)
                after = owned_state(SessionLocal, data)
                validate_audits(before, after, counts, identity, results)
                case.update(passed=True, phase="verified", called_tools=counts,
                    backend_audits_verified=True, other_account_untouched=True,
                    result_semantics_verified=True, mailbox_access_denied=name == "mail_permission_denial")
                save()
            report["passed"] = all(row["passed"] for row in report["cases"])
            report["verified_business_tools"] = sorted(set().union(*(set(row["called_tools"]) for row in report["cases"])))
            _require(len({row["thread_id"] for row in report["cases"]}) == len(cases), "Cases shared a cloud thread")
        finally:
            if identities:
                cleanup(SessionLocal, identities)
            report["cleanup_completed"] = True
            save()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--bundle-dir", type=Path, default=ROOT / ".local/orchestrate-prepared")
    p.add_argument("--agent-id", default="")
    p.add_argument("--live", action="store_true")
    p.add_argument("--confirm-synthetic-test", action="store_true")
    p.add_argument("--case", choices=CASE_NAMES, action="append", dest="selected_cases",
        help="Explicitly select a previously untested independent case; never resubmit an uncertain request")
    p.add_argument("--report", type=Path, default=ROOT / ".local/orchestrate-business-tools-result.json")
    args = p.parse_args(argv)
    cases = tuple(name for name in CASE_NAMES if name in (args.selected_cases or CASE_NAMES))
    if not args.live:
        print(json.dumps({"network_called": False, "cases": cases, "maximum_model_calls": len(cases),
            "next": "Review the fixed synthetic scope, then use --live --confirm-synthetic-test with an explicit server env and Agent UUID."}))
        return 0
    if not args.confirm_synthetic_test or args.env_file is None:
        print(json.dumps({"passed": False, "network_called": False, "reason": "Explicit env file and --confirm-synthetic-test required"}))
        return 2
    path, bundle = args.report.resolve(), args.bundle_dir.resolve()
    report = {"schema": "staytus-business-tools-probe-v1", "passed": False, "cases": [],
        "maximum_model_calls": len(cases), "model_calls_submitted": 0,
        "temporary_records_created": False, "real_student_data_used": False,
        "real_provider_action_used": False, "cleanup_completed": False, "product_readiness_changed": False}
    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        path.chmod(0o600)
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        save()
        run(environment(args.env_file.resolve()), bundle, args.agent_id, report, save, cases)
        report["verified_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 2
    except Exception as error:
        report["passed"] = False
        report["reason"] = str(error) if isinstance(error, SetupError) else "Business verification stopped; inspect configuration privately"
        report["failure_class"] = type(error).__name__
        save()
        print(json.dumps(report, indent=2))
        return 2
    finally:
        logging.disable(previous_logging)


if __name__ == "__main__":
    raise SystemExit(main())
