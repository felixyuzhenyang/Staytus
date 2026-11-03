"""Bounded two-process/two-account verification on the configured PostgreSQL.

Only synthetic .invalid accounts are created and removed. No IBM/model/mail requests.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / ".local/shared-database-verification.json")
    parser.add_argument("--database-env-file", type=Path,
                        help="Override only DATABASE_URL from a private file, preserving application secrets")
    args = parser.parse_args()
    from dotenv import dotenv_values
    environment = {**os.environ, **{key: value for key, value in dotenv_values(ROOT / "backend/.env").items() if value is not None},
                   "POLICY_WORKER_ENABLED": "false", "NOTIFICATION_WORKER_ENABLED": "false", "MAIL_MONITOR_WORKER_ENABLED": "false"}
    if args.database_env_file:
        database_url = dotenv_values(args.database_env_file).get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("The database override must contain DATABASE_URL")
        environment["DATABASE_URL"] = database_url
    os.environ.update(environment)
    from app.config import get_settings
    from app.db import SessionLocal, engine
    from app.models import Account, AuthSession, Profile
    from app.auth import digest, mint_tool_context
    from app.schema import metadata
    from sqlalchemy import delete, or_, select
    import httpx
    if engine.dialect.name != "postgresql":
        raise SystemExit("This verification requires the shared PostgreSQL database.")
    processes, accounts, profiles, logs = [], [], [], []
    api_port, gateway_port = port(), port()
    report = {"real_postgresql": True, "external_provider_calls": False}

    def start(module, number):
        filename = ROOT / ".local" / (module.split(".")[-1] + "-shared-verification.log")
        filename.touch(mode=0o600, exist_ok=True)
        log = filename.open("w")
        logs.append(log)
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", module + ":app", "--host", "127.0.0.1",
                                    "--port", str(number), "--no-access-log"], cwd=ROOT / "backend", env=environment,
                                   stdout=log, stderr=log)
        processes.append(process)
        end = time.monotonic() + 20
        while time.monotonic() < end and process.poll() is None:
            try:
                if httpx.get(f"http://127.0.0.1:{number}/health", timeout=1).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("A verification server did not become healthy")

    try:
        start("app.main", api_port)
        gateway = start("app.tool_gateway", gateway_port)
        capabilities = []
        with httpx.Client(base_url=f"http://127.0.0.1:{api_port}", timeout=10) as api:
            for index in range(2):
                response = api.post("/api/v1/auth/register", json={"email": f"shared-{uuid4().hex}@example.invalid",
                    "name": f"STAYTUS SYNTHETIC SHARED DB {index}", "password": secrets.token_urlsafe(24)})
                assert response.status_code == 201
                payload = response.json()
                account_id = payload["account"]["id"]
                accounts.append(account_id)
                token = payload["access_token"]
                response = api.post("/api/v1/profile", headers={"Authorization": "Bearer " + token}, json={
                    "status_type": "F-1" if index == 0 else "J-1 student", "program_start": "2026-08-20", "program_end": "2028-05-20"})
                assert response.status_code == 201
                profiles.append(response.json()["id"])
                with SessionLocal() as db:
                    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token)))
                    capabilities.append(mint_tool_context(session))
        with httpx.Client(base_url=f"http://127.0.0.1:{gateway_port}", timeout=10) as client:
            for index, capability in enumerate(capabilities):
                headers = {"X-Tool-Key": get_settings().tool_key, "X-Staytus-Context": capability}
                response = client.post("/tools/get_student_profile", headers=headers, json={})
                assert response.status_code == 200 and response.json()["id"] == profiles[index]
                assert response.json()["id"] != profiles[1-index]
                assert client.post("/tools/get_student_profile", headers=headers, json={"profile_id": profiles[1-index]}).status_code == 422
            assert client.post("/tools/get_student_profile", json={}).status_code == 401
            assert client.get("/api/v1/auth/me").status_code == 404
        gateway.terminate()
        gateway.wait(timeout=10)
        start("app.tool_gateway", gateway_port)
        response = httpx.post(f"http://127.0.0.1:{gateway_port}/tools/get_student_profile", json={}, timeout=10,
            headers={"X-Tool-Key": get_settings().tool_key, "X-Staytus-Context": capabilities[0]})
        assert response.status_code == 200 and response.json()["id"] == profiles[0]
        report.update({"independent_api_and_gateway": True, "two_accounts_isolated": True,
                       "forged_owner_rejected": True, "gateway_private_routes_absent": True,
                       "gateway_restart_preserves_session_and_profile": True})
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for stream in logs:
            stream.close()
        if accounts:
            with engine.begin() as connection:
                for table in reversed(metadata().sorted_tables):
                    conditions = []
                    if "account_id" in table.c:
                        conditions.append(table.c.account_id.in_(accounts))
                    if "profile_id" in table.c:
                        conditions.append(table.c.profile_id.in_(profiles))
                    if table.name == "accounts":
                        conditions.append(table.c.id.in_(accounts))
                    if conditions:
                        connection.execute(delete(table).where(or_(*conditions)))
            with SessionLocal() as db:
                assert db.scalar(select(Account.id).where(Account.id.in_(accounts))) is None
                assert db.scalar(select(Profile.id).where(Profile.id.in_(profiles))) is None
        report["synthetic_records_removed"] = True
        engine.dispose()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    args.report.chmod(0o600)
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Shared database verification failed ({type(error).__name__}); inspect private logs.", file=sys.stderr)
        raise SystemExit(1) from None
