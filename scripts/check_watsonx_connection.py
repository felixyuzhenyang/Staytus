"""Run from backend: .venv/bin/python ../scripts/check_watsonx_connection.py.

Default is offline configuration inspection with no secrets printed. --catalog
reads the current IBM regional model catalog. --live performs explicit bounded
embedding/generation probes with fixed synthetic text, and may use service quota.
No setting is written automatically. Actual student or mailbox data is not used.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings
from app.integrations.model_readiness import configuration_report, config_from_settings, discover_selection, probe_selected_models
from app.integrations.watsonx import ProviderError, WatsonxClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true", help="Read current regional model IDs; no model inference")
    parser.add_argument("--live", action="store_true", help="Run one synthetic embedding and generation probe")
    args = parser.parse_args()
    settings = get_settings()
    report = configuration_report(settings)
    if not (args.catalog or args.live):
        print(json.dumps(report, indent=2))
        return 0 if all(report[key] for key in ("url_configured", "credential_configured", "project_configured")) else 2
    if not all(report[key] for key in ("url_configured", "credential_configured")):
        report["error"] = "Configure server-side WATSONX_URL and WATSONX_API_KEY first"
        print(json.dumps(report, indent=2))
        return 2
    try:
        client = WatsonxClient(config_from_settings(settings))
        try:
            report["network_called"] = True
            if args.catalog:
                report["model_catalog"] = discover_selection(client)
            if args.live:
                report.update(probe_selected_models(client))
        finally:
            client.close()
    except ProviderError:
        report["error"] = "IBM discovery failed; check the service endpoint, server credential and permissions"
        print(json.dumps(report, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 1 if args.live and not (report["live_embedding_verified"] and report["live_generation_verified"]
        and report["quality_probe_passed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
