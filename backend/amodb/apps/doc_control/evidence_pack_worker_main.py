"""Dedicated Document Control evidence-pack worker.

This process intentionally owns a small database pool that is separate from the
HTTP API. Run more worker processes only when evidence-pack throughput needs it;
user-facing API connections must remain reserved for interactive work.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from pathlib import Path


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    from dotenv import load_dotenv

    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    load_dotenv(path, override=False)


def _configure_worker_pool() -> None:
    """Give this background process a bounded pool independent of the API."""

    if (os.getenv("DB_EXTERNAL_POOLER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    os.environ["DB_POOL_SIZE"] = os.getenv("DOCUMENT_EVIDENCE_PACK_DB_POOL_SIZE", "1")
    os.environ["DB_MAX_OVERFLOW"] = os.getenv("DOCUMENT_EVIDENCE_PACK_DB_MAX_OVERFLOW", "1")
    os.environ["DB_POOL_TIMEOUT"] = os.getenv("DOCUMENT_EVIDENCE_PACK_DB_POOL_TIMEOUT", "3")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Document Control evidence-pack worker")
    parser.add_argument(
        "--env-file",
        default=os.getenv("PORTAL_ENV_FILE"),
        help="Optional dotenv file loaded before database modules are imported",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Seconds to wait when the queue is empty",
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)
    _configure_worker_pool()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    # Storage validation is intentionally before queue consumption. Horizontal
    # production must never complete a job to container-local disk that an API
    # replica cannot retrieve.
    from amodb import storage

    storage.validate_storage_configuration()

    # Import only after the worker-specific DB pool has been applied. database.py
    # creates SQLAlchemy engines at import time.
    from amodb.apps.doc_control.evidence_pack_job_service import process_one_pending_job
    from amodb.database import dispose_engines

    poll_seconds = args.poll_seconds
    if poll_seconds is None:
        poll_seconds = float(os.getenv("DOCUMENT_EVIDENCE_PACK_WORKER_POLL_SECONDS", "2") or "2")
    poll_seconds = max(0.25, min(poll_seconds, 60.0))

    stopping = False

    def stop(_signum=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        while not stopping:
            try:
                processed = process_one_pending_job()
            except Exception:
                logging.exception("Document Control evidence-pack worker cycle failed")
                processed = False
            if not processed:
                time.sleep(poll_seconds)
    finally:
        dispose_engines()


if __name__ == "__main__":
    main()
