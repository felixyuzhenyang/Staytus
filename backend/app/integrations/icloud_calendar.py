"""Account-owned iCloud CalDAV access using an Apple app-specific password.

No Apple primary password, browser session, mail permission or send/invite API is
accepted. Authentication/discovery are bounded to fixed Apple HTTPS hosts. The
only write entry is called by the exact-content backend approval executor.
"""
from datetime import date
from hashlib import sha256
import json
import re
import time
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_session
from app.db import get_db
from app.integrations.connection_models import ProviderConnection
from app.integrations.connectors import ConnectorSettings, _cipher
from app.models import AuthSession, now, uid

router = APIRouter(prefix="/api/v1/connections/icloud", tags=["iCloud calendar"])
SCOPE = "icloud.calendar.write"
BASE = "https://caldav.icloud.com/"
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
MAX_XML_BYTES = 1_000_000
OPERATION_SECONDS = 30.0
PHASE_SECONDS = 5.0


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise httpx.TimeoutException("Calendar operation time budget exceeded")
    return remaining


class ICloudLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apple_id: str = Field(min_length=3, max_length=320)
    app_specific_password: SecretStr

    @model_validator(mode="before")
    @classmethod
    def strict_body_without_echo(cls, value):
        if not isinstance(value, dict) or set(value) != {"apple_id", "app_specific_password"}:
            raise HTTPException(422, "Supply only the Apple Account email and app-specific credential fields")
        return value

    @field_validator("apple_id")
    @classmethod
    def valid_id(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[^\s@\x00-\x1f]+@[^\s@\x00-\x1f]+\.[^\s@\x00-\x1f]+", value):
            raise ValueError("Enter the Apple Account email address")
        return value

    @field_validator("app_specific_password", mode="before")
    @classmethod
    def app_password_only(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-z]{4}(?:-[a-z]{4}){3}", value):
            # HTTPException avoids FastAPI's validation-error `input` echo.
            raise HTTPException(422, "Use an Apple-generated app-specific password, never the primary account password")
        return value


class ICloudSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendar_id: str = Field(min_length=1, max_length=64)


def _url(value: str, base: str = BASE):
    """All provider-controlled hrefs/redirects still cross an explicit host gate."""
    if not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid calendar location")
    resolved = urljoin(base, value)
    parsed = urlsplit(resolved)
    host = parsed.hostname or ""
    decoded = unquote(parsed.path)
    if (parsed.scheme != "https" or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not (host == "caldav.icloud.com" or re.fullmatch(r"p[0-9]{1,3}-caldav\.icloud\.com", host))
            or "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/"))):
        raise ValueError("Untrusted calendar location")
    return resolved


def _request(client, method, url, *, deadline, data=None, headers=None, redirects=2):
    """Never forward credentials outside the fixed Apple CalDAV hosts."""
    target = _url(url)
    for attempt in range(redirects + 1):
        # HTTPX phase timeouts alone reset across requests/chunks. One caller-
        # owned deadline spans all discovery redirects, parsing and final PUT.
        # Leave room for pool/connect/write/header phases instead of allowing
        # each phase to consume the entire remaining operation budget.
        timeout = min(PHASE_SECONDS, _remaining(deadline) / 4)
        with client.stream(method, target, content=data, headers=headers, timeout=timeout) as response:
            _remaining(deadline)
            if response.status_code in {301, 302, 307, 308}:
                if attempt == redirects or method != "PROPFIND":
                    raise ValueError("Calendar redirect refused")
                target = _url(response.headers.get("location", ""), target)
                continue
            if response.status_code in {401, 403}:
                raise HTTPException(409, "iCloud access was denied; reconnect using a valid app-specific password")
            content = bytearray()
            for chunk in response.iter_bytes():
                _remaining(deadline)
                content.extend(chunk)
                if len(content) > MAX_XML_BYTES:
                    raise ValueError("Calendar response too large")
            _remaining(deadline)
            return response.status_code, bytes(content), target, response.headers
    raise ValueError("Calendar redirect refused")


