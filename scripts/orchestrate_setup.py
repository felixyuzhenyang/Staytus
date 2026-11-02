"""Prepare and validate IBM deployment assets; no network or mutation by default.

Run with backend/.venv/bin/python for offline preparation. Use the isolated
.local/orchestrate-adk/bin/python for --check-adk and explicit --apply stages.
Credentials are read from an explicit env file/environment, never CLI arguments.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
import importlib.metadata
import importlib.util
import io
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADK_VERSION = "2.19.1"
APP_ID = "staytus_backend"


class SetupError(RuntimeError):
    """Operator-safe setup error: excludes credentials and upstream responses."""


def service_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise SetupError("The service-instance URL is invalid") from None
    parts = parsed.path.rstrip("/").split("/")
    if (parsed.scheme != "https" or not re.fullmatch(r"api\.[a-z0-9-]+\.watson-orchestrate\.cloud\.ibm\.com", parsed.hostname or "")
            or port not in (None, 443) or parsed.username or parsed.password or parsed.query or parsed.fragment
            or len(parts) != 3 or parts[1] != "instances"):
        raise SetupError("Use the exact HTTPS IBM Cloud service-instance URL, without /v1 or a dashboard path")
    try:
        instance = str(UUID(parts[2]))
    except ValueError:
        raise SetupError("The service-instance URL needs a UUID instance identifier") from None
    return f"https://{parsed.hostname}/instances/{instance}"


def backend_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise SetupError("The callback URL is invalid") from None
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host or port not in (None, 443) or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")):
        raise SetupError("Tool callbacks require an authorized public HTTPS base host, without /tools or a URL path")
    # A public hostname is required; localhost/private IP callback routes are not cloud reachability.
    import ipaddress
    try:
        if not ipaddress.ip_address(host).is_global:
            raise SetupError("A private or loopback IP is not a cloud-reachable tool callback")
    except ValueError:
        pass
    return value.rstrip("/")


def tool_names(path: Path) -> list[str]:
    names = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "tool":
                    name = next((entry.value.value for entry in decorator.keywords
                                 if entry.arg == "name" and isinstance(entry.value, ast.Constant)), node.name)
                    names.append(name)
    if len(names) != len(set(names)) or not names:
        raise SetupError("Tool source has missing or duplicate operation names")
    forbidden = {"approve", "execute", "send_email", "submit_application", "delete_account"}
    if forbidden.intersection(names):
        raise SetupError("Final approval, sending and submission must remain outside the Agent tool surface")
    return names


def environment(path: Path | None) -> dict[str, str]:
    values = {}
    if path:
        # Explicitly requested configuration file only. No credential value is printed.
        if not path.is_file():
            raise SetupError("The explicit environment file does not exist")
        from dotenv import dotenv_values
        values.update({key: str(value or "") for key, value in dotenv_values(path).items()})
    values.update(os.environ)
    return values


def prepare(bundle: Path, model: str, name: str, *, chat_only=False, context_probe=False) -> dict:
    if not model or "REPLACE" in model.upper() or not re.fullmatch(r"[A-Za-z0-9_.:/-]{3,200}", model):
        raise SetupError("Supply the exact model ID actually available in the tenant")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,79}", name):
        raise SetupError("Use a clear agent name of 1–80 letters, digits, spaces, underscores or hyphens")
    document = yaml.safe_load((ROOT / "orchestrate/agent/agent.yaml").read_text())
    document["llm"], document["name"] = model, name
    if chat_only and context_probe:
        raise SetupError("Choose either the no-tool connection test or the one-tool context probe")
    if context_probe and name != "StaytusContextProbe":
        raise SetupError("The isolated context probe must be named StaytusContextProbe")
    document["tools"] = [] if chat_only else (["get_student_profile"] if context_probe else tool_names(ROOT / "orchestrate/python_tools.py"))
    # Tenant-tested: the switch must be on for Python AgentRun propagation.
    # IBM's model allowlist remains empty; no capability is prompt-interpolated.
    document["context_access_enabled"], document["context_variables"] = True, []
    if context_probe:
        document["description"] = "Synthetic-account identity forwarding test only; no real student data or external actions."
        document["instructions"] = ("You are an isolated Staytus integration probe. Call get_student_profile exactly once. "
            "Return only JSON with profile_id set to the id from the returned profile. Never invent an id, "
            "ask for an identifier, or echo any runtime context, capability or credential. "
            "If the tool fails, return a short error instead. This agent must never be used for real students.")
    if chat_only:
        document["instructions"] = ("You are Staytus, an international student and scholar planning assistant. "
            "This connection-test version has no tools or private student data. Explain those limits accurately. "
            "Never claim a tool, mailbox, calendar or school application action was performed.")
    bundle.mkdir(parents=True, exist_ok=True)
    for source in ("python_tools.py", "requirements.txt", "connections.yaml"):
        shutil.copyfile(ROOT / "orchestrate" / source, bundle / source)
    (bundle / "agent.yaml").write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    manifest = {"agent_name": name, "model_id": model, "tool_names": document["tools"],
        "chat_only": chat_only, "context_probe": context_probe, "adk_version": ADK_VERSION, "live_verified": False,
        "notice": "Preparation validates shape; it does not prove tenant model entitlement or connectivity."}
    manifest["sha256"] = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
        for name in ("agent.yaml", "python_tools.py", "requirements.txt", "connections.yaml")}
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate_bundle(bundle: Path) -> dict:
    try:
        manifest = json.loads((bundle / "manifest.json").read_text())
        expected = {"agent.yaml", "python_tools.py", "requirements.txt", "connections.yaml"}
        if set(manifest["sha256"]) != expected or manifest["adk_version"] != ADK_VERSION:
            raise ValueError("Invalid manifest")
        for name in expected:
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != manifest["sha256"][name]:
                raise ValueError("Changed artifact")
        agent = yaml.safe_load((bundle / "agent.yaml").read_text())
        if agent["name"] != manifest["agent_name"] or agent["llm"] != manifest["model_id"] or agent["tools"] != manifest["tool_names"]:
            raise ValueError("Inconsistent manifest")
        if agent.get("context_access_enabled") is not True or agent.get("context_variables") != []:
            raise ValueError("Runtime capability must stay outside model context")
        return manifest
    except (KeyError, TypeError, ValueError, OSError):
        raise SetupError("Prepared artifacts changed or are incomplete; prepare and review the bundle again") from None


def check_adk(path: Path) -> dict:
    if importlib.metadata.version("ibm-watsonx-orchestrate") != ADK_VERSION:
        raise SetupError(f"Use the isolated IBM ADK {ADK_VERSION} environment for this version-checked setup")
    spec = importlib.util.spec_from_file_location("staytus_setup_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    for name in tool_names(path):
        tool = getattr(module, name)
        credentials = tool.expected_credentials
        if tool.get_run_param() != "context" or not any(item.app_id == APP_ID for item in credentials):
            raise SetupError("A tool lacks the expected runtime context binding or backend credential connection")
        results.append({"name": name, "runtime_parameter": tool.get_run_param(), "connection": APP_ID})
    # Exercise the actual SDK's context parsing/decorator plus our HTTP bridge
    # against a mock transport. This verifies local forwarding independently of
    # native-agent prompt allowlists; it does not substitute for a tenant test.
    from io import BytesIO
    captured = []
    class MockOpener:
        def open(self, request, *, timeout):
            captured.append(request)
            if timeout != 25:
                raise SetupError("The tool bridge needs its bounded request timeout")
            return BytesIO(b'{"id":"synthetic-sdk-only"}')
    original_opener, original_credentials = module.build_opener, module.connections.key_value
    try:
        module.build_opener = lambda *handlers: MockOpener()
        module.connections.key_value = lambda app_id: {"backend_url": "https://sdk-mock.example.invalid", "tool_key": "synthetic-sdk-service-key"}
        response = module.get_student_profile(context={"request_context": {"staytus_context": "synthetic-sdk-capability"}})
        if (response.content != {"id": "synthetic-sdk-only"} or len(captured) != 1
                or captured[0].get_header("X-staytus-context") != "synthetic-sdk-capability"):
            raise SetupError("The installed SDK did not forward the runtime context through the local mock tool bridge")
    finally:
        module.build_opener, module.connections.key_value = original_opener, original_credentials
    return {"version": ADK_VERSION, "tool_imports_valid": True, "tools": results,
        "mock_runtime_context_forwarding_valid": True,
        "tenant_context_verified": False, "network_called": False}


def scoped_sdk_config(directory: Path):
    """Keep official SDK state under ignored .local without changing HOME.

    ADK2.19.1 hardcodes standard folders and exposes no config-dir CLI option.
    The small launcher adapter changes only Config construction in this process.
    It neither edits installed SDK files nor touches the user's existing CLI state.
    """
    import ibm_watsonx_orchestrate_core.utils.config as config
    old_default, old_auth = config.DEFAULT_CONFIG_FILE_FOLDER, config.AUTH_CONFIG_FILE_FOLDER
    new_default, new_auth = str(directory / "config"), str(directory / "auth")
    original = config.Config
    config.DEFAULT_CONFIG_FILE_FOLDER, config.AUTH_CONFIG_FILE_FOLDER = new_default, new_auth

    class ProjectConfig(original):
        def __init__(self, config_file_folder=None, config_file=config.DEFAULT_CONFIG_FILE):
            folder = {None: new_default, old_default: new_default, old_auth: new_auth}.get(config_file_folder, config_file_folder)
            super().__init__(config_file_folder=folder, config_file=config_file)
            os.chmod(self.config_file_path, 0o600)

    config.Config = ProjectConfig
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return config


def authoring_credential(values: dict) -> tuple[str, str]:
    """Setup credentials never replace the application's runtime credential."""
    if values.get("ORCHESTRATE_AUTHORING_API_KEY"):
        return values["ORCHESTRATE_AUTHORING_API_KEY"], "separate_authoring_key"
    if values.get("ORCHESTRATE_API_KEY"):
        return values["ORCHESTRATE_API_KEY"], "runtime_key_fallback"
    raise SetupError("An authorized server-side authoring API key is required for remote ADK setup")


