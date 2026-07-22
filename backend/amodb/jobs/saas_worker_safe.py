from __future__ import annotations

import argparse
import json
import os
import socket
import time
from typing import Any

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_lease, saas_models as models, saas_queue
from amodb.database import WriteSessionLocal, close_session_safely


def _worker_id() -> str:
    return os.getenv("SAAS_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


def _record_worker_heartbeat(db, worker_id: str) -> None:
    # Import lazily so the existing handler module remains the single source for
    # provider processing while this module owns execution safety.
    from amodb.jobs import saas_worker as handlers

    handlers._heartbeat(db, worker_id)


def _mark_webhook_failure(db, job: models.SaaSJob, exc: Exception) -> None:
    if job.job_type != "STRIPE_WEBHOOK":
        return
    event_id = str((job.payload_json or {}).get("webhook_event_id") or "")
    event = db.get(account_models.WebhookEvent, event_id)
    if event:
        event.status = account_models.WebhookStatus.FAILED
        event.attempt_count = int(event.attempt_count or 0) + 1
        event.last_error = str(exc)[:4000]
        db.flush()


def run_once(*, batch_size: int = 1, worker_id: str | None = None) -> dict[str, Any]:
    from amodb.jobs import saas_worker as handlers

    worker_id = worker_id or _worker_id()
    lease_seconds = int(os.getenv("SAAS_JOB_LEASE_SECONDS", "120"))
    db = WriteSessionLocal()
    processed = 0
    failed = 0
    lease_lost = 0
    try:
        _record_worker_heartbeat(db, worker_id)
        jobs = saas_queue.claim_jobs(
            db,
            worker_id=worker_id,
            queue_names=("billing", "integrations", "fiscalization", "ai", "default"),
            batch_size=batch_size,
            lease_seconds=lease_seconds,
        )
        for job in jobs:
            try:
                with saas_lease.LeaseHeartbeat(
                    job,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                ) as heartbeat:
                    result = handlers.process_job(db, job)
                    heartbeat.raise_if_lost()
                saas_queue.complete_job(db, job, result, worker_id=worker_id)
                processed += 1
            except saas_queue.LeaseLostError:
                # A different worker owns the job now. Never overwrite or retry it
                # from this stale worker session.
                db.rollback()
                lease_lost += 1
            except Exception as exc:
                try:
                    _mark_webhook_failure(db, job, exc)
                    saas_queue.fail_job(
                        db,
                        job,
                        exc,
                        retryable=job.job_type != "AI_SUPPORT_REPLY",
                        worker_id=worker_id,
                    )
                except saas_queue.LeaseLostError:
                    db.rollback()
                    lease_lost += 1
                else:
                    failed += 1
        _record_worker_heartbeat(db, worker_id)
        return {
            "worker_id": worker_id,
            "claimed": len(jobs),
            "processed": processed,
            "failed": failed,
            "lease_lost": lease_lost,
        }
    finally:
        close_session_safely(db)


def run_forever(*, poll_seconds: float = 1.0, batch_size: int = 1) -> None:
    worker_id = _worker_id()
    while True:
        result = run_once(batch_size=batch_size, worker_id=worker_id)
        if result["claimed"] == 0:
            time.sleep(max(0.25, min(poll_seconds, 30.0)))


def main() -> None:
    parser = argparse.ArgumentParser(description="AMO Portal lease-fenced SaaS worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("SAAS_WORKER_BATCH_SIZE", "1")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("SAAS_WORKER_POLL_SECONDS", "1")))
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(batch_size=args.batch_size), default=str))
    else:
        run_forever(poll_seconds=args.poll_seconds, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
