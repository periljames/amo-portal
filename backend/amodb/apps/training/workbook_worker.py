"""Durable worker for Training workbook preview and commit jobs.

The HTTP upload route still schedules an eager background task for low latency,
but this worker is the durable recovery path.  Both entry points use atomic
status transitions, so multiple API replicas or a dedicated worker cannot
process the same workbook concurrently.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from amodb.database import WriteSessionLocal, close_session_safely

from .workbook_import import commit_workbook_import, new_commit_attempt_token, process_workbook_preview
from .workbook_models import TrainingWorkbookImportJob


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stale_seconds() -> int:
    return max(60, min(int(os.getenv("TRAINING_WORKBOOK_STALE_JOB_SECONDS", "600")), 86_400))


def _max_recoveries() -> int:
    return max(1, min(int(os.getenv("TRAINING_WORKBOOK_MAX_AUTO_RECOVERIES", "3")), 10))


def _recover_stale_jobs(db) -> int:
    cutoff = _utcnow() - timedelta(seconds=_stale_seconds())
    query = (
        db.query(TrainingWorkbookImportJob)
        .filter(
            TrainingWorkbookImportJob.status.in_(("PARSING", "COMMITTING")),
            TrainingWorkbookImportJob.updated_at < cutoff,
        )
        .order_by(TrainingWorkbookImportJob.updated_at.asc())
        .limit(20)
    )
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    else:
        query = query.with_for_update()

    recovered = 0
    for job in query.all():
        summary: dict[str, Any] = dict(job.summary_json or {})
        attempts = int(summary.get("automatic_recovery_attempts") or 0)
        if job.cancel_requested:
            job.status = "CANCELLED"
            job.stage = "CANCELLED"
            job.completed_at = _utcnow()
            summary["active_commit_token"] = None
        elif attempts >= _max_recoveries():
            job.status = "FAILED"
            job.stage = "FAILED"
            job.completed_at = _utcnow()
            job.error_message = (
                "Processing was interrupted repeatedly. The worker stopped safely; "
                "review the retained job before retrying."
            )
            summary["active_commit_token"] = None
        elif job.status == "PARSING":
            job.status = "QUEUED"
            job.stage = "RECOVERING_PREVIEW"
            job.processed_rows = 0
            job.current_sheet = None
            job.current_record_label = None
            job.error_message = None
            job.completed_at = None
            summary["automatic_recovery_attempts"] = attempts + 1
            summary["last_recovery_at"] = _utcnow().isoformat()
            summary["last_recovery_reason"] = "Preview worker heartbeat expired"
            recovered += 1
        else:
            token = new_commit_attempt_token()
            job.status = "QUEUED_COMMIT"
            job.stage = "RECOVERING_COMMIT"
            job.processed_rows = 0
            job.current_sheet = None
            job.current_record_label = None
            job.error_message = None
            job.completed_at = None
            summary["active_commit_token"] = token
            summary["automatic_recovery_attempts"] = attempts + 1
            summary["last_recovery_at"] = _utcnow().isoformat()
            summary["last_recovery_reason"] = "Commit worker heartbeat expired"
            recovered += 1
        job.summary_json = summary
        job.updated_at = _utcnow()
        db.add(job)
    if recovered or db.dirty:
        db.commit()
    return recovered


def run_once(*, limit: int = 2) -> dict[str, int]:
    limit = max(1, min(int(limit), 20))
    db = WriteSessionLocal()
    try:
        recovered = _recover_stale_jobs(db)
        preview_ids = [
            str(job_id)
            for (job_id,) in (
                db.query(TrainingWorkbookImportJob.id)
                .filter(TrainingWorkbookImportJob.status == "QUEUED")
                .order_by(TrainingWorkbookImportJob.created_at.asc())
                .limit(limit)
                .all()
            )
        ]
        commit_rows = (
            db.query(TrainingWorkbookImportJob.id, TrainingWorkbookImportJob.summary_json)
            .filter(TrainingWorkbookImportJob.status == "QUEUED_COMMIT")
            .order_by(TrainingWorkbookImportJob.updated_at.asc())
            .limit(limit)
            .all()
        )
    finally:
        close_session_safely(db)

    for job_id in preview_ids:
        process_workbook_preview(job_id)

    commits = 0
    for job_id, raw_summary in commit_rows:
        summary = dict(raw_summary or {})
        token = str(summary.get("active_commit_token") or "").strip()
        request = summary.get("commit_request")
        force_reimport = bool(request.get("force_reimport")) if isinstance(request, dict) else False
        if not token:
            logger.error("Training workbook commit job %s has no active commit token", job_id)
            continue
        commit_workbook_import(str(job_id), force_reimport=force_reimport, attempt_token=token)
        commits += 1

    return {
        "recovered": recovered,
        "previews": len(preview_ids),
        "commits": commits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Training workbook durable worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=int(os.getenv("TRAINING_WORKBOOK_WORKER_LIMIT", "2")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("TRAINING_WORKBOOK_WORKER_POLL_SECONDS", "2")))
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
