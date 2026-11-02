"""Read-only tool-chain preflight for the Staytus Orchestrate deployment.

Distinguishes four failure categories without any write, import, deployment,
model call or credential-value retrieval:

  1. Local configuration/assets missing (env vars absent, no bundle, source errors).
  2. Authentication rejected (IAM 401) vs authoring-metadata access_denied (403)
     from an existing tenant.
  3. staytus_backend connection absent (404) vs access_denied (403); Draft and
     Live credentials_entered states reported separately.  403 means insufficient
     metadata permission, never absent.  credentials_entered=True proves entry
     only, not validity.  Tools are additionally checked to bind APP_ID to the
     exact connection UUID returned by the GET, not merely the APP_ID key.
  4. Wrapper tools present in cloud vs absent; Agent tool UUIDs resolved to
     names via the tool inventory (fetched once); duplicates and unknowns rejected.

Offline by default.  Network requires --preflight and an explicit env file.
Only IAM + metadata GETs and an optional gateway health GET are used.
No credential values, bearer tokens, response bodies or personal data are printed.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from orchestrate_setup import (
    APP_ID, ROOT, SetupError,
    backend_url, service_url, tool_names, validate_bundle,
)

_REQUIRED_VARS = [
    "ORCHESTRATE_SERVICE_URL",
    "ORCHESTRATE_API_KEY",
    "ORCHESTRATE_BACKEND_URL",
    "ORCHESTRATE_TOOL_KEY",
    "CONTEXT_SECRET",
]
_AUTHORING_VAR = "ORCHESTRATE_AUTHORING_API_KEY"

# ---------------------------------------------------------------------------
# Offline checks
# ---------------------------------------------------------------------------

def local_config_check(values: dict[str, str]) -> dict[str, Any]:
    """Report which required variables are set; never print their values."""
    missing = [n for n in _REQUIRED_VARS if not values.get(n)]
    invalid = []
    for name, validator in (("ORCHESTRATE_SERVICE_URL", service_url),
                            ("ORCHESTRATE_BACKEND_URL", backend_url)):
        if values.get(name):
            try:
                validator(values[name])
            except (SetupError, TypeError):
                invalid.append(name)
    for name in ("CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY"):
        value = values.get(name, "")
        if (not isinstance(value, str) or len(value) < 32
                or any(not 33 <= ord(char) <= 126 for char in value)):
            invalid.append(name)
    if values.get("CONTEXT_SECRET") and values.get("CONTEXT_SECRET") == values.get("ORCHESTRATE_TOOL_KEY"):
        invalid.extend(["CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY"])
    authoring = bool(values.get(_AUTHORING_VAR))
    return {
        "missing_variables": missing,
        "invalid_variables": sorted(set(invalid)),
        "configuration_valid": not missing and not invalid,
        "authoring_key_present": authoring,
        "credential_source": (
            "separate_authoring_key" if authoring
            else ("runtime_key_fallback" if values.get("ORCHESTRATE_API_KEY") else "none")
        ),
    }


def local_assets_check(bundle: Path | None) -> dict[str, Any]:
    """Verify local bundle integrity with no network."""
    if bundle is None or not (bundle / "manifest.json").is_file():
        return {"bundle_present": False, "bundle_valid": False, "tool_names": [],
                "reason": "no_bundle"}
    try:
        m = validate_bundle(bundle)
        return {"bundle_present": True, "bundle_valid": True,
                "agent_name": m.get("agent_name"), "model_id": m.get("model_id"),
                "tool_names": m.get("tool_names", []),
                "chat_only": m.get("chat_only", False),
                "context_probe": m.get("context_probe", False)}
    except SetupError as exc:
        return {"bundle_present": True, "bundle_valid": False,
                "tool_names": [], "reason": str(exc)}


def _resolve_name_constants(tree: ast.Module) -> dict[str, str]:
    """Resolve module-level simple string assignments: NAME = "literal".

    Only accepts ast.Constant string values; no eval.  Used to resolve
    Name references like APP_ID = "staytus_backend" so that
    CREDENTIALS = [{"app_id": APP_ID, ...}] can be validated correctly.
    """
    constants: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            constants[node.targets[0].id] = node.value.value
    return constants


def _resolve_credentials_app_id(tree: ast.Module,
                                  name_constants: dict[str, str]) -> str | None:
    """Return the app_id from the module-level CREDENTIALS list assignment, or None.

    Accepts dict literals with string constant or Name-resolved values for app_id:
        CREDENTIALS = [{"app_id": APP_ID, ...}]   # Name → resolved constant
        CREDENTIALS = [{"app_id": "staytus_backend", ...}]  # direct string
    No eval; only safe AST constant/Name resolution.
    """
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "CREDENTIALS"
                and isinstance(node.value, ast.List)):
            continue
        for elt in node.value.elts:
            if not isinstance(elt, ast.Dict):
                continue
            for k, v in zip(elt.keys, elt.values):
                if not (isinstance(k, ast.Constant) and k.value == "app_id"):
                    continue
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    return v.value
                if isinstance(v, ast.Name):
                    resolved = name_constants.get(v.id)
                    if isinstance(resolved, str):
                        return resolved
    return None


def wrapper_binding_check() -> dict[str, Any]:
    """Verify ADK tool contracts offline using AST-only inspection.

    Checks each @tool-decorated function for:
      - context parameter present
      - AgentRun annotation present and recognised (absence → all_bindings_valid=False)
      - expected_credentials references the CREDENTIALS constant whose app_id
        resolves to APP_ID via the module-level assignment (no eval, safe only)
    """
    source_path = ROOT / "orchestrate/python_tools.py"
    try:
        src = source_path.read_text()
        tree = ast.parse(src)
    except (OSError, SyntaxError) as exc:
        return {"source_present": False, "all_bindings_valid": False, "reason": str(exc)}

    try:
        names = tool_names(source_path)
    except SetupError as exc:
        return {"source_present": True, "all_bindings_valid": False, "reason": str(exc)}

    name_constants = _resolve_name_constants(tree)
    cred_app_id = _resolve_credentials_app_id(tree, name_constants)

    missing_context: list[str] = []
    missing_agent_run: list[str] = []
    unknown_agent_run: list[str] = []
    missing_credential: list[str] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        is_tool = any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "tool"
            for d in node.decorator_list
        )
        if not is_tool:
            continue
        fn = node.name

        # context parameter + AgentRun annotation
        ctx_arg = next((a for a in node.args.args if a.arg == "context"), None)
        if ctx_arg is None:
            missing_context.append(fn)
        else:
            ann = ctx_arg.annotation
            if ann is None:
                unknown_agent_run.append(fn)   # missing annotation → invalid
            elif not (isinstance(ann, ast.Name) and ann.id == "AgentRun"):
                missing_agent_run.append(fn)

        # expected_credentials must resolve to CREDENTIALS with app_id == APP_ID,
        # or be an inline list literal with the same.
        has_cred = False
        for d in node.decorator_list:
            if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                    and d.func.id == "tool"):
                continue
            for kw in d.keywords:
                if kw.arg != "expected_credentials":
                    continue
                val = kw.value
                if isinstance(val, ast.Name) and val.id == "CREDENTIALS":
                    has_cred = (cred_app_id == APP_ID)
                elif isinstance(val, ast.List):
                    for elt in val.elts:
                        if not isinstance(elt, ast.Dict):
                            continue
                        for k, v in zip(elt.keys, elt.values):
                            if not (isinstance(k, ast.Constant) and k.value == "app_id"):
                                continue
                            if isinstance(v, ast.Constant) and v.value == APP_ID:
                                has_cred = True
                            elif isinstance(v, ast.Name):
                                resolved = name_constants.get(v.id)
                                if resolved == APP_ID:
                                    has_cred = True
        if not has_cred:
            missing_credential.append(fn)

    # unknown_agent_run also invalidates: absence means the binding is unverified.
    valid = not (missing_context or missing_agent_run or unknown_agent_run
                 or missing_credential)
    return {
        "source_present": True,
        "tool_count": len(names),
        "tool_names": names,
        "all_bindings_valid": valid,
        "missing_context_param": missing_context,
        "missing_agent_run_annotation": missing_agent_run,
        "unknown_agent_run_annotation": unknown_agent_run,
        "missing_credential_binding": missing_credential,
    }


# ---------------------------------------------------------------------------
# Network helpers (explicit --preflight only)
# ---------------------------------------------------------------------------

def _safe_uuid(value: object) -> str | None:
    try:
        return str(UUID(str(value)))
    except Exception:  # noqa: BLE001
        return None


def _safe_tool_name(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,199}", value) else None


def _iam_token(client: Any, api_key: str) -> tuple[str, str]:
    """Return (token, status).  Status: 'ok'|'auth_rejected'|'auth_error'."""
    try:
        resp = client.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                  "apikey": api_key},
            headers={"Accept": "application/json"},
            timeout=20,
            follow_redirects=False,
        )
        if resp.status_code == 401:
            return "", "auth_rejected"
        resp.raise_for_status()
        token = resp.json().get("access_token", "")
        valid = isinstance(token, str) and 0 < len(token) <= 16384 and all(33 <= ord(c) <= 126 for c in token)
        return (token, "ok") if valid else ("", "auth_error")
    except Exception:  # noqa: BLE001
        return "", "auth_error"


def _metadata_get(client: Any, url: str, token: str) -> tuple[Any, str]:
    """Authenticated GET; returns (parsed_body_or_None, status_label).

    Status labels: 'ok'|'auth_rejected'|'access_denied'|'not_found'|'error'.
    Response bodies are consumed only for status/structure; never forwarded raw.
    """
    try:
        resp = client.get(
            url,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            timeout=20,
            follow_redirects=False,
        )
        if resp.status_code == 401:
            return None, "auth_rejected"
        if resp.status_code == 403:
            return None, "access_denied"
        if resp.status_code == 404:
            return None, "not_found"
        resp.raise_for_status()
        return resp.json(), "ok"
    except Exception:  # noqa: BLE001
        return None, "error"


# ---------------------------------------------------------------------------
# Per-resource checks
# ---------------------------------------------------------------------------

def _check_connection(client: Any, base: str, token: str) -> tuple[dict[str, Any], str | None]:
    """Check staytus_backend connection existence and per-environment entry.

    Returns (result_dict, connection_id_or_None).
    connection_id is kept private — never exposed in output; used only internally
    to validate tool binding UUIDs.

    GET /v1/orchestrate/connections/applications?app_id=APP_ID
      → {"connection_id": ..., "app_id": ...}   (404 when absent)

    GET /v1/orchestrate/connections/applications?include_details=true
      → {"applications": [{app_id, environment, credentials_entered: bool|None, ...}]}
      Only credentials_entered=True counts; None/absent → 'unknown'.
    """
    conn_url = base + f"/v1/orchestrate/connections/applications?app_id={APP_ID}"
    conn_body, conn_status = _metadata_get(client, conn_url, token)

    result: dict[str, Any] = {"http_status": conn_status,
        "draft_credentials_entered": "unknown", "live_credentials_entered": "unknown"}

    if conn_status == "not_found":
        result["draft_credentials_entered"] = "absent"
        result["live_credentials_entered"] = "absent"
        return result, None

    if conn_status != "ok":
        # 403 = access_denied (not absent); auth_rejected; error
        result["draft_credentials_entered"] = "unknown"
        result["live_credentials_entered"] = "unknown"
        if conn_status == "access_denied":
            result["note"] = (
                "403 means insufficient metadata permission, not absent; "
                "review the authorized authoring role and instance scope"
            )
        return result, None

    # Validate app_id in response matches; extract connection_id privately.
    connection_id = _safe_uuid(conn_body.get("connection_id")) if isinstance(conn_body, dict) else None
    if not isinstance(conn_body, dict) or conn_body.get("app_id") != APP_ID or not connection_id:
        result.update(http_status="invalid_response", identity_verified=False,
                      reason="connection_identity_unknown")
        return result, None
    result["identity_verified"] = True

    # Per-environment credentials_entered via list endpoint.
    list_url = base + "/v1/orchestrate/connections/applications?include_details=true"
    list_body, list_status = _metadata_get(client, list_url, token)
    envs: dict[str, str] = {"draft": "unknown", "live": "unknown"}
    rows = list_body.get("applications") if isinstance(list_body, dict) else None
    result["credential_metadata_status"] = list_status if list_status != "ok" else (
        "ok" if isinstance(rows, list) else "invalid_response")
    if list_status == "ok" and isinstance(rows, list):
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or row.get("app_id") != APP_ID:
                continue
            env_name = str(row.get("environment") or "").lower()
            entered = row.get("credentials_entered")
            if env_name in envs:
                if env_name in seen or (row.get("connection_id") is not None
                        and _safe_uuid(row["connection_id"]) != connection_id):
                    envs[env_name] = "unknown"
                    result["credential_metadata_status"] = "ambiguous_environment"
                    seen.add(env_name)
                    continue
                seen.add(env_name)
                scheme, preference = row.get("security_scheme"), row.get("preference")
                compatible = "unknown" if scheme is None or preference is None else (
                    scheme == "key_value_creds" and preference == "team")
                result[f"{env_name}_configuration_compatible"] = compatible
                if compatible is False:
                    envs[env_name] = "unknown"
                    continue
                if entered is True:
                    envs[env_name] = "entered"
                elif entered is False:
                    envs[env_name] = "not_entered"
                # None → stays "unknown"

    result["draft_credentials_entered"] = envs["draft"]
    result["live_credentials_entered"] = envs["live"]
    return result, connection_id


def _build_tool_inventory(body: Any) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Build (name→id, id→name, duplicate_names) from a raw tools-list response.

    Ambiguous or malformed inventories never expose a usable lookup map.
    """
    name_to_id: dict[str, str] = {}
    id_to_name: dict[str, str] = {}
    duplicate_names: list[str] = []
    duplicate_ids: list[str] = []
    if not isinstance(body, list):
        return name_to_id, id_to_name, duplicate_names
    for t in body:
        if not isinstance(t, dict):
            return {}, {}, ["invalid_inventory"]
        n = _safe_tool_name(t.get("name"))
        tid = _safe_uuid(t.get("id"))
        if not n or not tid:
            return {}, {}, ["invalid_inventory"]
        if n in name_to_id:
            if n not in duplicate_names:
                duplicate_names.append(n)
        else:
            name_to_id[n] = tid
        if tid in id_to_name:
            if tid not in duplicate_ids:
                duplicate_ids.append(tid)
            duplicate_names.extend([id_to_name[tid], n])
        else:
            id_to_name[tid] = n
    if duplicate_names or duplicate_ids:
        return {}, {}, sorted(set(duplicate_names))
    return name_to_id, id_to_name, []


