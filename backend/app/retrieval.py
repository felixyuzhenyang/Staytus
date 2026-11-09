"""One retrieval path for captured official pages, with optional matching-model vectors."""
from __future__ import annotations

import math
import re
from collections import defaultdict

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.watsonx import ProviderError
from app.models import PolicyChunk, PolicySource, PolicyVersion
from app.policy_models import PolicySnapshot
from app.source_registry import load_sources


def cosine(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def _iso(value):
    return value.isoformat() + "Z" if value is not None else None


def search_snapshots(db: Session, query: str, status_type: str, *, include_pending=False, limit=10,
                     include_fixtures=False, embedder=None, school=None, policy_version_id=None) -> list[dict]:
    """Pending text is informational evidence, never implicitly current or reviewed law.

    Retrieval operates on actual chunks and groups their best excerpts under the cited
    source version. In-process cosine works for this small corpus on SQLite or PostgreSQL;
    persisted vectors can later support a database-native index without a second search API.
    """
    statement = select(PolicyChunk, PolicyVersion, PolicySource).join(
        PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.id).join(
        PolicySource, PolicyVersion.source_id == PolicySource.id)
    if policy_version_id:
        statement = statement.where(PolicyVersion.id == policy_version_id)
    else:
        statement = statement.where(PolicyChunk.superseded.is_(False))
    if not include_fixtures:
        statement = statement.where(PolicyVersion.fixture.is_(False))
    if not include_pending:
        statement = statement.where(PolicyVersion.reviewed.is_(True), PolicyVersion.status == "current_effective")
    registry = {entry["id"]: entry for entry in load_sources()}
    is_penn = school is None or school.strip().casefold() in {"penn", "upenn", "university of pennsylvania"}
    rows = [(chunk, policy, source) for chunk, policy, source in db.execute(statement)
            if status_type in policy.visa_types
            and (is_penn or registry.get(source.id, {}).get("school_id") != "penn")]
    words = set(re.findall(r"[a-z0-9]{2,}", query.casefold()))
    for phrase in re.findall(r"[\u3400-\u9fff]+", query):
        words.update(phrase[index:index + 2] for index in range(max(1, len(phrase) - 1)))
    query_vector, model, embedding_failed = None, None, False
    if embedder is not None and query.strip() and rows:
        try:
            query_vector = embedder.embeddings([query])[0]
            model = embedder.config.embedding_model
        except (ProviderError, httpx.HTTPError, ValueError, TypeError, IndexError):
            embedding_failed = True
    if query.strip() and not words and query_vector is None:
        # A question with no usable lexical features must not return the whole
        # corpus as if it were semantically relevant.
        return []
    grouped = defaultdict(list)
    for chunk, policy, source in rows:
        # A page title matches every chunk equally; body matches must rank ahead of
        # navigation/footer chunks that happen to share the source title.
        keyword = (sum(word in chunk.text.casefold() for word in words)
                   + 0.15 * sum(word in policy.title.casefold() for word in words)) / max(1, len(words))
        can_vector = bool(query_vector and chunk.embedding and chunk.embedding_model == model
                          and len(query_vector) == len(chunk.embedding))
        semantic = max(0.0, cosine(query_vector, chunk.embedding)) if can_vector else 0.0
        if words and keyword == 0 and semantic <= 0:
            continue
        mode = "hybrid" if can_vector else ("keyword_embedding_unavailable" if embedding_failed else "keyword")
        grouped[policy.id].append((keyword + semantic, chunk, policy, source, mode))
    results = []
    for candidates in grouped.values():
        candidates.sort(key=lambda row: row[0], reverse=True)
        score, _, policy, source, mode = candidates[0]
        metadata = db.get(PolicySnapshot, policy.id)
        excerpt_rows = candidates[:3]
        url = metadata.final_url if metadata else source.url
        captures = _iso(metadata.captured_at if metadata else policy.created_at)
        citations = [{"source_id": source.id, "policy_version_id": policy.id, "version": policy.version,
            "chunk_id": chunk.id, "source_url": url, "captured_at": captures, "review_status": policy.status,
            "reviewed": policy.reviewed} for _, chunk, _, _, _ in excerpt_rows]
        results.append({"id": policy.id, "policy_version_id": policy.id, "title": policy.title,
            "text": "\n\n".join(chunk.text for _, chunk, _, _, _ in excerpt_rows),
            "status": policy.status, "reviewed": policy.reviewed, "review_required": not policy.reviewed, "source_id": source.id,
            "source_url": url, "source_title": source.title,
            "source_authority": registry.get(source.id, {}).get("authority", "other"), "version": policy.version,
            "created_at": _iso(policy.created_at), "captured_at": captures, "verified_at": _iso(policy.verified_at),
            "fixture": policy.fixture, "fictional": policy.fixture, "visa_types": policy.visa_types,
            "freshness": "source_snapshot_awaiting_review" if not policy.reviewed else "reviewed_snapshot",
            "authority": "fixture" if policy.fixture else "official source snapshot",
            "notice": "Source capture is not verification of current law. Pending changes require review.",
            "retrieval_mode": mode, "index_mode": metadata.index_status if metadata else "legacy",
            "score": round(score, 4), "citations": citations,
            "chunks": [{"id": chunk.id, "text": chunk.text, "score": round(value, 4)}
                       for value, chunk, _, _, _ in excerpt_rows]})
    return sorted(results, key=lambda row: (row["score"], row["created_at"]), reverse=True)[:max(1, min(limit, 30))]


def hybrid_search(db: Session, query: str, status_type: str, embedder=None, limit=5, **kwargs):
    """Compatibility name; all policy searches use the same implementation."""
    return search_snapshots(db, query, status_type, embedder=embedder, limit=limit, **kwargs)


def retrieve_for_profile(db: Session, profile, query: str = "", *, include_pending=False, limit=10):
    """Shared retrieval service for chat grounding, policy UI and Agent tools.

    Only server-owned profile fields determine school/category scope. Embeddings
    are optional; returned items always identify the retrieval mode actually used.
    """
    from app.policy_pipeline import optional_embedder

    with optional_embedder() as embedder:
        return search_snapshots(db, query, profile.status_type, include_pending=include_pending,
            include_fixtures=False, embedder=embedder, school=profile.school, limit=limit)
