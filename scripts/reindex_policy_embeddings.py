"""Reindex saved official captures after selecting a watsonx.ai embedding model.

Run from backend. Default is offline status only; --run explicitly calls the
selected model on already-saved public text. No website recrawl or personal data.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import SessionLocal
from app.policy_pipeline import optional_embedder, reindex_current_captures, source_statuses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Registered source ID; omitted means all current captures")
    parser.add_argument("--run", action="store_true", help="Generate real embeddings and update saved indexes; uses provider quota")
    args = parser.parse_args()
    with SessionLocal() as db:
        if not args.run:
            rows = source_statuses(db)
            print(json.dumps({"network_called": False, "sources": [{key: row[key] for key in (
                "id", "version", "chunk_count", "retrieval_mode", "embedding_model", "embedding_dimension")}
                for row in rows if not args.source or row["id"] == args.source]}, indent=2))
            return 0
        with optional_embedder() as embedder:
            if embedder is None:
                print(json.dumps({"network_called": False, "error": "Configure the watsonx.ai embedding service/model first"}))
                return 2
            result = reindex_current_captures(db, embedder, source_id=args.source)
            db.commit()
            print(json.dumps({"network_called": True, **result}, indent=2))
            return 1 if result["embedding_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