def _check_tools(raw_inventory: Any, expected_names: list[str],
                 connection_id: str | None) -> dict[str, Any]:
    """Analyse tool inventory for expected wrappers and correct connection binding.

    Each tool's binding.python.connections maps app_id → connection_UUID.
    We verify the UUID value equals the connection_id returned by the connection
    GET (kept private), not merely that APP_ID is present as a key.

    connection_id=None means the connection UUID could not be read (403, absent,
    or unvalidatable); binding correctness is then 'unknown', not False.
    """
    name_to_id, id_to_name, duplicate_names = _build_tool_inventory(raw_inventory)

    expected_set = set(expected_names)
    found_names = set(name_to_id)
    if not expected_names or not isinstance(raw_inventory, list) or duplicate_names:
        return {"http_status": "invalid_response" if not isinstance(raw_inventory, list) or duplicate_names else "not_assessed",
            "assessment": "not_assessed" if not expected_names else "invalid_inventory",
            "tool_count": len(name_to_id), "inventory_valid": isinstance(raw_inventory, list) and not duplicate_names,
            "duplicate_names": [name if name in expected_set else "unreviewed_tool" for name in duplicate_names],
            "expected_present": [], "expected_missing": [], "all_expected_present": False,
            "all_expected_bound": False, "binding_uuid_check": "unknown",
            "staytus_backend_bound_correct": [], "staytus_backend_key_present_wrong_uuid": []}

    correct_binding: list[str] = []    # APP_ID key + correct UUID value
    key_present_wrong_uuid: list[str] = []  # APP_ID key but UUID does not match

    if isinstance(raw_inventory, list):
        for t in raw_inventory:
            if not isinstance(t, dict):
                continue
            n = str(t.get("name") or "").strip()
            if n not in expected_set:
                continue  # duplicate; skip
            binding = t.get("binding") or {}
            py = binding.get("python") or {} if isinstance(binding, dict) else {}
            conns = py.get("connections") or {} if isinstance(py, dict) else {}
            if not isinstance(conns, dict) or APP_ID not in conns:
                continue
            bound_uuid = str(conns[APP_ID])
            if connection_id is None:
                # Cannot verify UUID; record as key-present but unverifiable.
                key_present_wrong_uuid.append(n)
            elif _safe_uuid(bound_uuid) == connection_id:
                correct_binding.append(n)
            else:
                key_present_wrong_uuid.append(n)

    result: dict[str, Any] = {
        "http_status": "ok" if isinstance(raw_inventory, list) else "unavailable",
        "tool_count": len(name_to_id),
        "duplicate_names": duplicate_names,
        "expected_present": sorted(expected_set & found_names),
        "expected_missing": sorted(expected_set - found_names),
        "all_expected_present": not bool(expected_set - found_names),
        "staytus_backend_bound_correct": sorted(
            n for n in correct_binding if n in expected_set
        ),
        "staytus_backend_key_present_wrong_uuid": sorted(
            n for n in key_present_wrong_uuid if n in expected_set
        ),
    }
    if connection_id is None:
        result["binding_uuid_check"] = "skipped_connection_id_unavailable"
        result["all_expected_bound"] = False
    else:
        expected_bound = expected_set == set(result["staytus_backend_bound_correct"])
        result["all_expected_bound"] = expected_bound
        result["binding_uuid_check"] = "verified"
    return result


