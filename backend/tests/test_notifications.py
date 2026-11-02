"""Durable reminders and email outbox checks use only synthetic records/transports."""
from datetime import datetime, timedelta
import smtplib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import notifications as n
from app.auth import digest
from app.db import Base, get_db, make_engine
from app.models import Account, AuthSession, Notification, Profile, now
from app.notification_models import NotificationDelivery, NotificationDeliveryItem, NotificationPreference, ReminderNotice


STAMP = datetime(2026, 11, 1, 12)
Settings = n.NotificationSettings


def settings(enabled=False):
    return Settings(_env_file=None, notification_worker_enabled=True,
        notification_email_enabled=enabled, notification_smtp_host="smtp.example.invalid" if enabled else "",
        notification_smtp_port=465, notification_smtp_security="ssl",
        notification_smtp_username="synthetic-user" if enabled else "",
        notification_smtp_password="synthetic-secret-never-log" if enabled else "",
        notification_from_email="staytus@example.invalid" if enabled else "")


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path}/reminders.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        for name in ("a", "b"):
            db.add(Account(id=name, email=f"unverified-{name}@example.invalid", name=f"Synthetic {name}", password_hash="unusable"))
            db.flush()
            db.add(Profile(id="p-" + name, account_id=name, name=f"Synthetic {name}", school="University of Pennsylvania",
                status_type="F-1", program_start=STAMP.date() - timedelta(days=100), program_end=STAMP.date() + timedelta(days=66),
                travel_date=STAMP.date() + timedelta(days=36), notification_frequency="daily", synthetic=True))
            db.flush()
            db.add(AuthSession(account_id=name, profile_id="p-" + name, token_hash=digest("token-" + name),
                role="student", expires_at=now() + timedelta(days=1)))
        db.commit()
    identities = {name: {"email": f"verified-{name}@example.invalid", "provider": "google", "connection_id": "connection-" + name}
        for name in ("a", "b")}
    monkeypatch.setattr(n, "verified_mailbox", lambda db, account_id, provider=None:
        identities.get(account_id) if provider in (None, "google") else None)
    yield factory, identities
    engine.dispose()


@pytest.fixture
def client(store, monkeypatch):
    factory, _ = store
    config = settings()
    monkeypatch.setattr(n, "NotificationSettings", lambda: config)
    app = FastAPI()
    app.include_router(n.router)
    def db():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
    app.dependency_overrides[get_db] = db
    with TestClient(app) as api:
        yield api


def authorization(who="a"):
    return {"Authorization": "Bearer token-" + who}


def enable_digest(factory):
    with factory() as db:
        pref = n.preferences_for(db, "a")
        pref.email_enabled = True
        pref.scheduled_frequency = "daily"
        pref.email_provider, pref.email_connection_id, pref.email_recipient = "google", "connection-a", "verified-a@example.invalid"
        pref.next_email_at = STAMP - timedelta(seconds=1)
        db.commit()


def test_default_inbox_and_no_outbound_sending_even_when_transport_available(store):
    factory, _ = store
    calls = []
    result = n.run_notifications_once(factory, settings=settings(True), sender=lambda *args: calls.append(args), stamp=STAMP)
    assert result["notices_created"] == 4 and not calls and result["digests_queued"] == 0
    with factory() as db:
        assert all(not p.email_enabled for p in db.scalars(select(NotificationPreference)))
        rows = list(db.scalars(select(ReminderNotice)))
        assert len(rows) == 4 and all(row.data["is_planning_buffer"] for row in rows)
        assert all("not an official filing deadline" in row.message for row in rows)


