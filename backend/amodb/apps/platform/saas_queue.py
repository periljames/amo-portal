from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import saas_models as models

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "DEAD", "CANCELLED"}
RETRYABLE_MANUAL_STATUSES = {"FAILED", "DEAD", "CANCELLED", "RETRY"}
CLAIMABLE_STATUSES = {"PENDING", "RETRY"}
NON_REPEATABLE_JOB_TYPES = {"AI_SUPPORT_REPLY", "ETIMS_FISCALIZE_INVOICE"}


class LeaseLostError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scope(tenant_id: str | None) -> str:
    return tenant_id or "__platform__"


def add_event(
    db: Session,
    job: models.SaaSJob,
    status: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    db.add(models.SaaSJobEvent(job_id=job.id, status=status, message=message, data_json=data or {}))


def _add_event_by_id(
    db: Session,
    *,
    job_id: str,
    status: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    db.add(models.SaaSJobEvent(job_id=job_id, status=status, message=message, data_json=data or {}))


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None,
    idempotency_key: str,
    tenant_id: str | None = None,
    queue_name: str = "default",
    priority: int = 100,
    max_attempts: int = 5,
    available_at: datetime | None = None,
    correlation_id: str | None = None,
    created_by: str | None = None,
    commit: bool = True,
) -> models.SaaSJob:
    normalized_type = job_type.strip().upper()
    normalized_key = idempotency_key.strip()
    if not normalized_type:
        raise ValueError("job_type is required")
    if not normalized_key:
        raise ValueError("idempotency_key is required")

    existing = db.query(models.SaaSJob).filter(
        models.SaaSJob.job_type == normalized_type,
        models.SaaSJob.tenant_scope == _scope(tenant_id),
        models.SaaSJob.idempotency_key == normalized_key,
    ).first()
    if existing:
        return existing

    effective_max_attempts = 1 if normalized_type in NON_REPEATABLE_JOB_TYPES else max(1, min(int(max_attempts), 25))
    job = models.SaaSJob(
        queue_name=(queue_name or "default").strip().lower(),
        job_type=normalized_type,
        tenant_id=tenant_id,
        tenant_scope=_scope(tenant_id),
        status="PENDING",
        priority=max(0, min(int(priority), 1000)),
        payload_json=payload or {},
        idempotency_key=normalized_key,
        correlation_id=correlation_id,
        max_attempts=effective_max_attempts,
        available_at=available_at or utcnow(),
        created_by=created_by,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.SaaSJob).filter(
            models.SaaSJob.job_type == normalized_type,
            models.SaaSJob.tenant_scope == _scope(tenant_id),
            models.SaaSJob.idempotency_key == normalized_key,
        ).first()
        if existing:
            return existing
        raise
    add_event(
        db,
        job,
        "PENDING",
        "Job accepted by the durable queue.",
        {"non_repeatable": normalized_type in NON_REPEATABLE_JOB_TYPES},
    )
    if commit:
        db.commit()
        db.refresh(job)
    return job


def release_expired_leases(db: Session, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    query = db.query(models.SaaSJob).filter(
        models.SaaSJob.status == "RUNNING",
        models.SaaSJob.lease_expires_at.isnot(None),
        models.SaaSJob.lease_expires_at <= now,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for job in rows:
        job.locked_at = None
        job.locked_by = None
        job.lease_token = None
        job.lease_expires_at = None
        exhausted = int(job.attempt_count or 0) >= int(job.max_attempts or 1)
        if exhausted or job.job_type in NON_REPEATABLE_JOB_TYPES:
            job.status = "DEAD"
            job.finished_at = now
            reason = (
                "Non-repeatable job lease expired; manual reconciliation is required."
                if job.job_type in NON_REPEATABLE_JOB_TYPES
                else "Worker lease expired and retry allowance was exhausted."
            )
            add_event(db, job, "DEAD", reason)
        else:
            job.status = "RETRY"
            job.available_at = now + _retry_delay(job.attempt_count)
            add_event(db, job, "RETRY", "Expired worker lease released for retry.")
    if rows:
        db.flush()
    return len(rows)


def claim_jobs(
    db: Session,
    *,
    worker_id: str,
    queue_names: Iterable[str] = ("default",),
    batch_size: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[models.SaaSJob]:
    """Atomically lease one side-effect job per worker.

    Workers scale horizontally. Claiming a serial batch caused later jobs to
    expire before execution, which could duplicate external side effects.
    ``batch_size`` remains accepted for compatibility; safe claim width is one.
    """

    now = now or utcnow()
    release_expired_leases(db, now=now)
    normalized_queues = [name.strip().lower() for name in queue_names if name and name.strip()] or ["default"]
    requested_batch_size = max(1, min(int(batch_size), 100))
    safe_lease_seconds = max(30, min(int(lease_seconds), 3600))
    query = db.query(models.SaaSJob).filter(
        models.SaaSJob.queue_name.in_(normalized_queues),
        models.SaaSJob.status.in_(CLAIMABLE_STATUSES),
        models.SaaSJob.available_at <= now,
        or_(models.SaaSJob.lease_expires_at.is_(None), models.SaaSJob.lease_expires_at <= now),
    ).order_by(
        models.SaaSJob.priority.asc(),
        models.SaaSJob.available_at.asc(),
        models.SaaSJob.created_at.asc(),
    ).limit(1)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    else:
        query = query.with_for_update()

    jobs = query.all()
    lease_until = now + timedelta(seconds=safe_lease_seconds)
    for job in jobs:
        job.status = "RUNNING"
        job.locked_at = now
        job.locked_by = worker_id[:128]
        job.lease_token = secrets.token_urlsafe(32)[:64]
        job.lease_expires_at = lease_until
        job.attempt_count = int(job.attempt_count or 0) + 1
        add_event(
            db,
            job,
            "RUNNING",
            f"Claimed by worker {worker_id}.",
            {"requested_batch_size": requested_batch_size, "safe_claim_width": 1},
        )
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


def _lease_filter(db: Session, job: models.SaaSJob, worker_id: str | None = None):
    expected_worker = (worker_id or job.locked_by or "")[:128]
    expected_token = str(job.lease_token or "")
    if not expected_worker or not expected_token:
        raise LeaseLostError("Job has no active lease fence")
    return db.query(models.SaaSJob).filter(
        models.SaaSJob.id == job.id,
        models.SaaSJob.status == "RUNNING",
        models.SaaSJob.locked_by == expected_worker,
        models.SaaSJob.lease_token == expected_token,
    )


def heartbeat_job(
    db: Session,
    job: models.SaaSJob,
    *,
    worker_id: str,
    lease_seconds: int = 60,
) -> None:
    next_expiry = utcnow() + timedelta(seconds=max(30, min(int(lease_seconds), 3600)))
    updated = _lease_filter(db, job, worker_id).update(
        {models.SaaSJob.lease_expires_at: next_expiry},
        synchronize_session=False,
    )
    if updated != 1:
        db.rollback()
        raise LeaseLostError("Job lease was lost before heartbeat")
    db.commit()
    job.lease_expires_at = next_expiry


def complete_job(
    db: Session,
    job: models.SaaSJob,
    result: dict[str, Any] | None = None,
    *,
    worker_id: str | None = None,
) -> None:
    now = utcnow()
    updated = _lease_filter(db, job, worker_id).update(
        {
            models.SaaSJob.status: "SUCCEEDED",
            models.SaaSJob.result_json: result or {},
            models.SaaSJob.last_error: None,
            models.SaaSJob.finished_at: now,
            models.SaaSJob.locked_at: None,
            models.SaaSJob.locked_by: None,
            models.SaaSJob.lease_token: None,
            models.SaaSJob.lease_expires_at: None,
        },
        synchronize_session=False,
    )
    if updated != 1:
        db.rollback()
        raise LeaseLostError("Job lease was lost before completion")
    _add_event_by_id(db, job_id=job.id, status="SUCCEEDED", message="Job completed.", data=result)
    db.commit()
    db.expire(job)
    db.refresh(job)


def _retry_delay(attempt_count: int) -> timedelta:
    return timedelta(seconds=min(1800, 5 * (3 ** max(0, int(attempt_count) - 1))))


def fail_job(
    db: Session,
    job: models.SaaSJob,
    error: BaseException | str,
    *,
    retryable: bool = True,
    worker_id: str | None = None,
) -> None:
    message = str(error)[:4000]
    now = utcnow()
    effective_retryable = retryable and job.job_type not in NON_REPEATABLE_JOB_TYPES
    if effective_retryable and int(job.attempt_count or 0) < int(job.max_attempts or 1):
        status = "RETRY"
        available_at = now + _retry_delay(job.attempt_count)
        finished_at = None
        event_data = {"available_at": available_at.isoformat()}
    else:
        status = "DEAD" if retryable else "FAILED"
        available_at = job.available_at
        finished_at = now
        event_data = {"manual_reconciliation_required": job.job_type in NON_REPEATABLE_JOB_TYPES}
    updated = _lease_filter(db, job, worker_id).update(
        {
            models.SaaSJob.status: status,
            models.SaaSJob.available_at: available_at,
            models.SaaSJob.finished_at: finished_at,
            models.SaaSJob.last_error: message,
            models.SaaSJob.locked_at: None,
            models.SaaSJob.locked_by: None,
            models.SaaSJob.lease_token: None,
            models.SaaSJob.lease_expires_at: None,
        },
        synchronize_session=False,
    )
    if updated != 1:
        db.rollback()
        raise LeaseLostError("Job lease was lost before failure handling")
    _add_event_by_id(db, job_id=job.id, status=status, message=message, data=event_data)
    db.commit()
    db.expire(job)
    db.refresh(job)


def retry_job(db: Session, job: models.SaaSJob, *, actor_user_id: str | None = None) -> models.SaaSJob:
    if job.job_type in NON_REPEATABLE_JOB_TYPES:
        raise ValueError(
            "This non-repeatable job cannot be retried automatically; reconcile the external provider state and create a new audited action"
        )
    if job.status not in RETRYABLE_MANUAL_STATUSES:
        raise ValueError("Only failed, dead, cancelled or retrying jobs can be retried")
    job.status = "PENDING"
    job.available_at = utcnow()
    job.finished_at = None
    job.last_error = None
    job.locked_at = None
    job.locked_by = None
    job.lease_token = None
    job.lease_expires_at = None
    if actor_user_id:
        job.created_by = actor_user_id
    add_event(db, job, "PENDING", "Job manually requeued.")
    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, job: models.SaaSJob, *, reason: str) -> models.SaaSJob:
    if job.status == "RUNNING":
        raise ValueError("A running job cannot be cancelled until its lease expires")
    if job.status in TERMINAL_STATUSES:
        return job
    job.status = "CANCELLED"
    job.finished_at = utcnow()
    job.last_error = reason[:4000]
    job.lease_token = None
    add_event(db, job, "CANCELLED", reason)
    db.commit()
    db.refresh(job)
    return job


def queue_summary(db: Session) -> dict[str, Any]:
    rows = db.query(models.SaaSJob.status, models.SaaSJob.queue_name).all()
    counts: dict[str, int] = {}
    queues: dict[str, int] = {}
    for status, queue_name in rows:
        counts[str(status)] = counts.get(str(status), 0) + 1
        if str(status) not in TERMINAL_STATUSES:
            queues[str(queue_name)] = queues.get(str(queue_name), 0) + 1
    oldest = db.query(models.SaaSJob).filter(
        models.SaaSJob.status.in_({"PENDING", "RETRY", "RUNNING"})
    ).order_by(models.SaaSJob.created_at.asc()).first()
    return {
        "counts": counts,
        "queues": queues,
        "oldest_active_created_at": oldest.created_at if oldest else None,
    }
