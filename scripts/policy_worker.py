"""Polling service: uv run python ../scripts/policy_worker.py [--once].

Run this alongside the API, or enable its lifespan worker. Notification delivery is
in-app only; email/calendar connectors are separate explicitly authorized integrations.
"""
import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import Base, engine
from app.policy_pipeline import run_worker, run_worker_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    if args.once:
        print(json.dumps(run_worker_once(), indent=2))
        return
    stop = threading.Event()
    try:
        run_worker(stop, args.interval_seconds)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