def test_reminders_deduplicate_across_worker_restarts_and_preserve_pending_policy_status(store):
    factory, _ = store
    with factory() as db:
        db.add(Notification(profile_id="p-a", title="Official source changed — review pending", message="Unreviewed page change.",
            data={"review_status": "detected_pending_review", "legal_deadline_changed": False}, created_at=STAMP))
        db.commit()
    assert n.run_notifications_once(factory, settings=settings(), stamp=STAMP)["notices_created"] == 5
    assert n.run_notifications_once(factory, settings=settings(), stamp=STAMP + timedelta(minutes=1))["notices_created"] == 0
    with factory() as db:
        row = db.scalar(select(ReminderNotice).where(ReminderNotice.kind == "policy_update"))
        assert row.data["review_status"] == "detected_pending_review" and row.data["legal_deadline_changed"] is False


def test_off_pauses_new_reminders_without_deleting_existing_inbox(store):
    factory, _ = store
    n.run_notifications_once(factory, settings=settings(), stamp=STAMP)
    with factory() as db:
        profile = db.get(Profile, "p-a")
        profile.notification_frequency = "off"
        db.add(Notification(profile_id=profile.id, title="New source", message="Pending", created_at=STAMP))
        db.commit()
    assert n.run_notifications_once(factory, settings=settings(), stamp=STAMP)["notices_created"] == 0
    with factory() as db:
        assert len(list(db.scalars(select(ReminderNotice).where(ReminderNotice.account_id == "a")))) == 2


def test_inbox_and_read_popup_acknowledgements_are_owned(client, store):
    factory, _ = store
    n.run_notifications_once(factory, settings=settings(), stamp=STAMP)
    own = client.get("/api/v1/notifications", headers=authorization()).json()
    other = client.get("/api/v1/notifications", headers=authorization("b")).json()
    assert own["unread_count"] == 2 and not ({r["id"] for r in own["notifications"]} & {r["id"] for r in other["notifications"]})
    other_id = other["notifications"][0]["id"]
    for path in ("read", "popup-seen"):
        assert client.post(f"/api/v1/notifications/{other_id}/{path}", headers=authorization()).status_code == 404
    notice_id = own["notifications"][0]["id"]
    assert client.post(f"/api/v1/notifications/{notice_id}/popup-seen", headers=authorization()).status_code == 200
    assert client.post(f"/api/v1/notifications/{notice_id}/read", headers=authorization()).status_code == 200
    updated = client.get("/api/v1/notifications", headers=authorization()).json()
    assert updated["unread_count"] == 1
    assert next(item for item in updated["notifications"] if item["id"] == notice_id)["popup_seen_at"]
    assert client.post("/api/v1/notifications/read-all", headers=authorization()).status_code == 200
    assert client.get("/api/v1/notifications", headers=authorization()).json()["unread_count"] == 0
    assert client.get("/api/v1/notifications", headers=authorization("b")).json()["unread_count"] == 2
    assert client.get("/api/v1/notifications").status_code == 401


def test_preferences_reject_invalid_timezone_arbitrary_recipient_and_unconfigured_email(client):
    response = client.get("/api/v1/notifications/preferences", headers=authorization()).json()
    assert not response["preferences"]["email_enabled"] and not response["email_readiness"]["configured"]
    assert response["channels"]["browser_push"] == "not_configured"
    for body in ({"timezone": "Not/A/Timezone"}, {"email_recipient": "attacker@example.invalid"}, {"digest_hour": 24}, {"popup_enabled": None}):
        assert client.patch("/api/v1/notifications/preferences", headers=authorization(), json=body).status_code == 422
    result = client.patch("/api/v1/notifications/preferences", headers=authorization(), json={"email_enabled": True})
    assert result.status_code == 409 and "SMTP" in result.json()["detail"]
    result = client.patch("/api/v1/notifications/preferences", headers=authorization(), json={"timezone": "America/New_York", "frequency": "weekly", "popup_enabled": False})
    assert result.status_code == 200 and result.json()["preferences"]["timezone"] == "America/New_York"
    assert result.json()["preferences"]["frequency"] == "weekly"


