"""Durable account-owned notification preferences, inbox and delivery outbox."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now, uid


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    popup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    digest_hour: Mapped[int] = mapped_column(Integer, default=9)
    digest_weekday: Mapped[int] = mapped_column(Integer, default=0)
    digest_monthday: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_frequency: Mapped[str] = mapped_column(String(16), default="")
    lead_days: Mapped[int] = mapped_column(Integer, default=7)
    email_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_connection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)
    next_email_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReminderNotice(Base):
    __tablename__ = "reminder_inbox"
    __table_args__ = (UniqueConstraint("profile_id", "dedup_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    dedup_key: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    popup_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("account_id", "dedup_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"))
    dedup_key: Mapped[str] = mapped_column(String(180))
    recipient: Mapped[str] = mapped_column(String(320))
    provider: Mapped[str] = mapped_column(String(20))
    connection_id: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class NotificationDeliveryItem(Base):
    """An inbox item is reserved by at most one digest, including uncertain sends."""
    __tablename__ = "notification_delivery_items"
    notice_id: Mapped[str] = mapped_column(ForeignKey("reminder_inbox.id", ondelete="CASCADE"), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(ForeignKey("notification_deliveries.id", ondelete="CASCADE"), index=True)
