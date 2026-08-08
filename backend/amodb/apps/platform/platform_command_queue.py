from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import models, services
from .command_registry import get_definition


PENDING_PLATFORM_STATUSES = {"PENDING", "APPROVED"}


def _execution_actor(job: models.PlatformCommandJob) -> str:
    return str(job.approved_by_user_id or job.actor_user_id or job.requested_by_user_id or "")


def _validate_approval(job: models.PlatformCommandJob) -> None:
    definition = get_definition(job.command_name)
    if definition is None:
        raise ValueError(f"Unsupported platform command {job.command_name}")
    if not definition.requires_approval:
        return
    approved_by = str(job.approved_by_user_id or "")
    requested_by = str(job.requested_by_user_id or "")
    if not approved_by:
        raise PermissionError("High-impact platform command requires second-person approval")
    if requested_by and approved_by == requested_by:
        raise PermissionError("High-impact platform command approver must differ from requester")


def reconcile_pending_jobs(db: Session, *, limit: int = 50) -> int:
    """Move legacy/pending PlatformCommandJob rows onto the lease-fenced SaaS queue.

    This reconciliation does not execute side effects. PostgreSQL row locking only
    protects the state transition into the durable queue; actual execution is
    protected by the SaaSJob lease token and heartbeat fence.
    """

    query = (
        db.query(models.PlatformCommandJob)
        .filter(models.PlatformCommandJob.status.in_(PENDING_PLATFORM_STATUSES))
        .order_by(models.PlatformCommandJob.created_at.asc())
        .limit(max(1, min(int(limit), 500)))
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    else:
        query = query.with_for_update()

    rows = query.all()
    queued = 0
    for job in rows:
        try:
            _validate_approval(job)
        except PermissionError as exc:
            job.status = "NEEDS_APPROVAL"
            services.add_job_event(db, job, "NEEDS_APPROVAL", str(exc))
            continue
        actor_id = _execution_actor(job) or "platform-worker"
        services.queue_command_job(db, job, actor_id=actor_id)
        queued += 1
    if rows:
        db.commit()
    return queued


def process_leased_job(db: Session, queue_job) -> dict[str, Any]:
    """Execute a Platform command only after the SaaS queue lease is acquired.

    Approval is revalidated immediately before execution. Both native queue rows
    and pre-migration ``legacy_job_id`` rows are accepted, but neither path can
    execute outside an already-acquired SaaSJob lease.
    """

    payload = queue_job.payload_json or {}
    command_job_id = str(payload.get("command_job_id") or "").strip()
    legacy_job_id = str(payload.get("legacy_job_id") or "").strip()
    if not command_job_id and legacy_job_id:
        from .saas_legacy_bridge import execute_legacy_command_in_worker

        job = db.get(models.PlatformCommandJob, legacy_job_id)
        if job is None:
            raise ValueError("Legacy Platform command job not found")
        _validate_approval(job)
        actor_id = str(payload.get("actor_id") or _execution_actor(job) or "platform-worker")
        return execute_legacy_command_in_worker(db, legacy_job_id=legacy_job_id, actor_id=actor_id)
    if not command_job_id:
        raise ValueError("Platform command queue payload is missing command_job_id")

    job = db.get(models.PlatformCommandJob, command_job_id)
    if job is None:
        raise ValueError("Platform command job not found")
    if job.status in {"SUCCEEDED", "CANCELLED"}:
        return {"command_job_id": job.id, "status": job.status, "result": job.output_json or {}}

    try:
        _validate_approval(job)
    except PermissionError as exc:
        job.status = "NEEDS_APPROVAL"
        services.add_job_event(db, job, "NEEDS_APPROVAL", f"Execution blocked: {exc}")
        db.flush()
        raise

    return services.process_command_queue_job(db, queue_job)


def queue_job_is_retryable(queue_job) -> bool:
    payload = queue_job.payload_json or {}
    if not (str(payload.get("command_job_id") or "").strip() or str(payload.get("legacy_job_id") or "").strip()):
        return False
    return int(queue_job.max_attempts or 1) > int(queue_job.attempt_count or 0)