def test_email_opt_in_requires_verified_mailbox_and_binds_exact_connection(client, store, monkeypatch):
    factory, identities = store
    config = settings(True)
    monkeypatch.setattr(n, "NotificationSettings", lambda: config)
    identities.clear()
    assert client.patch("/api/v1/notifications/preferences", headers=authorization(), json={"email_enabled": True}).status_code == 409
    identities["a"] = {"email": "authorized@example.invalid", "provider": "google", "connection_id": "verified-connection"}
    result = client.patch("/api/v1/notifications/preferences", headers=authorization(), json={"email_enabled": True, "email_provider": "google"})
    assert result.status_code == 200 and result.json()["preferences"]["email_recipient"] == "authorized@example.invalid"
    with factory() as db:
        pref = db.get(NotificationPreference, "a")
        assert pref.email_connection_id == "verified-connection" and pref.next_email_at > now()
    identities["a"]["connection_id"] = "relinked"
    result = client.get("/api/v1/notifications/preferences", headers=authorization()).json()
    assert result["preferences"]["email_consent_current"] is False


@pytest.mark.parametrize("stamp,zone,hour,weekday,frequency,expected", [
    (datetime(2026, 11, 1, 13, 30), "America/New_York", 9, 0, "daily", datetime(2026, 11, 1, 14)),
    (datetime(2026, 11, 1, 15), "America/New_York", 9, 6, "weekly", datetime(2026, 11, 8, 14)),
    (datetime(2027, 3, 14, 5), "America/New_York", 2, 0, "daily", datetime(2027, 3, 14, 7)),
    (STAMP, "UTC", 9, 0, "off", None),
])
def test_digest_schedule_handles_timezone_dst_and_off(stamp, zone, hour, weekday, frequency, expected):
    assert n.next_digest_at(stamp, zone, hour, weekday, frequency) == expected


def test_monthly_schedule_preserves_monthday_after_short_month_and_year_rollover():
    assert n.next_digest_at(datetime(2027, 1, 31, 10), "UTC", 9, 0, "monthly", 31) == datetime(2027, 2, 28, 9)
    assert n.next_digest_at(datetime(2027, 2, 28, 10), "UTC", 9, 0, "monthly", 31) == datetime(2027, 3, 31, 9)
    assert n.next_digest_at(datetime(2026, 12, 31, 10), "UTC", 9, 0, "monthly", 31) == datetime(2027, 1, 31, 9)


def test_profile_frequency_change_reschedules_existing_digest_and_releases_unsent_reservation(store):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        assert n.queue_digest(db, profile, pref, STAMP)
        db.commit()
        profile.notification_frequency = "monthly"
        pref.digest_monthday = 1
        n.sync_schedule(db, profile, pref, STAMP)
        db.commit()
        assert pref.next_email_at == datetime(2026, 12, 1, 9)
        assert db.scalar(select(NotificationDelivery)).status == "CANCELLED"
        assert not list(db.scalars(select(NotificationDeliveryItem)))
        # An unread reminder was not permanently consumed by a cancelled send.
        assert n.queue_digest(db, profile, pref, datetime(2026, 12, 1, 9))
        db.commit()
        assert len(list(db.scalars(select(NotificationDeliveryItem)))) == 2


def test_existing_monthly_profile_is_never_treated_as_daily(store):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        profile.notification_frequency = pref.scheduled_frequency = "monthly"
        pref.digest_monthday = 1
        n.sync_profile_reminders(db, profile, pref, STAMP)
        assert n.queue_digest(db, profile, pref, STAMP)
        assert pref.next_email_at == datetime(2026, 12, 1, 9)


def test_date_restored_reactivates_superseded_planning_notice(store):
    factory, _ = store
    with factory() as db:
        profile = db.get(Profile, "p-a")
        pref = n.preferences_for(db, profile.account_id)
        original_end = profile.program_end
        n.sync_profile_reminders(db, profile, pref, STAMP)
        before = db.scalar(select(ReminderNotice).where(ReminderNotice.data["workflow"].as_string() == "program_extension"))
        profile.program_end += timedelta(days=20)
        n.sync_profile_reminders(db, profile, pref, STAMP)
        assert before.superseded_at
        profile.program_end = original_end
        n.sync_profile_reminders(db, profile, pref, STAMP)
        assert before.superseded_at is None


