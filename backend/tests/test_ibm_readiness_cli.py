"""CLI probes must remain offline unless model entitlement is explicitly confirmed."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from cryptography.fernet import Fernet
import httpx
import pytest

from app.integrations.connectors import ConnectorSettings


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_ibm_connection.py"
    spec = importlib.util.spec_from_file_location("staytus_ibm_readiness_cli_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configured_chat():
    return SimpleNamespace(orchestrate_service_url="https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/11111111-1111-4111-8111-111111111111",
        orchestrate_agent_id="22222222-2222-4222-8222-222222222222", orchestrate_api_key="private-orchestrate-key",
        orchestrate_bearer_token="", orchestrate_context_verified=True, orchestrate_timeout_seconds=90)


def configured_application():
    return SimpleNamespace(tool_key="private-tool-key", watsonx_url="https://us-south.ml.cloud.ibm.com",
        watsonx_api_key="private-watsonx-key", watsonx_project_id="private-project-id",
        watsonx_embedding_model="private-selected-embedding", watsonx_generation_model="private-selected-generation",
        watsonx_api_version="2024-05-31")


def configure(cli, monkeypatch):
    chat, application = configured_chat(), configured_application()
    monkeypatch.setattr(cli, "ChatSettings", lambda: chat)
    monkeypatch.setattr(cli, "get_settings", lambda: application)
    return chat, application


def test_live_without_entitlement_confirmation_never_constructs_or_calls_runtime(cli, monkeypatch, capsys):
    configure(cli, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["probe", "--live"])
    def prohibited(*args, **kwargs):
        raise AssertionError("Unconfirmed live mode must not touch the provider")
    monkeypatch.setattr(cli, "OrchestrateRuntime", prohibited)
    assert cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["network_called"] is False and report["live_transport_verified"] is False
    assert "--confirm-entitlement" in report["error"]
    assert "private-orchestrate-key" not in json.dumps(report)


def test_confirmed_live_probe_is_generic_and_never_claims_personalized_tool_verification(cli, monkeypatch, capsys):
    configure(cli, monkeypatch)
    calls = []
    class Runtime:
        def __init__(self, config):
            pass
        def send(self, message, **kwargs):
            calls.append((message, kwargs))
            return SimpleNamespace(message="A private provider reply should not be printed")
        def close(self):
            pass
    monkeypatch.setattr(cli, "OrchestrateRuntime", Runtime)
    monkeypatch.setattr(sys, "argv", ["probe", "--live", "--confirm-entitlement"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["network_called"] and report["live_transport_verified"]
    assert report["personalized_tools_verified"] is False
    assert calls[0][1] == {"context": {}} and "without student data" in calls[0][0]
    assert "private provider reply" not in output and "private-orchestrate-key" not in output


def test_unavailable_configuration_remains_nonzero_without_network(cli, monkeypatch, capsys):
    chat, _ = configure(cli, monkeypatch)
    chat.orchestrate_api_key = ""
    monkeypatch.setattr(sys, "argv", ["probe"])
    assert cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["missing"] == ["server_credential"] and report["network_called"] is False


def test_setup_report_reuses_real_oauth_validator_but_outputs_only_booleans(cli, monkeypatch, capsys):
    configure(cli, monkeypatch)
    settings = ConnectorSettings(_env_file=None, connector_token_key=Fernet.generate_key().decode(),
        google_client_id="private-google-id", google_client_secret="private-google-secret",
        microsoft_client_id="", microsoft_client_secret="",
        oauth_callback_base="https://private-host.example/api/backend", frontend_url="https://private-host.example")
    monkeypatch.setattr(cli, "ConnectorSettings", lambda: settings)
    def no_network(request):
        raise AssertionError("Setup mode must not perform any network request")
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(no_network), **kwargs))
    monkeypatch.setattr(sys, "argv", ["probe", "--setup-report"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    def booleans_only(value):
        return all(booleans_only(child) for child in value.values()) if isinstance(value, dict) else isinstance(value, bool)
    assert booleans_only(report) and report["network_called"] is False
    assert report["oauth"]["google"]["configuration_valid"]
    assert report["oauth"]["microsoft"]["configuration_valid"] is False
    assert report["at_least_one_email_provider_configured"] and not report["all_email_providers_configured"]
    assert report["ibm"]["orchestrate"]["personalized_tools_verified"] is False
    for sentinel in ("private-", "11111111", "22222222", "https://", settings.connector_token_key):
        assert sentinel not in output


def test_invalid_oauth_callback_fails_offline_readiness_using_existing_validator(cli, monkeypatch, capsys):
    configure(cli, monkeypatch)
    settings = ConnectorSettings(_env_file=None, connector_token_key=Fernet.generate_key().decode(),
        google_client_id="id", google_client_secret="secret", microsoft_client_id="", microsoft_client_secret="",
        oauth_callback_base="https://different.example/api/backend", frontend_url="https://app.example")
    monkeypatch.setattr(cli, "ConnectorSettings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["probe", "--setup-report"])
    assert cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["oauth"]["google"]["configuration_valid"] is False and report["setup_configuration_ready"] is False
    assert report["network_called"] is False
