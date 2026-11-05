"""Durable model-generation outbox, independent of active chat sessions."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now, uid


class AssistantUpdate(Base):
    __tablename__ = "assistant_updates"
    __table_args__ = (UniqueConstraint("account_id", "batch_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    profile_version: Mapped[int] = mapped_column(Integer)
    batch_key: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssistantUpdateEvent(Base):
    __tablename__ = "assistant_update_events"
    notice_id: Mapped[str] = mapped_column(ForeignKey("reminder_inbox.id", ondelete="CASCADE"), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    update_id: Mapped[str] = mapped_column(ForeignKey("assistant_updates.id", ondelete="CASCADE"), index=True)