def _check_agent(agent_id: str, manifest: dict,
                 id_to_name: dict[str, str],
                 client: Any, base: str, token: str) -> dict[str, Any]:
    """Check cloud agent name/model/context guards and resolve tool UUIDs to names.

    Agent tools field stores UUIDs; resolve via the already-fetched id_to_name map.
    GET /v1/orchestrate/agents/{id}/environment → [{name, id, current_version}]
    Rejects unknown UUIDs, duplicate resolved names, and unexpected/missing tools.
    """
    normalized_id = _safe_uuid(agent_id)
    result: dict[str, Any] = {"agent_id": normalized_id or "invalid_uuid", "http_status": "invalid_response",
        "definition_environment": "draft", "live_definition_verified": False}
    if not normalized_id:
        result["reason"] = "agent_identity_unknown"
        return result
    agent_id = normalized_id
    agent_url = base + f"/v1/orchestrate/agents/{agent_id}"
    body, status = _metadata_get(client, agent_url, token)
    result["http_status"] = status
    if status != "ok":
        return result
    if not isinstance(body, dict) or not _safe_uuid(agent_id) or _safe_uuid(body.get("id")) != _safe_uuid(agent_id):
        result.update(http_status="invalid_response", reason="agent_identity_unknown")
        return result

    agent_name = manifest.get("agent_name", "")
    result["name_matches"] = agent_name in (body.get("name"), body.get("display_name"))
    result["model_matches"] = (body.get("llm") == manifest.get("model_id"))

    # Tenant-tested tool propagation needs True, while an empty allowlist keeps
    # all runtime capabilities out of native-agent prompt context. Missing flags
    # are unknown, never silently treated as either True or False.
    cae = body.get("context_access_enabled")
    result["context_access_disabled"] = (cae is False)
    result["tool_context_access_enabled"] = (cae is True)
    if cae is None:
        result["context_access_note"] = (
            "context_access_enabled absent from response; tool propagation is unverified"
        )
    result["context_variables_empty"] = (body.get("context_variables") == [])
    result["context_configuration_matches"] = (cae is True and result["context_variables_empty"])
    result["collaborators_empty"] = body.get("collaborators") == []

    # Tool UUID → name resolution using the already-fetched inventory.
    cloud_uuids = body.get("tools")
    if not isinstance(cloud_uuids, list):
        result.update(http_status="invalid_response", tools_match_manifest=False, reason="tool_references_unknown")
        return result
    expected_names: list[str] = manifest.get("tool_names") or []
    resolved_names: list[str] = []
    unknown_uuids: list[str] = []
    seen_resolved: set[str] = set()
    duplicate_resolved: list[str] = []
    for uid in cloud_uuids:
        uid_str = _safe_uuid(uid)
        n = id_to_name.get(uid_str)
        if n is None:
            unknown_uuids.append(uid_str or "invalid_uuid")
        elif n in seen_resolved:
            duplicate_resolved.append(n)
        else:
            seen_resolved.add(n)
            resolved_names.append(n)
    result["cloud_tool_names_resolved"] = sorted(n if n in expected_names else "unreviewed_tool" for n in resolved_names)
    result["cloud_tool_uuids_unknown"] = unknown_uuids
    result["cloud_tool_names_duplicate"] = [n if n in expected_names else "unreviewed_tool" for n in duplicate_resolved]
    resolved_set = set(resolved_names)
    expected_set = set(expected_names)
    result["all_expected_tools_present"] = (
        not unknown_uuids and not duplicate_resolved
        and expected_set == resolved_set
    )
    result["tools_match_manifest"] = result["all_expected_tools_present"]
    result["scope_matches_manifest"] = result["tools_match_manifest"] and result["collaborators_empty"]
    result["unexpected_tools"] = ["unreviewed_tool"] * len(resolved_set - expected_set)
    result["missing_tools"] = sorted(expected_set - resolved_set)

    # Environments: GET /v1/orchestrate/agents/{id}/environment
    env_url = base + f"/v1/orchestrate/agents/{agent_id}/environment"
    env_body, env_status = _metadata_get(client, env_url, token)
    result["environment_http_status"] = env_status
    if env_status == "ok" and isinstance(env_body, list):
        envs: dict[str, Any] = {}
        for row in env_body:
            if not isinstance(row, dict):
                continue
            ename = str(row.get("name") or "").lower()
            if ename in ("draft", "live"):
                envs[ename] = {
                    "environment_id": _safe_uuid(row.get("id")),
                    "live_published": (type(row.get("current_version")) is int and _safe_uuid(row.get("id")) is not None
                                       if ename == "live" else None),
                }
        result["environments"] = envs
    return result


