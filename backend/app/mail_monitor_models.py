"""Separate opt-in to background mailbox reads, without storing message bodies."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now, uid


class MailMonitorPreference(Base):
    __tablename__ = "mail_monitor_preferences"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    check_hour: Mapped[int] = mapped_column(Integer, default=9)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MailMonitorSeen(Base):
    __tablename__ = "mail_monitor_seen"
    __table_args__ = (UniqueConstraint("account_id", "provider", "connection_id", "message_hash"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    connection_id: Mapped[str] = mapped_column(String(64))
    message_hash: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now)
