from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
import time
from typing import Any

from sqlalchemy import text

from amodb.apps.accounts import models as account_models
from amodb.apps.tasks import services as task_services
from amodb.apps.platform import (
    commercial_services,
    saas_lease,
    saas_models as models,
    saas_queue,
    saas_side_effects,
)
from amodb.database import WriteSessionLocal, close_session_safely


logger = logging.getLogger(__name__)


def _worker_id() -> str:
    return os.getenv("SAAS_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


def _record_worker_heartbeat(db, worker_id: str) -> None:
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


def _process_job(db, job: models.SaaSJob) -> dict[str, Any]:
    if job.job_type in commercial_services.COMMERCIAL_JOB_TYPES:
        return commercial_services.process_job(db, job)
    if job.job_type == "ETIMS_FISCALIZE_INVOICE":
        return saas_side_effects.process_etims_fiscalization(db, job=job)
    if job.job_type == "AI_SUPPORT_REPLY":
        return saas_side_effects.process_ai_support_reply(db, job=job)
    if (
        job.job_type == "PROVIDER_HEALTH_CHECK"
        and str((job.payload_json or {}).get("provider") or "").strip().lower() == "resend"
    ):
        from amodb.apps.platform.resend_email_policy import process_resend_authentication_job

        return process_resend_authentication_job(db, job)
    from amodb.jobs import saas_worker as handlers

    return handlers.process_job(db, job)


def run_once(*, batch_size: int = 1, worker_id: str | None = None) -> dict[str, Any]:
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
                    result = _process_job(db, job)
                    heartbeat.raise_if_lost()
                saas_queue.complete_job(db, job, result, worker_id=worker_id)
                processed += 1
            except saas_queue.LeaseLostError:
                db.rollback()
                lease_lost += 1
            except Exception as exc:
                try:
                    _mark_webhook_failure(db, job, exc)
                    retryable = not isinstance(exc, saas_side_effects.NonRepeatableJobError)
                    saas_queue.fail_job(
                        db,
                        job,
                        exc,
                        retryable=retryable,
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


def _health_interval_seconds() -> int:
    requested = int(os.getenv("RESEND_HEALTH_INTERVAL_SECONDS", "3600"))
    return max(300, min(requested, 86400))


def _run_periodic_health(last_run: float | None) -> float:
    now = time.monotonic()
    interval = _health_interval_seconds()
    if last_run is not None and now - last_run < interval:
        return last_run
    from amodb.jobs import platform_integration_health

    platform_integration_health.run_once(min_interval_seconds=interval)
    return now


def _quality_task_interval_seconds() -> int:
    requested = int(os.getenv("QUALITY_TASK_INTERVAL_SECONDS", "300"))
    return max(60, min(requested, 86400))


def _run_periodic_quality_tasks(last_run: float | None) -> float:
    now = time.monotonic()
    interval = _quality_task_interval_seconds()
    if last_run is not None and now - last_run < interval:
        return last_run

    db = WriteSessionLocal()
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            digest = hashlib.sha256(b"quality:task-reminder-runner").digest()
            lock_key = int.from_bytes(digest[:8], byteorder="big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF
            acquired = bool(
                db.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                ).scalar()
            )
            if not acquired:
                db.rollback()
                return now
        summary = task_services.run_task_runner(db)
        db.commit()
        if summary.get("reminders") or summary.get("escalations"):
            logger.info("Quality task email run completed: %s", summary)
    except Exception:
        db.rollback()
        logger.exception("Quality task reminder/escalation run failed")
    finally:
        close_session_safely(db)
    return now


def run_forever(*, poll_seconds: float = 1.0, batch_size: int = 1) -> None:
    worker_id = _worker_id()
    last_health_run: float | None = None
    last_quality_task_run: float | None = None
    while True:
        result = run_once(batch_size=batch_size, worker_id=worker_id)
        last_health_run = _run_periodic_health(last_health_run)
        last_quality_task_run = _run_periodic_quality_tasks(last_quality_task_run)
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