def _propfind(client, url, properties, depth="0", *, deadline):
    names = "".join(f"<{name}/>" for name in properties)
    body = (f'<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" '
            f'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>{names}</d:prop></d:propfind>')
    status, content, target, _ = _request(client, "PROPFIND", url, data=body.encode(),
        headers={"Content-Type": "application/xml; charset=utf-8", "Depth": depth}, deadline=deadline)
    if status != 207 or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("Invalid calendar discovery response")
    tree = ET.fromstring(content)
    if tree.tag != "{DAV:}multistatus" or len(tree) > 200:
        raise ValueError("Invalid calendar discovery response")
    return tree, target


def _properties(response):
    for propstat in response.findall("d:propstat", NS):
        if re.fullmatch(r"HTTP/[0-9.]+ 200(?: .*)?", propstat.findtext("d:status", "", NS)):
            prop = propstat.find("d:prop", NS)
            if prop is not None:
                yield prop


def _href(tree, name, base):
    for response in tree.findall("d:response", NS):
        for prop in _properties(response):
            href = prop.findtext(name + "/d:href", None, NS)
            if href:
                return _url(href, base)
    raise ValueError("Calendar discovery property unavailable")


def _discover(client, *, deadline):
    tree, target = _propfind(client, BASE, ["d:current-user-principal"], deadline=deadline)
    principal = _href(tree, "d:current-user-principal", target)
    tree, target = _propfind(client, principal, ["c:calendar-home-set"], deadline=deadline)
    home = _href(tree, "c:calendar-home-set", target)
    tree, target = _propfind(client, home,
        ["d:resourcetype", "d:displayname", "d:owner", "d:current-user-privilege-set", "c:supported-calendar-component-set"], "1", deadline=deadline)
    calendars = []
    for response in tree.findall("d:response", NS):
        _remaining(deadline)
        properties = list(_properties(response))
        if not properties:
            continue
        prop = ET.Element("props")
        for item in properties:
            prop.extend(list(item))
        if prop.find("d:resourcetype/c:calendar", NS) is None:
            continue
        owner = prop.findtext("d:owner/d:href", None, NS)
        # Only the authenticated principal's owned calendars. Shared writable
        # calendars are deliberately not offered as reminder destinations.
        if not owner or urlsplit(_url(owner, target)).path.rstrip("/") != urlsplit(principal).path.rstrip("/"):
            continue
        privileges = prop.find("d:current-user-privilege-set", NS)
        permitted = bool(privileges is not None and any(privileges.find(".//d:" + privilege, NS) is not None
                         for privilege in ("all", "write", "bind")))
        if not permitted:
            continue
        components = prop.find("c:supported-calendar-component-set", NS)
        if components is not None and not any(item.get("name") == "VEVENT" for item in components):
            continue
        location = _url(response.findtext("d:href", "", NS), target)
        if not location.endswith("/") or not urlsplit(location).path.startswith(urlsplit(home).path.rstrip("/") + "/"):
            continue
        name = (prop.findtext("d:displayname", "iCloud calendar", NS) or "iCloud calendar")[:160]
        name = "".join(char for char in name if ord(char) >= 32)
        calendars.append({"id": sha256(location.encode()).hexdigest(), "name": name, "url": location})
        if len(calendars) > 50:
            raise ValueError("Too many calendar collections")
    if not calendars:
        raise HTTPException(409, "No owned writable iCloud event calendar was found; enable iCloud Calendar and check permissions")
    return principal, calendars


def _connection(db, account_id):
    return db.scalar(select(ProviderConnection).where(ProviderConnection.account_id == account_id,
        ProviderConnection.provider == "icloud"))


def _stored(connection):
    try:
        value = json.loads(_cipher(ConnectorSettings()).decrypt(connection.encrypted_tokens.encode()))
        if not isinstance(value, dict) or not isinstance(value.get("apple_id"), str) or not value.get("app_specific_password"):
            raise ValueError("Missing calendar credentials")
        return value
    except (InvalidToken, TypeError, ValueError, KeyError):
        raise HTTPException(409, "Reconnect iCloud; stored calendar credentials are unavailable") from None


