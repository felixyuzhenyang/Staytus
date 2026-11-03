"""Explicit public BFF smoke test; synthetic accounts only, with exact-row cleanup.

No mailbox connection, provider write, legal-rule review or real-user data is used.
Runtime secrets are read from the existing local configuration, never arguments.
"""
import argparse
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import delete, func, or_, select

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local/vercel"
BASE = "https://mystaytus.vercel.app"


def save(name, value):
    path = STATE / name
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def database():
    os.environ.update({k: str(v) for k, v in dotenv_values(ROOT / "backend/.env").items() if v is not None})
    sys.path.insert(0, str(ROOT / "backend"))
    from app import chat_models, mail_monitor_models, notification_models, policy_models  # noqa: F401
    from app.db import Base, SessionLocal
    from app.integrations import connection_models  # noqa: F401
    from app.models import Account, AuditEvent, Profile
    return Base, SessionLocal, Account, Profile, AuditEvent


def cleanup(identities):
    base, factory, account_model, profile_model, _ = database()
    with factory() as db:
        accounts, profiles = [], []
        for row in identities:
            account = db.get(account_model, row["account_id"])
            if account is None:
                continue
            if account.email != row["email"] or not account.email.startswith("staytus-public-smoke-") or not account.email.endswith("@example.invalid"):
                raise RuntimeError("Synthetic cleanup identity mismatch")
            owned = db.scalars(select(profile_model).where(profile_model.account_id == account.id)).all()
            if any(not profile.synthetic or profile.id != row.get("profile_id") for profile in owned):
                raise RuntimeError("Synthetic cleanup profile mismatch")
            accounts.append(account.id)
            profiles.extend(profile.id for profile in owned)
        for table in reversed(base.metadata.sorted_tables):
            if table.name in {"accounts", "user_profiles"}:
                continue
            clauses = []
            if "account_id" in table.c:
                clauses.append(table.c.account_id.in_(accounts))
            if "profile_id" in table.c:
                clauses.append(table.c.profile_id.in_(profiles))
            if clauses:
                db.execute(delete(table).where(or_(*clauses)))
        db.execute(delete(profile_model).where(profile_model.id.in_(profiles), profile_model.synthetic.is_(True)))
        db.execute(delete(account_model).where(account_model.id.in_(accounts)))
        db.commit()
        return not db.scalar(select(func.count()).select_from(account_model).where(account_model.id.in_(accounts)))


