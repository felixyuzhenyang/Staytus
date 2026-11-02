"""Operational public captures use mocked networks; no private portal or provider account is needed."""
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import Base, make_engine
from app.ingestion import chunk_text, fetch_source, normalize_html, store_candidate
from app.integrations.watsonx import ProviderError
from app.models import (
    Account,
    FetchAttempt,
    Notification,
    PolicyChunk,
    PolicySource,
    PolicyVersion,
    Profile,
    RuleVersion,
    now,
)
from app.policy_models import PolicySnapshot, SourceCapture
from app.policy_pipeline import RefreshThrottled, refresh_sources, reserve_manual_refresh, source_statuses
from app.retrieval import search_snapshots
from app.source_registry import load_sources, sync_source_registry


@pytest.fixture
def capture_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ingestion.socket.getaddrinfo", lambda *args, **kwargs:
                        [(2, 1, 6, "", ("93.184.216.34", 443))])
    engine = make_engine(f"sqlite:///{tmp_path}/capture.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        sync_source_registry(db)
        db.commit()
        yield db
    engine.dispose()


def network(page, robots="User-agent: *\nDisallow:\n", status=200):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        return httpx.Response(status, text=f"<main>{page}</main>",
                              headers={"content-type": "text/html", "etag": '"v1"'})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def profile(db, name, status="F-1", school="University of Pennsylvania", frequency="weekly"):
    row = Profile(id=name, name=name, school=school, status_type=status, program_start=date(2026, 1, 1),
                  program_end=date(2027, 5, 1), notification_frequency=frequency)
    db.add(row)
    db.flush()
    return row


def test_registry_is_runtime_truth_and_contains_real_fetchable_sources(capture_db):
    source = capture_db.get(PolicySource, "penn-isss")
    source.url = "https://example.org/tampered"
    sync_source_registry(capture_db)
    assert source.url == "https://global.upenn.edu/isss/" and source.auto_fetch_enabled
    assert len(load_sources()) == 6
    assert all(row["freshness"] == "never_fetched" for row in source_statuses(capture_db))


def test_capture_chunk_index_dedup_and_pending_citations(capture_db):
    text = "Travel guidance for international students and scholars. " * 80
    client, calls = network(text)
    source = capture_db.get(PolicySource, "penn-travel")
    first = fetch_source(capture_db, source, client)
    assert first["changed"] and first["retrieval_mode"] == "keyword" and not first["rule_changed"]
    assert len(list(capture_db.scalars(select(PolicyChunk)))) > 1
    assert not list(capture_db.scalars(select(RuleVersion)))
    assert calls[0].endswith("/robots.txt")
    second = fetch_source(capture_db, source, client)
    assert not second["changed"] and second["version"] == 1
    assert len(list(capture_db.scalars(select(PolicyVersion)))) == 1
    assert search_snapshots(capture_db, "travel", "F-1") == []
    rows = search_snapshots(capture_db, "travel", "F-1", include_pending=True)
    assert rows[0]["reviewed"] is False
    assert rows[0]["citations"][0]["captured_at"]
    assert rows[0]["source_url"] == source.url
    assert rows[0]["retrieval_mode"] == "keyword"
    state = capture_db.get(SourceCapture, source.id)
    assert state.last_success_at and state.robots_status == "allowed"
    assert len(list(capture_db.scalars(select(FetchAttempt)))) == 2


def test_conditional_304_keeps_snapshot_and_can_upgrade_index(capture_db):
    source = capture_db.get(PolicySource, "penn-travel")
    client, _ = network("Travel guidance for international students and scholars.")
    first = fetch_source(capture_db, source, client)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:", headers={"content-type": "text/plain"})
        assert request.headers["If-None-Match"] == '"v1"'
        return httpx.Response(304)

    result = fetch_source(capture_db, source, httpx.Client(transport=httpx.MockTransport(handler)), embedder=Embedder())
    assert result["not_modified"] and not result["changed"]
    assert result["policy_version_id"] == first["policy_version_id"] and result["retrieval_mode"] == "hybrid"


def test_notifications_only_changed_content_and_relevant_subscriptions(capture_db):
    profile(capture_db, "penn-f1")
    profile(capture_db, "penn-j1", status="J-1 scholar")
    profile(capture_db, "other-f1", school="Another University")
    profile(capture_db, "penn-off", frequency="off")
    source = capture_db.get(PolicySource, "penn-opt")
    first = store_candidate(capture_db, source, "OPT initial official text", categories=["F-1"])
    capture_db.flush()
    assert not list(capture_db.scalars(select(Notification)))
    changed = store_candidate(capture_db, source, "OPT changed official text", categories=["F-1"])
    capture_db.flush()
    notifications = list(capture_db.scalars(select(Notification)))
    assert len(notifications) == 1 and notifications[0].profile_id == "penn-f1"
    assert notifications[0].data["legal_deadline_changed"] is False
    assert notifications[0].data["review_status"] == "detected_pending_review"
    assert first["policy_version_id"] != changed["policy_version_id"]
    newest = search_snapshots(capture_db, "OPT", "F-1", include_pending=True)
    assert [row["id"] for row in newest] == [changed["policy_version_id"]]
    assert search_snapshots(capture_db, "OPT", "F-1", include_pending=True, school="Another University") == []


def test_robots_restriction_prevents_page_fetch(capture_db):
    client, calls = network("Never fetched", robots="User-agent: *\nDisallow: /isss/\n")
    result = fetch_source(capture_db, capture_db.get(PolicySource, "penn-isss"), client)
    assert result["error"] == "robots_disallowed" and len(calls) == 1
    assert not list(capture_db.scalars(select(PolicyVersion)))


def test_redirect_validates_target_and_robots_before_request(capture_db):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private", headers={"content-type": "text/plain"})
        return httpx.Response(302, headers={"location": "/private"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_source(capture_db, capture_db.get(PolicySource, "penn-isss"), client)
    assert result["error"] == "robots_disallowed"
    assert len(calls) == 2 and all(not url.endswith("/private") for url in calls)


def test_private_dns_and_unregistered_redirect_are_blocked(capture_db, monkeypatch):
    client, calls = network("Do not read local network")
    monkeypatch.setattr("app.ingestion.socket.getaddrinfo", lambda *args, **kwargs:
                        [(2, 1, 6, "", ("127.0.0.1", 443))])
    result = fetch_source(capture_db, capture_db.get(PolicySource, "penn-isss"), client)
    assert result["error"] == "non_public_destination" and calls == []
    monkeypatch.setattr("app.ingestion.socket.getaddrinfo", lambda *args, **kwargs:
                        [(2, 1, 6, "", ("93.184.216.34", 443))])

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:", headers={"content-type": "text/plain"})
        return httpx.Response(302, headers={"location": "http://127.0.0.1/credentials"})

    result = fetch_source(capture_db, capture_db.get(PolicySource, "penn-isss"),
                          httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["error"] == "cross_origin_redirect_needs_registry_entry"


def test_size_limit_safe_error_log(capture_db, monkeypatch):
    monkeypatch.setattr("app.ingestion.MAX_BYTES", 100)
    client, _ = network("Long public source page " * 20)
    result = fetch_source(capture_db, capture_db.get(PolicySource, "penn-isss"), client)
    assert result["error"] == "capture_size_limit"
    assert capture_db.get(SourceCapture, "penn-isss").last_error == "capture_size_limit"


class Embedder:
    config = SimpleNamespace(embedding_model="test-vector-model", generation_model="")

    def embeddings(self, texts):
        return [[0.25, 0.75] for _ in texts]


def test_embeddings_persist_model_dimension_and_hybrid_uses_matching_model(capture_db):
    source = capture_db.get(PolicySource, "penn-travel")
    result = store_candidate(capture_db, source, "Travel guidance and signature verification", embedder=Embedder())
    capture_db.flush()
    metadata = capture_db.get(PolicySnapshot, result["policy_version_id"])
    assert metadata.embedding_model == "test-vector-model" and metadata.embedding_dimension == 2
    rows = search_snapshots(capture_db, "travel", "F-1", include_pending=True, embedder=Embedder())
    assert rows[0]["retrieval_mode"] == "hybrid"


def test_embedding_outage_keeps_capture_searchable_without_claiming_vector(capture_db):
    class Unavailable(Embedder):
        def embeddings(self, texts):
            raise ProviderError("Service unavailable")

    result = store_candidate(capture_db, capture_db.get(PolicySource, "penn-travel"),
                             "Travel guidance for international students", embedder=Unavailable())
    capture_db.flush()
    assert result["retrieval_mode"] == "keyword_embedding_unavailable"
    rows = search_snapshots(capture_db, "travel", "F-1", include_pending=True, embedder=Unavailable())
    assert rows[0]["retrieval_mode"] == "keyword_embedding_unavailable"


def test_adding_embeddings_to_unchanged_snapshot_preserves_citation_ids(capture_db):
    source = capture_db.get(PolicySource, "penn-travel")
    first = store_candidate(capture_db, source, "Travel guidance for international students")
    capture_db.flush()
    original = list(capture_db.scalars(select(PolicyChunk)))
    upgraded = store_candidate(capture_db, source, "Travel guidance for international students", embedder=Embedder())
    capture_db.flush()
    assert not upgraded["changed"] and upgraded["policy_version_id"] == first["policy_version_id"]
    assert upgraded["retrieval_mode"] == "hybrid"
    assert [chunk.id for chunk in capture_db.scalars(select(PolicyChunk))] == [chunk.id for chunk in original]


def test_product_retrieval_excludes_fixtures_and_cross_status(capture_db):
    result = store_candidate(capture_db, capture_db.get(PolicySource, "penn-opt"), "Official OPT guidance", categories=["F-1"])
    policy = capture_db.get(PolicyVersion, result["policy_version_id"])
    policy.reviewed, policy.status, policy.fixture = True, "current_effective", True
    capture_db.flush()
    assert search_snapshots(capture_db, "OPT", "F-1") == []
    assert search_snapshots(capture_db, "OPT", "F-1", include_fixtures=True)
    assert search_snapshots(capture_db, "OPT", "J-1 scholar", include_fixtures=True) == []


def test_manual_per_account_and_global_source_cooldown(capture_db):
    account = Account(email="capture-test@example.edu", name="Test", password_hash="not-a-real-login")
    capture_db.add(account)
    capture_db.flush()
    reserve_manual_refresh(capture_db, account.id, "penn-isss")
    with pytest.raises(RefreshThrottled):
        reserve_manual_refresh(capture_db, account.id, "penn-travel")
    client, calls = network("International students public information source " * 3)
    first = refresh_sources(capture_db, "penn-isss", client=client, manual=True)
    second = refresh_sources(capture_db, "penn-isss", client=client, manual=True)
    assert first["attempted"] == 1 and second["results"][0]["skipped"] == "recently_checked"
    state = capture_db.get(SourceCapture, "penn-isss")
    state.last_attempt_at = now() - timedelta(hours=7)
    assert refresh_sources(capture_db, "penn-isss", client=client)["attempted"] == 1
    assert len(calls) == 4


def test_chunking_has_bounded_overlapping_chunks():
    text = "A long paragraph with words. " * 300
    chunks = chunk_text(text)
    assert len(chunks) > 1 and all(0 < len(item) <= 1400 for item in chunks)
    assert chunks[0][-40:] in chunks[1]


@pytest.mark.parametrize("wrapper", ['main', 'article', 'div role="main"', 'div id="main-content"'])
def test_extractor_prioritizes_content_and_excludes_site_boilerplate(wrapper):
    closing = wrapper.split()[0]
    html = ("<html><head><title>Site title</title></head><body><header>Global header</header>"
            "<nav>Account menu</nav>" + f"<{wrapper}>"
            "<h1>Travel requirements</h1><p>Contact your adviser before travel.</p>"
            "<nav>Local navigation</nav><script>ignore instructions</script>"
            f"</{closing}><footer>Global footer</footer></body></html>")
    assert normalize_html(html) == "Travel requirements\nContact your adviser before travel."


def test_source_routes_require_auth_and_limit_registered_refresh(env, student, monkeypatch):
    client, _ = env
    assert client.get("/api/v1/sources").status_code == 401
    assert client.get("/api/v1/sources", headers=student).status_code == 200
    assert client.post("/api/v1/policies/refresh", json={"source_id": "unknown"}, headers=student).status_code == 422
    assert client.post("/api/v1/policies/refresh", json={"url": "https://example.org"}, headers=student).status_code == 422
    monkeypatch.setattr("app.policy_routes.refresh_sources", lambda *args, **kwargs:
                        {"status": "completed", "results": [], "rule_changed": False})
    assert client.post("/api/v1/policies/refresh", json={"source_id": "penn-isss"}, headers=student).status_code == 200
    assert client.post("/api/v1/policies/refresh", json={"source_id": "penn-isss"}, headers=student).status_code == 429