def _save(connection, value):
    connection.encrypted_tokens = _cipher(ConnectorSettings()).encrypt(json.dumps(value).encode()).decode()


def _selection(value):
    selected = value.get("selected_calendar_id")
    return next((item for item in value.get("calendars", []) if item.get("id") == selected), None)


def describe_connection(db, account_id):
    connection = _connection(db, account_id)
    configured = True
    try:
        _cipher(ConnectorSettings())
    except HTTPException:
        configured = False
    reconnect_required = False
    try:
        value = _stored(connection) if connection and configured else None
    except HTTPException:
        value, reconnect_required = None, True
    selected = _selection(value) if value else None
    return {"provider": "icloud", "configured": configured, "connected": connection is not None,
        "connection_id": connection.id if connection else None,
        "calendar_write": bool(selected and connection and SCOPE in connection.scopes),
        "scopes": [SCOPE] if connection and SCOPE in connection.scopes else [],
        "capabilities": {"mail_read": False, "mail_draft": False, "calendar_write": bool(selected)},
        "agent_access": False, "email_identity_verified": False, "reconnect_required": reconnect_required,
        "account_label": value["apple_id"] if value else None,
        "selected_calendar_id": selected["id"] if selected else None,
        "calendars": [{"id": item["id"], "name": item["name"]} for item in value.get("calendars", [])] if value else [],
        "last_sync_at": connection.last_sync_at.isoformat() + "Z" if connection and connection.last_sync_at else None,
        "setup": {"configured": configured, "authentication": "apple_app_specific_password",
            "missing": [] if configured else ["CONNECTOR_TOKEN_KEY"],
            "errors": [] if configured else ["A valid server token-encryption key is required"],
            "requirements": ["Apple Account two-factor authentication", "A dedicated Apple-generated app-specific password", "An owned writable iCloud calendar"],
            "help_url": "https://support.apple.com/en-us/102654",
            "notice": "Use a dedicated app-specific password, never your primary Apple password. Stored credentials are encrypted. Apple app-specific credentials are not granular OAuth scopes; Staytus restricts their use to calendar discovery and approved event creation, with no mailbox access or invitations."}}


def approval_connector_target(db, profile):
    connection = _connection(db, profile.account_id)
    value = _stored(connection) if connection else None
    selected = _selection(value) if value else None
    return {"provider": "icloud", "connection_id": connection.id if connection and selected else None,
        "account_label": f"{value['apple_id']} · {selected['name']}" if selected else None}


