"""Account-owned reminders and opt-in digest outbox; not a model tool surface.

Policy capture remains in policy_pipeline. This module consumes its existing
notifications and the deterministic planning service, without inventing policy
or changing review/legal status. Email is off until an operator configures a sender
and a user consents to delivery to an OAuth-verified connected mailbox.
"""
from datetime import date, datetime, time, timedelta, timezone
from calendar import monthrange
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
import smtplib
import ssl
import threading
import httpx
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import require_profile_session
from app.db import SessionLocal, get_db
from app.models import Account, AuthSession, Notification, Profile, now
from app.notification_models import NotificationDelivery, NotificationDeliveryItem, NotificationPreference, ReminderNotice
from app.services import audit, deadlines, iso

router = APIRouter(prefix="/api/v1/notifications", tags=["Personal reminders"])
_worker_lock = threading.Lock()
MAX_EMAIL_ATTEMPTS = 3


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    notification_worker_enabled: bool = True
    notification_email_enabled: bool = False
    notification_email_transport: Literal["smtp", "brevo_api"] = "smtp"
    notification_brevo_api_key: str = Field(default="", repr=False)
    notification_smtp_host: str = ""
    notification_smtp_port: int = 465
    notification_smtp_security: Literal["ssl", "starttls"] = "ssl"
    notification_smtp_username: str = Field(default="", repr=False)
    notification_smtp_password: str = Field(default="", repr=False)
    notification_from_email: str = ""


def email_readiness(settings: NotificationSettings) -> dict:
    missing = []
    if not settings.notification_email_enabled:
        missing.append("NOTIFICATION_EMAIL_ENABLED")
    fields = [("notification_from_email", "NOTIFICATION_FROM_EMAIL")]
    fields += [("notification_brevo_api_key", "NOTIFICATION_BREVO_API_KEY")] if settings.notification_email_transport == "brevo_api" else [
            ("notification_smtp_host", "NOTIFICATION_SMTP_HOST"),
            ("notification_smtp_username", "NOTIFICATION_SMTP_USERNAME"),
            ("notification_smtp_password", "NOTIFICATION_SMTP_PASSWORD")]
    for field, variable in fields:
        if not getattr(settings, field):
            missing.append(variable)
    errors = []
    if settings.notification_email_transport == "smtp" and not 1 <= settings.notification_smtp_port <= 65535:
        errors.append("invalid_smtp_port")
    if settings.notification_from_email and not _email_address(settings.notification_from_email):
        errors.append("invalid_from_email")
    if any(c.isspace() for c in settings.notification_smtp_host):
        errors.append("invalid_smtp_host")
    return {"configured": not missing and not errors, "transport": settings.notification_email_transport, "missing": missing, "errors": errors,
        "verified_mailbox_required": True, "delivery_requires_user_opt_in": True}


def _email_address(value: str) -> bool:
    return bool(value and "\r" not in value and "\n" not in value and not any(c.isspace() for c in value)
        and parseaddr(value)[1] == value and value.count("@") == 1)


def verified_mailbox(db: Session, account_id: str, provider: str | None = None) -> dict | None:
    # Legacy OAuth links without verified provider identity must be relinked.
    from app.integrations import connectors
    helper = getattr(connectors, "verified_connected_email", None)
    value = helper(db, account_id, provider) if helper else None
    if (not isinstance(value, dict) or value.get("provider") not in {"google", "microsoft"}
            or not _email_address(str(value.get("email", ""))) or not value.get("connection_id")):
        return None
    return value


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_app_enabled: bool | None = None
    popup_enabled: bool | None = None
    email_enabled: bool | None = None
    email_provider: Literal["google", "microsoft"] | None = None
    frequency: Literal["daily", "weekly", "monthly", "off"] | None = None
    timezone: str | None = Field(default=None, max_length=100)
    digest_hour: int | None = Field(default=None, ge=0, le=23)
    digest_weekday: int | None = Field(default=None, ge=0, le=6)
    digest_monthday: int | None = Field(default=None, ge=1, le=31)
    lead_days: int | None = Field(default=None, ge=0, le=30)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Choose a valid IANA timezone") from None
        return value


