"""Offline deployment preparation cannot silently become a cloud mutation."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def setup_module():
    path = Path(__file__).resolve().parents[2] / "scripts/orchestrate_setup.py"
    spec = importlib.util.spec_from_file_location("staytus_setup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cloud_instance_url_only(setup_module):
    valid = "https://api.ca-tor.watson-orchestrate.cloud.ibm.com/instances/9341da6b-8993-4252-8436-b3aad470ef7c"
    assert setup_module.service_url(valid + "/") == valid
    for invalid in (valid + "/v1", valid + "?key=private", valid.replace("https:", "http:"),
                    valid.replace("api.ca-tor.", "ca-tor."), valid.replace("cloud.ibm.com", "cloud.ibm.com.attacker.test"),
                    valid.replace("/instances/", ":invalid/instances/")):
        with pytest.raises(setup_module.SetupError):
            setup_module.service_url(invalid)


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://127.0.0.1", "https://10.0.0.1",
    "https://[::1]", "https://example.com/tools", "https://user:secret@example.com", "https://example.com?key=secret"])
def test_callback_rejects_private_or_scoped_urls(setup_module, url):
    with pytest.raises(setup_module.SetupError):
        setup_module.backend_url(url)


def test_bundle_is_reviewable_no_credentials_and_supports_chat_only(setup_module, tmp_path):
    result = setup_module.prepare(tmp_path, "groq/openai/gpt-oss-120b", "Staytus", chat_only=True)
    assert result["tool_names"] == [] and result["live_verified"] is False
    assert set(result["sha256"]) == {"agent.yaml", "python_tools.py", "requirements.txt", "connections.yaml"}
    assert setup_module.validate_bundle(tmp_path)["agent_name"] == "Staytus"
    assert not any(name.endswith(".env") for name in result["sha256"])
    (tmp_path / "agent.yaml").write_text("changed after review")
    with pytest.raises(setup_module.SetupError, match="changed"):
        setup_module.validate_bundle(tmp_path)


def test_full_bundle_uses_current_tool_names(setup_module, tmp_path):
    result = setup_module.prepare(tmp_path, "groq/openai/gpt-oss-120b", "Staytus")
    assert "get_student_profile" in result["tool_names"]
    assert "read_recent_official_messages" in result["tool_names"]
    assert not {"approve", "execute", "send_email"}.intersection(result["tool_names"])


def test_placeholder_model_cannot_be_prepared(setup_module, tmp_path):
    with pytest.raises(setup_module.SetupError):
        setup_module.prepare(tmp_path, "watsonx/REPLACE_WITH_TENANT_MODEL_ID", "Staytus")


@pytest.mark.parametrize("change", [
    {"context_access_enabled": False},
    {"context_access_enabled": None},
    {"context_variables": ["staytus_context"]},
])
def test_reviewed_bundle_requires_tool_context_and_empty_model_allowlist(setup_module, tmp_path, change):
    """A rehashed artifact still cannot disable identity delivery or expose it."""
    import hashlib
    import yaml
    manifest = setup_module.prepare(tmp_path, "synthetic/model", "Staytus")
    agent_path = tmp_path / "agent.yaml"
    agent = yaml.safe_load(agent_path.read_text())
    assert agent["context_access_enabled"] is True
    assert agent["context_variables"] == []
    agent.update(change)
    agent_path.write_text(yaml.safe_dump(agent))
    manifest["sha256"]["agent.yaml"] = hashlib.sha256(agent_path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(setup_module.SetupError):
        setup_module.validate_bundle(tmp_path)


def test_default_check_never_calls_apply_or_prints_credentials(setup_module, monkeypatch, capsys):
    monkeypatch.setenv("ORCHESTRATE_API_KEY", "private-never-output")
    monkeypatch.setenv("ORCHESTRATE_AUTHORING_API_KEY", "author-private-never-output")
    monkeypatch.setattr(setup_module, "apply", lambda *a, **k: pytest.fail("Unexpected cloud operation"))
    assert setup_module.main([]) == 0
    output = capsys.readouterr().out
    assert "private-never-output" not in output
    result = json.loads(output)
    assert result["network_called"] is False
    assert result["configuration_present"]["ORCHESTRATE_AUTHORING_API_KEY"] is True


def test_apply_requires_explicit_cloud_flag(setup_module, monkeypatch, capsys):
    monkeypatch.setattr(setup_module, "apply", lambda *a, **k: pytest.fail("Unexpected cloud operation"))
    assert setup_module.main(["--apply", "activate"]) == 2
    assert "--confirm-cloud-changes" in capsys.readouterr().out


def test_authoring_key_preferred_without_replacing_runtime_value(setup_module):
    values = {"ORCHESTRATE_API_KEY": "runtime-private", "ORCHESTRATE_AUTHORING_API_KEY": "author-private"}
    assert setup_module.authoring_credential(values) == ("author-private", "separate_authoring_key")
    assert values["ORCHESTRATE_API_KEY"] == "runtime-private"
    assert setup_module.authoring_credential({"ORCHESTRATE_API_KEY": "runtime-private"}) == ("runtime-private", "runtime_key_fallback")
    with pytest.raises(setup_module.SetupError):
        setup_module.authoring_credential({})


def test_sdk_unbound_cached_identity_requires_distinct_environment(setup_module, tmp_path):
    with pytest.raises(setup_module.SetupError, match="distinct --environment-name") as error:
        setup_module.sdk_identity_guard(tmp_path, "staytus-cloud", "https://approved.example.invalid", "author-private", cache_present=True)
    assert "author-private" not in str(error.value)


def test_sdk_key_binding_persists_only_fingerprint_and_detects_key_switch(setup_module, tmp_path):
    url, key = "https://approved.example.invalid", "author-private"
    bindings, fingerprint = setup_module.sdk_identity_guard(tmp_path, "staytus-authoring", url, key, cache_present=False)
    setup_module.save_sdk_identity(tmp_path, bindings, "staytus-authoring", fingerprint, "separate_authoring_key")
    path = tmp_path / "credential-bindings.json"
    content = path.read_text()
    assert key not in content and url not in content and "credential_sha256" in content
    assert path.stat().st_mode & 0o777 == 0o600
    assert setup_module.sdk_identity_guard(tmp_path, "staytus-authoring", url, key, cache_present=True)[1] == fingerprint
    with pytest.raises(setup_module.SetupError, match="distinct --environment-name"):
        setup_module.sdk_identity_guard(tmp_path, "staytus-authoring", url, "different-author-key", cache_present=True)
    # A genuinely fresh, empty SDK environment performs a new key login.
    assert setup_module.sdk_identity_guard(tmp_path, "staytus-authoring-2", url, "different-author-key", cache_present=False)[1] != fingerprint


def test_invalid_sdk_binding_metadata_fails_without_credential_output(setup_module, tmp_path):
    (tmp_path / "credential-bindings.json").write_text("not-json")
    with pytest.raises(setup_module.SetupError) as error:
        setup_module.sdk_identity_guard(tmp_path, "staytus-authoring", "https://example.invalid", "private-key", cache_present=False)
    assert "private-key" not in str(error.value)


# ---------------------------------------------------------------------------
# Preflight tests
# ---------------------------------------------------------------------------

@pytest.fixture
def preflight_module(monkeypatch):
    import importlib.util
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("staytus_preflight_test", scripts / "orchestrate_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_offline_default_no_network(preflight_module, monkeypatch):
    """Default (no --preflight flag): fully offline, no network, no crash."""
    values = {
        "ORCHESTRATE_SERVICE_URL": "https://api.ca-tor.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111",
        "ORCHESTRATE_API_KEY": "private-api-key",
        "ORCHESTRATE_BACKEND_URL": "https://approved.example.invalid",
        "ORCHESTRATE_TOOL_KEY": "private-tool-key",
    }
    import httpx
    def no_network(request):
        raise AssertionError("Offline preflight must not call the network")
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(no_network), **kwargs),
    )
    result = preflight_module.run_preflight(values, None, network=False)
    assert result["network_called"] is False
    assert result["personalized_context_verified"] is False
    assert "private-api-key" not in json.dumps(result)
    assert "private-tool-key" not in json.dumps(result)


def test_preflight_local_config_incomplete_reports_missing_vars(preflight_module):
    result = preflight_module.run_preflight({}, None, network=False)
    missing = result["local"]["config"]["missing_variables"]
    assert "ORCHESTRATE_SERVICE_URL" in missing
    assert "ORCHESTRATE_API_KEY" in missing
    assert result["local_readiness"] == "local_config_incomplete"


def test_wrapper_binding_check_passes_for_actual_source(preflight_module):
    """Real python_tools.py uses CREDENTIALS = [{"app_id": APP_ID, ...}]; must pass."""
    result = preflight_module.wrapper_binding_check()
    assert result["source_present"] is True
    assert result["all_bindings_valid"] is True, result
    assert result["tool_count"] == 14
    assert result["missing_credential_binding"] == []
    assert result["missing_context_param"] == []
    assert result["missing_agent_run_annotation"] == []
    assert result["unknown_agent_run_annotation"] == []


def test_wrapper_binding_check_rejects_name_only_when_constant_is_wrong_app_id(preflight_module, tmp_path, monkeypatch):
    """CREDENTIALS with wrong APP_ID resolved constant must fail."""
    bad_src = (
        'from ibm_watsonx_orchestrate.agent_builder.tools import tool\n'
        'from ibm_watsonx_orchestrate.run.context import AgentRun\n'
        'APP_ID = "wrong_app_id"\n'
        'CREDENTIALS = [{"app_id": APP_ID, "type": "key_value_creds"}]\n'
        '@tool(name="get_student_profile", expected_credentials=CREDENTIALS)\n'
        'def get_student_profile(context: AgentRun) -> dict:\n'
        '    """doc"""\n'
        '    return {}\n'
    )
    fake_path = tmp_path / "python_tools.py"
    fake_path.write_text(bad_src)
    monkeypatch.setattr(preflight_module, "ROOT", tmp_path.parent)
    # We need to redirect ROOT / "orchestrate/python_tools.py" to our fake path.
    # Patch tool_names and the path directly via monkeypatching ROOT.
    fake_root = tmp_path.parent
    (fake_root / "orchestrate").mkdir(exist_ok=True)
    import shutil
    shutil.copy(fake_path, fake_root / "orchestrate/python_tools.py")
    old_root = preflight_module.ROOT
    monkeypatch.setattr(preflight_module, "ROOT", fake_root)
    try:
        result = preflight_module.wrapper_binding_check()
        assert result["all_bindings_valid"] is False
        assert "get_student_profile" in result["missing_credential_binding"]
    finally:
        monkeypatch.setattr(preflight_module, "ROOT", old_root)


def test_wrapper_binding_check_unknown_agent_run_annotation_invalidates(preflight_module, tmp_path, monkeypatch):
    """Missing AgentRun annotation must set all_bindings_valid=False."""
    bad_src = (
        'from ibm_watsonx_orchestrate.agent_builder.tools import tool\n'
        'APP_ID = "staytus_backend"\n'
        'CREDENTIALS = [{"app_id": APP_ID, "type": "key_value_creds"}]\n'
        '@tool(name="get_student_profile", expected_credentials=CREDENTIALS)\n'
        'def get_student_profile(context) -> dict:\n'   # no AgentRun annotation
        '    """doc"""\n'
        '    return {}\n'
    )
    fake_root = tmp_path
    (fake_root / "orchestrate").mkdir(exist_ok=True)
    (fake_root / "orchestrate/python_tools.py").write_text(bad_src)
    old_root = preflight_module.ROOT
    monkeypatch.setattr(preflight_module, "ROOT", fake_root)
    try:
        result = preflight_module.wrapper_binding_check()
        assert result["all_bindings_valid"] is False
        assert "get_student_profile" in result["unknown_agent_run_annotation"]
    finally:
        monkeypatch.setattr(preflight_module, "ROOT", old_root)


def test_preflight_iam_401_is_auth_rejected_not_missing(preflight_module, monkeypatch):
    """IAM 401 must report auth_rejected; 403 on connection must be access_denied."""
    import httpx
    def iam_401(request):
        return httpx.Response(401, json={"error": "unauthorized"})
    with httpx.Client(transport=httpx.MockTransport(iam_401)) as client:
        token, status = preflight_module._iam_token(client, "private-key")
    assert status == "auth_rejected"
    assert token == ""
    assert "private-key" not in token


def test_preflight_connection_403_is_access_denied_not_absent(preflight_module, monkeypatch):
    """403 on connection GET must report access_denied, not absent."""
    import httpx
    base = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111"

    def transport(request):
        return httpx.Response(403, json={"detail": "forbidden"})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result, cid = preflight_module._check_connection(client, base, "synthetic-token")
    assert result["http_status"] == "access_denied"
    assert result["draft_credentials_entered"] == "unknown"
    assert result["live_credentials_entered"] == "unknown"
    assert "403 means insufficient metadata permission" in result["note"]
    assert cid is None
    # http_status and state fields must never be not_found or absent.
    assert result["http_status"] != "not_found"
    assert result["draft_credentials_entered"] != "absent"
    assert result["live_credentials_entered"] != "absent"


def test_preflight_connection_404_is_absent(preflight_module):
    """404 on connection GET must report absent for both environments."""
    import httpx
    base = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111"

    def transport(request):
        return httpx.Response(404, json={"detail": "not found"})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result, cid = preflight_module._check_connection(client, base, "synthetic-token")
    assert result["http_status"] == "not_found"
    assert result["draft_credentials_entered"] == "absent"
    assert result["live_credentials_entered"] == "absent"
    assert cid is None


def test_preflight_connection_ok_credentials_entered_only_true_counts(preflight_module):
    """Only credentials_entered=True counts; False→not_entered, None→unknown."""
    import httpx
    from uuid import uuid4
    base = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111"
    conn_id = str(uuid4())

    def transport(request):
        path = str(request.url)
        if "app_id=staytus_backend" in path:
            return httpx.Response(200, json={"connection_id": conn_id, "app_id": "staytus_backend"})
        # include_details list
        return httpx.Response(200, json={"applications": [
            {"app_id": "staytus_backend", "environment": "draft", "credentials_entered": True},
            {"app_id": "staytus_backend", "environment": "live", "credentials_entered": None},
            {"app_id": "other_app", "environment": "draft", "credentials_entered": True},
        ]})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result, cid = preflight_module._check_connection(client, base, "synthetic-token")
    assert result["http_status"] == "ok"
    assert result["draft_credentials_entered"] == "entered"
    assert result["live_credentials_entered"] == "unknown"   # None → unknown
    assert cid == conn_id
    # connection_id must not appear in the serialised result dict.
    assert conn_id not in json.dumps(result)


def test_preflight_tool_binding_verifies_exact_connection_uuid(preflight_module):
    """Tool binding must match the exact connection_id UUID, not just APP_ID key."""
    from uuid import uuid4
    conn_id = str(uuid4())
    wrong_id = str(uuid4())
    inventory = [
        {"id": str(uuid4()), "name": "get_student_profile",
         "binding": {"python": {"connections": {"staytus_backend": conn_id}}}},
        {"id": str(uuid4()), "name": "list_action_tasks",
         "binding": {"python": {"connections": {"staytus_backend": wrong_id}}}},
        {"id": str(uuid4()), "name": "escalate_to_isss",
         "binding": {"python": {}}},  # no connection
    ]
    result = preflight_module._check_tools(inventory, ["get_student_profile", "list_action_tasks"], conn_id)
    assert "get_student_profile" in result["staytus_backend_bound_correct"]
    assert "list_action_tasks" in result["staytus_backend_key_present_wrong_uuid"]
    assert result["all_expected_bound"] is False


def test_preflight_tool_binding_skipped_when_no_connection_id(preflight_module):
    """When connection_id is None (403/absent), binding_uuid_check is skipped."""
    from uuid import uuid4
    inventory = [
        {"id": str(uuid4()), "name": "get_student_profile",
         "binding": {"python": {"connections": {"staytus_backend": str(uuid4())}}}},
    ]
    result = preflight_module._check_tools(inventory, ["get_student_profile"], None)
    assert result["binding_uuid_check"] == "skipped_connection_id_unavailable"
    assert result["all_expected_bound"] is False
    # APP_ID key present but UUID unverifiable → key_present_wrong_uuid
    assert "get_student_profile" in result["staytus_backend_key_present_wrong_uuid"]


def test_preflight_tool_inventory_rejects_duplicate_names(preflight_module):
    """Duplicate tool names in inventory must be reported."""
    from uuid import uuid4
    inventory = [
        {"id": str(uuid4()), "name": "get_student_profile", "binding": {}},
        {"id": str(uuid4()), "name": "get_student_profile", "binding": {}},  # duplicate
    ]
    _, _, dups = preflight_module._build_tool_inventory(inventory)
    assert "get_student_profile" in dups


def test_preflight_agent_rejects_unknown_tool_uuids(preflight_module):
    """Agent tool UUIDs not present in the inventory must be flagged."""
    import httpx
    from uuid import uuid4
    base = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111"
    known_id, agent_id = str(uuid4()), str(uuid4())
    unknown_uuid = str(uuid4())
    id_to_name = {known_id: "get_student_profile"}
    manifest = {"agent_name": "Staytus", "model_id": "tenant/model",
                "tool_names": ["get_student_profile"]}

    def transport(request):
        if f"/agents/{agent_id}/environment" in str(request.url):
            return httpx.Response(200, json=[
                {"name": "draft", "id": str(uuid4())},
            ])
        return httpx.Response(200, json={
            "id": agent_id, "name": "Staytus", "llm": "tenant/model",
            "tools": [unknown_uuid],  # unknown UUID
            "context_access_enabled": False, "context_variables": [],
        })

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = preflight_module._check_agent(agent_id, manifest, id_to_name, client, base, "token")
    assert result["cloud_tool_uuids_unknown"] == [unknown_uuid]
    assert result["all_expected_tools_present"] is False


def test_preflight_agent_context_access_absent_is_not_verified(preflight_module):
    """Missing context metadata proves neither delivery nor prompt isolation."""
    import httpx
    from uuid import uuid4
    base = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111"
    agent_id = str(uuid4())
    id_to_name: dict = {}
    manifest = {"agent_name": "Staytus", "model_id": "tenant/model", "tool_names": []}

    def transport(request):
        if "/environment" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={
            "id": agent_id, "name": "Staytus", "llm": "tenant/model",
            "tools": [],
            # context_access_enabled intentionally absent
            "context_variables": [],
        })

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = preflight_module._check_agent(agent_id, manifest, id_to_name, client, base, "token")
    assert result["context_access_disabled"] is False
    assert result["tool_context_access_enabled"] is False
    assert result["context_configuration_matches"] is False
    assert "context_access_note" in result


def test_preflight_no_secrets_in_output(preflight_module, monkeypatch):
    """No credential values, tokens or raw response bodies appear in output."""
    import httpx
    values = {
        "ORCHESTRATE_SERVICE_URL": "https://api.ca-tor.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111",
        "ORCHESTRATE_AUTHORING_API_KEY": "private-authoring-key",
        "ORCHESTRATE_API_KEY": "private-runtime-key",
        "ORCHESTRATE_BACKEND_URL": "https://approved.example.invalid",
        "ORCHESTRATE_TOOL_KEY": "private-tool-key",
    }
    def transport(request):
        if "iam.cloud.ibm.com" in str(request.url):
            return httpx.Response(401, json={"error": "unauthorized"})
        raise AssertionError("Unexpected request")
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    result = preflight_module.run_preflight(values, None, network=True)
    serialised = json.dumps(result)
    for sentinel in ("private-authoring-key", "private-runtime-key", "private-tool-key"):
        assert sentinel not in serialised
    assert result["remote"]["iam_status"] == "auth_rejected"
    assert result["remote_readiness"] == "auth_rejected"


def test_preflight_cli_requires_env_file(setup_module, monkeypatch, capsys):
    """--preflight without --env-file must error; no network call."""
    monkeypatch.setenv("ORCHESTRATE_API_KEY", "private-never-called")
    called = []
    def no_network(*a, **k):
        called.append(1)
        raise AssertionError("Network must not be called without --env-file")
    import sys
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    import orchestrate_preflight as pf
    monkeypatch.setattr(pf, "network_preflight", no_network)
    result_code = setup_module.main(["--preflight"])
    assert result_code == 2
    assert not called
    output = json.loads(capsys.readouterr().out)
    assert "env-file" in output["reason"].lower() or "--env-file" in output["reason"]


def test_preflight_cli_rejects_combine_with_apply(setup_module, capsys, tmp_path):
    """--preflight combined with --apply must error before any cloud call."""
    env_file = tmp_path / ".env"
    env_file.write_text("ORCHESTRATE_API_KEY=private\n")
    result_code = setup_module.main([
        "--preflight", "--env-file", str(env_file), "--apply", "activate",
    ])
    assert result_code == 2
    output = json.loads(capsys.readouterr().out)
    assert "read-only" in output["reason"].lower() or "apply" in output["reason"].lower()