def test_opted_in_digest_has_verified_recipient_and_is_reserved_once(store):
    factory, _ = store
    enable_digest(factory)
    calls = []
    result = n.run_notifications_once(factory, settings=settings(True), sender=lambda delivery, config: calls.append((delivery.recipient, delivery.body)), stamp=STAMP)
    assert result["digests_queued"] == 1 and result["email"]["sent"] == 1
    assert calls[0][0] == "verified-a@example.invalid" and "internal planning reminder" in calls[0][1]
    n.run_notifications_once(factory, settings=settings(True), sender=lambda *args: calls.append(args), stamp=STAMP + timedelta(days=1))
    assert len(calls) == 1
    with factory() as db:
        assert len(list(db.scalars(select(NotificationDelivery)))) == 1
        assert len(list(db.scalars(select(NotificationDeliveryItem)))) == 2


def test_ambiguous_send_is_terminal_even_after_restart(store):
    factory, _ = store
    enable_digest(factory)
    calls = []
    def uncertain(delivery, config):
        calls.append(delivery.id)
        raise n.DeliveryUncertain()
    n.run_notifications_once(factory, settings=settings(True), sender=uncertain, stamp=STAMP)
    n.deliver_pending(factory, settings=settings(True), sender=uncertain, stamp=STAMP + timedelta(hours=1))
    assert len(calls) == 1
    with factory() as db:
        value = db.scalar(select(NotificationDelivery))
        assert value.status == "UNKNOWN" and value.attempts == 1 and value.error_code == "delivery_result_uncertain"


def test_definite_rejection_retries_with_backoff_then_stops(store):
    factory, _ = store
    enable_digest(factory)
    calls = []
    def reject(delivery, config):
        calls.append(delivery.id)
        raise n.DeliveryRejected(retryable=True)
    n.run_notifications_once(factory, settings=settings(True), sender=reject, stamp=STAMP)
    assert n.deliver_pending(factory, settings=settings(True), sender=reject, stamp=STAMP + timedelta(minutes=4))["retry_queued"] == 0
    n.deliver_pending(factory, settings=settings(True), sender=reject, stamp=STAMP + timedelta(minutes=5))
    n.deliver_pending(factory, settings=settings(True), sender=reject, stamp=STAMP + timedelta(minutes=15))
    n.deliver_pending(factory, settings=settings(True), sender=reject, stamp=STAMP + timedelta(days=1))
    assert len(calls) == 3
    with factory() as db:
        value = db.scalar(select(NotificationDelivery))
        assert value.status == "FAILED" and value.attempts == 3


def test_relinked_mailbox_cancels_queued_delivery(store):
    factory, identities = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        assert n.queue_digest(db, profile, pref, STAMP)
        db.commit()
    identities["a"]["connection_id"] = "new-connection"
    calls = []
    result = n.deliver_pending(factory, settings=settings(True), sender=lambda *args: calls.append(args), stamp=STAMP)
    assert result["cancelled"] == 1 and not calls


def test_relink_between_initial_check_and_claim_is_rechecked_before_transport(store, monkeypatch):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        n.queue_digest(db, profile, pref, STAMP)
        db.commit()
    values = iter([
        {"email": "verified-a@example.invalid", "provider": "google", "connection_id": "connection-a"},
        {"email": "verified-a@example.invalid", "provider": "google", "connection_id": "new-connection"},
    ])
    monkeypatch.setattr(n, "verified_mailbox", lambda *args: next(values))
    result = n.deliver_pending(factory, settings=settings(True), sender=lambda *args: pytest.fail("Revoked consent sent"), stamp=STAMP)
    assert result["cancelled"] == 1
    with factory() as db:
        assert db.scalar(select(NotificationDelivery)).error_code == "consent_changed_before_transport"
        assert not list(db.scalars(select(NotificationDeliveryItem)))


