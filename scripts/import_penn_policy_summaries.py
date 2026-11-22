"""Validate or import an operator-prepared batch of public Penn ISSS summaries.

From backend: uv run python ../scripts/import_penn_policy_summaries.py BATCH [--apply]
Without --apply this checks the file and source registry without contacting services.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import chunk_text, store_candidate
from app.models import PolicySource
from app.policy_models import SourceCapture
from app.policy_pipeline import optional_embedder
from app.scheduled_jobs import job_lock_key
from app.source_registry import source_entry


def load_batch(path):
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    checked_on = date.fromisoformat(document["checked_on"])
    sources = document["sources"]
    if not sources or checked_on > date.today():
        raise ValueError("The batch must contain summaries checked on or before today")
    batch = []
    for source_id, note in sorted(sources.items()):
        entry = source_entry(source_id)
        if entry.get("school_id") != "penn" or note["url"] != entry["url"]:
            raise ValueError(f"Expected the registered Penn URL for {source_id}")
        if entry.get("terms_review") != "public_read_only_robots_required":
            raise ValueError(f"Source is not in the public registry: {source_id}")
        supporting_urls = note.get("supporting_urls", [])
        for url in supporting_urls:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.netloc != "global.upenn.edu" or not parsed.path.startswith("/isss/"):
                raise ValueError(f"Expected a public Penn ISSS supporting URL for {source_id}")
        summary = note["summary"].strip()
        if not summary:
            raise ValueError(f"Empty summary for {source_id}")
        content = f"Staytus summary of public Penn ISSS guidance. Manually checked {checked_on}; pending review.\n\n{summary}"
        if supporting_urls:
            content += "\n\nSupporting Penn ISSS pages:\n" + "\n".join(supporting_urls)
        if len(chunk_text(content)) != 1:
            raise ValueError(f"Keep the summary and its provenance together in one chunk: {source_id}")
        provenance = {"capture_method": "manual_public_source_summary", "source_checked_on": str(checked_on),
            "supporting_urls": supporting_urls, "review_required": True}
        batch.append((entry, content, provenance))
    return batch


def import_batch(db, batch, embedder=None):
    results = []
    for entry, content, provenance in batch:
        source_id = entry["id"]
        if db.get_bind().dialect.name == "postgresql" and not db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": job_lock_key("policy:" + source_id)}):
            raise ValueError(f"Scheduled capture is running for {source_id}; retry the batch")
        source = db.get(PolicySource, source_id)
        if source is None or source.url != entry["url"]:
            raise ValueError(f"Registered source URL mismatch in database: {source_id}")
        state = db.get(SourceCapture, source_id, with_for_update=True)
        if state is None:
            state = SourceCapture(source_id=source_id)
            db.add(state)
        result = store_candidate(db, source, content, categories=entry["categories"],
            embedder=embedder, manual_capture=provenance)
        state.latest_version_id = result["policy_version_id"]
        state.chunk_count = result["chunk_count"]
        state.retrieval_mode = result["retrieval_mode"]
        if result["changed"]:
            # These validators describe the old automatic response, not this summary.
            state.etag = state.last_modified = None
        results.append({"source_id": source_id, **result})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write the checked batch to configured Supabase")
    args = parser.parse_args()
    try:
        batch = load_batch(args.batch)
        if not args.apply:
            print(json.dumps({"mode": "validate", "source_ids": [entry["id"] for entry, _, _ in batch]}))
            return
        url = make_url(get_settings().database_url)
        if (url.get_backend_name() != "postgresql" or not (url.host or "").endswith(".supabase.com")
                or url.query.get("sslmode") != "verify-full"):
            raise ValueError("Apply requires the configured Supabase PostgreSQL connection with verified TLS")
        with optional_embedder() as embedder, SessionLocal.begin() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            results = import_batch(db, batch, embedder)
        print(json.dumps({"mode": "apply", "results": results}, indent=2))
    except SQLAlchemyError as error:
        provider_error = getattr(error, "orig", None)
        raise SystemExit(f"Batch rolled back: {type(error).__name__} ({getattr(provider_error, 'sqlstate', None)})") from None
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
