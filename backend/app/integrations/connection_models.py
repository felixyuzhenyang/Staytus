"""Server-only OAuth state and encrypted provider tokens."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import uid, now


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    session_id: Mapped[str] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String)
    verifier: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (UniqueConstraint("account_id", "provider"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    provider: Mapped[str] = mapped_column(String)
    encrypted_tokens: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MailAgentPermission(Base):
    """OAuth access alone is not consent to share or analyze mailbox content."""
    __tablename__ = "mail_agent_permissions"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    content_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    content_analysis_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
