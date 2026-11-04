"""Opt-in public guided-plan probe, fictional accounts and export-only calendar actions."""
import argparse
import json
import secrets
from uuid import uuid4

import httpx
from verify_public_deployment import BASE, STATE, cleanup, database, save


def execute(keep_fixture=False):
    _, factory, _, profile_model, _ = database()
    identities, clients = [], []
    report = {"passed": False, "checks": {}}
    phase = "start"
    try:
        for index, status in enumerate(("F-1", "J-1 student")):
            phase = f"onboarding_{index}"
            identity = {"email": f"staytus-public-smoke-{uuid4()}@example.invalid", "password": secrets.token_urlsafe(32),
                "name": f"SYNTHETIC Guided Plan {index + 1}"}
            client = httpx.Client(base_url=BASE, timeout=220, headers={"Origin": BASE})
            clients.append(client)
            result = client.post("/api/backend/auth/register", json=identity)
            assert result.status_code in {200, 201}, result.status_code
            identity["account_id"] = result.json()["account"]["id"]
            identities.append(identity)
            save("guided-plan-fixtures.json", identities)
            result = client.post("/api/backend/profile", json={"school": "University of Pennsylvania", "status_type": status,
                "program_start": "2026-01-01", "program_end": "2028-05-15", "notification_frequency": "off",
                "nationality": "Synthetic test only"})
            assert result.status_code == 201, result.status_code
            identity["profile_id"] = result.json()["id"]
            with factory() as db:
                db.get(profile_model, identity["profile_id"]).synthetic = True
                db.commit()
            save("guided-plan-fixtures.json", identities)
        for index, client in enumerate(clients):
            phase = f"live_guided_plan_{index}"
            before = client.get("/api/backend/profile").json()
            request = {"workflow": "travel" if index == 0 else "academic_training", "profile_version": before["version"],
                "notes": "请用中文生成准备计划，并指出缺少的信息。"}
            if index == 0:
                request.update(travel_date="2027-01-10", travel_signature_date="2026-06-01",
                    planning_details={"travel_destination": "Japan", "return_date": "2027-01-22",
                        "visa_expiry": "2026-12-31", "passport_expiry": "2029-01-01", "f1_activity": "studying"})
            else:
                request["planning_details"] = {"academic_training_stage": "active", "sponsor_name": "Example synthetic sponsor",
                    "academic_training_start": "2026-10-01", "academic_training_end": "2027-06-01"}
            result = client.post("/api/backend/chat", json={"message": "Generate my personal preparation plan in Chinese", "planning_request": request})
            assert result.status_code == 200, result.status_code
            data = result.json()
            save(f"guided-plan-synthetic-response-{index}.json", data)
            plan = data["planning"]
            assert data["mode"] == "orchestrate" and len(data["message"]) > 100
            assert plan["workflow"] == request["workflow"] and plan["retrieved_source_count"] > 0
            assert plan["calendar_targets"] and client.get("/api/backend/profile").json() == before
            identity = identities[index]
            identity["conversation_id"] = data["conversation_id"]
            history = client.get("/api/backend/chat/history").json()
            assert history["messages"][-1]["planning"] == plan
            assert history["messages"][-1]["message"] == data["message"]
            report["checks"][phase] = {"source_count": plan["retrieved_source_count"], "reply_characters": len(data["message"]),
                "calendar_targets": len(plan["calendar_targets"]), "profile_unchanged": True, "history_restored": True}
            if index == 0:
                phase = "travel_narrative_uses_scenario"
                assert "Japan" in data["message"] or "日本" in data["message"]
                phase = "travel_record_conflict"
                assert any(check["id"] == "visa_expiry_before_return" for check in plan["record_checks"])
                target = plan["calendar_targets"][0]
                phase = "calendar_export_proposal"
                response = client.post("/api/backend/approvals", json={"kind": "calendar", "payload": {
                    "title": target["title"], "date": target["date"], "description": target["description"], "provider": "export"}})
                assert response.status_code in {200, 201}
                approval = response.json()
                preview = client.post(f"/api/backend/approvals/{approval['id']}/preview").json()
                phase = "calendar_export_execution"
                receipt = client.post(f"/api/backend/approvals/{approval['id']}/approve", json={"payload_hash": preview["payload_hash"]})
                assert receipt.status_code == 200 and receipt.json()["status"] == "SUCCEEDED"
                report["checks"]["approved_calendar_export"] = True
            print(json.dumps({"completed": phase}), flush=True)
        phase = "cross_account"
        assert clients[1].post("/api/backend/chat", json={"message": "Continue", "conversation_id": identities[0]["conversation_id"]}).status_code == 404
        assert clients[1].get("/api/backend/chat/history").json()["conversation_id"] == identities[1]["conversation_id"]
        report["checks"][phase] = True
        report["passed"] = True
    except Exception as error:  # noqa: BLE001 - Keep private provider/auth responses out of logs.
        report.update(failed_phase=phase, error_type=type(error).__name__, safe_error=str(error) if str(error).isdigit() else "Probe assertion failed")
    finally:
        for client in clients:
            client.close()
        if report["passed"] and keep_fixture:
            save("guided-plan-fixtures.json", identities)
            report["ui_fixture_retained"] = True
        else:
            report["cleanup_completed"] = cleanup(identities)
        save("guided-plan-probe.json", report)
    print(json.dumps(report, indent=2))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-synthetic-test", action="store_true")
    parser.add_argument("--keep-ui-fixture", action="store_true")
    parser.add_argument("--cleanup-fixture", action="store_true")
    args = parser.parse_args()
    if not args.live or not args.confirm_synthetic_test:
        raise SystemExit("Use both --live and --confirm-synthetic-test for the public fictional-account test")
    if args.cleanup_fixture:
        identities = json.loads((STATE / "guided-plan-fixtures.json").read_text())
        print(json.dumps({"cleanup_completed": cleanup(identities)}))
    else:
        raise SystemExit(0 if execute(args.keep_ui_fixture) else 1)
