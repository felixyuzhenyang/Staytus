"""Bounded public-source capture. Capturing text never activates immigration rules."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.watsonx import ProviderError
from app.models import FetchAttempt, Notification, PolicyChunk, PolicySource, PolicyVersion, Profile, now
from app.policy_models import PolicySnapshot, SourceCapture
from app.source_registry import source_entry

MAX_BYTES = 2_000_000
MAX_ROBOTS_BYTES = 128_000
MAX_REDIRECTS = 4
MAX_CAPTURE_SECONDS = 30
USER_AGENT = "Staytus/0.2"


class SourceFetchError(ValueError):
    """A non-sensitive machine-readable reason for a failed public capture."""


class TextExtractor(HTMLParser):
    void_tags = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})

    def __init__(self):
        super().__init__()
        self.parts, self.main_parts, self.article_parts, self.stack = [], [], [], []
        self.hidden, self.main_depth, self.article_depth = 0, 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        main = tag == "main" or attrs.get("role") == "main" or (attrs.get("id") or "").casefold() in {
            "main", "main-content", "main_content", "maincontent", "content", "primary"}
        article = tag == "article"
        hidden = tag in {"script", "style", "noscript", "svg", "nav", "footer"} or (
            tag == "header" and not self.main_depth and not self.article_depth)
        if tag not in self.void_tags:
            self.stack.append((tag, main, article, hidden))
            self.main_depth += int(main)
            self.article_depth += int(article)
            self.hidden += int(hidden)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void_tags:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _, main, article, hidden in self.stack[index:]:
                    self.main_depth -= int(main)
                    self.article_depth -= int(article)
                    self.hidden -= int(hidden)
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.hidden and data.strip():
            text = re.sub(r"\s+", " ", data).strip()
            self.parts.append(text)
            if self.main_depth:
                self.main_parts.append(text)
            if self.article_depth:
                self.article_parts.append(text)


def normalize_html(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return "\n".join(parser.main_parts or parser.article_parts or parser.parts)


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 160) -> list[str]:
    """Paragraph-aware overlapping chunks; no student or mailbox content enters this index."""
    if max_chars < 100 or not 0 <= overlap < max_chars:
        raise ValueError("Invalid chunk sizes")
    chunks, start = [], 0
    text = text.strip()
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary < 0:
                boundary = text.rfind(" ", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def validate_public_source(source: PolicySource, url: str | None = None, allowed_hosts=None):
    """Validate every redirect and all resolved addresses, using only the admin-owned registry."""
    parsed = urlsplit(url or source.url)
    if (parsed.scheme != "https" or parsed.hostname not in (allowed_hosts or [source.allowed_host])
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise SourceFetchError("unregistered_https_destination")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise SourceFetchError("non_public_destination")


def _read(client, source, url, hosts, limit, headers=None, robots=None, deadline=None):
    deadline = deadline or time.monotonic() + MAX_CAPTURE_SECONDS
    for hop in range(MAX_REDIRECTS + 1):
        if time.monotonic() >= deadline:
            raise SourceFetchError("capture_time_limit")
        validate_public_source(source, url, hosts)
        if robots is not None and not robots.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        with client.stream("GET", url, headers={"User-Agent": USER_AGENT,
                "Accept": "text/html,text/plain", **(headers or {})}, follow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location or hop == MAX_REDIRECTS:
                    raise SourceFetchError("redirect_limit_or_missing_location")
                target = urljoin(url, location)
                # One robots policy cannot authorize a different origin. Register it separately.
                if robots is not None and urlsplit(target).netloc != urlsplit(url).netloc:
                    raise SourceFetchError("cross_origin_redirect_needs_registry_entry")
                url = target
                continue
            raw = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() >= deadline:
                    raise SourceFetchError("capture_time_limit")
                raw.extend(chunk)
                if len(raw) > limit:
                    raise SourceFetchError("capture_size_limit")
            return response.status_code, dict(response.headers), bytes(raw), str(response.url)
    raise SourceFetchError("redirect_limit")


def _robots(client, source, hosts, deadline=None):
    origin = urlsplit(source.url)
    url = f"{origin.scheme}://{origin.netloc}/robots.txt"
    status, headers, raw, final_url = _read(client, source, url, hosts, MAX_ROBOTS_BYTES, deadline=deadline)
    parser = RobotFileParser(url)
    if status in (404, 410):
        parser.parse(["User-agent: *", "Disallow:"])
        return parser, "not_published"
    if status in (401, 403):
        raise SourceFetchError("robots_disallowed")
    if status != 200 or "text/html" in headers.get("content-type", ""):
        raise SourceFetchError("robots_temporarily_unavailable")
    if urlsplit(final_url).netloc != origin.netloc:
        raise SourceFetchError("cross_origin_robots_redirect")
    parser.parse(raw.decode("utf-8", errors="replace").splitlines())
    if not parser.can_fetch(USER_AGENT, source.url):
        raise SourceFetchError("robots_disallowed")
    return parser, "allowed"


def _index_chunks(db: Session, version: PolicyVersion, embedder=None) -> tuple[int, str, str | None, int | None]:
    texts = chunk_text(version.text)
    if len(texts) > 4096:
        raise SourceFetchError("chunk_count_limit")
    vectors, model, dimension, mode = None, None, None, "keyword"
    if embedder is not None and getattr(embedder.config, "embedding_model", ""):
        try:
            vectors = []
            for start in range(0, len(texts), 16):
                vectors.extend(embedder.embeddings(texts[start:start + 16]))
            if len(vectors) != len(texts) or not vectors or not vectors[0]:
                raise ProviderError("Invalid embedding count")
            model, dimension = embedder.config.embedding_model, len(vectors[0])
            mode = "hybrid"
        except (ProviderError, httpx.HTTPError, ValueError, TypeError):
            vectors, model, dimension, mode = None, None, None, "keyword_embedding_unavailable"
    existing = {}
    for chunk in db.scalars(select(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)):
        existing.setdefault(chunk.text, []).append(chunk)
    for index, text in enumerate(texts):
        matches = existing.get(text, [])
        chunk = matches.pop() if matches else PolicyChunk(policy_version_id=version.id, text=text, superseded=False)
        chunk.embedding = vectors[index] if vectors else []
        chunk.vector = vectors[index] if vectors else None
        chunk.embedding_model = model
        db.add(chunk)
    db.flush()
    return len(texts), mode, model, dimension


def store_candidate(db: Session, source: PolicySource, content: str, *, categories=None,
                    final_url=None, embedder=None, http_status=200, manual_capture=None) -> dict:
    """Index public evidence. A manual summary has provenance but no HTTP result or change alert."""
    if manual_capture is not None:
        http_status = 0  # The import did not issue an HTTP request.
    digest = hashlib.sha256(content.encode()).hexdigest()
    latest = db.scalar(select(PolicyVersion).where(PolicyVersion.source_id == source.id,
        PolicyVersion.fixture.is_(False)).order_by(PolicyVersion.version.desc(), PolicyVersion.created_at.desc()).limit(1))
    if latest and latest.content_hash == digest:
        metadata = db.get(PolicySnapshot, latest.id)
        count = db.query(PolicyChunk).filter_by(policy_version_id=latest.id).count()
        target_model = embedder.config.embedding_model if embedder is not None else None
        if not count or (target_model and (metadata is None or metadata.embedding_model != target_model)):
            count, mode, model, dimension = _index_chunks(db, latest, embedder)
            if metadata is None:
                metadata = PolicySnapshot(policy_version_id=latest.id, requested_url=source.url,
                    final_url=final_url or source.url, captured_at=latest.created_at, http_status=http_status,
                    classification=manual_capture or {})
                db.add(metadata)
            metadata.index_status, metadata.embedding_model, metadata.embedding_dimension = mode, model, dimension
        return {"changed": False, "policy_version_id": latest.id, "version": latest.version,
            "status": latest.status, "retrieval_mode": metadata.index_status if metadata else "not_indexed",
            "chunk_count": count, "embedding_dimension": metadata.embedding_dimension if metadata else None,
            "rule_changed": False, "review_required": not latest.reviewed}
    version = PolicyVersion(source_id=source.id, title=source.title, text=content, content_hash=digest,
        status="detected_pending_review", reviewed=False, fixture=False,
        version=(latest.version + 1 if latest else 1),
        visa_types=categories or ["F-1", "J-1 student", "J-1 scholar"])
    db.add(version)
    db.flush()
    # Retain reviewed evidence and all historical content; supersede only earlier raw candidates in retrieval.
    for chunk, previous in db.execute(select(PolicyChunk, PolicyVersion).join(PolicyVersion)
            .where(PolicyVersion.source_id == source.id, PolicyVersion.reviewed.is_(False))):
        if previous.id != version.id:
            chunk.superseded = True
    count, mode, model, dimension = _index_chunks(db, version, embedder)
    classification = manual_capture or {}
    if manual_capture is None and latest and embedder is not None and getattr(embedder.config, "generation_model", ""):
        try:
            classification = embedder.classify_candidate(latest.text, content)
        except (ProviderError, ValueError, httpx.HTTPError):
            classification = {"review_required": True, "classification_status": "unavailable"}
    db.add(PolicySnapshot(policy_version_id=version.id, requested_url=source.url, final_url=final_url or source.url,
        captured_at=now(), http_status=http_status, embedding_model=model, embedding_dimension=dimension,
        index_status=mode, classification=classification))
    if latest and manual_capture is None:
        try:
            school = source_entry(source.id).get("school_id")
        except ValueError:
            school = None
        for profile in db.scalars(select(Profile).where(Profile.notification_frequency != "off")):
            is_penn = profile.school.strip().lower() in {"penn", "upenn", "university of pennsylvania"}
            if profile.status_type not in version.visa_types or (school == "penn" and not is_penn):
                continue
            db.add(Notification(profile_id=profile.id, title="Official source changed — review pending",
                message=f"{source.title} changed since the previous capture. The change awaits review; "
                        "this is not a verified change to your legal requirements or deadlines.",
                data={"event": "detected_source_change", "source_id": source.id, "source_url": final_url or source.url,
                      "policy_version_id": version.id, "previous_version_id": latest.id,
                      "review_status": "detected_pending_review", "legal_deadline_changed": False,
                      "channel": "in_app", "delivery_preference": profile.notification_frequency}))
    return {"changed": True, "policy_version_id": version.id, "version": version.version, "status": version.status,
        "chunk_count": count, "retrieval_mode": mode, "embedding_dimension": dimension,
        "rule_changed": False, "review_required": True}


def fetch_source(db: Session, source: PolicySource, client: httpx.Client | None = None, *, embedder=None,
                 conditional=True) -> dict:
    """Capture one registered source. Failures are persisted as safe operational status, not hidden."""
    entry = source_entry(source.id)
    if source.url != entry["url"] or not source.auto_fetch_enabled or not entry.get("fetch_enabled"):
        raise ValueError("Registered public-source capture is disabled")
    state = db.get(SourceCapture, source.id)
    if state is None:
        state = SourceCapture(source_id=source.id)
        db.add(state)
    state.last_attempt_at, state.last_error = now(), None
    own_client = client is None
    transport = client or httpx.Client(timeout=httpx.Timeout(12, connect=8), follow_redirects=False)
    deadline = time.monotonic() + MAX_CAPTURE_SECONDS
    try:
        if entry.get("terms_review") in {"restricted", "prohibited", "manual_only"}:
            raise SourceFetchError("explicit_source_restriction")
        robots, state.robots_status = _robots(transport, source, entry["allowed_hosts"], deadline)
        headers = {}
        if conditional and state.etag:
            headers["If-None-Match"] = state.etag
        if conditional and state.last_modified:
            headers["If-Modified-Since"] = state.last_modified
        status, response_headers, raw, final_url = _read(transport, source, source.url,
            entry["allowed_hosts"], MAX_BYTES, headers, robots, deadline)
        state.http_status, state.final_url = status, final_url
        if status == 304 and state.latest_version_id:
            latest = db.get(PolicyVersion, state.latest_version_id)
            if latest is None:
                raise SourceFetchError("conditional_response_without_snapshot")
            result = store_candidate(db, source, latest.text, categories=entry["categories"],
                final_url=final_url, embedder=embedder, http_status=status)
            result["not_modified"] = True
        else:
            if status != 200:
                raise SourceFetchError(f"source_http_{status}")
            content_type = response_headers.get("content-type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/plain")):
                raise SourceFetchError("unsupported_content_type")
            decoded = raw.decode("utf-8", errors="replace")
            text = normalize_html(decoded) if "html" in content_type else decoded.strip()
            if len(text) < 40:
                raise SourceFetchError("source_text_empty_or_too_short")
            result = store_candidate(db, source, text, categories=entry["categories"],
                final_url=final_url, embedder=embedder, http_status=status)
            state.etag, state.last_modified = response_headers.get("etag"), response_headers.get("last-modified")
        state.latest_version_id = result["policy_version_id"]
        state.retrieval_mode = result.get("retrieval_mode", "keyword")
        state.chunk_count = db.query(PolicyChunk).filter_by(policy_version_id=state.latest_version_id).count()
        state.last_success_at = now()
        db.add(FetchAttempt(source_id=source.id, success=True,
            detail=f"{'Changed snapshot' if result['changed'] else 'Unchanged snapshot'}; "
                   f"HTTP {status}; robots {state.robots_status}; {state.retrieval_mode}; no rule activation"))
        return {"source_id": source.id, "source_url": final_url,
            "fetched_at": state.last_success_at.isoformat() + "Z", **result}
    except (httpx.HTTPError, ValueError, OSError) as error:
        code = str(error) if isinstance(error, SourceFetchError) else type(error).__name__
        state.last_error = code
        if code.startswith("robots_"):
            state.robots_status = code
        db.add(FetchAttempt(source_id=source.id, success=False, detail=code))
        return {"source_id": source.id, "source_url": source.url, "changed": False, "error": code,
            "fetched_at": None, "rule_changed": False, "review_required": True}
    finally:
        if own_client:
            transport.close()
