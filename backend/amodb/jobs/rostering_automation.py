"""Run due tenant roster-automation policies.

Intended for cron, Task Scheduler or the platform worker at an hourly cadence.
The database policy controls the tenant-local execution day and hour. Multiple
workers are safe: each policy row is locked and every execution has a stable
tenant-scoped idempotency key.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import time as time_module
from typing import Optional

from amodb.database import WriteSessionLocal
from amodb.apps.rostering import automation_service
from amodb.apps.rostering.automation_models import (
    RosterAutomationRunStatus,
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


def _record_failed_scheduled_run(
    db,
    *,
    policy_id: str,
    actor_user_id: Optional[str],
    idempotency_key: str,
    message: str,
    scheduled_occurrence: datetime,
    as_of: datetime,
    failure_kind: str = "EXECUTION_FAILED",
) -> bool:
    """Roll back generated work, then record one terminal scheduled attempt.

    The operational transaction is discarded before evidence is inserted. The
    policy advances to its next scheduled occurrence so a deterministic failed
    idempotency key cannot leave the hourly worker replaying the same cycle.
    Missing accountable ownership is recorded as SKIPPED rather than FAILED.
    """
    db.rollback()
    try:
        policy = db.query(RosterGenerationPolicy).filter(
            RosterGenerationPolicy.id == policy_id,
        ).with_for_update().first()
        if policy is None:
            return False

        skipped = failure_kind == "NO_ACCOUNTABLE_OWNER"
        existing = db.query(RosterGenerationRun).filter(
            RosterGenerationRun.amo_id == policy.amo_id,
            RosterGenerationRun.idempotency_key == idempotency_key,
        ).first()
        if existing is None:
            target_from, target_to = automation_service._target_window_for_occurrence(
                policy, scheduled_occurrence
            )
            row = RosterGenerationRun(
                amo_id=policy.amo_id,
                policy_id=policy.id,
                trigger=RosterAutomationTrigger.SCHEDULED,
                status=(
                    RosterAutomationRunStatus.SKIPPED
                    if skipped
                    else RosterAutomationRunStatus.FAILED
                ),
                idempotency_key=idempotency_key,
                dry_run=False,
                target_from=target_from.isoformat(),
                target_to=target_to.isoformat(),
                generated_count=0,
                skipped_count=0,
                conflict_count=0,
                validation_blocker_count=0,
                validation_warning_count=0,
                summary_json={
                    "operational_changes_committed": False,
                    "failure_recorded_after_rollback": not skipped,
                    "skip_recorded_after_rollback": skipped,
                    "scheduled_cycle_advanced": True,
                    "failure_kind": failure_kind,
                },
                error_message=message,
                requested_by_user_id=actor_user_id,
                started_at=as_of,
                completed_at=as_of,
                created_at=as_of,
            )
            db.add(row)

        policy.last_run_at = as_of
        policy.next_run_at = automation_service._next_run(
            policy,
            now=as_of,
            previous_scheduled_at=scheduled_occurrence,
        )
        policy.updated_reason = (
            "Scheduled run skipped because no accountable policy owner is recorded."
            if skipped
            else "Scheduled automation failed; all generated changes were rolled back."
        )
        db.add(policy)
        db.commit()
        return True
    except Exception:
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

        scheduled_occurrence = policy.next_run_at
        target_from, target_to = automation_service._target_window_for_occurrence(
            policy, scheduled_occurrence
        )
        amo_id = policy.amo_id
        due_key = scheduled_occurrence.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        idempotency_key = f"scheduled:{policy.id}:{due_key}"
        actor_user_id: Optional[str] = policy.updated_by_user_id or policy.created_by_user_id
        if not actor_user_id:
            message = "Scheduled run skipped because no accountable policy owner is recorded."
            retained = _record_failed_scheduled_run(
                db,
                policy_id=policy_id,
                actor_user_id=None,
                idempotency_key=idempotency_key,
                message=message,
                scheduled_occurrence=scheduled_occurrence,
                as_of=as_of,
                failure_kind="NO_ACCOUNTABLE_OWNER",
            )
            return {
                "policy_id": policy_id,
                "amo_id": amo_id,
                "outcome": "skipped_no_owner",
                "evidence_retained": retained,
                "error": message,
            }

        try:
            row = automation_service.run(
                db,
                amo_id=amo_id,
                actor_user_id=actor_user_id,
                trigger=RosterAutomationTrigger.SCHEDULED,
                payload=RosterAutomationRunRequest(
                    idempotency_key=idempotency_key,
                    target_from=target_from,
                    target_to=target_to,
                    confirm_preview=True,
                    create_missing_period=True,
                    create_initial_draft=policy.create_initial_draft,
                    generate_from_patterns=policy.generate_from_patterns,
                ),
            )
            db.commit()
            outcome = str(getattr(row.status, "value", row.status))
            return {
                "policy_id": policy.id,
                "amo_id": amo_id,
                "run_id": row.id,
                "outcome": outcome,
                "generated_count": row.generated_count,
                "conflict_count": row.conflict_count,
            }
        except Exception as exc:
            message = str(exc)
            retained = _record_failed_scheduled_run(
                db,
                policy_id=policy_id,
                actor_user_id=actor_user_id,
                idempotency_key=idempotency_key,
                message=message,
                scheduled_occurrence=scheduled_occurrence,
                as_of=as_of,
            )
            return {
                "policy_id": policy_id,
                "amo_id": amo_id,
                "outcome": "failed",
                "evidence_retained": retained,
                "error": message,
            }
    finally:
        db.close()


def run(*, as_of: Optional[datetime] = None, limit: int = 100) -> dict:
    """Execute due policies and return a scheduler-safe summary.

    One tenant failure is returned as an isolated result and never prevents
    later due tenants from being attempted in the same scheduler invocation.
    """
    effective_as_of = as_of or _utcnow()
    policy_ids = _due_policy_ids(as_of=effective_as_of, limit=max(1, min(limit, 500)))
    results: list[dict] = []
    for policy_id in policy_ids:
        try:
            results.append(_run_policy(policy_id, as_of=effective_as_of))
        except Exception as exc:
            results.append({
                "policy_id": policy_id,
                "outcome": "failed",
                "evidence_retained": False,
                "error": str(exc),
            })
    return {
        "as_of": effective_as_of.isoformat(),
        "due_count": len(policy_ids),
        "completed_count": sum(1 for item in results if item.get("outcome") in {"COMPLETED", "COMPLETED_WITH_CONFLICTS"}),
        "failed_count": sum(1 for item in results if item.get("outcome") == "failed"),
        "skipped_count": sum(1 for item in results if str(item.get("outcome", "")).startswith("skipped")),
        "results": results,
    }


def _positive_int(value: str, *, field: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{field} must be at least 1")
    return parsed


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Execute due roster automation policies")
    parser.add_argument("--loop", action="store_true", help="Run continuously for container deployments")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=_positive_int(os.getenv("ROSTER_AUTOMATION_POLL_SECONDS", "3600"), field="ROSTER_AUTOMATION_POLL_SECONDS"),
    )
    parser.add_argument(
        "--retry-seconds",
        type=int,
        default=_positive_int(os.getenv("ROSTER_AUTOMATION_RETRY_SECONDS", "60"), field="ROSTER_AUTOMATION_RETRY_SECONDS"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_positive_int(os.getenv("ROSTER_AUTOMATION_BATCH_LIMIT", "100"), field="ROSTER_AUTOMATION_BATCH_LIMIT"),
    )
    args = parser.parse_args(argv)
    if args.interval_seconds < 1 or args.retry_seconds < 1 or args.limit < 1:
        parser.error("interval, retry and limit values must be at least 1")

    while True:
        exit_code = 0
        try:
            summary = run(limit=args.limit)
        except Exception as exc:
            exit_code = 1
            summary = {
                "as_of": _utcnow().isoformat(),
                "outcome": "scheduler_error",
                "error": str(exc),
            }
        print(json.dumps(summary, sort_keys=True, default=str), flush=True)
        if not args.loop:
            return exit_code
        time_module.sleep(args.interval_seconds if exit_code == 0 else args.retry_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