def sdk_identity_guard(directory: Path, env_name: str, url: str, key: str, *, cache_present: bool) -> tuple[dict, str]:
    """Refuse stale SDK identity reuse when a different API key is selected.

    ADK activate can ignore its apikey argument while an environment has a valid
    cached IAM token. It cannot prove that token belongs to the supplied key.
    Store a one-way binding after a fresh/known login; never persist raw API keys.
    An older unbound cache must use a distinct environment, not silent reuse.
    """
    path = directory / "credential-bindings.json"
    try:
        bindings = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(bindings, dict):
            raise ValueError("Invalid binding metadata")
        fingerprint = hashlib.sha256(json.dumps([url, key], separators=(",", ":")).encode()).hexdigest()
        existing = bindings.get(env_name, {})
        if not isinstance(existing, dict):
            raise ValueError("Invalid environment binding")
        if cache_present and existing.get("credential_sha256") != fingerprint:
            raise SetupError("The SDK environment has an unbound or different cached identity; use a distinct --environment-name such as staytus-authoring before selecting another key")
        return bindings, fingerprint
    except (OSError, TypeError, ValueError):
        raise SetupError("Project SDK identity metadata is unreadable; review it privately before using an existing environment") from None


def save_sdk_identity(directory: Path, bindings: dict, env_name: str, fingerprint: str, source: str):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    bindings[env_name] = {"credential_sha256": fingerprint, "credential_source": source}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".identity-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(bindings, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory / "credential-bindings.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def context_binding(values: dict) -> str:
    """Bind redacted evidence to one tenant/callback/signing configuration."""
    fields = [service_url(values.get("ORCHESTRATE_SERVICE_URL", "")), backend_url(values.get("ORCHESTRATE_BACKEND_URL", ""))]
    for name in ("ORCHESTRATE_TOOL_KEY", "CONTEXT_SECRET"):
        value = values.get(name, "")
        if len(value) < 32 or any(char.isspace() for char in value):
            raise SetupError("Context testing requires explicit strong service and signing secrets")
        fields.append(value)
    if fields[2] == fields[3]:
        raise SetupError("Service and signing secrets must be independent")
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()