def test_changed_profile_supersedes_old_target_and_cancels_old_digest(store):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        n.queue_digest(db, profile, pref, STAMP)
        profile.program_end += timedelta(days=20)
        n.sync_profile_reminders(db, profile, pref, STAMP)
        db.commit()
    result = n.deliver_pending(factory, settings=settings(True), sender=lambda *args: pytest.fail("Stale snapshot sent"), stamp=STAMP)
    assert result["cancelled"] == 1
    with factory() as db:
        assert db.scalar(select(ReminderNotice).where(ReminderNotice.data["workflow"].as_string() == "program_extension")).superseded_at


def test_profile_version_change_cancels_frozen_digest_before_next_notice_sync(store):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        n.queue_digest(db, profile, pref, STAMP)
        db.commit()
        profile.program_end += timedelta(days=20)
        profile.version += 1
        db.commit()
    result = n.deliver_pending(factory, settings=settings(True), sender=lambda *args: pytest.fail("Old profile snapshot sent"), stamp=STAMP)
    assert result["cancelled"] == 1


def test_interrupted_send_claim_never_retries(store):
    factory, _ = store
    enable_digest(factory)
    with factory() as db:
        profile, pref = db.get(Profile, "p-a"), db.get(NotificationPreference, "a")
        n.sync_profile_reminders(db, profile, pref, STAMP)
        n.queue_digest(db, profile, pref, STAMP)
        value = db.scalar(select(NotificationDelivery))
        value.status, value.claimed_at, value.attempts = "SENDING", STAMP - timedelta(minutes=20), 1
        db.commit()
    n.deliver_pending(factory, settings=settings(True), sender=lambda *args: pytest.fail("Interrupted send repeated"), stamp=STAMP)
    with factory() as db:
        assert db.scalar(select(NotificationDelivery)).status == "UNKNOWN"


@pytest.mark.parametrize("stage,expected", [("login", n.DeliveryRejected), ("data", n.DeliveryUncertain)])
def test_smtp_error_classification_never_exposes_response_content(store, monkeypatch, stage, expected):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            assert kwargs["context"].check_hostname
        def login(self, *args):
            if stage == "login":
                raise smtplib.SMTPAuthenticationError(535, b"private-provider-canary")
        def send_message(self, *args, **kwargs):
            raise smtplib.SMTPServerDisconnected("private-provider-canary")
        def close(self):
            pass
    monkeypatch.setattr(n.smtplib, "SMTP_SSL", FakeSMTP)
    delivery = NotificationDelivery(id="synthetic", recipient="verified@example.invalid", subject="Reminder", body="Synthetic")
    with pytest.raises(expected) as error:
        n.send_smtp(delivery, settings(True))
    assert "canary" not in str(error.value)


def test_acknowledged_smtp_send_stays_successful_if_close_disconnects(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def login(self, *args):
            pass
        def send_message(self, message, **kwargs):
            assert kwargs["to_addrs"] == ["verified@example.invalid"]
            return {}
        def close(self):
            raise smtplib.SMTPServerDisconnected("closed after acknowledgement")
    monkeypatch.setattr(n.smtplib, "SMTP_SSL", FakeSMTP)
    delivery = NotificationDelivery(id="synthetic", recipient="verified@example.invalid", subject="Reminder", body="Synthetic")
    n.send_smtp(delivery, settings(True))


def test_explicit_smtp_data_rejection_is_safe_to_retry_without_exposing_body(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def login(self, *args):
            pass
        def send_message(self, *args, **kwargs):
            raise smtplib.SMTPDataError(450, b"private rejection canary")
        def close(self):
            pass
    monkeypatch.setattr(n.smtplib, "SMTP_SSL", FakeSMTP)
    delivery = NotificationDelivery(id="synthetic", recipient="verified@example.invalid", subject="Reminder", body="Synthetic")
    with pytest.raises(n.DeliveryRejected) as error:
        n.send_smtp(delivery, settings(True))
    assert error.value.retryable and "canary" not in str(error.value)
