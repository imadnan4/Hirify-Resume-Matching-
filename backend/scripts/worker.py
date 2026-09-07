"""Queue worker: polls Postgres for queued/crashed runs and drains them.

Run on the worker dyno/process: `python backend/scripts/worker.py`.
Tune with SCREEN_CONCURRENCY (parallel LLM calls) and WORKER_POLL_SEC.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import init_db
from app.services.runner import drain_runs


def main() -> None:
    init_db()
    poll = int(os.getenv("WORKER_POLL_SEC", "5"))
    print(f"worker up (concurrency={os.getenv('SCREEN_CONCURRENCY', '4')}, poll={poll}s)", flush=True)
    while True:
        try:
            handled = drain_runs()
            if handled:
                print(f"drained {handled} run(s)", flush=True)
        except Exception as e:  # noqa: BLE001 — worker must never exit on a bad run
            print(f"worker error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    main()
