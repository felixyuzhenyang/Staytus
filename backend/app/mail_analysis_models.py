"""Encrypted, expiring summaries of explicitly authorized matching email content."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now, uid


class MailMessageAnalysis(Base):
    __tablename__ = "mail_message_analyses"
    __table_args__ = (UniqueConstraint("account_id", "provider", "connection_id", "message_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    profile_version: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    connection_id: Mapped[str] = mapped_column(ForeignKey("provider_connections.id", ondelete="CASCADE"))
    message_hash: Mapped[str] = mapped_column(String(64))
    encrypted_result: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
