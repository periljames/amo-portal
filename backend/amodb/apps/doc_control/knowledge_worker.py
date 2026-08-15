"""Durable recovery worker for queued Documentation reference indexing."""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from amodb.database import WriteSessionLocal, close_session_safely

from . import knowledge_models as km
from .knowledge_indexer import index_revision_background


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stale_seconds() -> int:
    return max(120, min(int(os.getenv("DOCUMENT_INDEX_STALE_SECONDS", "900")), 86_400))


def run_once(*, limit: int = 2) -> dict[str, int]:
    limit = max(1, min(int(limit), 20))
    db = WriteSessionLocal()
    recovered = 0
    try:
        cutoff = _utcnow() - timedelta(seconds=_stale_seconds())
        stale_query = (
            db.query(km.DocumentationIndexJob)
            .filter(
                km.DocumentationIndexJob.status == "RUNNING",
                km.DocumentationIndexJob.updated_at < cutoff,
            )
            .order_by(km.DocumentationIndexJob.updated_at.asc())
            .limit(limit)
        )
        if db.get_bind().dialect.name == "postgresql":
            stale_query = stale_query.with_for_update(skip_locked=True)
        else:
            stale_query = stale_query.with_for_update()
        for job in stale_query.all():
            job.status = "PENDING"
            job.started_at = None
            job.completed_at = None
            job.error_summary = "Automatically recovered after an interrupted indexing worker"
            db.add(job)
            recovered += 1
        if recovered:
            db.commit()

        revision_ids = [
            str(revision_id)
            for (revision_id,) in (
                db.query(km.DocumentationIndexJob.revision_id)
                .filter(km.DocumentationIndexJob.status == "PENDING")
                .order_by(km.DocumentationIndexJob.created_at.asc())
                .limit(limit)
                .all()
            )
        ]
    finally:
        close_session_safely(db)

    for revision_id in revision_ids:
        index_revision_background(revision_id)
    return {"recovered": recovered, "indexed": len(revision_ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Documentation indexing worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=int(os.getenv("DOCUMENT_INDEX_WORKER_LIMIT", "2")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("DOCUMENT_INDEX_WORKER_POLL_SECONDS", "2")))
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    while True:
        result = run_once(limit=args.limit)
        if args.once:
            return
        if not any(result.values()):
            time.sleep(max(0.5, min(args.poll_seconds, 30.0)))


if __name__ == "__main__":
    main()