def validate_context_report(path: Path | None, values: dict, manifest: dict) -> dict:
    """A Draft pass permits staged validation; it never enables product chat."""
    try:
        report = json.loads(path.read_text()) if path else {}
        probe_path = Path(report["bundle_dir"]).resolve()
        if not probe_path.is_relative_to(ROOT / ".local"):
            raise ValueError("Unmanaged evidence bundle")
        tested_manifest = validate_bundle(probe_path)
        runs = report["runs"]
        stamp = datetime.fromisoformat(report["verified_at"])
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        if (report["schema"] != "staytus-context-probe-v1" or report["passed"] is not True
                or report["adk_version"] != ADK_VERSION or not 0 <= age <= 86400
                or report["binding_sha256"] != context_binding(values)
                or report["wrapper_sha256"] != manifest["sha256"]["python_tools.py"]
                or report["bundle_sha256"] != tested_manifest["sha256"]
                or any(tested_manifest["sha256"][name] != manifest["sha256"][name]
                       for name in ("python_tools.py", "requirements.txt", "connections.yaml"))
                or report["agent_name"] != tested_manifest["agent_name"]
                or report["model_id"] != tested_manifest["model_id"]
                or report["model_id"] != manifest["model_id"]
                or report["tested_tool"] != "get_student_profile"
                or not isinstance(runs, list) or len(runs) != 2
                or not all(item.get("assistant_message_verified") is True
                           and item.get("owned_profile_returned") is True
                           and item.get("backend_audit_verified") is True for item in runs)
                or len({str(UUID(item["thread_id"])) for item in runs}) != 2
                or len(set(report["synthetic_profile_ids"])) != 2
                or not all(UUID(value) for value in report["synthetic_profile_ids"])
                or report["cleanup_completed"] is not True):
            raise ValueError("Invalid probe report")
        if report["target"] not in {"draft", "live"}:
            raise ValueError("Invalid target")
        UUID(report["agent_id"])
        if tested_manifest.get("context_probe") and report["agent_name"] != "StaytusContextProbe":
            raise ValueError("Unrecognized isolated probe identity")
        # Publishing the isolated one-tool probe after Draft testing enables a
        # controlled Live test. The full Agent needs the Live probe first.
        if not manifest.get("context_probe") and report["target"] != "live":
            raise ValueError("Full deployment needs Live synthetic validation")
        return report
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        raise SetupError("A matching successful synthetic context report from the last 24 hours is required; test Draft, then the isolated Live probe before full deployment") from None