def preferences_for(db: Session, account_id: str) -> NotificationPreference:
    pref = db.get(NotificationPreference, account_id)
    if pref is None:
        try:
            with db.begin_nested():
                pref = NotificationPreference(account_id=account_id, digest_monthday=now().day)
                db.add(pref)
                db.flush()
        except IntegrityError:
            pref = db.get(NotificationPreference, account_id)
            if pref is None:
                raise
    return pref


def next_digest_at(stamp: datetime, zone: str, hour: int, weekday: int, frequency: str,
        monthday: int | None = None) -> datetime | None:
    if frequency == "off":
        return None
    local = stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone))
    day = local.date()
    if frequency == "weekly":
        day += timedelta(days=(weekday - day.weekday()) % 7)
    elif frequency == "monthly":
        day = day.replace(day=min(monthday or day.day, monthrange(day.year, day.month)[1]))
    candidate = datetime.combine(day, time(hour), ZoneInfo(zone))
    # Round-trip normalizes a nonexistent local hour during a DST spring gap.
    candidate = candidate.astimezone(timezone.utc).astimezone(ZoneInfo(zone))
    if candidate <= local:
        if frequency == "monthly":
            year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
            day = date(year, month, min(monthday or local.day, monthrange(year, month)[1]))
        else:
            day += timedelta(days=7 if frequency == "weekly" else 1)
        candidate = datetime.combine(day, time(hour), ZoneInfo(zone)).astimezone(timezone.utc)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def _preferences_json(db: Session, pref: NotificationPreference, profile: Profile) -> dict:
    identity = verified_mailbox(db, profile.account_id, pref.email_provider)
    bound = bool(identity and identity["connection_id"] == pref.email_connection_id
        and identity["email"].casefold() == (pref.email_recipient or "").casefold())
    return {"in_app_enabled": pref.in_app_enabled, "popup_enabled": pref.popup_enabled,
        "email_enabled": pref.email_enabled, "frequency": profile.notification_frequency,
        "timezone": pref.timezone, "digest_hour": pref.digest_hour, "digest_weekday": pref.digest_weekday,
        "digest_monthday": pref.digest_monthday,
        "lead_days": pref.lead_days, "email_provider": pref.email_provider,
        "email_recipient": pref.email_recipient if pref.email_enabled else None,
        "verified_mailbox": {k: identity[k] for k in ("email", "provider")} if identity else None,
        "email_consent_current": bound if pref.email_enabled else False, "next_email_at": iso(pref.next_email_at)}


def _notice_json(notice: ReminderNotice) -> dict:
    return {"id": notice.id, "kind": notice.kind, "title": notice.title, "message": notice.message,
        "data": notice.data, "created_at": iso(notice.created_at), "read_at": iso(notice.read_at),
        "popup_seen_at": iso(notice.popup_seen_at)}


