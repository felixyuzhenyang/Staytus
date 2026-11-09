"""Explicit real-IBM probe using disposable fictional accounts, with owned cleanup."""
import argparse
import json
import secrets
from uuid import uuid4

import httpx

from verify_public_deployment import BASE, STATE, cleanup, database, save


def execute(*, local=False, keep_fixture=False):
    _, factory, _, profile_model, _ = database()
    identities, clients = [], []
    report = {"passed": False, "local": local, "checks": {}}
    prefix = "/api/v1" if local else "/api/backend"
    fixture_name = "timeline-local-fixtures.json" if local else "timeline-fixtures.json"
    phase = "onboarding"
    actual_runtime = None
    try:
        if local:
            from app.chat import get_runtime
            from app.main import app
            runtime_generator = get_runtime()
            actual_runtime = next(runtime_generator)
            provider_outputs = []
            class Recorder:
                def send(self, *args, **kwargs):
                    reply = actual_runtime.send(*args, **kwargs)
                    provider_outputs.append({"phase": phase, "reply": reply.message})
                    save("timeline-local-provider-outputs.json", provider_outputs)
                    return reply
            app.dependency_overrides[get_runtime] = lambda: Recorder()
        for index in range(2):
            identity = {"email": f"staytus-public-smoke-{uuid4()}@example.invalid", "password": secrets.token_urlsafe(32),
                "name": f"SYNTHETIC Timeline {index + 1}"}
            if local:
                from fastapi.testclient import TestClient
                from app.main import app
                client = TestClient(app)
            else:
                client = httpx.Client(base_url=BASE, timeout=280, headers={"Origin": BASE})
            clients.append(client)
            response = client.post(prefix + "/auth/register", json=identity)
            assert response.status_code in {200, 201}, response.status_code
            payload = response.json()
            if local:
                client.headers["Authorization"] = "Bearer " + payload["access_token"]
            identity["account_id"] = payload["account"]["id"]
            identities.append(identity)
            save(fixture_name, identities)
            response = client.post(prefix + "/profile", json={"school": "University of Pennsylvania", "status_type": "F-1",
                "program_start": "2026-01-01", "program_end": "2028-05-15", "notification_frequency": "off",
                "nationality": "Synthetic test only", "planning_details": {"opt_stage": "considering", "opt_type": "pre_completion"}})
            assert response.status_code == 201, response.status_code
            identity["profile_id"] = response.json()["id"]
            with factory() as db:
                db.get(profile_model, identity["profile_id"]).synthetic = True
                db.commit()
            save(fixture_name, identities)
        client = clients[0]
        saved = client.get(prefix + "/profile").json()
        cases = [
            ("form", {"message": "Plan OPT / EAD. Please plan my summer internship in English.", "planning_request": {"workflow": "opt", "profile_version": saved["version"],
                "goal_date": "2027-05-20", "notes": "Please plan my summer internship in English.",
                "planning_details": {"opt_type": "pre_completion", "opt_stage": "considering"}}}),
            ("direct", {"message": "I am considering pre-completion OPT and want to start an internship on May 20, 2027. Please plan my timeline."}),
            ("definition", {"message": "What does DSO stand for? Just explain the abbreviation."}),
        ]
        for phase, request in cases:
            response = client.post(prefix + "/chat", json=request)
            if response.status_code != 200:
                save(f"timeline-{phase}-error.json", {"status": response.status_code, "detail": response.json().get("detail")})
            assert response.status_code == 200, response.status_code
            data = response.json()
            save(f"timeline-{phase}-response.json", data)
            if phase != "definition":
                plan = data["planning"]
                nodes = {node["id"]: node for node in plan["timeline"]["nodes"]}
                assert nodes["prepare"]["date"] == "2027-03-21"
                assert nodes["filing"]["date"] is None and nodes["filing"]["date_kind"] == "to_confirm"
                assert nodes["goal"]["date"] == "2027-05-20"
                assert all(node["explanation"] and node["sources"] for node in nodes.values())
                assert len(data["message"].split()) <= 100
                assert client.get(prefix + "/chat/history").json()["messages"][-1]["planning"] == plan
                assert clients[1].post(prefix + "/chat", json={"message": "Continue", "conversation_id": data["conversation_id"]}).status_code == 404
                identities[0]["conversation_id"] = data["conversation_id"]
                report["checks"][phase] = {"nodes": len(nodes), "summary_characters": len(data["message"]), "history_restored": True}
            else:
                assert "planning" not in data
                report["checks"][phase] = True
            assert client.get(prefix + "/profile").json() == saved
            print(json.dumps({"completed": phase}), flush=True)
        report["passed"] = True
    except Exception as error:
        report.update(failed_phase=phase, error_type=type(error).__name__, safe_error=str(error) if str(error).isdigit() else "Probe assertion failed")
    finally:
        if actual_runtime:
            app.dependency_overrides.pop(get_runtime, None)
            runtime_generator.close()
        for client in clients:
            client.close()
        if report["passed"] and keep_fixture:
            save(fixture_name, identities)
            report["ui_fixture_retained"] = True
        else:
            report["cleanup_completed"] = cleanup(identities)
        save("timeline-probe.json", report)
    print(json.dumps(report, indent=2))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-synthetic-test", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--keep-ui-fixture", action="store_true")
    parser.add_argument("--cleanup-fixture", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_test:
        raise SystemExit("Explicit --confirm-synthetic-test is required")
    if args.cleanup_fixture:
        print(json.dumps({"cleanup_completed": cleanup(json.loads((STATE / "timeline-fixtures.json").read_text()))}))
    else:
        raise SystemExit(0 if execute(local=args.local, keep_fixture=args.keep_ui_fixture) else 1)