@router.get("")
def status(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    return describe_connection(db, session.account_id)


@router.post("/link")
def link(body: ICloudLink, session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    settings = ConnectorSettings()
    _cipher(settings)  # fail before transmitting a credential if storage is not ready
    deadline = time.monotonic() + OPERATION_SECONDS
    try:
        with httpx.Client(timeout=10, follow_redirects=False,
                auth=httpx.BasicAuth(body.apple_id, body.app_specific_password.get_secret_value())) as client:
            principal, calendars = _discover(client, deadline=deadline)
    except httpx.TimeoutException:
        raise HTTPException(409, "iCloud discovery timed out before any calendar change; retry connecting when the service is available") from None
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, ET.ParseError, TypeError, KeyError):
        raise HTTPException(502, "iCloud discovery failed; verify the app-specific password and calendar access") from None
    # Rotate the binding for every relink; old previews must never switch targets.
    db.execute(delete(ProviderConnection).where(ProviderConnection.account_id == session.account_id,
        ProviderConnection.provider == "icloud"))
    connection = ProviderConnection(id=uid(), account_id=session.account_id, provider="icloud", scopes=[SCOPE], last_sync_at=now())
    _save(connection, {"apple_id": body.apple_id, "app_specific_password": body.app_specific_password.get_secret_value(),
        "principal_url": principal, "calendars": calendars,
        "selected_calendar_id": calendars[0]["id"] if len(calendars) == 1 else None})
    db.add(connection)
    db.flush()
    return describe_connection(db, session.account_id)


@router.patch("/calendar")
def select_calendar(body: ICloudSelection, session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    connection = _connection(db, session.account_id)
    if connection is None:
        raise HTTPException(409, "Connect iCloud before choosing a calendar")
    value = _stored(connection)
    if not any(item["id"] == body.calendar_id for item in value.get("calendars", [])):
        raise HTTPException(422, "Choose one of this account's discovered calendars")
    if value.get("selected_calendar_id") != body.calendar_id:
        value["selected_calendar_id"] = body.calendar_id
        connection.id = uid()
        _save(connection, value)
        db.flush()
    return describe_connection(db, session.account_id)


@router.delete("")
def disconnect(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    db.execute(delete(ProviderConnection).where(ProviderConnection.account_id == session.account_id,
        ProviderConnection.provider == "icloud"))
    return {"disconnected": True, "provider": "icloud",
        "notice": "Local credential removed. Revoke the dedicated app-specific password in Apple Account settings to remove provider access too."}


def execute_calendar(db, approval, profile):
    if (approval.kind != "calendar" or approval.status != "EXECUTING" or approval.profile_id != profile.id
            or approval.payload.get("provider") != "icloud"):
        raise HTTPException(409, "iCloud writes require the current user's claimed calendar approval")
    target = approval.payload.get("_connector_target")
    if (not isinstance(target, dict) or set(target) != {"provider", "connection_id", "account_label"}
            or target.get("provider") != "icloud" or not target.get("connection_id")):
        raise HTTPException(409, "Connect iCloud and create a fresh preview bound to the selected calendar")
    connection = _connection(db, profile.account_id)
    if not connection or connection.id != target["connection_id"] or SCOPE not in connection.scopes:
        raise HTTPException(409, "iCloud account or calendar changed; create a fresh preview")
    value = _stored(connection)
    selected = _selection(value)
    if not selected:
        raise HTTPException(409, "Choose an iCloud calendar and create a fresh preview")
    # Discover again before the write: ownership and create privilege may have
    # changed since linking. Read failures cannot have created an event.
    deadline = time.monotonic() + OPERATION_SECONDS
    try:
        with httpx.Client(timeout=10, follow_redirects=False,
                auth=httpx.BasicAuth(value["apple_id"], value["app_specific_password"])) as client:
            _, current = _discover(client, deadline=deadline)
            if not any(item["url"] == selected["url"] for item in current):
                raise HTTPException(409, "The chosen iCloud calendar is no longer owned and writable; reconnect")
            from app.services import calendar_ics
            event = calendar_ics(approval)
            event_id = sha256(f"staytus:{profile.account_id}:{approval.id}".encode()).hexdigest()
            location = _url(selected["url"] + event_id + ".ics")
            # If reads/parsing exhausted the shared budget, no write may start.
            _remaining(deadline)
            # If-None-Match prevents replacing an existing object. There is one
            # PUT attempt; a timeout/lost response is never blindly repeated.
            try:
                status_code, _, _, headers = _request(client, "PUT", location, data=event.encode("utf-8"),
                    headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"}, redirects=0, deadline=deadline)
            except HTTPException:
                raise
            except (httpx.HTTPError, ValueError, TypeError):
                raise HTTPException(502, "iCloud event creation could not be confirmed; check Calendar before creating another preview") from None
            if status_code != 201:
                raise HTTPException(502, "iCloud event creation could not be confirmed; check Calendar before creating another preview")
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(409, "iCloud verification timed out before any calendar change; reconnect or create a fresh preview later") from None
    except (httpx.HTTPError, ValueError, ET.ParseError, TypeError, KeyError):
        raise HTTPException(409, "iCloud calendar could not be verified; reconnect before creating a new preview") from None
    connection.last_sync_at = now()
    return {"id": f"calendar-{approval.id}", "mode": "provider_calendar", "provider": "icloud",
        "external_id": event_id, "calendar_name": selected["name"], "date": date.fromisoformat(str(approval.payload["date"])).isoformat(),
        "all_day": True, "reminder_minutes": approval.payload.get("reminder_minutes", 1440),
        "attendees_notified": False, "created_at": now().isoformat() + "Z"}