# ---------------------------------------------------------------------------
# Top-level network preflight
# ---------------------------------------------------------------------------

def network_preflight(
    values: dict[str, str],
    bundle: Path | None,
    *,
    gateway_check: bool = False,
) -> dict[str, Any]:
    """Perform IAM + metadata GETs only.  Never writes, imports or calls a model."""
    import httpx

    result: dict[str, Any] = {"network_called": True, "iam_status": "not_attempted"}

    api_key = values.get(_AUTHORING_VAR) or values.get("ORCHESTRATE_API_KEY", "")
    result["credential_source"] = (
        "separate_authoring_key" if values.get(_AUTHORING_VAR)
        else ("runtime_key_fallback" if values.get("ORCHESTRATE_API_KEY") else "none")
    )
    if not api_key:
        result["iam_status"] = "missing_credential"
        return result

    try:
        base = service_url(values.get("ORCHESTRATE_SERVICE_URL", ""))
    except SetupError as exc:
        result["iam_status"] = "invalid_service_url"
        result["reason"] = str(exc)
        return result

    with httpx.Client(timeout=25, follow_redirects=False) as client:
        token, iam_status = _iam_token(client, api_key)
        result["iam_status"] = iam_status
        if iam_status != "ok":
            return result

        # --- Connection check ---
        conn_result, connection_id = _check_connection(client, base, token)
        result["staytus_backend_connection"] = conn_result

        # --- Tool inventory (fetched once; shared with agent check) ---
        expected_names: list[str] = []
        manifest: dict | None = None
        if bundle is not None and (bundle / "manifest.json").is_file():
            try:
                manifest = validate_bundle(bundle)
                expected_names = manifest.get("tool_names") or []
            except SetupError:
                manifest = None

        tools_url = base + "/v1/orchestrate/tools"
        tools_body, tools_status = _metadata_get(client, tools_url, token)
        raw_inventory = tools_body if tools_status == "ok" else None
        result["tools"] = _check_tools(raw_inventory, expected_names, connection_id)
        if tools_status != "ok":
            result["tools"]["http_status"] = tools_status

        # Build id→name for agent UUID resolution.
        _, id_to_name, _ = _build_tool_inventory(raw_inventory or [])

        # --- Agent check ---
        if manifest is not None:
            agent_name = manifest.get("agent_name", "")
            agents_url = base + "/v1/orchestrate/agents"
            agents_body, agents_status = _metadata_get(client, agents_url, token)
            if agents_status == "ok" and not isinstance(agents_body, list):
                result["cloud_agent"] = {"http_status": "invalid_response", "found": None}
            elif agents_status == "ok":
                agents = agents_body
                matches = [
                    a for a in agents
                    if isinstance(a, dict) and agent_name in (
                        a.get("name"), a.get("display_name")
                    )
                ]
                if len(matches) == 0:
                    result["cloud_agent"] = {"found": False, "agent_name": agent_name}
                elif len(matches) > 1:
                    result["cloud_agent"] = {
                        "found": False,
                        "error": "multiple_name_matches",
                        "agent_name": agent_name,
                    }
                else:
                    agent_id = str(matches[0].get("id") or "")
                    result["cloud_agent"] = _check_agent(
                        agent_id, manifest, id_to_name, client, base, token,
                    )
                    result["cloud_agent"]["found"] = result["cloud_agent"].get("http_status") == "ok"
            else:
                result["cloud_agent"] = {"http_status": agents_status}

        # --- Optional gateway health GET (unauthenticated public /health only) ---
        if gateway_check:
            try:
                cb = backend_url(values.get("ORCHESTRATE_BACKEND_URL", ""))
                gw = client.get(cb + "/health", timeout=10, follow_redirects=False)
                if gw.status_code == 200:
                    try:
                        confirmed = gw.json().get("service") == "staytus-tool-gateway"
                    except Exception:  # noqa: BLE001
                        confirmed = False
                    result["gateway_health"] = {"status": "ok",
                                                 "service_confirmed": confirmed}
                else:
                    result["gateway_health"] = {"status": f"http_{gw.status_code}"}
            except SetupError as exc:
                result["gateway_health"] = {"status": "invalid_url", "reason": str(exc)}
            except Exception:  # noqa: BLE001
                result["gateway_health"] = {"status": "unreachable"}

    return result


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def run_preflight(
    values: dict[str, str],
    bundle: Path | None,
    *,
    network: bool = False,
    gateway_check: bool = False,
) -> dict[str, Any]:
    """Assemble preflight report.  Offline by default."""
    config = local_config_check(values)
    assets = local_assets_check(bundle)
    wrappers = wrapper_binding_check()

    if config["missing_variables"] or config["invalid_variables"]:
        local_readiness = "local_config_incomplete"
    elif not wrappers["all_bindings_valid"]:
        local_readiness = "wrapper_binding_invalid"
    elif not assets["bundle_valid"]:
        local_readiness = "bundle_missing_or_invalid"
    else:
        local_readiness = "local_ready"

    report: dict[str, Any] = {
        "schema": "staytus-orchestrate-preflight-v1",
        "network_called": False,
        "local_readiness": local_readiness,
        "local": {"config": config, "assets": assets, "wrappers": wrappers},
        "personalized_context_verified": False,
    }

    if not network:
        return report

    net = network_preflight(values, bundle, gateway_check=gateway_check)
    report["network_called"] = True
    report["remote"] = net

    iam = net.get("iam_status")
    conn = net.get("staytus_backend_connection", {})
    if iam == "auth_rejected":
        report["remote_readiness"] = "auth_rejected"
    elif iam not in ("ok",):
        report["remote_readiness"] = "iam_error"
    elif conn.get("http_status") == "access_denied":
        report["remote_readiness"] = "connection_access_denied_403"
    elif conn.get("http_status") == "not_found":
        report["remote_readiness"] = "connection_not_imported"
    elif conn.get("http_status") == "ok":
        draft = conn.get("draft_credentials_entered")
        live = conn.get("live_credentials_entered")
        if draft == "entered" and live == "entered":
            report["remote_readiness"] = "connection_both_entered"
        elif draft == "entered":
            report["remote_readiness"] = "connection_draft_only"
        elif draft == "not_entered" and live == "not_entered":
            report["remote_readiness"] = "connection_credentials_not_entered"
        else:
            report["remote_readiness"] = "connection_credentials_unknown"
    else:
        report["remote_readiness"] = "unknown"

    return report
