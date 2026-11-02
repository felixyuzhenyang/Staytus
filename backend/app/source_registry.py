"""Administrator-owned YAML is the runtime source and school registry."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolicySource

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
SUPPORTED_CATEGORIES = {"F-1", "J-1 student", "J-1 scholar"}


def load_sources(path: Path | None = None) -> list[dict]:
    data = yaml.safe_load((path or CONFIG_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    entries = data.get("sources", []) if isinstance(data, dict) else []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in seen:
            raise ValueError("Source registry IDs must be unique strings")
        parsed = urlsplit(entry.get("url", ""))
        hosts = entry.get("allowed_hosts", [])
        if (parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in hosts
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError("Registered source must use its explicit allowed HTTPS hostname")
        if not set(entry.get("categories", [])).issubset(SUPPORTED_CATEGORIES):
            raise ValueError("Unknown source audience category")
        if not isinstance(entry.get("title"), str) or not entry["title"].strip():
            raise ValueError("Source registry title is required")
        seen.add(entry["id"])
    return entries


def source_entry(source_id: str) -> dict:
    for entry in load_sources():
        if entry["id"] == source_id:
            return entry
    raise ValueError("Unknown registered source")


def load_school(school_id: str = "penn") -> dict:
    # No caller-supplied path, and no school identifier is interpreted as a filename.
    if school_id != "penn":
        raise ValueError("This institution does not yet have a supported school adapter")
    data = yaml.safe_load((CONFIG_ROOT / "schools" / "penn.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("id") != school_id:
        raise ValueError("Invalid school configuration")
    defaults = data.get("planning_defaults", {})
    if any(not isinstance(value, int) or not 0 <= value <= 365 for value in defaults.values()):
        raise ValueError("Planning buffers must be integers between zero and 365 days")
    return data


def sync_source_registry(db: Session) -> list[PolicySource]:
    """Upsert configuration, not sample policy content or sample students."""
    entries = load_sources()
    configured = {entry["id"] for entry in entries}
    for source in db.scalars(select(PolicySource)):
        if source.id not in configured:
            source.auto_fetch_enabled = False
    rows = []
    for entry in entries:
        row = db.get(PolicySource, entry["id"])
        if row is None:
            row = PolicySource(id=entry["id"])
            db.add(row)
        row.title = entry["title"]
        row.url = entry["url"]
        row.allowed_host = urlsplit(entry["url"]).hostname
        row.freshness_days = int(entry.get("staleness_days", 7))
        row.auto_fetch_enabled = bool(entry.get("fetch_enabled", False))
        rows.append(row)
    db.flush()
    return rows