@router.get("/preferences")
def get_preferences(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    profile = db.get(Profile, session.profile_id)
    pref = preferences_for(db, session.account_id)
    mailboxes = [verified_mailbox(db, session.account_id, provider) for provider in ("google", "microsoft")]
    return {"preferences": _preferences_json(db, pref, profile), "email_readiness": email_readiness(NotificationSettings()),
        "verified_mailboxes": [{k: item[k] for k in ("email", "provider")} for item in mailboxes if item],
        "channels": {"in_app": "available_while_app_is_open", "browser_push": "not_configured",
            "background_delivery": "requires_running_backend", "native_device_notifications": "not_configured"}}


@router.patch("/preferences")
def set_preferences(body: PreferenceUpdate, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    values = body.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise HTTPException(422, "Provide non-null reminder settings")
    profile = db.get(Profile, session.profile_id)
    pref = preferences_for(db, session.account_id)
    provider = values.get("email_provider", pref.email_provider)
    if values.get("email_enabled") is True or (pref.email_enabled and "email_provider" in values):
        if not email_readiness(NotificationSettings())["configured"]:
            raise HTTPException(409, "Email delivery needs an operator-configured sending service before it can be enabled.")
        identity = verified_mailbox(db, session.account_id, provider)
        if identity is None:
            raise HTTPException(409, "Connect and authorize your mailbox before enabling email digests.")
        pref.email_provider, pref.email_connection_id, pref.email_recipient = (
            identity["provider"], identity["connection_id"], identity["email"])
    for key, value in values.items():
        if key == "frequency":
            profile.notification_frequency = value
        else:
            setattr(pref, key, value)
    if values.get("email_enabled") is False:
        pref.email_connection_id = pref.email_recipient = None
    pref.updated_at = now()
    pref.scheduled_frequency = profile.notification_frequency
    pref.next_email_at = next_digest_at(pref.updated_at, pref.timezone, pref.digest_hour, pref.digest_weekday,
        profile.notification_frequency, pref.digest_monthday) if pref.email_enabled else None
    # Existing queued snapshots cannot survive changing consent or preferences.
    cancel_queued(db, session.account_id, pref.updated_at, "preferences_changed")
    audit(db, profile.id, "notifications.preferences_updated", {"fields": sorted(values)})
    db.flush()
    return get_preferences(session, db)


@router.get("")
def list_notifications(limit: int = Query(default=30, ge=1, le=100),
        session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    pref = preferences_for(db, session.account_id)
    statement = select(ReminderNotice).where(ReminderNotice.account_id == session.account_id,
        ReminderNotice.profile_id == session.profile_id, ReminderNotice.superseded_at.is_(None))
    items = list(db.scalars(statement.order_by(ReminderNotice.created_at.desc()).limit(limit))) if pref.in_app_enabled else []
    unread = db.scalar(select(func.count()).select_from(ReminderNotice).where(
        ReminderNotice.account_id == session.account_id, ReminderNotice.profile_id == session.profile_id,
        ReminderNotice.superseded_at.is_(None), ReminderNotice.read_at.is_(None))) if pref.in_app_enabled else 0
    return {"notifications": [_notice_json(row) for row in items], "unread_count": unread,
        "popup_enabled": pref.in_app_enabled and pref.popup_enabled}


def _owned_notice(db: Session, session: AuthSession, notice_id: str) -> ReminderNotice:
    value = db.scalar(select(ReminderNotice).where(ReminderNotice.id == notice_id,
        ReminderNotice.account_id == session.account_id, ReminderNotice.profile_id == session.profile_id))
    if value is None:
        raise HTTPException(404, "Notification not found")
    return value


@router.post("/read-all")
def read_all(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    db.execute(update(ReminderNotice).where(ReminderNotice.account_id == session.account_id,
        ReminderNotice.profile_id == session.profile_id, ReminderNotice.read_at.is_(None)).values(read_at=now()))
    return {"ok": True}


@router.post("/{notice_id}/read")
def read_notice(notice_id: str, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    _owned_notice(db, session, notice_id).read_at = now()
    return {"ok": True}


@router.post("/{notice_id}/popup-seen")
def popup_seen(notice_id: str, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    _owned_notice(db, session, notice_id).popup_seen_at = now()
    return {"ok": True}


@router.get("/deliveries")
def list_deliveries(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    items = db.scalars(select(NotificationDelivery).where(NotificationDelivery.account_id == session.account_id)
        .order_by(NotificationDelivery.created_at.desc()).limit(20))
    return {"deliveries": [{"id": item.id, "status": item.status, "attempts": item.attempts,
        "created_at": iso(item.created_at), "finished_at": iso(item.finished_at), "error_code": item.error_code} for item in items]}


class TestEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/test-email")
def test_email(body: TestEmailRequest, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    """Send one fixed, non-sensitive test only to the owner's opted-in mailbox."""
    settings, stamp = NotificationSettings(), now()
    if not email_readiness(settings)["configured"]:
        raise HTTPException(409, "Email delivery is not configured yet.")
    # Serializes simultaneous tests for an account on the shared PostgreSQL DB.
    db.scalar(select(Account).where(Account.id == session.account_id).with_for_update())
    profile = db.get(Profile, session.profile_id)
    pref = preferences_for(db, session.account_id)
    identity = verified_mailbox(db, session.account_id, pref.email_provider)
    if not (pref.email_enabled and profile.notification_frequency != "off" and identity
            and identity["connection_id"] == pref.email_connection_id
            and identity["email"].casefold() == (pref.email_recipient or "").casefold()):
        raise HTTPException(409, "Save your email reminder subscription before sending a test.")
    recent = db.scalar(select(NotificationDelivery.id).where(
        NotificationDelivery.account_id == session.account_id,
        NotificationDelivery.dedup_key.like("test:%"),
        NotificationDelivery.created_at >= stamp - timedelta(minutes=5)).limit(1))
    if recent:
        raise HTTPException(429, "Wait five minutes before requesting another test email.", headers={"Retry-After": "300"})
    slot = int(stamp.replace(tzinfo=timezone.utc).timestamp()) // 300
    delivery = NotificationDelivery(account_id=session.account_id, profile_id=profile.id,
        dedup_key=f"test:{slot}|profile:{profile.version}", recipient=identity["email"], provider=identity["provider"],
        connection_id=identity["connection_id"], subject="Staytus — your email reminders are connected",
        body=("This is the test email you requested in Staytus.\n\n"
              "Your email reminder subscription is enabled. Scheduled digests are sent when there are eligible new reminders; "
              "a quiet day may not produce an email. This test contains no immigration records or mailbox content.\n\n"
              "Open https://mystaytus.vercel.app/ to review or turn off your subscription in Reminder settings.\n"
              "Receiving email reminders does not enable the chat assistant to read your mailbox."),
        status="QUEUED", attempts=0, next_attempt_at=stamp, created_at=stamp)
    db.add(delivery)
    db.flush()
    identity_id = delivery.id
    audit(db, profile.id, "notifications.test_email_requested", {"delivery_id": identity_id})
    db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    deliver_pending(factory, settings=settings, stamp=stamp, account_id=session.account_id, delivery_id=identity_id)
    db.expire_all()
    saved = db.get(NotificationDelivery, identity_id)
    return {"delivery_id": identity_id, "status": saved.status,
        "provider_accepted": saved.status == "SENT", "inbox_delivery_verified": False}


def _insert_notice(db: Session, profile: Profile, key: str, kind: str, title: str, message: str,
        data: dict, stamp: datetime) -> bool:
    existing = db.scalar(select(ReminderNotice).where(ReminderNotice.profile_id == profile.id, ReminderNotice.dedup_key == key))
    if existing:
        if kind == "planning" and existing.superseded_at is not None:
            existing.superseded_at = existing.read_at = existing.popup_seen_at = None
            existing.created_at, existing.title, existing.message, existing.data = stamp, title[:200], message, data
            return True
        return False
    try:
        with db.begin_nested():
            db.add(ReminderNotice(account_id=profile.account_id, profile_id=profile.id, dedup_key=key,
                kind=kind, title=title[:200], message=message, data=data, created_at=stamp))
            db.flush()
        return True
    except IntegrityError:
        return False


def sync_profile_reminders(db: Session, profile: Profile, pref: NotificationPreference, stamp: datetime) -> int:
    if profile.notification_frequency == "off" or not (pref.in_app_enabled or pref.email_enabled):
        return 0
    added = 0
    for event in db.scalars(select(Notification).where(Notification.profile_id == profile.id,
            Notification.created_at >= stamp - timedelta(days=30)).order_by(Notification.created_at.desc()).limit(100)):
        added += _insert_notice(db, profile, "policy:" + event.id, "policy_update", event.title,
            event.message, {**event.data, "legal_deadline_changed": event.data.get("legal_deadline_changed", False)}, event.created_at)
    today = stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(pref.timezone)).date()
    calculated = deadlines(db, profile)
    current_targets = {item["workflow"]: item["date"] for item in calculated}
    for prior in db.scalars(select(ReminderNotice).where(ReminderNotice.profile_id == profile.id,
            ReminderNotice.kind == "planning", ReminderNotice.superseded_at.is_(None))):
        if prior.data.get("target_date") != current_targets.get(prior.data.get("workflow")):
            prior.superseded_at = stamp
    for item in calculated:
        target = date.fromisoformat(item["date"])
        days = (target - today).days
        if not -7 <= days <= pref.lead_days:
            continue
        stage = "upcoming" if days > 0 else "today" if days == 0 else "past_target"
        message = (f"Your Staytus preparation target is {target.isoformat()}. "
            "This is an internal planning reminder, not an official filing deadline or an eligibility decision. "
            "Review your dates and confirm the applicable process with your adviser.")
        added += _insert_notice(db, profile, f"planning:{item['workflow']}:{target.isoformat()}:{stage}",
            "planning", item["title"], message, {"workflow": item["workflow"], "target_date": target.isoformat(),
                "stage": stage, "is_planning_buffer": True, "legal_deadline_changed": False}, stamp)
    return added


def cancel_queued(db: Session, account_id: str, stamp: datetime, reason: str):
    for identity in list(db.scalars(select(NotificationDelivery.id).where(
            NotificationDelivery.account_id == account_id, NotificationDelivery.status == "QUEUED"))):
        changed = db.execute(update(NotificationDelivery).where(NotificationDelivery.id == identity,
            NotificationDelivery.status == "QUEUED").values(status="CANCELLED", error_code=reason, finished_at=stamp))
        if changed.rowcount == 1:
            # No send was claimed; reservation can be reused under fresh settings.
            db.execute(delete(NotificationDeliveryItem).where(NotificationDeliveryItem.delivery_id == identity))


def sync_schedule(db: Session, profile: Profile, pref: NotificationPreference, stamp: datetime):
    if pref.scheduled_frequency != profile.notification_frequency:
        pref.scheduled_frequency = profile.notification_frequency
        pref.next_email_at = next_digest_at(stamp, pref.timezone, pref.digest_hour, pref.digest_weekday,
            profile.notification_frequency, pref.digest_monthday) if pref.email_enabled else None
        cancel_queued(db, profile.account_id, stamp, "frequency_changed")


def queue_digest(db: Session, profile: Profile, pref: NotificationPreference, stamp: datetime) -> bool:
    if not pref.email_enabled or profile.notification_frequency == "off":
        return False
    if pref.next_email_at is None:
        pref.next_email_at = next_digest_at(stamp, pref.timezone, pref.digest_hour, pref.digest_weekday,
            profile.notification_frequency, pref.digest_monthday)
        return False
    if pref.next_email_at > stamp:
        return False
    scheduled = pref.next_email_at
    pref.next_email_at = next_digest_at(stamp, pref.timezone, pref.digest_hour, pref.digest_weekday,
        profile.notification_frequency, pref.digest_monthday)
    identity = verified_mailbox(db, profile.account_id, pref.email_provider)
    if not identity or identity["connection_id"] != pref.email_connection_id or identity["email"].casefold() != (pref.email_recipient or "").casefold():
        pref.email_enabled = False
        pref.next_email_at = None
        return False
    items = list(db.scalars(select(ReminderNotice).where(ReminderNotice.profile_id == profile.id,
        ReminderNotice.account_id == profile.account_id, ReminderNotice.read_at.is_(None), ReminderNotice.superseded_at.is_(None),
        ~exists().where(NotificationDeliveryItem.notice_id == ReminderNotice.id))
        .order_by(ReminderNotice.created_at).limit(20)))
    if not items:
        return False
    body = "Your Staytus reminders\n\n" + "\n\n".join(f"{item.title}\n{item.message[:2000]}" for item in items)
    body += "\n\nOpen https://mystaytus.vercel.app/ to review the sources, dates and next steps. You can turn off digests in Reminder settings."
    try:
        with db.begin_nested():
            delivery = NotificationDelivery(account_id=profile.account_id, profile_id=profile.id,
                dedup_key=f"digest:{scheduled.isoformat()}|profile:{profile.version}", recipient=identity["email"], provider=identity["provider"],
                connection_id=identity["connection_id"], subject="Your Staytus reminders", body=body,
                status="QUEUED", attempts=0, next_attempt_at=stamp, created_at=stamp)
            db.add(delivery)
            db.flush()
            db.add_all([NotificationDeliveryItem(notice_id=item.id, delivery_id=delivery.id) for item in items])
            db.flush()
        return True
    except IntegrityError:
        return False


class DeliveryRejected(Exception):
    def __init__(self, *, retryable: bool):
        self.retryable = retryable


class DeliveryUncertain(Exception):
    pass


def send_smtp(delivery: NotificationDelivery, settings: NotificationSettings):
    """Never log provider errors; a lost DATA response is not safe to retry."""
    smtp = None
    def close():
        if smtp:
            try:
                smtp.close()
            except (OSError, smtplib.SMTPException):
                pass
    try:
        context = ssl.create_default_context()
        if settings.notification_smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(settings.notification_smtp_host, settings.notification_smtp_port, timeout=20, context=context)
        else:
            smtp = smtplib.SMTP(settings.notification_smtp_host, settings.notification_smtp_port, timeout=20)
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(settings.notification_smtp_username, settings.notification_smtp_password)
    except smtplib.SMTPResponseException as error:
        close()
        raise DeliveryRejected(retryable=400 <= error.smtp_code < 500) from None
    except (OSError, smtplib.SMTPException):
        close()
        raise DeliveryRejected(retryable=True) from None
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = formataddr(("Staytus", settings.notification_from_email)), delivery.recipient, delivery.subject
    message["Message-ID"] = f"<staytus-{delivery.id}@{settings.notification_from_email.rsplit('@', 1)[-1]}>"
    message.set_content(delivery.body)
    try:
        refused = smtp.send_message(message, from_addr=settings.notification_from_email, to_addrs=[delivery.recipient])
        if refused:
            codes = [value[0] for value in refused.values()]
            raise DeliveryRejected(retryable=bool(codes) and all(400 <= code < 500 for code in codes))
    except smtplib.SMTPRecipientsRefused as error:
        codes = [value[0] for value in error.recipients.values()]
        raise DeliveryRejected(retryable=bool(codes) and all(400 <= code < 500 for code in codes)) from None
    except smtplib.SMTPResponseException as error:
        raise DeliveryRejected(retryable=400 <= error.smtp_code < 500) from None
    except (OSError, smtplib.SMTPException):
        raise DeliveryUncertain() from None
    finally:
        # A disconnect during QUIT cannot turn an acknowledged DATA send into a retry.
        close()


def send_brevo_api(delivery: NotificationDelivery, settings: NotificationSettings):
    """Use the restricted transactional-email key; never follow redirects or log bodies."""
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False) as client:
            response = client.post("https://api.brevo.com/v3/smtp/email",
                headers={"api-key": settings.notification_brevo_api_key, "accept": "application/json"},
                json={"sender": {"name": "Staytus", "email": settings.notification_from_email},
                    "to": [{"email": delivery.recipient}], "subject": delivery.subject, "textContent": delivery.body,
                    "headers": {"X-Staytus-Delivery-ID": delivery.id}})
    except httpx.HTTPError:
        # The server might have accepted the request before the connection failed.
        raise DeliveryUncertain() from None
    if response.status_code == 201:
        try:
            message_id = response.json()["messageId"]
            if not isinstance(message_id, str) or not message_id or len(message_id) > 500:
                raise ValueError("Invalid receipt")
            return {"transport": "brevo_api", "provider_message_id": message_id}
        except (KeyError, TypeError, ValueError):
            raise DeliveryUncertain() from None
    if response.status_code == 429:
        raise DeliveryRejected(retryable=True)
    if 400 <= response.status_code < 500 and response.status_code != 408:
        raise DeliveryRejected(retryable=False)
    # A timeout, redirect or provider-side failure isn't proof that no mail was accepted.
    raise DeliveryUncertain()


def deliver_pending(factory=SessionLocal, *, settings: NotificationSettings | None = None, sender=None, stamp=None,
                    account_id: str | None = None, delivery_id: str | None = None) -> dict:
    settings, stamp = settings or NotificationSettings(), stamp or now()
    result = {"sent": 0, "retry_queued": 0, "uncertain": 0, "cancelled": 0, "failed": 0}
    if not email_readiness(settings)["configured"]:
        return {**result, "email_configured": False}
    sender = sender or (send_brevo_api if settings.notification_email_transport == "brevo_api" else send_smtp)
    if delivery_id is not None and account_id is None:
        raise ValueError("Targeted delivery requires an account")
    scope = []
    if account_id is not None:
        scope.append(NotificationDelivery.account_id == account_id)
    if delivery_id is not None:
        scope.append(NotificationDelivery.id == delivery_id)
    with factory() as db:
        # A process may have crashed after transmitting DATA. Never resend that claim.
        db.execute(update(NotificationDelivery).where(*scope, NotificationDelivery.status == "SENDING",
            NotificationDelivery.claimed_at < stamp - timedelta(minutes=15)).values(
                status="UNKNOWN", error_code="worker_interrupted_after_claim", finished_at=stamp))
        ids = list(db.scalars(select(NotificationDelivery.id).where(*scope, NotificationDelivery.status == "QUEUED",
            NotificationDelivery.next_attempt_at <= stamp).order_by(NotificationDelivery.created_at).limit(20)))
        db.commit()
    for identity in ids:
        with factory() as db:
            delivery = db.get(NotificationDelivery, identity)
            if delivery is None:
                continue
            pref = db.get(NotificationPreference, delivery.account_id)
            profile = db.get(Profile, delivery.profile_id)
            current = verified_mailbox(db, delivery.account_id, delivery.provider)
            stale_notice = db.scalar(select(NotificationDeliveryItem.notice_id).join(ReminderNotice,
                ReminderNotice.id == NotificationDeliveryItem.notice_id).where(NotificationDeliveryItem.delivery_id == identity,
                    ReminderNotice.superseded_at.is_not(None)).limit(1))
            allowed = bool(pref and pref.email_enabled and profile and profile.notification_frequency != "off"
                and delivery.dedup_key.endswith(f"|profile:{profile.version}")
                and pref.email_connection_id == delivery.connection_id and current
                and current["connection_id"] == delivery.connection_id and current["email"].casefold() == delivery.recipient.casefold()
                and not stale_notice)
            if not allowed:
                changed = db.execute(update(NotificationDelivery).where(NotificationDelivery.id == identity,
                    NotificationDelivery.status == "QUEUED").values(status="CANCELLED", error_code="consent_or_content_changed", finished_at=stamp))
                if changed.rowcount == 1:
                    db.execute(delete(NotificationDeliveryItem).where(NotificationDeliveryItem.delivery_id == identity))
                db.commit()
                result["cancelled"] += bool(changed.rowcount)
                continue
            changed = db.execute(update(NotificationDelivery).where(NotificationDelivery.id == identity,
                NotificationDelivery.status == "QUEUED", NotificationDelivery.attempts < MAX_EMAIL_ATTEMPTS).values(
                    status="SENDING", claimed_at=stamp, attempts=NotificationDelivery.attempts + 1))
            db.commit()
            if changed.rowcount != 1:
                continue
            # Refresh after the durable claim: relink/revocation may have landed
            # between the first read and the claim. The network send below is
            # the in-flight boundary; a transmitted message cannot be recalled.
            db.expire_all()
            db.refresh(delivery)
            pref = db.get(NotificationPreference, delivery.account_id)
            profile = db.get(Profile, delivery.profile_id)
            current = verified_mailbox(db, delivery.account_id, delivery.provider)
            if not (pref and pref.email_enabled and profile and profile.notification_frequency != "off"
                    and delivery.dedup_key.endswith(f"|profile:{profile.version}")
                    and pref.email_connection_id == delivery.connection_id and current
                    and current["connection_id"] == delivery.connection_id
                    and current["email"].casefold() == delivery.recipient.casefold()):
                delivery.status, delivery.finished_at, delivery.error_code = "CANCELLED", stamp, "consent_changed_before_transport"
                db.execute(delete(NotificationDeliveryItem).where(NotificationDeliveryItem.delivery_id == identity))
                db.commit()
                result["cancelled"] += 1
                continue
            # Keep no database read transaction open during an SMTP round trip.
            db.commit()
            try:
                receipt = sender(delivery, settings)
                delivery.status, delivery.finished_at = "SENT", stamp
                if isinstance(receipt, dict) and receipt.get("provider_message_id"):
                    audit(db, profile.id, "notifications.provider_accepted", {"delivery_id": delivery.id, **receipt})
                result["sent"] += 1
            except DeliveryRejected as error:
                if error.retryable and delivery.attempts < MAX_EMAIL_ATTEMPTS:
                    delivery.status = "QUEUED"
                    delivery.next_attempt_at = stamp + timedelta(minutes=5 * 2 ** (delivery.attempts - 1))
                    delivery.error_code = "provider_rejected_retryable"
                    result["retry_queued"] += 1
                else:
                    delivery.status, delivery.finished_at, delivery.error_code = "FAILED", stamp, "provider_rejected"
                    result["failed"] += 1
            except Exception:
                # Includes unknown custom transport errors; no exception contents leave this service.
                delivery.status, delivery.finished_at, delivery.error_code = "UNKNOWN", stamp, "delivery_result_uncertain"
                result["uncertain"] += 1
            db.commit()
    return {**result, "email_configured": True}


def run_notifications_once(factory=SessionLocal, *, settings=None, sender=None, stamp=None) -> dict:
    settings, stamp = settings or NotificationSettings(), stamp or now()
    if not _worker_lock.acquire(blocking=False):
        return {"skipped": "already_running"}
    try:
        result = {"notices_created": 0, "digests_queued": 0}
        with factory() as db:
            for profile in db.scalars(select(Profile).where(Profile.account_id.is_not(None)).limit(1000)):
                pref = preferences_for(db, profile.account_id)
                sync_schedule(db, profile, pref, stamp)
                result["notices_created"] += sync_profile_reminders(db, profile, pref, stamp)
                if email_readiness(settings)["configured"]:
                    result["digests_queued"] += queue_digest(db, profile, pref, stamp)
            db.commit()
        result["email"] = deliver_pending(factory, settings=settings, sender=sender, stamp=stamp)
        return result
    finally:
        _worker_lock.release()


def run_notifications_worker(stop_event: threading.Event, interval_seconds=60):
    while not stop_event.is_set():
        try:
            if NotificationSettings().notification_worker_enabled:
                run_notifications_once()
        except Exception:
            # Do not log database/provider exception text containing recipient data.
            import logging
            logging.getLogger(__name__).warning("Reminder polling batch failed; no uncertain send will be retried")
        stop_event.wait(max(10, interval_seconds))
