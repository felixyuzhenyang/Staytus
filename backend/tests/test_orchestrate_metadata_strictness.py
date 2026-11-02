"""Synthetic metadata regressions: unknown or ambiguous evidence cannot be ready.

No env file, SDK cache, model invocation, real account or network is needed.
MockTransport permits only IAM and the explicitly enumerated metadata routes.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest


@pytest.fixture
def metadata_module(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("staytus_metadata_strictness", scripts / "orchestrate_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def metadata_world(metadata_module, monkeypatch, tmp_path):
    from orchestrate_setup import prepare

    instance, connection, tool, extra, agent, draft, live = [str(uuid4()) for _ in range(7)]
    bundle = tmp_path / "reviewed-bundle"
    manifest = prepare(bundle, "synthetic/model", "StaytusContextProbe", context_probe=True)
    values = {"ORCHESTRATE_SERVICE_URL": f"https://api.ca-tor.watson-orchestrate.cloud.ibm.com/instances/{instance}",
        "ORCHESTRATE_API_KEY": "synthetic-runtime-canary-never-output",
        "ORCHESTRATE_BACKEND_URL": "https://approved-gateway.example.invalid",
        "ORCHESTRATE_TOOL_KEY": "synthetic-service-key-" + "s" * 40,
        "CONTEXT_SECRET": "synthetic-context-key-" + "c" * 40}
    rows = [{"app_id": metadata_module.APP_ID, "connection_id": connection,
             "environment": environment, "security_scheme": "key_value_creds",
             "auth_type": None, "preference": "team", "credentials_entered": True}
            for environment in ("draft", "live")]
    world = {"connection_id": connection, "tool_id": tool, "extra_id": extra, "agent_id": agent,
        "bundle": bundle, "manifest": manifest, "values": values, "requests": [],
        "connection": {"app_id": metadata_module.APP_ID, "connection_id": connection},
        "applications": {"applications": rows},
        "tools": [{"id": tool, "name": "get_student_profile", "binding": {"python": {
            "connections": {metadata_module.APP_ID: connection}, "agent_run_paramater": "context"}}}],
        "agent": {"id": agent, "name": "internal_probe_slug", "display_name": "StaytusContextProbe",
                  "llm": "synthetic/model", "tools": [tool], "collaborators": [],
                  "context_access_enabled": True, "context_variables": []},
        "environments": [{"id": draft, "agent_id": agent, "name": "draft", "current_version": None},
                         {"id": live, "agent_id": agent, "name": "live", "current_version": 1}]}
    world["agents"] = [world["agent"]]
    prefix = f"/instances/{instance}/v1/orchestrate"

    def json_response(payload):
        # Explicit JSON encoding matters for None: httpx's json=None produces
        # an empty body, whereas a valid JSON null is malformed metadata too.
        return httpx.Response(200, content=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})

    def transport(request):
        world["requests"].append(request)
        if request.url.host == "iam.cloud.ibm.com":
            assert request.method == "POST" and request.url.path == "/identity/token"
            return httpx.Response(200, json={"access_token": "synthetic-iam-canary-never-output"})
        assert request.method == "GET", "Preflight must not mutate or invoke an agent"
        assert request.url.path.startswith(prefix), "Cloud metadata needs /v1/orchestrate"
        route = request.url.path.removeprefix(prefix)
        if route == "/connections/applications":
            key = "connection" if request.url.params.get("app_id") else "applications"
            return json_response(world[key])
        if route.startswith(f"/connections/applications/{metadata_module.APP_ID}/configurations/"):
            environment = route.rsplit("/", 1)[1]
            assert environment in {"draft", "live"}
            return httpx.Response(200, json={"app_id": metadata_module.APP_ID,
                "environment": environment, "security_scheme": "key_value_creds", "preference": "team"})
        if route == "/tools":
            return json_response(world["tools"])
        if route == "/agents":
            return json_response(world["agents"])
        if route == f"/agents/{agent}":
            return httpx.Response(200, json=world["agent"])
        if route == f"/agents/{agent}/environment":
            return httpx.Response(200, json=world["environments"])
        pytest.fail("Unexpected route: credentials, artifacts and inference are outside preflight")

    original_client = httpx.Client
    def client_factory(**kwargs):
        return original_client(transport=httpx.MockTransport(transport), **kwargs)
    monkeypatch.setattr(httpx, "Client", client_factory)

    def check(*, selected_bundle=bundle, selected_values=None, network=True):
        effective_values = selected_values if selected_values is not None else world["values"]
        report = metadata_module.run_preflight(effective_values, selected_bundle, network=network)
        rendered = json.dumps(report)
        assert "synthetic-runtime-canary-never-output" not in rendered
        assert "synthetic-iam-canary-never-output" not in rendered
        for field in ("ORCHESTRATE_API_KEY", "ORCHESTRATE_TOOL_KEY", "CONTEXT_SECRET"):
            secret = effective_values.get(field)
            if secret and len(secret) >= 20:
                assert secret not in rendered
        assert report.get("personalized_context_verified") is False
        return report

    world["check"] = check
    return world


def _toolset_match(agent_report):
    # Accept a dedicated strict-match field while retaining compatibility with
    # the initial report's all_expected_tools_present field.
    for field in ("tools_match_manifest", "toolset_matches_manifest", "all_tools_match_manifest"):
        if field in agent_report:
            return agent_report[field]
    return agent_report.get("all_expected_tools_present")


def _uncertain(report):
    if isinstance(report, dict):
        return any(_uncertain(value) for value in report.values())
    if isinstance(report, list):
        return any(_uncertain(value) for value in report)
    return isinstance(report, str) and any(word in report.lower() for word in (
        "unknown", "unavailable", "invalid", "error", "not_assessed", "not_evaluated"))


def test_matching_connection_and_canonical_uuid_enable_only_matching_tool(metadata_world):
    report = metadata_world["check"]()
    connection = report["remote"]["staytus_backend_connection"]
    assert connection["draft_credentials_entered"] == "entered"
    assert report["remote"]["tools"]["all_expected_bound"] is True
    assert _toolset_match(report["remote"]["cloud_agent"]) is True


@pytest.mark.parametrize("identity_change", [
    {"app_id": "another_backend"}, {"connection_id": "not-a-uuid"},
])
def test_wrong_connection_identity_cannot_confirm_tool_binding(metadata_world, identity_change):
    metadata_world["connection"].update(identity_change)
    report = metadata_world["check"]()
    assert report["remote"]["tools"].get("all_expected_bound") is not True
    assert report.get("remote_readiness") != "connection_both_entered"


@pytest.mark.parametrize("collision", ["same_uuid", "same_name"])
def test_duplicate_inventory_identity_cannot_yield_verified_binding(metadata_world, collision):
    duplicate = deepcopy(metadata_world["tools"][0])
    if collision == "same_uuid":
        duplicate["name"] = "unrelated_tool"
    else:
        duplicate["id"] = metadata_world["extra_id"]
    metadata_world["tools"].append(duplicate)
    tools = metadata_world["check"]()["remote"]["tools"]
    assert tools.get("all_expected_bound") is not True
    assert tools.get("binding_uuid_check") != "verified"


def test_wrong_bound_connection_uuid_is_not_verified(metadata_world):
    metadata_world["tools"][0]["binding"]["python"]["connections"]["staytus_backend"] = str(uuid4())
    assert metadata_world["check"]()["remote"]["tools"].get("all_expected_bound") is not True


def test_real_wrapper_app_id_constant_is_resolved_without_sdk_or_env(metadata_module):
    result = metadata_module.wrapper_binding_check()
    assert result["tool_count"] == 13
    assert "read_recent_official_messages" in result["tool_names"]
    assert result["all_bindings_valid"] is True
    assert result.get("missing_credential_binding", []) == []


@pytest.mark.parametrize("change", [
    {"CONTEXT_SECRET": ""}, {"CONTEXT_SECRET": "short"},
    {"ORCHESTRATE_TOOL_KEY": "short"}, {"CONTEXT_SECRET": None},
    {"CONTEXT_SECRET": "same-secret-" + "x" * 40, "ORCHESTRATE_TOOL_KEY": "same-secret-" + "x" * 40},
])
def test_missing_weak_or_shared_secrets_cannot_be_full_local_ready(metadata_world, change):
    values = {**metadata_world["values"], **change}
    if values.get("CONTEXT_SECRET") is None:
        values.pop("CONTEXT_SECRET", None)
    report = metadata_world["check"](selected_values=values, network=False)
    assert report.get("local_readiness") not in {"local_ready", "ready"}
    assert metadata_world["requests"] == []


@pytest.mark.parametrize("malformed", [None, [], {"unexpected": "shape"}])
def test_malformed_connection_http_200_is_unknown_not_confirmed_or_absent(metadata_world, malformed):
    metadata_world["connection"] = malformed
    report = metadata_world["check"]()
    connection = report["remote"]["staytus_backend_connection"]
    assert connection.get("draft_credentials_entered") not in {"entered", "absent", "not_entered"}
    assert connection.get("live_credentials_entered") not in {"entered", "absent", "not_entered"}
    assert report["remote"]["tools"].get("all_expected_bound") is not True


def test_malformed_tool_http_200_does_not_claim_expected_tools_missing(metadata_world):
    metadata_world["tools"] = {"unexpected": "not-an-array"}
    tools = metadata_world["check"]()["remote"]["tools"]
    assert tools.get("all_expected_present") is not True
    assert tools.get("expected_missing") in (None, [])
    assert _uncertain(tools)


def test_malformed_agent_listing_http_200_is_unknown_not_absence(metadata_world):
    metadata_world["agents"] = {"unexpected": "not-an-array"}
    agent = metadata_world["check"]()["remote"]["cloud_agent"]
    assert agent.get("found") is not False or _uncertain(agent)


def test_no_bundle_means_tools_not_assessed_instead_of_vacuous_success(metadata_world):
    tools = metadata_world["check"](selected_bundle=None)["remote"]["tools"]
    assert tools.get("all_expected_present") is not True
    assert tools.get("all_expected_bound") is not True
    assert _uncertain(tools) or tools.get("assessed") is False


@pytest.mark.parametrize("extra_kind", ["known_extra", "unknown_extra", "repeated_reference"])
def test_agent_scope_requires_exact_toolset(metadata_world, extra_kind):
    if extra_kind == "known_extra":
        metadata_world["tools"].append({"id": metadata_world["extra_id"], "name": "unreviewed_extra_tool"})
        metadata_world["agent"]["tools"].append(metadata_world["extra_id"])
    elif extra_kind == "unknown_extra":
        metadata_world["agent"]["tools"].append(str(uuid4()))
    else:
        metadata_world["agent"]["tools"].append(metadata_world["tool_id"])
    assert _toolset_match(metadata_world["check"]()["remote"]["cloud_agent"]) is not True


def test_unexpected_collaborator_is_not_silently_accepted(metadata_world):
    metadata_world["agent"]["collaborators"] = [str(uuid4())]
    agent = metadata_world["check"]()["remote"]["cloud_agent"]
    assert (agent.get("collaborators_empty") is False
            or agent.get("collaborators_match") is False
            or agent.get("scope_matches_manifest") is False
            or bool(agent.get("unexpected_collaborators")))


def test_draft_definition_is_labelled_and_live_version_is_not_live_content_verification(metadata_world):
    agent = metadata_world["check"]()["remote"]["cloud_agent"]
    labels = [agent.get(field) for field in ("checked_environment", "definition_environment",
              "configuration_environment", "agent_definition_target", "target")]
    assert "draft" in labels or agent.get("draft_definition_checked") is True
    assert agent.get("live_definition_verified") is not True
    assert agent.get("live_tools_verified") is not True
