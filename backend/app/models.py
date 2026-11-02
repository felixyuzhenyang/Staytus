from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Profile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    school: Mapped[str] = mapped_column(String(100), default="University of Pennsylvania")
    status_type: Mapped[str] = mapped_column(String(32))
    program_start: Mapped[datetime] = mapped_column(Date)
    program_end: Mapped[datetime] = mapped_column(Date)
    graduation_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    travel_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    travel_signature_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    notification_frequency: Mapped[str] = mapped_column(String(16), default="weekly")
    nationality: Mapped[str] = mapped_column(String(64), default="Not supplied")
    version: Mapped[int] = mapped_column(Integer, default=1)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="student")
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class PolicySource(Base):
    __tablename__ = "policy_sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    allowed_host: Mapped[str] = mapped_column(String(100))
    freshness_days: Mapped[int] = mapped_column(Integer, default=7)
    auto_fetch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    visa_types: Mapped[list] = mapped_column(JSON, default=list)


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    version: Mapped[int] = mapped_column(Integer)
    school: Mapped[str] = mapped_column(String(32), default="penn")
    preparation_days: Mapped[int] = mapped_column(Integer, default=60)
    policy_version_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reviewed_by: Mapped[str] = mapped_column(String(64))
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=now)


class DeadlineResult(Base):
    __tablename__ = "deadline_results"
    __table_args__ = (UniqueConstraint("profile_id", "workflow", "profile_version", "rule_version_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    workflow: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[int] = mapped_column(Integer)
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("rule_versions.id"))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Approval(Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    kind: Mapped[str] = mapped_column(String(32))
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Notification(Base):
    __tablename__ = "notification_queue"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FetchAttempt(Base):
    __tablename__ = "fetch_attempt_log"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"))
    success: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    policy_version_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vector: Mapped[list | None] = mapped_column(Vector().with_variant(JSON, "sqlite"), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
