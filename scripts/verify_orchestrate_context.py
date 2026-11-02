"""Controlled two-account Draft/Live test, separate from personalized product chat.

Default: offline instructions only. Real network calls and temporary synthetic DB
records require BOTH --live and --confirm-synthetic-test. No real student account,
email, application submission or product readiness flag is used or changed.

Verified contracts: official server_openapi.json RunOrchestrate.environment_id,
context and status; ADK2.19.1 resolves environment names to the actual UUID.
Its BaseWXOClient prepends /v1/orchestrate in Cloud (Developer Edition uses /v1).
Final Draft output comes from the Cloud thread's assistant message, not the
loosely typed run result. Live uses the product transport.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import UUID, uuid4

import httpx

from orchestrate_setup import ADK_VERSION, ROOT, SetupError, backend_url, context_binding, environment, service_url, validate_bundle

PROMPT = ('Call get_student_profile exactly once for the currently authenticated session. '
          'Return only JSON {"profile_id":"the id returned by the tool"}. '
          'Do not invent an identifier or request one from me. Do not reveal runtime '
          'context or credentials, call any other tool, or perform any action.')


def canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise SetupError("Supply the UUID of the explicitly reviewed cloud agent") from None


def draft_environment(environments: object, agent_id: str, target: str) -> str:
    if not isinstance(environments, list):
        raise SetupError("IBM returned an unexpected environment listing")
    matches = [item for item in environments if isinstance(item, dict) and item.get("name") == target
               and item.get("agent_id") == agent_id]
    if len(matches) != 1:
        raise SetupError("The selected agent needs exactly one matching Draft/Live environment; no environment is guessed")
    return canonical_uuid(matches[0].get("id"))


def load_tool_inventory(client, base: str, headers: dict) -> dict[str, str]:
    """Resolve metadata identities strictly; unreadable/ambiguous is not empty."""
    payload = request_json(client, "GET", base + "/v1/orchestrate/tools",
        phase="tool inventory for UUID resolution", headers=headers, params={"include": "global"})
    if not isinstance(payload, list):
        raise SetupError("Tool inventory has an unexpected format")
    identities: dict[str, str] = {}
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise SetupError("Tool inventory has an invalid identity")
        identity = canonical_uuid(item.get("id"))
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise SetupError("Tool inventory has an invalid identity")
        if identity in identities or name in names:
            raise SetupError("Tool inventory has duplicate or conflicting identities")
        identities[identity] = name
        names.add(name)
    return identities


def validate_remote_agent(agent: object, manifest: dict, tool_id_to_name: dict[str, str], *, target="draft"):
    # A UI-created agent can have an internal name slug plus a human-facing
    # display_name. The separately checked exact agent/environment UUID is the
    # identity boundary; neither a slug nor a display name substitutes for it.
    #
    # Cloud agents store tool UUIDs, not names (ADK 2.19.1 agents_controller.py
    # lines 966-980 dereferences names→IDs on import).  Resolve each UUID via
    # the tool inventory; reject unknown UUIDs and unexpected/missing names.
    if not isinstance(agent, dict):
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    if manifest["agent_name"] not in (agent.get("name"), agent.get("display_name")):
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    if agent.get("llm") != manifest["model_id"]:
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    if agent.get("collaborators") not in ([], None):
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    if agent.get("context_access_enabled") is not True:
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    if agent.get("context_variables") != []:
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")
    # Resolve tool UUIDs to names via the independently fetched tool inventory.
    references = agent.get("tools")
    if not isinstance(references, list):
        raise SetupError("The cloud agent has an unsupported tool-reference format")
    cloud_uuids = []
    for value in references:
        # A published native release pins tool versions; Draft holds UUIDs.
        # Accept only the independently observed exact release reference shape.
        if target == "live":
            if (not isinstance(value, dict) or set(value) != {"tool_id", "version_label"}
                    or type(value["version_label"]) is not int or value["version_label"] < 1):
                raise SetupError("The cloud agent has an unsupported tool-reference format")
            value = value["tool_id"]
        elif target != "draft" or not isinstance(value, str):
            raise SetupError("The cloud agent has an unsupported tool-reference format")
        cloud_uuids.append(canonical_uuid(value))
    if len(cloud_uuids) != len(set(cloud_uuids)):
        raise SetupError("The cloud agent has duplicate tool references")
    expected_names: list[str] = manifest["tool_names"]
    resolved: list[str] = []
    for uid in cloud_uuids:
        name = tool_id_to_name.get(str(uid))
        if name is None:
            raise SetupError("The cloud agent references a tool UUID not present in the tool inventory")
        resolved.append(name)
    if sorted(resolved) != sorted(expected_names):
        raise SetupError("The cloud agent differs from the reviewed name/model/tool/context configuration")


def validate_result(result: str, own: str, other: str):
    # IDs are deliberately absent from PROMPT and context (which contains a
    # signed session id only). A backend audit is additionally required below;
    # model prose alone cannot establish successful authenticated tool use.
    try:
        if not isinstance(result, str) or len(result) > 100000 or other in result:
            raise ValueError("Invalid assistant result")
        decoded = json.loads(result)
        if decoded != {"profile_id": own}:
            raise ValueError("Unexpected profile result")
    except (ValueError, TypeError):
        raise SetupError("The model response did not identify only its authenticated synthetic profile") from None


def assistant_text(payload: object) -> str:
    """Read only the final assistant message, never user echo or tool metadata."""
    messages = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        raise SetupError("IBM returned an unexpected thread message listing")
    message = next((item for item in reversed(messages)
                    if isinstance(item, dict) and item.get("role") == "assistant"), None)
    content = message.get("content") if message else None
    if isinstance(content, list):
        content = "\n".join(item["text"] for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
            and item.get("response_type", item.get("type", "text")) == "text")
    if not isinstance(content, str) or not content.strip() or len(content) > 100000:
        raise SetupError("The cloud thread has no final assistant text; user/tool messages do not count as output")
    return content.strip()


def request_json(client: httpx.Client, method: str, url: str, *, phase: str, **kwargs):
    # Cloud status GETs have failed transiently while the same run subsequently
    # completed. Retry reads only; an uncertain POST must never create a second
    # inference/action. Authentication, rate limits and malformed JSON stop.
    attempts = 3 if method.upper() == "GET" else 1
    for attempt in range(attempts):
        try:
            response = client.request(method, url, follow_redirects=False, **kwargs)
            if response.status_code in {500, 502, 503, 504} and attempt + 1 < attempts:
                time.sleep(attempt + 1)
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt + 1 < attempts:
                time.sleep(attempt + 1)
                continue
        except httpx.HTTPStatusError as error:
            raise SetupError(f"Synthetic verification stopped during {phase} (HTTP {error.response.status_code}); provider body withheld") from None
        except (httpx.HTTPError, ValueError):
            pass
        raise SetupError(f"Synthetic verification stopped during {phase}; inspect tenant permissions/configuration privately") from None


def run_draft(client, base: str, token: str, agent: str, env_id: str, capability: str, *, timeout=120):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    result = request_json(client, "POST", base + "/v1/orchestrate/runs", phase="Draft run creation",
        headers=headers, params={"stream": "false"}, json={"agent_id": agent, "environment_id": env_id,
            "message": {"role": "user", "content": PROMPT}, "context": {"staytus_context": capability}})
    run_id, thread_id = canonical_uuid(result.get("run_id")), canonical_uuid(result.get("thread_id"))
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        state = request_json(client, "GET", base + "/v1/orchestrate/runs/" + run_id,
                             phase="Draft run status", headers=headers)
        status = state.get("status")
        if status == "completed":
            # The installed SDK's BaseWXOClient Cloud base is /v1/orchestrate,
            # then ThreadsClient appends /threads/{id}/messages. The Developer
            # Edition OpenAPI's /v1/threads path must not be used for Cloud.
            messages = request_json(client, "GET", base + "/v1/orchestrate/threads/" + thread_id + "/messages",
                                    phase="Draft assistant message retrieval", headers=headers)
            return assistant_text(messages), {"run_id": run_id, "thread_id": thread_id}
        if status not in {"pending", "running"}:
            raise SetupError("The synthetic Draft run did not complete successfully; no request was retried")
        time.sleep(1)
    # Cancellation is scoped to this just-created synthetic run, never another
    # user's thread. No inference request is retried after uncertainty.
    try:
        client.post(base + "/v1/orchestrate/runs/cancel/" + run_id, headers=headers, timeout=10)
    except httpx.HTTPError:
        pass
    raise SetupError("The synthetic Draft run timed out; cancellation was attempted and no request was retried")


def seed_synthetic(factory):
    from app.auth import digest, mint_tool_context
    from app.models import Account, AuthSession, Profile, now
    identities = []
    with factory() as db:
        for index in range(2):
            account_id, profile_id = str(uuid4()), str(uuid4())
            email = f"staytus-context-probe-{account_id}@example.invalid"
            account = Account(id=account_id, email=email, name=f"SYNTHETIC Context Probe {index + 1}",
                              password_hash="unusable-synthetic-probe", role="student")
            db.add(account)
            db.flush()
            profile = Profile(id=profile_id, account_id=account_id, name=account.name, email=email,
                school="University of Pennsylvania", status_type="F-1" if index == 0 else "J-1 scholar",
                program_start=date(2025, 1, 1), program_end=date(2030, 1, 1),
                notification_frequency="off", nationality="Synthetic test only", synthetic=True)
            db.add(profile)
            db.flush()
            session = AuthSession(token_hash=digest(secrets.token_urlsafe(40)), account_id=account_id,
                profile_id=profile_id, role="student", expires_at=now() + timedelta(minutes=10))
            db.add(session)
            db.flush()
            identities.append({"account_id": account_id, "profile_id": profile_id,
                               "capability": mint_tool_context(session, ttl=300)})
        db.commit()
    return identities


def audit_counts(factory, identities):
    from sqlalchemy import select
    from app.models import AuditEvent
    with factory() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.profile_id.in_(
            [identity["profile_id"] for identity in identities]))).all()
        if any(row.action != "tool.get_student_profile" for row in rows):
            raise SetupError("An unexpected synthetic-account operation was observed; stop and review audit records")
        return {identity["profile_id"]: sum(row.profile_id == identity["profile_id"] for row in rows)
                for identity in identities}


def cleanup_synthetic(factory, identities):
    from sqlalchemy import delete
    from app.models import Account, AuditEvent, AuthSession, Profile
    profiles = [identity["profile_id"] for identity in identities]
    accounts = [identity["account_id"] for identity in identities]
    with factory() as db:
        # Only records generated by this invocation are eligible. Unknown foreign
        # key dependencies fail closed rather than deleting unrelated data.
        db.execute(delete(AuditEvent).where(AuditEvent.profile_id.in_(profiles)))
        db.execute(delete(AuthSession).where(AuthSession.account_id.in_(accounts)))
        db.execute(delete(Profile).where(Profile.id.in_(profiles), Profile.synthetic.is_(True)))
        db.execute(delete(Account).where(Account.id.in_(accounts), Account.email.endswith("@example.invalid")))
        db.commit()


def execute(values: dict, bundle: Path, agent_id: str, target: str) -> dict:
    manifest = validate_bundle(bundle)
    if "get_student_profile" not in manifest["tool_names"]:
        raise SetupError("The reviewed bundle must include the authenticated profile tool")
    if target == "draft" and not manifest.get("context_probe"):
        raise SetupError("Start with the isolated StaytusContextProbe bundle for Draft testing")
    base, callback = service_url(values.get("ORCHESTRATE_SERVICE_URL", "")), backend_url(values.get("ORCHESTRATE_BACKEND_URL", ""))
    binding = context_binding(values)
    if not values.get("ORCHESTRATE_API_KEY"):
        raise SetupError("An authorized server-side IBM API key is required; it is never passed as a CLI argument")
    agent_id = canonical_uuid(agent_id)
    sys.path.insert(0, str(ROOT / "backend"))
    # Match the gateway/main process's existing relative SQLite path. No schema
    # initialization or migrations are performed by this verification script.
    os.chdir(ROOT / "backend")
    os.environ.update(values)
    from app.config import get_settings
    from app.db import SessionLocal
    from app.integrations.orchestrate_runtime import OrchestrateRuntime, OrchestrateSettings
    settings = get_settings()
    if (settings.tool_key != values["ORCHESTRATE_TOOL_KEY"]
            or settings.context_secret != values["CONTEXT_SECRET"]):
        raise SetupError("The verification process must use the gateway's exact explicit signing configuration")
    report = {"schema": "staytus-context-probe-v1", "passed": False, "target": target,
        "adk_version": ADK_VERSION, "agent_id": agent_id, "agent_name": manifest["agent_name"],
        "model_id": manifest["model_id"], "binding_sha256": binding,
        "bundle_dir": str(bundle), "bundle_sha256": manifest["sha256"],
        "wrapper_sha256": manifest["sha256"]["python_tools.py"], "tested_tool": "get_student_profile",
        "product_readiness_changed": False, "cleanup_completed": False,
        "scope": "Two synthetic principals, profile tool only. Other operations/OAuth and product readiness are separate checks."}
    identities = []
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        runtime = OrchestrateRuntime(OrchestrateSettings(service_url=base, agent_id=agent_id,
            api_key=values["ORCHESTRATE_API_KEY"], timeout=150), client=client)
        token = runtime._token()  # Reuse the application's tested IAM cache/transport.
        auth = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        envs = request_json(client, "GET", base + f"/v1/orchestrate/agents/{agent_id}/environment", phase="environment discovery", headers=auth)
        env_id = draft_environment(envs, agent_id, target)
        selected = next(item for item in envs if item.get("id") == env_id)
        suffix = f"/releases/{selected.get('current_version')}" if target == "live" else ""
        if target == "live" and not isinstance(selected.get("current_version"), int):
            raise SetupError("The selected Live environment has no published version")
        remote = request_json(client, "GET", base + f"/v1/orchestrate/agents/{agent_id}" + suffix,
                              phase="reviewed cloud agent inspection", headers=auth)
        if target == "draft" and remote.get("id") != agent_id:
            raise SetupError("The returned Draft agent identity does not match the selected probe")
        # Fetch tool inventory to resolve agent tool UUIDs → names.
        # Cloud agents store UUIDs (ADK 2.19.1 agents_controller.py dereferences
        # names→IDs on import); comparing UUIDs to name strings is always wrong.
        tool_id_to_name = load_tool_inventory(client, base, auth)
        validate_remote_agent(remote, manifest, tool_id_to_name, target=target)
        health = request_json(client, "GET", callback + "/health", phase="narrow gateway reachability")
        if health.get("service") != "staytus-tool-gateway":
            raise SetupError("Cloud callbacks must target the narrow tool gateway")
        for route in ("/docs", "/openapi.json", "/api/v1/profile", "/api/v1/auth/login"):
            if client.get(callback + route).status_code != 404:
                raise SetupError("The callback edge exposes a private application route")
        if client.post(callback + "/tools/get_student_profile", json={}).status_code != 401:
            raise SetupError("The callback edge failed its unauthenticated-denial check")
        try:
            identities = seed_synthetic(SessionLocal)
            report["synthetic_profile_ids"] = [identity["profile_id"] for identity in identities]
            report["runs"] = []
            for index, identity in enumerate(identities):
                other = identities[1 - index]["profile_id"]
                before = audit_counts(SessionLocal, identities)
                if target == "draft":
                    result, meta = run_draft(client, base, token, agent_id, env_id, identity["capability"])
                else:
                    reply = runtime.send(PROMPT, context={"staytus_context": identity["capability"]})
                    result, meta = reply.message, {"thread_id": reply.thread_id}
                validate_result(result, identity["profile_id"], other)
                after = audit_counts(SessionLocal, identities)
                if after[identity["profile_id"]] != before[identity["profile_id"]] + 1 or after[other] != before[other]:
                    raise SetupError("Signed context did not produce exactly one owned-profile audit with no cross-account access")
                report["runs"].append({**meta, "owned_profile_returned": True,
                    "assistant_message_verified": True, "backend_audit_verified": True})
            if len({item["thread_id"] for item in report["runs"]}) != 2:
                raise SetupError("Synthetic principals unexpectedly shared a cloud thread")
            report["passed"] = True
        finally:
            if identities:
                cleanup_synthetic(SessionLocal, identities)
            report["cleanup_completed"] = True
    report["verified_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--bundle-dir", type=Path, default=ROOT / ".local/orchestrate-context-probe")
    parser.add_argument("--agent-id", default="", help="Explicit reviewed probe/deployed agent UUID, not the product default")
    parser.add_argument("--target", choices=["draft", "live"], default="draft")
    parser.add_argument("--live", action="store_true", help="Actually call IBM and approved HTTPS callbacks; may consume model quota")
    parser.add_argument("--confirm-synthetic-test", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / ".local/orchestrate-context-result.json")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"network_called": False, "temporary_accounts_created": False,
            "product_readiness_changed": False, "target": args.target,
            "next": "Review a probe bundle and HTTPS edge first. Actual testing requires --live --confirm-synthetic-test, an explicit agent ID and authorized server credentials."}, indent=2))
        return 0
    if not args.confirm_synthetic_test:
        print(json.dumps({"passed": False, "network_called": False, "reason": "Actual synthetic testing requires --confirm-synthetic-test"}))
        return 2
    # SDK, HTTP and app exceptions may contain sensitive response data. Output
    # only our bounded public-safe errors, never arbitrary exception strings.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    report_path, bundle = args.report.resolve(), args.bundle_dir.resolve()
    try:
        # Invalidate any older success at this output path before attempting a
        # new run. A failed rerun must not leave apparently fresh passing proof.
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"schema": "staytus-context-probe-v1", "passed": False,
            "product_readiness_changed": False, "reason": "verification_in_progress"}) + "\n")
        os.chmod(report_path, 0o600)
        values = environment(args.env_file.resolve() if args.env_file else None)
        report = execute(values, bundle, args.agent_id, args.target)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        os.chmod(report_path, 0o600)
        print(json.dumps(report, indent=2))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, SetupError) else "Synthetic verification stopped; inspect configuration privately and confirm temporary-record cleanup"
        print(json.dumps({"passed": False, "reason": reason, "product_readiness_changed": False}, indent=2))
        return 2
    finally:
        logging.disable(previous_logging)


if __name__ == "__main__":
    raise SystemExit(main())