def execute(keep_fixture):
    from verify_orchestrate_context import PROMPT, validate_result
    _, factory, _, profile_model, audit_model = database()
    identities, clients = [], []
    report = {"passed": False, "base_url": BASE, "verified_at": datetime.now(UTC).isoformat(), "checks": {}}
    phase = "unauthenticated boundaries"
    try:
        with httpx.Client(base_url=BASE, timeout=45) as guest:
            assert guest.get("/api/backend/auth/me").status_code == 401
            assert guest.post("/tools/get_student_profile", json={}).status_code == 401
            assert guest.get("/api/v1/profile").status_code == 404
            assert guest.get("/internal/jobs/reminders").status_code == 401
            assert guest.post("/api/backend/auth/login", json={}, headers={"Origin": "https://foreign.example"}).status_code == 403
        report["checks"][phase] = True
        for index, status in enumerate(("F-1", "J-1 scholar")):
            phase = f"public account {index + 1} onboarding"
            identity = {"email": f"staytus-public-smoke-{uuid4()}@example.invalid", "password": secrets.token_urlsafe(32),
                        "name": f"SYNTHETIC Public Smoke {index + 1}"}
            client = httpx.Client(base_url=BASE, timeout=220, headers={"Origin": BASE})
            clients.append(client)
            result = client.post("/api/backend/auth/register", json=identity)
            assert result.status_code in {200, 201}
            payload = result.json()
            assert "access_token" not in payload and payload["needs_onboarding"] is True
            cookie = result.headers.get("set-cookie", "").lower()
            assert all(item in cookie for item in ("httponly", "secure", "samesite=lax"))
            identity["account_id"] = payload["account"]["id"]
            identities.append(identity)
            save("public-smoke-fixtures.json", identities)
            result = client.post("/api/backend/profile", json={"school": "University of Pennsylvania", "status_type": status,
                "program_start": "2026-01-01", "program_end": "2030-01-01", "notification_frequency": "off",
                "nationality": "Synthetic test only"})
            assert result.status_code == 201
            identity["profile_id"] = result.json()["id"]
            with factory() as db:
                profile = db.get(profile_model, identity["profile_id"])
                assert profile.account_id == identity["account_id"] and profile.email == identity["email"]
                profile.synthetic = True
                db.commit()
            save("public-smoke-fixtures.json", identities)
            dashboard = client.get("/api/backend/dashboard")
            assert dashboard.status_code == 200 and dashboard.json()["profile"]["id"] == identity["profile_id"]
            report["checks"][phase] = True
            print(json.dumps({"completed": phase}), flush=True)
        phase = "public hybrid policy retrieval"
        result = clients[0].get("/api/backend/policies", params={"q": "F-1 OPT application preparation", "include_pending": "true"})
        assert result.status_code == 200
        data = result.json()
        assert data["policies"] and "hybrid" in data["retrieval_mode"]
        assert any(row.get("url") or row.get("source_url") for row in data["policies"])
        report["checks"][phase] = {"passed": True, "retrieval_mode": data["retrieval_mode"], "results": len(data["policies"])}
        for index, (client, identity) in enumerate(zip(clients, identities, strict=True)):
            phase = f"public account {index + 1} Live chat"
            with factory() as db:
                before = db.scalar(select(func.count()).select_from(audit_model).where(audit_model.profile_id == identity["profile_id"],
                    audit_model.action == "tool.get_student_profile"))
            result = client.post("/api/backend/chat", json={"message": PROMPT})
            assert result.status_code == 200
            data = result.json()
            assert data["mode"] == "orchestrate"
            validate_result(data["message"], identity["profile_id"], identities[1 - index]["profile_id"])
            identity["conversation_id"] = data["conversation_id"]
            with factory() as db:
                after = db.scalar(select(func.count()).select_from(audit_model).where(audit_model.profile_id == identity["profile_id"],
                    audit_model.action == "tool.get_student_profile"))
            assert after - before == 1
            report["checks"][phase] = {"passed": True, "owned_tool_audit_delta": after - before}
            print(json.dumps({"completed": phase}), flush=True)
        phase = "cross-account conversation rejection"
        result = clients[1].post("/api/backend/chat", json={"message": "Synthetic ownership check", "conversation_id": identities[0]["conversation_id"]})
        assert result.status_code == 404
        report["checks"][phase] = True
        report["passed"] = True
        report["ui_fixture_retained"] = keep_fixture
    except Exception as error:  # noqa: BLE001 - Do not emit provider responses, cookies or passwords.
        report.update(failed_phase=phase, error_type=type(error).__name__)
    finally:
        for client in clients:
            try:
                client.post("/api/backend/auth/logout")
            except httpx.HTTPError:
                pass  # Exact database cleanup below also removes owned sessions.
            client.close()
        if report["passed"] and keep_fixture:
            save("public-smoke-fixtures.json", identities)
            report["cleanup_pending_ui_check"] = True
        else:
            report["cleanup_completed"] = cleanup(identities)
        save("public-bff-live-smoke.json", report)
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
        raise SystemExit("Explicit live synthetic-test confirmation is required")
    os.umask(0o077)
    if args.cleanup_fixture:
        result = cleanup(json.loads((STATE / "public-smoke-fixtures.json").read_text()))
        if result:
            report = json.loads((STATE / "public-bff-live-smoke.json").read_text())
            report.update(cleanup_completed=True, cleanup_pending_ui_check=False, ui_fixture_retained=False)
            save("public-bff-live-smoke.json", report)
            (STATE / "public-smoke-fixtures.json").unlink()
        print(json.dumps({"cleanup_completed": result}))
    else:
        raise SystemExit(0 if execute(args.keep_ui_fixture) else 2)
