"""Run due tenant roster-automation policies.

Intended for cron, Task Scheduler or the platform worker at an hourly cadence.
The database policy controls the tenant-local execution day and hour. Multiple
workers are safe: each policy row is locked and every execution has a stable
tenant-scoped idempotency key.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import PendingRollbackError

from amodb.database import WriteSessionLocal
from amodb.apps.rostering import automation_service
from amodb.apps.rostering.automation_models import (
    RosterAutomationTrigger,
    RosterGenerationPolicy,
    RosterGenerationRun,
)
from amodb.apps.rostering.automation_schemas import RosterAutomationRunRequest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _due_policy_ids(*, as_of: datetime, limit: int) -> list[str]:
    db = WriteSessionLocal()
    try:
        return [
            str(row[0])
            for row in db.query(RosterGenerationPolicy.id).filter(
                RosterGenerationPolicy.enabled.is_(True),
                RosterGenerationPolicy.next_run_at.is_not(None),
                RosterGenerationPolicy.next_run_at <= as_of,
            ).order_by(
                RosterGenerationPolicy.next_run_at.asc(),
                RosterGenerationPolicy.id.asc(),
            ).limit(limit).all()
        ]
    finally:
        db.close()


def _commit_failed_run_if_present(db, *, amo_id: str, idempotency_key: str) -> bool:
    try:
        row = db.query(RosterGenerationRun).filter(
            RosterGenerationRun.amo_id == amo_id,
            RosterGenerationRun.idempotency_key == idempotency_key,
        ).first()
        if row is not None and str(getattr(row.status, "value", row.status)) == "FAILED":
            db.commit()
            return True
    except PendingRollbackError:
        pass
    db.rollback()
    return False


def _run_policy(policy_id: str, *, as_of: datetime) -> dict:
    db = WriteSessionLocal()
    try:
        policy = db.query(RosterGenerationPolicy).filter(
            RosterGenerationPolicy.id == policy_id,
        ).with_for_update(skip_locked=True).first()
        if policy is None:
            return {"policy_id": policy_id, "outcome": "locked_or_missing"}
        if not policy.enabled or policy.next_run_at is None or policy.next_run_at > as_of:
            return {"policy_id": policy_id, "outcome": "not_due"}

        actor_user_id: Optional[str] = policy.updated_by_user_id or policy.created_by_user_id
        if not actor_user_id:
            policy.next_run_at = automation_service._next_run(policy, now=as_of)
            policy.updated_reason = "Scheduled run skipped because no accountable policy owner is recorded."
            db.add(policy)
            db.commit()
            return {"policy_id": policy_id, "outcome": "skipped_no_owner"}

        due_key = policy.next_run_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        idempotency_key = f"scheduled:{policy.id}:{due_key}"
        try:
            row = automation_service.run(
                db,
                amo_id=policy.amo_id,
                actor_user_id=actor_user_id,
                trigger=RosterAutomationTrigger.SCHEDULED,
                payload=RosterAutomationRunRequest(
                    idempotency_key=idempotency_key,
                    confirm_preview=True,
                    create_missing_period=True,
                    create_initial_draft=policy.create_initial_draft,
                    generate_from_patterns=policy.generate_from_patterns,
                ),
            )
            db.commit()
            return {
                "policy_id": policy.id,
                "amo_id": policy.amo_id,
                "run_id": row.id,
                "outcome": str(getattr(row.status, "value", row.status)),
                "generated_count": row.generated_count,
                "conflict_count": row.conflict_count,
            }
        except (ValueError, RuntimeError) as exc:
            retained = _commit_failed_run_if_present(
                db,
                amo_id=policy.amo_id,
                idempotency_key=idempotency_key,
            )
            return {
                "policy_id": policy.id,
                "amo_id": policy.amo_id,
                "outcome": "failed",
                "evidence_retained": retained,
                "error": str(exc),
            }
    finally:
        db.close()


def run(*, as_of: Optional[datetime] = None, limit: int = 100) -> dict:
    """Execute due policies and return a scheduler-safe summary."""
    effective_as_of = as_of or _utcnow()
    policy_ids = _due_policy_ids(as_of=effective_as_of, limit=max(1, min(limit, 500)))
    results = [_run_policy(policy_id, as_of=effective_as_of) for policy_id in policy_ids]
    return {
        "as_of": effective_as_of.isoformat(),
        "due_count": len(policy_ids),
        "completed_count": sum(1 for item in results if item.get("outcome") in {"COMPLETED", "COMPLETED_WITH_CONFLICTS"}),
        "failed_count": sum(1 for item in results if item.get("outcome") == "failed"),
        "skipped_count": sum(1 for item in results if str(item.get("outcome", "")).startswith("skipped")),
        "results": results,
    }


if __name__ == "__main__":
    print("Rostering automation completed:", run())
