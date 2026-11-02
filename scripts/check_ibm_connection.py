"""Non-secret readiness report. Network requires --live --confirm-entitlement.

Run from backend: .venv/bin/python ../scripts/check_ibm_connection.py
--setup-report checks IBM and email OAuth configuration offline using booleans.
Only run --live after authorizing the tenant model/license and service usage.
This generic transport probe does NOT verify personalized tool authorization.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.chat import ChatSettings
from app.config import get_settings
from app.integrations.connectors import ConnectorSettings, provider_readiness
from app.integrations.model_readiness import config_from_settings
from app.integrations.orchestrate_runtime import OrchestrateRuntime, OrchestrateSettings, OrchestrateError
from app.integrations.watsonx import ProviderError, WatsonxClient
from fastapi import HTTPException


def runtime_settings(chat):
    return OrchestrateSettings(chat.orchestrate_service_url, chat.orchestrate_agent_id,
        chat.orchestrate_api_key, chat.orchestrate_bearer_token, chat.orchestrate_timeout_seconds)


def setup_report(chat, application):
    """Pure configuration checks; never output credential/ID/URL values."""
    orchestrate = {"service_url_configured": bool(chat.orchestrate_service_url),
        "agent_id_configured": bool(chat.orchestrate_agent_id),
        "server_credential_configured": bool(chat.orchestrate_api_key or chat.orchestrate_bearer_token),
        "tool_service_key_configured": bool(application.tool_key),
        "context_verification_declared": bool(chat.orchestrate_context_verified),
        "configuration_valid": False, "live_transport_verified": False, "personalized_tools_verified": False}
    try:
        runtime = OrchestrateRuntime(runtime_settings(chat))
        runtime.close()
        orchestrate["configuration_valid"] = True
    except OrchestrateError:
        pass
    orchestrate["personalized_tool_configuration_ready"] = bool(orchestrate["configuration_valid"]
        and orchestrate["tool_service_key_configured"] and orchestrate["context_verification_declared"])
    watsonx = {"url_configured": bool(application.watsonx_url),
        "server_credential_configured": bool(application.watsonx_api_key),
        "project_configured": bool(application.watsonx_project_id),
        "embedding_model_configured": bool(application.watsonx_embedding_model),
        "generation_model_configured": bool(application.watsonx_generation_model),
        "configuration_valid": False, "live_embedding_verified": False, "live_generation_verified": False}
    if watsonx["url_configured"] and watsonx["server_credential_configured"] and watsonx["project_configured"]:
        try:
            client = WatsonxClient(config_from_settings(application))
            client.close()
            watsonx["configuration_valid"] = True
        except ProviderError:
            pass
    mail_settings = ConnectorSettings()
    providers = {}
    for name in ("google", "microsoft"):
        try:
            readiness = provider_readiness(name, mail_settings)
            valid = readiness["configured"]
        except HTTPException:
            valid = False
        providers[name] = {"client_id_configured": bool(getattr(mail_settings, f"{name}_client_id")),
            "client_secret_configured": bool(getattr(mail_settings, f"{name}_client_secret")),
            "encryption_key_configured": bool(mail_settings.connector_token_key),
            "configuration_valid": bool(valid), "user_authorization_verified": False}
    one_email = any(value["configuration_valid"] for value in providers.values())
    model_ready = watsonx["configuration_valid"] and watsonx["embedding_model_configured"] and watsonx["generation_model_configured"]
    return {"network_called": False, "ibm": {"orchestrate": orchestrate, "watsonx_ai": watsonx},
        "oauth": providers, "at_least_one_email_provider_configured": one_email,
        "all_email_providers_configured": all(value["configuration_valid"] for value in providers.values()),
        "setup_configuration_ready": bool(orchestrate["personalized_tool_configuration_ready"] and model_ready and one_email)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Make one non-personal IBM model request; may consume service quota")
    mode.add_argument("--setup-report", action="store_true", help="Offline Boolean checks for IBM and Google/Microsoft OAuth")
    parser.add_argument("--confirm-entitlement", action="store_true", help="Confirm permission, model/license terms and quota use for this live probe")
    args = parser.parse_args()
    chat, application = ChatSettings(), get_settings()
    if args.setup_report:
        report = setup_report(chat, application)
        print(json.dumps(report, indent=2))
        return 0 if report["setup_configuration_ready"] else 2
    fields = {"service_url": bool(chat.orchestrate_service_url), "agent_id": bool(chat.orchestrate_agent_id),
        "server_credential": bool(chat.orchestrate_api_key or chat.orchestrate_bearer_token),
        "tool_service_key": bool(application.tool_key), "tenant_context_verified": chat.orchestrate_context_verified}
    report = {"configuration_present": fields, "network_called": False, "live_transport_verified": False,
        "personalized_tools_verified": False}
    if args.live and not args.confirm_entitlement:
        report["error"] = "Live probe requires --confirm-entitlement after verifying permission, model/license terms and quota usage"
        print(json.dumps(report, indent=2))
        return 2
    missing = [name for name in ("service_url", "agent_id", "server_credential") if not fields[name]]
    if missing:
        report["missing"] = missing
        print(json.dumps(report, indent=2))
        return 2
    try:
        runtime = OrchestrateRuntime(runtime_settings(chat))
        try:
            report["configuration_valid"] = True
            if args.live:
                report["network_called"] = True
                reply = runtime.send("This is a connectivity test without student data. Reply briefly that the connection works. Do not call any tools.", context={})
                report["live_transport_verified"] = bool(reply.message)
                report["reply_received"] = bool(reply.message)
                # No upstream text, tokens, URLs or thread IDs are written to logs.
        finally:
            runtime.close()
    except OrchestrateError:
        report["error"] = "IBM configuration or transport check failed; inspect credentials, tenant permissions and deployed agent version"
        print(json.dumps(report, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