def apply(stage: str, values: dict, bundle: Path, *, env_name: str, target: str, allow_update=False, confirm_context=False,
          context_report: Path | None = None):
    if importlib.metadata.version("ibm-watsonx-orchestrate") != ADK_VERSION:
        raise SetupError(f"Cloud setup requires isolated ADK {ADK_VERSION}")
    url = service_url(values.get("ORCHESTRATE_SERVICE_URL", ""))
    key, key_source = authoring_credential(values)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", env_name) or env_name == "local":
        raise SetupError("Choose a distinct project environment name")
    if stage in {"tools", "agent"} and not allow_update:
        raise SetupError("Import can update same-name cloud assets; review the prepared bundle and pass --allow-update explicitly")
    if stage != "activate" and not (bundle / "manifest.json").is_file():
        raise SetupError("Prepare and review the deployment bundle first")
    manifest = validate_bundle(bundle) if (bundle / "manifest.json").is_file() else {}
    if stage == "deploy" and manifest.get("tool_names"):
        if not confirm_context:
            raise SetupError("Tool-enabled deployment requires reviewed synthetic evidence and --confirm-context-tested")
        validate_context_report(context_report, values, manifest)
    callback, service_key = "", ""
    if stage == "connection":
        callback = backend_url(values.get("ORCHESTRATE_BACKEND_URL", ""))
        service_key = values.get("ORCHESTRATE_TOOL_KEY", "")
        if not service_key:
            raise SetupError("Configure the independently random backend tool-service key first")
    sdk_directory = ROOT / ".local/orchestrate-cli"
    try:
        scoped_sdk_config(sdk_directory)
        from ibm_watsonx_orchestrate.cli.commands.environment import environment_controller as controller
        from ibm_watsonx_orchestrate_core.utils.config import (Config, ENVIRONMENTS_SECTION_HEADER,
            AUTH_CONFIG_FILE_FOLDER, AUTH_CONFIG_FILE, AUTH_SECTION_HEADER)
        settings = Config()
        current = settings.read(ENVIRONMENTS_SECTION_HEADER, env_name)
        if current and current.get("wxo_url") != url:
            raise SetupError("The existing project CLI environment points at a different tenant; choose another environment name")
        auth = Config(AUTH_CONFIG_FILE_FOLDER, AUTH_CONFIG_FILE)
        bindings, fingerprint = sdk_identity_guard(sdk_directory, env_name, url, key,
            cache_present=bool(auth.read(AUTH_SECTION_HEADER, env_name)))
    except SetupError:
        raise
    except (Exception, SystemExit):
        # Malformed YAML errors can quote token-bearing source lines.
        raise SetupError("Project SDK state cannot be inspected safely; review its local configuration privately before continuing") from None
    # Provider libraries can include response bodies in exceptions/logging. Capture
    # their output and return a bounded non-secret stage result instead.
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            if not current:
                controller.add(name=env_name, url=url)
            controller.activate(name=env_name, apikey=key, skip_version_check=True)
            save_sdk_identity(sdk_directory, bindings, env_name, fingerprint, key_source)
            if stage == "connection":
                from ibm_watsonx_orchestrate.cli.commands.connections.connections_controller import import_connection, set_credentials_connection
                from ibm_watsonx_orchestrate.agent_builder.connections.types import ConnectionEnvironment, KeyValueEntry
                import_connection(str(bundle / "connections.yaml"))
                for environment_name in (["draft", "live"] if target == "both" else [target]):
                    set_credentials_connection(app_id=APP_ID, environment=ConnectionEnvironment(environment_name),
                        entries=[KeyValueEntry(key="backend_url", value=callback), KeyValueEntry(key="tool_key", value=service_key)])
            elif stage != "activate":
                from ibm_watsonx_orchestrate.cli.main import app
                arguments = {
                    "tools": ["tools", "import", "--kind", "python", "--file", str(bundle / "python_tools.py"),
                              "--requirements-file", str(bundle / "requirements.txt"), "--app-id", APP_ID],
                    "agent": ["agents", "import", "--file", str(bundle / "agent.yaml")],
                    "deploy": ["agents", "deploy", "--name", manifest["agent_name"]],
                }[stage]
                app(args=arguments, standalone_mode=False)
    except SetupError:
        raise
    except (Exception, SystemExit):
        raise SetupError(f"IBM ADK stage '{stage}' failed; verify credentials, role, tenant model and connection configuration") from None
    finally:
        logging.disable(previous)
    return {"stage_completed": stage, "credential_source": key_source,
        "cloud_operation_attempted": True, "personalized_tools_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Explicit server env file; values are never printed")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--model-id", default="")
    parser.add_argument("--agent-name", default="Staytus")
    parser.add_argument("--chat-only", action="store_true", help="Prepare a no-tool connection-test agent")
    parser.add_argument("--context-probe", action="store_true", help="Prepare isolated one-tool StaytusContextProbe")
    parser.add_argument("--check-adk", action="store_true")
    parser.add_argument("--bundle-dir", type=Path, default=ROOT / ".local/orchestrate-prepared")
    parser.add_argument("--apply", choices=["activate", "connection", "tools", "agent", "deploy"])
    parser.add_argument("--confirm-cloud-changes", action="store_true")
    parser.add_argument("--allow-update", action="store_true")
    parser.add_argument("--confirm-context-tested", action="store_true")
    parser.add_argument("--context-test-report", type=Path, help="Reviewed matching synthetic-test evidence; never enables product chat")
    parser.add_argument("--environment-name", default="staytus-cloud")
    parser.add_argument("--connection-environment", choices=["draft", "live", "both"], default="draft")
    parser.add_argument("--preflight", action="store_true",
        help="Read-only tool-chain preflight: IAM + metadata GETs only; requires --env-file")
    parser.add_argument("--preflight-gateway", action="store_true",
        help="Also check the narrow gateway /health during --preflight")
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            if not args.env_file:
                raise SetupError("--preflight requires --env-file to load explicit server credentials")
            if args.apply or args.prepare or args.check_adk:
                raise SetupError("--preflight is read-only and cannot be combined with setup/apply operations")
        values = environment(args.env_file)
        report = {"tool_names": tool_names(ROOT / "orchestrate/python_tools.py"), "network_called": False,
            "configuration_present": {name: bool(values.get(name)) for name in (
                "ORCHESTRATE_SERVICE_URL", "ORCHESTRATE_API_KEY", "ORCHESTRATE_AUTHORING_API_KEY",
                "ORCHESTRATE_BACKEND_URL", "ORCHESTRATE_TOOL_KEY")}}
        if args.prepare:
            report["prepared"] = prepare(args.bundle_dir, args.model_id, args.agent_name, chat_only=args.chat_only, context_probe=args.context_probe)
        if args.check_adk:
            report["adk"] = check_adk(ROOT / "orchestrate/python_tools.py")
        if args.preflight:
            from orchestrate_preflight import run_preflight
            report["preflight"] = run_preflight(values, args.bundle_dir,
                network=True, gateway_check=args.preflight_gateway)
            report["network_called"] = True
        if args.apply:
            if not args.confirm_cloud_changes:
                raise SetupError("Review the prepared assets and authorize this specific cloud operation with --confirm-cloud-changes")
            report["result"] = apply(args.apply, values, args.bundle_dir, env_name=args.environment_name,
                target=args.connection_environment, allow_update=args.allow_update, confirm_context=args.confirm_context_tested,
                context_report=args.context_test_report)
            report["network_called"] = True
        print(json.dumps(report, indent=2))
        return 0
    except (SetupError, importlib.metadata.PackageNotFoundError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error) if isinstance(error, SetupError) else "Install the isolated IBM ADK first", "live_verified": False}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
