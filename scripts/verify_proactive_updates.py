"""Explicit fictional-account proof: logged-out generation, no user chat prompt."""
import argparse
import json
import secrets
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from verify_public_deployment import BASE, STATE, cleanup, database, save


def execute(keep_fixture=False):
    _, factory, _, Profile, _ = database()
    from app.assistant_update_models import AssistantUpdate
    from app.assistant_updates import run_assistant_once
    from app.chat_models import Conversation
    from app.models import AuthSession, now
    clients, identities = [], []
    report = {"passed": False, "checks": {}}
    phase = "onboarding"
    try:
        today = now().date()
        for index, category in enumerate(("F-1", "J-1 student")):
            identity = {"email": f"staytus-public-smoke-{uuid4()}@example.invalid", "password": secrets.token_urlsafe(32),
                "name": f"SYNTHETIC Proactive Check {index+1}"}
            client = httpx.Client(base_url=BASE, headers={"Origin": BASE}, timeout=195)
            clients.append(client)
            result = client.post("/api/backend/auth/register", json=identity)
            assert result.status_code in (200, 201), result.status_code
            identity["account_id"] = result.json()["account"]["id"]
            identities.append(identity)
            save("proactive-fixtures.json", identities)
            result = client.post("/api/backend/profile", json={"school": "University of Pennsylvania", "status_type": category,
                "program_start": (today-timedelta(days=60)).isoformat(), "program_end": (today+timedelta(days=730)).isoformat(),
                "travel_date": (today+timedelta(days=30)).isoformat(), "nationality": "Synthetic test only", "notification_frequency": "daily"})
            assert result.status_code == 201, result.status_code
            identity["profile_id"] = result.json()["id"]
            with factory() as db:
                db.get(Profile, identity["profile_id"]).synthetic = True
                db.commit()
            save("proactive-fixtures.json", identities)
            assert client.patch("/api/backend/assistant-updates/preferences", json={"enabled": True, "language": "zh"}).status_code == 200
            assert client.post("/api/backend/auth/logout").status_code == 200
        phase = "logged_out_model_generation"
        for identity in identities:
            with factory() as db:
                assert db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.account_id == identity["account_id"])) == 0
            result = run_assistant_once(factory, account_id=identity["account_id"], max_messages=1)
            assert result["generated"] == 1, json.dumps(result)
            assert run_assistant_once(factory, account_id=identity["account_id"], max_messages=1)["generated"] == 0
        report["checks"][phase] = {"accounts": 2, "active_sessions": 0, "deduplicated": True}
        for index, (identity, client) in enumerate(zip(identities, clients, strict=True)):
            phase = f"return_without_chat_prompt_{index}"
            assert client.post("/api/backend/auth/login", json={"email": identity["email"], "password": identity["password"]}).status_code == 200
            response = client.get("/api/backend/assistant-updates")
            assert response.status_code == 200
            messages = response.json()["updates"]
            assert len(messages) == 1 and messages[0]["generated_by"] == "watsonx.ai" and messages[0]["model"]
            assert len(messages[0]["content"]["summary"]) > 15 and not messages[0]["read_at"]
            identity["update_id"] = messages[0]["id"]
            with factory() as db:
                assert db.scalar(select(func.count()).select_from(Conversation).where(Conversation.account_id == identity["account_id"])) == 0
                assert db.scalar(select(func.count()).select_from(AssistantUpdate).where(AssistantUpdate.account_id == identity["account_id"], AssistantUpdate.state == "READY")) == 1
            report["checks"][phase] = {"message_persisted": True, "source_count": len(messages[0]["citations"]), "user_chat_turns": 0}
        phase = "public_ownership_and_manual_dedup"
        assert clients[1].post(f"/api/backend/assistant-updates/{identities[0]['update_id']}/read").status_code == 404
        result = clients[0].post("/api/backend/assistant-updates/check")
        assert result.status_code == 200 and result.json()["generated"] == 0
        assert httpx.get(BASE + "/internal/jobs/assistant").status_code == 401
        report["checks"][phase] = True
        report["passed"] = True
    except Exception as error:  # noqa: BLE001 - No credentials or personal/provider text in console output.
        report.update(failed_phase=phase, error_type=type(error).__name__)
        if isinstance(error, AssertionError) and str(error).startswith("{\"queued\""):
            report["generation_status"] = json.loads(str(error))
    finally:
        for client in clients:
            client.close()
        if report["passed"] and keep_fixture:
            save("proactive-fixtures.json", identities)
            report["ui_fixture_retained"] = True
        else:
            report["cleanup_completed"] = cleanup(identities)
        save("proactive-verification.json", report)
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
        raise SystemExit("Use --live --confirm-synthetic-test for the public fictional-account test")
    if args.cleanup_fixture:
        cleaned = cleanup(json.loads((STATE / "proactive-fixtures.json").read_text()))
        report_path = STATE / "proactive-verification.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        report.update(cleanup_completed=cleaned, ui_fixture_retained=False)
        save("proactive-verification.json", report)
        print(json.dumps({"cleanup_completed": cleaned}))
    else:
        raise SystemExit(0 if execute(args.keep_ui_fixture) else 1)
