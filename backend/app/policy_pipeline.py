"""Source freshness, capture scheduling and optional IBM embedding configuration."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import _index_chunks, fetch_source
from app.integrations.watsonx import ProviderError, WatsonxClient, WatsonxConfig
from app.models import FetchAttempt, PolicySource, PolicyVersion, now
from app.policy_models import PolicySnapshot, SourceCapture, SourceRefreshRequest
from app.source_registry import load_sources, source_entry, sync_source_registry

_refresh_lock = threading.Lock()
MANUAL_COOLDOWN_SECONDS = 300


def iso(value):
    return value.isoformat() + "Z" if value else None


@contextmanager
def optional_policy_models(*, for_retrieval=False):
    """Policy generation and embeddings are independent optional capabilities.

    Capture may use either model. Retrieval creates a client only with an
    embedding model, so generation-only credentials never imply vector search.
    No network request is made merely by constructing this client.
    """
    settings = get_settings()
    provider = None
    values = (settings.watsonx_url, settings.watsonx_api_key, settings.watsonx_project_id)
    embedding_model = settings.watsonx_embedding_model
    generation_model = settings.watsonx_generation_model
    capability = embedding_model if for_retrieval else (embedding_model or generation_model)
    if all(values) and capability:
        try:
            provider = WatsonxClient(WatsonxConfig(*values, embedding_model=embedding_model,
                generation_model=generation_model, version=settings.watsonx_api_version))
        except ProviderError:
            # An invalid or unavailable provider must not prevent public-source capture.
            provider = None
    try:
        yield provider
    finally:
        if provider is not None:
            provider.close()


@contextmanager
def optional_embedder():
    """Compatibility entry point for all user-facing policy retrieval."""
    with optional_policy_models(for_retrieval=True) as provider:
        yield provider


def source_statuses(db: Session) -> list[dict]:
    registry = {entry["id"]: entry for entry in load_sources()}
    output = []
    for source in db.scalars(select(PolicySource).where(PolicySource.id.in_(registry)).order_by(PolicySource.id)):
        entry = registry[source.id]
        state = db.get(SourceCapture, source.id)
        version = db.get(PolicyVersion, state.latest_version_id) if state and state.latest_version_id else None
        metadata = db.get(PolicySnapshot, version.id) if version else None
        last_attempt = db.scalar(select(FetchAttempt).where(FetchAttempt.source_id == source.id)
            .order_by(FetchAttempt.created_at.desc()).limit(1))
        age = (now() - state.last_success_at).total_seconds() if state and state.last_success_at else None
        freshness = "never_fetched" if age is None else ("stale" if age > source.freshness_days * 86400 else "fresh_capture")
        output.append({"id": source.id, "title": source.title, "source_url": source.url,
            "final_url": state.final_url if state else None, "authority": entry.get("authority"),
            "school_id": entry.get("school_id"), "categories": entry["categories"],
            "fetch_enabled": source.auto_fetch_enabled, "terms_state": entry.get("terms_review", "unreviewed"),
            "robots_state": state.robots_status if state else "not_checked", "freshness": freshness,
            "freshness_days": source.freshness_days, "poll_interval_minutes": entry.get("poll_interval_minutes", 360),
            "last_attempt_at": iso(state.last_attempt_at) if state else None,
            "last_success_at": iso(state.last_success_at) if state else None,
            "last_error": state.last_error if state else None, "http_status": state.http_status if state else None,
            "last_fetch_detail": last_attempt.detail if last_attempt else None,
            "policy_version_id": version.id if version else None, "version": version.version if version else None,
            "review_status": version.status if version else "not_captured", "reviewed": version.reviewed if version else False,
            "captured_at": iso(metadata.captured_at) if metadata else None,
            "chunk_count": state.chunk_count if state else 0,
            "retrieval_mode": state.retrieval_mode if state else "not_indexed",
            "embedding_model": metadata.embedding_model if metadata else None,
            "embedding_dimension": metadata.embedding_dimension if metadata else None,
            "notice": "Fresh capture describes retrieval time, not verification of current law. Changes await review."})
    return output


class RefreshThrottled(ValueError):
    def __init__(self, seconds):
        self.seconds = max(1, int(seconds))
        super().__init__("Source refresh cooldown")


def reserve_manual_refresh(db: Session, account_id: str, source_id: str | None):
    if source_id:
        source_entry(source_id)  # No URLs or arbitrary hosts are accepted from the client.
    scope = source_id or "all"
    row = db.get(SourceRefreshRequest, (account_id, scope))
    latest = db.scalar(select(SourceRefreshRequest).where(SourceRefreshRequest.account_id == account_id)
        .order_by(SourceRefreshRequest.requested_at.desc()).limit(1))
    if latest and (now() - latest.requested_at).total_seconds() < 60:
        raise RefreshThrottled(60 - (now() - latest.requested_at).total_seconds())
    if row and (now() - row.requested_at).total_seconds() < MANUAL_COOLDOWN_SECONDS:
        raise RefreshThrottled(MANUAL_COOLDOWN_SECONDS - (now() - row.requested_at).total_seconds())
    if row is None:
        row = SourceRefreshRequest(account_id=account_id, source_scope=scope)
        db.add(row)
    row.requested_at = now()
    db.flush()


def refresh_sources(db: Session, source_id=None, *, force=False, embedder=None, client=None,
                    max_sources=6, manual=False) -> dict:
    """Poll registered pages only. The worker and CLI share exactly the API capture path."""
    entries = load_sources()
    if source_id:
        entries = [source_entry(source_id)]
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "busy", "results": [], "notice": "Another source refresh is running."}
    try:
        sync_source_registry(db)
        results, attempted = [], 0
        for entry in entries:
            source = db.get(PolicySource, entry["id"])
            state = db.get(SourceCapture, source.id)
            cooldown = MANUAL_COOLDOWN_SECONDS if manual else int(entry.get("poll_interval_minutes", 360)) * 60
            due = not state or not state.last_attempt_at or now() - state.last_attempt_at >= timedelta(seconds=cooldown)
            if not source.auto_fetch_enabled:
                results.append({"source_id": source.id, "skipped": "disabled"})
            elif (not due and (manual or not force)):
                results.append({"source_id": source.id, "skipped": "recently_checked",
                    "next_check_at": iso(state.last_attempt_at + timedelta(seconds=cooldown))})
            elif attempted >= max_sources:
                results.append({"source_id": source.id, "skipped": "batch_limit_deferred"})
            else:
                results.append(fetch_source(db, source, client=client, embedder=embedder, conditional=not force))
                attempted += 1
        db.flush()
        return {"status": "completed", "results": results, "attempted": attempted,
            "changed_count": sum(bool(row.get("changed")) for row in results),
            "error_count": sum(bool(row.get("error")) for row in results),
            "rule_changed": False,
            "notice": "Captured changes are unreviewed source snapshots. No legal rules or deadlines were activated."}
    finally:
        _refresh_lock.release()


def run_worker_once(*, source_id=None, force=False) -> dict:
    with SessionLocal() as db, optional_policy_models() as embedder:
        result = refresh_sources(db, source_id, force=force, embedder=embedder)
        db.commit()
        return result


def reindex_current_captures(db: Session, embedder, *, source_id=None):
    """Explicit operator action: embed saved public captures without recrawling.

    Corpus/model changes can be validated even if an official site currently
    rejects automated recapture. No capture/review/legal-effective date changes.
    """
    if source_id:
        source_entry(source_id)
    if embedder is None or not getattr(embedder.config, "embedding_model", ""):
        raise ValueError("Configure an embedding model before reindexing")
    states = list(db.scalars(select(SourceCapture).where(SourceCapture.source_id == source_id))) if source_id else list(db.scalars(select(SourceCapture)))
    results = []
    for state in states:
        version = db.get(PolicyVersion, state.latest_version_id) if state.latest_version_id else None
        metadata = db.get(PolicySnapshot, version.id) if version else None
        if version is None or version.fixture or metadata is None:
            continue
        count, mode, model, dimension = _index_chunks(db, version, embedder)
        state.chunk_count, state.retrieval_mode = count, mode
        metadata.index_status, metadata.embedding_model, metadata.embedding_dimension = mode, model, dimension
        results.append({"source_id": state.source_id, "policy_version_id": version.id,
            "chunk_count": count, "retrieval_mode": mode, "embedding_model": model, "embedding_dimension": dimension})
    db.flush()
    return {"results": results, "indexed_sources": len(results),
        "embedding_failures": sum(row["retrieval_mode"] != "hybrid" for row in results),
        "recrawled": False, "rule_changed": False}


def run_worker(stop_event: threading.Event, interval_seconds=60):
    """Explicitly started by application lifespan or the CLI; never starts on module import."""
    while not stop_event.is_set():
        try:
            run_worker_once()
        except Exception:
            # Capture attempts normally retain safe source-level errors. A transient DB failure
            # must not silently kill the scheduling thread; the next poll retries due sources.
            import logging
            logging.getLogger(__name__).exception("Policy polling batch failed")
        stop_event.wait(max(10, interval_seconds))
