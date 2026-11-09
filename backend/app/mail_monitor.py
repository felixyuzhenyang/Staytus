"""Daily, explicitly opted-in INBOX checks with separately authorized summarization."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import threading
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import or_, select, update

from app.auth import require_profile_session
from app.db import SessionLocal, get_db
from app.integrations.connectors import read_recent_messages, verified_connected_email
from app.mail_monitor_models import MailMonitorPreference, MailMonitorSeen
from app.models import AuthSession, Profile, now, uid
from app.notification_models import ReminderNotice

router = APIRouter(prefix="/api/v1/mail-monitor", tags=["Read-only mailbox monitoring"])
Provider = Literal["google", "microsoft"]
_worker_lock = threading.Lock()


class MailMonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mail_monitor_worker_enabled: bool = True


class MonitorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    timezone: str = "UTC"
    check_hour: int = Field(default=9, ge=0, le=23)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as failure:
            raise ValueError("Choose a valid IANA timezone") from failure
        return value


def next_daily_check(stamp: datetime, zone: str, hour: int) -> datetime:
    """UTC-naive storage, local wall-clock schedule; first occurrence at DST fold."""
    tz = ZoneInfo(zone)
    local = stamp.replace(tzinfo=timezone.utc).astimezone(tz)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0, fold=0)
    if candidate.astimezone(timezone.utc).replace(tzinfo=None) <= stamp:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def preference(db, account_id, provider):
    row = db.get(MailMonitorPreference, (account_id, provider))
    if row is None:
        row = MailMonitorPreference(account_id=account_id, provider=provider, enabled=False,
            timezone="UTC", check_hour=9, revision=1, failure_count=0)
        db.add(row)
        db.flush()
    return row


def _identity(db, account_id, provider):
    return verified_connected_email(db, account_id, provider)


def _current_binding(db, row):
    identity = _identity(db, row.account_id, row.provider)
    return identity if identity and identity.get("connection_id") == row.connection_id else None


def state(db, row):
    from app.integrations.connection_models import MailAgentPermission
    identity = _identity(db, row.account_id, row.provider)
    current = bool(identity and identity.get("connection_id") == row.connection_id)
    permission = db.get(MailAgentPermission, (row.account_id, row.provider))
    content_analysis = bool(permission and permission.content_analysis_enabled)
    return {"provider": row.provider, "enabled": bool(row.enabled and current),
        "consent_current": bool(row.enabled and current), "connected": bool(identity),
        "mailbox": identity.get("email") if identity else None,
        "connection_id": identity.get("connection_id") if identity else None,
        "timezone": row.timezone, "check_hour": row.check_hour,
        "frequency": "daily", "next_check_at": _iso(row.next_check_at) if row.enabled and current else None,
        "last_check_at": _iso(row.last_check_at), "last_error_code": row.last_error_code,
        "scope": "Bounded matching official-topic messages in the inbox from the last30days",
        "message_bodies_stored": False, "model_sharing_enabled_by_monitor": bool(row.enabled and current and content_analysis),
        "content_analysis_enabled": content_analysis,
        "notice": "Background reading needs this separate opt-in. When email-content analysis is also enabled, only newly detected matching body text is summarized by watsonx.ai. Raw bodies and attachments are not retained; encrypted summaries include the subject, sender and short quoted date evidence and are deleted after 90 days. Mail is untrusted and does not establish policy."}


def _iso(value):
    return value.isoformat() + "Z" if value else None


@router.get("/{provider}")
def get_monitor(provider: Provider, session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    return state(db, preference(db, session.account_id, provider))


@router.patch("/{provider}")
def update_monitor(provider: Provider, body: MonitorUpdate, session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    row = preference(db, session.account_id, provider)
    identity = _identity(db, session.account_id, provider)
    if body.enabled and not identity:
        raise HTTPException(409, "Connect and verify this mailbox with read permission before enabling daily checks")
    row.enabled, row.timezone, row.check_hour = body.enabled, body.timezone, body.check_hour
    row.connection_id = identity["connection_id"] if body.enabled else None
    row.revision += 1
    row.lease_token, row.lease_until = None, None
    row.failure_count, row.last_error_code = 0, None
    row.updated_at = now()
    row.next_check_at = next_daily_check(row.updated_at, row.timezone, row.check_hour) if body.enabled else None
    db.flush()
    return state(db, row)


def check_mailbox(db, account_id, provider, *, background=False, stamp=None, reader=None):
    """User-action reads need no recurring consent; background reads always do."""
    stamp, reader = stamp or now(), reader or read_recent_messages
    if not db.scalar(select(Profile.id).where(Profile.account_id == account_id)):
        raise HTTPException(409, "Complete your profile before checking mail")
    row = preference(db, account_id, provider)
    identity = _identity(db, account_id, provider)
    if identity is None:
        row.enabled, row.next_check_at, row.last_error_code = False, None, "mailbox_reauthorization_required"
        db.commit()
        raise HTTPException(409, "Reconnect and verify this mailbox with read permission")
    if background and (not row.enabled or row.connection_id != identity["connection_id"]):
        row.enabled, row.next_check_at, row.last_error_code = False, None, "daily_consent_required"
        db.commit()
        raise HTTPException(409, "Daily checks require consent for the current connection")
    if not background and row.connection_id != identity["connection_id"]:
        # Manual permission does not enable recurring monitoring for a new link.
        row.enabled, row.connection_id, row.next_check_at = False, identity["connection_id"], None
        row.revision += 1
        db.flush()
    revision, connection_id, token = row.revision, identity["connection_id"], uid()
    db.flush()
    changed = db.execute(update(MailMonitorPreference).where(
        MailMonitorPreference.account_id == account_id, MailMonitorPreference.provider == provider,
        MailMonitorPreference.revision == revision,
        or_(MailMonitorPreference.lease_until.is_(None), MailMonitorPreference.lease_until <= stamp),
        or_(MailMonitorPreference.last_attempt_at.is_(None), MailMonitorPreference.last_attempt_at <= stamp - timedelta(minutes=5)),
    ).values(lease_token=token, lease_until=stamp + timedelta(minutes=2), last_attempt_at=stamp))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(429, "Mailbox checks are already running or were attempted within the last5minutes")
    db.commit()
    db.expire_all()
    row = db.get(MailMonitorPreference, (account_id, provider))
    if not _still_current(db, row, token, revision, connection_id, background):
        raise HTTPException(409, "Mailbox authorization changed; no read started")
    try:
        result = reader(db, account_id, provider, limit=20, for_agent=False, inbox_only=True)
    except HTTPException as failure:
        _failed(db, account_id, provider, token, stamp, failure.status_code)
        raise HTTPException(failure.status_code if failure.status_code in (401, 403, 409, 429) else 502,
            "Mailbox check could not complete; inspect the connection or retry later") from None
    except Exception:
        _failed(db, account_id, provider, token, stamp, 502)
        raise HTTPException(502, "Mailbox check failed safely; retry later") from None
    # End the provider read/refresh transaction so consent is read from a fresh
    # database snapshot, including a revocation committed during the request.
    db.commit()
    db.expire_all()
    row = db.get(MailMonitorPreference, (account_id, provider))
    if not _still_current(db, row, token, revision, connection_id, background):
        db.rollback()
        raise HTTPException(409, "Mailbox consent or connection changed; results discarded")
    profile = db.scalar(select(Profile).where(Profile.account_id == account_id))
    if not profile:
        db.rollback()
        raise HTTPException(409, "Complete your profile first")
    fresh = []
    messages = result.get("messages", [])[:20]
    for message in messages:
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id:
            continue
        hashed = sha256((provider + "\0" + connection_id + "\0" + message_id).encode()).hexdigest()
        seen = db.scalar(select(MailMonitorSeen.id).where(MailMonitorSeen.account_id == account_id,
            MailMonitorSeen.provider == provider, MailMonitorSeen.connection_id == connection_id,
            MailMonitorSeen.message_hash == hashed))
        if not seen:
            fresh.append((hashed, message))
    analysis_count = 0
    content_analysis_authorized = False
    if fresh:
        from app.integrations.connection_models import MailAgentPermission
        permission = db.get(MailAgentPermission, (account_id, provider))
        content_analysis_authorized = bool(permission and permission.content_analysis_enabled)
        if content_analysis_authorized:
            def monitor_consent_current(session):
                current = session.scalar(select(MailMonitorPreference).where(
                    MailMonitorPreference.account_id == account_id,
                    MailMonitorPreference.provider == provider).with_for_update())
                return _still_current(session, current, token, revision, connection_id, background)
            try:
                from app.mail_analysis import analyze_matching_messages
                analysis_count = len(analyze_matching_messages(db, account_id, profile, provider,
                    limit=min(5, len(fresh)), previews=[message for _, message in fresh[:5]],
                    consent_check=monitor_consent_current))
            except HTTPException:
                # A normal count notice remains useful. No raw body is retained.
                analysis_count = 0
            db.expire_all()
            current_permission = db.get(MailAgentPermission, (account_id, provider))
            content_analysis_authorized = bool(current_permission and current_permission.content_analysis_enabled)
            row = db.get(MailMonitorPreference, (account_id, provider))
            if not _still_current(db, row, token, revision, connection_id, background):
                db.rollback()
                raise HTTPException(409, "Mailbox consent or connection changed; results discarded")
        to_mark = fresh if not content_analysis_authorized else (fresh[:5] if analysis_count else [])
        for hashed, _ in to_mark:
            db.add(MailMonitorSeen(account_id=account_id, provider=provider, connection_id=connection_id,
                message_hash=hashed, first_seen_at=stamp))
        db.flush()
    if fresh:
        hashes = [hashed for hashed, _ in fresh]
        batch = sha256("".join(sorted(hashes)).encode()).hexdigest()
        dedup_key = f"mail:{provider}:{batch}"
        message = (f"Found {len(fresh)} newly detected official-topic message(s)." +
            (f" {analysis_count} private AI summary/summaries are ready in Connections." if analysis_count else "") +
            (f" {len(fresh) - len(to_mark)} message(s) remain queued for a later analysis batch."
                if len(to_mark) < len(fresh) and content_analysis_authorized else "") +
            " Open Connections and verify important details in your original mailbox. Email content is untrusted and does not establish a policy change.")
        data = {"provider": provider, "new_message_count": len(fresh), "untrusted_content": True,
            "analysis_count": analysis_count, "review_required": True,
            "source": "connected_mailbox", "policy_authority": False}
        notice = db.scalar(select(ReminderNotice).where(
            ReminderNotice.profile_id == profile.id, ReminderNotice.dedup_key == dedup_key))
        if notice is None:
            db.add(ReminderNotice(account_id=account_id, profile_id=profile.id,
                dedup_key=dedup_key, kind="mailbox_update", title="Relevant messages in your connected inbox",
                message=message, data=data, created_at=stamp))
        else:
            notice.message, notice.data, notice.created_at = message, data, stamp
            notice.read_at = notice.popup_seen_at = notice.superseded_at = None
    completed = db.execute(update(MailMonitorPreference).where(
        MailMonitorPreference.account_id == account_id, MailMonitorPreference.provider == provider,
        MailMonitorPreference.revision == revision, MailMonitorPreference.lease_token == token,
    ).values(last_check_at=stamp, last_error_code=None, failure_count=0, lease_token=None, lease_until=None,
        next_check_at=next_daily_check(stamp, row.timezone, row.check_hour) if row.enabled else None))
    if completed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Mailbox consent changed; results discarded")
    db.commit()
    return {"provider": provider, "new_relevant_count": len(fresh), "analysis_count": analysis_count,
        "checked_at": _iso(stamp),
        "messages": messages if not background else [], "untrusted_content": True,
        "partial_window": True, "notice": ("Checked a bounded recent inbox window; this is not a complete mailbox archive. "
            + ("This check was authorized to share matching body text with watsonx.ai; raw bodies were not retained. "
                if fresh and content_analysis_authorized else "No message body was authorized for model analysis during this check. ")
            + "No message was sent or marked read.")}


def _still_current(db, row, token, revision, connection_id, background):
    return bool(row and row.lease_token == token and row.revision == revision and row.connection_id == connection_id
        and (not background or row.enabled) and _current_binding(db, row))


def _failed(db, account_id, provider, token, stamp, status):
    db.rollback()
    row = db.get(MailMonitorPreference, (account_id, provider))
    if not row or row.lease_token != token:
        return
    row.lease_token, row.lease_until = None, None
    row.failure_count += 1
    row.last_error_code = "mailbox_reauthorization_required" if status in (401, 403, 409) else "mailbox_check_unavailable"
    if status in (401, 403, 409):
        row.enabled, row.next_check_at = False, None
    elif row.enabled:
        row.next_check_at = (stamp + timedelta(hours=1) if row.failure_count < 3
            else next_daily_check(stamp, row.timezone, row.check_hour))
    db.commit()


@router.post("/{provider}/check")
def check_now(provider: Provider, session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    return check_mailbox(db, session.account_id, provider)


def run_mail_monitor_once(factory=SessionLocal, *, stamp=None, reader=None):
    stamp = stamp or now()
    if not _worker_lock.acquire(blocking=False):
        return {"skipped": "already_running"}
    result = {"checked": 0, "failed": 0, "new_relevant_count": 0}
    try:
        with factory() as db:
            from app.mail_analysis import purge_expired_analyses
            purge_expired_analyses(db, stamp)
            db.commit()
            due = list(db.execute(select(MailMonitorPreference.account_id, MailMonitorPreference.provider).where(
                MailMonitorPreference.enabled.is_(True), MailMonitorPreference.next_check_at <= stamp)
                .order_by(MailMonitorPreference.next_check_at).limit(100)))
        for account_id, provider in due:
            with factory() as db:
                try:
                    checked = check_mailbox(db, account_id, provider, background=True, stamp=stamp, reader=reader)
                    result["checked"] += 1
                    result["new_relevant_count"] += checked["new_relevant_count"]
                except HTTPException:
                    result["failed"] += 1
        return result
    finally:
        _worker_lock.release()


def run_mail_monitor_worker(stop_event: threading.Event, interval_seconds=60):
    while not stop_event.is_set():
        try:
            if MailMonitorSettings().mail_monitor_worker_enabled:
                run_mail_monitor_once()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Mailbox monitoring batch failed; no provider details logged")
        stop_event.wait(max(10, interval_seconds))
