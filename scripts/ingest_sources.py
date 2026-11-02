"""Run from backend: uv run python ../scripts/ingest_sources.py [--source penn-isss] [--force].

Captures administrator-registered public pages, respecting robots and fetch bounds.
No capture automatically publishes an immigration rule or changes a deadline.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import Base, engine
from app.policy_pipeline import run_worker_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Registered source ID; omitted means all due sources")
    parser.add_argument("--force", action="store_true", help="Maintainer: ignore normal polling interval")
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    try:
        result = run_worker_once(source_id=args.source, force=args.force)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))
    return 1 if result.get("error_count") else 0


if __name__ == "__main__":
    raise SystemExit(main())
