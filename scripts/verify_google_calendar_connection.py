"""Read-only, exactly scoped check after the user grants Calendar OAuth consent.

Target must come from this user's authenticated, visible Connections details.
Never enumerates connections, creates a session or returns token/event content.
"""
import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from verify_public_deployment import ROOT, database


def execute(target_file):
    target = json.loads(target_file.read_text())
    connection_id = str(UUID(target["connection_id"]))
    expected_mailbox = target["expected_mailbox"].strip().casefold()
    if target.get("source") != "authenticated-own-connections-ui" or "@" not in expected_mailbox:
        raise ValueError("Explicit own-account UI target is required")
    _, factory, _, _, _ = database()
    from app.integrations.connection_models import ProviderConnection
    from app.integrations.connectors import (
        ConnectorSettings,
        _access_token,
        _can_calendar,
        _tokens,
    )
    report = {"passed": False, "checked_at": datetime.now(UTC).isoformat(),
              "query_scope": "one UI-observed connection UUID and Google provider",
              "calendar_events_created": 0, "event_details_requested": False}
    try:
        with factory() as db:
            # Exact UUID was obtained from the signed-in user's Connections UI.
            # No global/user-list query or operator-created login session.
            connection = db.scalar(select(ProviderConnection).where(
                ProviderConnection.id == connection_id, ProviderConnection.provider == "google"))
            assert connection is not None
            settings = ConnectorSettings()
            tokens = _tokens(connection, settings)
            identity = tokens.get("mailbox_identity", {})
            assert identity.get("verified") is True and identity.get("email", "").casefold() == expected_mailbox
            assert _can_calendar(connection)
            report.update(verified_mailbox_matches=True, encrypted_token_verified=True,
                offline_refresh_available=bool(tokens.get("refresh_token")),
                account_fingerprint=hashlib.sha256(connection.account_id.encode()).hexdigest()[:12])
            with httpx.Client(timeout=25, follow_redirects=False) as client:
                token = _access_token(connection, client, settings)
                response = client.get("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": "Bearer " + token}, params={"maxResults": 1, "fields": "kind"})
            report["calendar_api_http_status"] = response.status_code
            assert response.status_code == 200 and response.json() == {"kind": "calendar#events"}
            db.commit()  # Persist a routine refresh if one was required.
            report["passed"] = True
    except Exception as error:  # noqa: BLE001 - Do not print tokens, mailbox identities or response bodies.
        report["error_type"] = type(error).__name__
    path = ROOT / ".local/oauth-production/calendar-readonly-verification.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps(report, indent=2))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-file", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-own-connection", action="store_true")
    args = parser.parse_args()
    if not args.live or not args.confirm_own_connection:
        raise SystemExit("Explicit own-connection read-only test confirmation is required")
    os.umask(0o077)
    raise SystemExit(0 if execute(args.target_file) else 2)
