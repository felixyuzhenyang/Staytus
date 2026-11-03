"""Explicit synthetic public OAuth pre-consent probe; never exchanges a real code.

Checks public callbacks, PKCE, scope separation, account/session ownership,
cancellation and one-time state. Does not prove provider consent/token exchange.
"""
import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from verify_public_deployment import BASE, ROOT, cleanup


def execute():
    identities, clients = [], []
    report = {"passed": False, "verified_at": datetime.now(UTC).isoformat(), "checks": {},
              "provider_code_exchange_tested": False, "real_mailbox_accessed": False}
    phase = "synthetic public registration"
    try:
        for index in range(2):
            identity = {"email": f"staytus-public-smoke-{uuid4()}@example.invalid",
                        "password": secrets.token_urlsafe(32), "name": f"SYNTHETIC OAuth Probe {index + 1}"}
            client = httpx.Client(base_url=BASE, timeout=60, follow_redirects=False, headers={"Origin": BASE})
            clients.append(client)
            response = client.post("/api/backend/auth/register", json=identity)
            assert response.status_code in {200, 201}
            payload = response.json()
            assert "access_token" not in payload
            identities.append({"email": identity["email"], "account_id": payload["account"]["id"]})
        phase = "production OAuth configuration"
        response = clients[0].get("/api/backend/connections")
        assert response.status_code == 200
        providers = {item["provider"]: item for item in response.json()["providers"]}
        google = providers["google"]
        callback = BASE + "/api/backend/connections/google/callback"
        assert google["configured"] and not google["connected"] and google["setup"]["callback_uri"] == callback
        report["checks"][phase] = True
        report["microsoft_configured"] = providers["microsoft"]["configured"]
        for capability, scope in (("mail_read", "gmail.readonly"), ("calendar_write", "calendar.events.owned")):
            phase = f"{capability} request and account-bound cancellation"
            response = clients[0].post("/api/backend/connections/google/start", json={"capability": capability})
            assert response.status_code == 200
            target = urlsplit(response.json()["authorization_url"])
            params = parse_qs(target.query)
            assert target.scheme == "https" and target.hostname == "accounts.google.com"
            assert params["redirect_uri"] == [callback]
            assert params["scope"] == ["https://www.googleapis.com/auth/" + scope]
            assert params["code_challenge_method"] == ["S256"] and len(params["code_challenge"][0]) >= 43
            assert params["access_type"] == ["offline"] and len(params["state"][0]) >= 32
            query = {"state": params["state"][0], "error": "access_denied"}
            route = "/api/backend/connections/google/callback"
            assert clients[1].get(route, params=query).status_code == 400
            cancelled = clients[0].get(route, params=query)
            assert cancelled.status_code == 303 and cancelled.headers["location"] == BASE + "/?connection=cancelled"
            assert clients[0].get(route, params=query).status_code == 400
            report["checks"][phase] = {"passed": True, "pkce": "S256", "scope": scope,
                                      "cross_account_denied": True, "state_replay_denied": True}
        report["passed"] = True
    except Exception as error:  # noqa: BLE001 - Never print cookies, authorization URL/state or responses.
        report.update(failed_phase=phase, error_type=type(error).__name__)
    finally:
        for client in clients:
            try:
                client.post("/api/backend/auth/logout")
            except httpx.HTTPError:
                pass
            client.close()
        report["cleanup_completed"] = cleanup(identities)
        path = ROOT / ".local/oauth-production/preauthorization-probe.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        path.chmod(0o600)
    print(json.dumps(report, indent=2))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-synthetic-test", action="store_true")
    args = parser.parse_args()
    if not args.live or not args.confirm_synthetic_test:
        raise SystemExit("Explicit live synthetic-test confirmation is required")
    os.umask(0o077)
    raise SystemExit(0 if execute() else 2)
