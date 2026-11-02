"""Operational metadata, kept separate from student identity models."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now


class SourceCapture(Base):
    __tablename__ = "source_capture_state"
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    robots_status: Mapped[str] = mapped_column(String(64), default="not_checked")
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_mode: Mapped[str] = mapped_column(String(64), default="not_indexed")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)


class PolicySnapshot(Base):
    __tablename__ = "policy_snapshot_metadata"
    policy_version_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"), primary_key=True)
    requested_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    http_status: Mapped[int] = mapped_column(Integer, default=200)
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_status: Mapped[str] = mapped_column(String(64), default="keyword")
    classification: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceRefreshRequest(Base):
    """Persist account cooldown across sessions and API process restarts."""
    __tablename__ = "source_refresh_requests"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    source_scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=now)
