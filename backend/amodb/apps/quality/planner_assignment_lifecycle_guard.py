from __future__ import annotations

import importlib
from datetime import datetime, timezone

from amodb.apps.audit import services as audit_services

from .audit_assignment_guard import evaluate_schedule_auditors


_planner = importlib.import_module("amodb.apps.quality.planner_schedule_router")


def _install() -> None:
    if getattr(_planner, "_qms_assignment_guard_installed", False):
        return

    original = _planner._materialize_occurrence
    _planner._materialize_occurrence_without_assignment_guard = original

    def guarded_materialize_occurrence(db, *, schedule, actor_user_id):
        gate = evaluate_schedule_auditors(
            db,
            schedule=schedule,
            as_of=schedule.next_due_date,
            context_type="AUDIT_SCHEDULE",
            context_id=str(schedule.id),
            enforce_independence=True,
            assignment_scope_key=schedule.audit_scope_code,
            exclude_schedule_id=str(schedule.id),
        )
        if gate.get("governed_assignments", 0) and not gate.get("eligible", False):
            metadata = _planner._metadata_for_schedule(
                db,
                amo_id=str(schedule.amo_id),
                schedule_id=schedule.id,
                lock=True,
            )
            before = {
                "automation_active": bool(schedule.is_active),
                "lifecycle_status": metadata.lifecycle_status if metadata else None,
            }
            schedule.is_active = False
            if metadata is not None:
                metadata.lifecycle_status = "SUSPENDED"
                metadata.suspension_reason = "Governed auditor assignment eligibility failed before audit materialization."
                metadata.suspended_at = datetime.now(timezone.utc)
                metadata.suspended_by_user_id = actor_user_id
                metadata.version = int(metadata.version or 1) + 1
                metadata.updated_by_user_id = actor_user_id
            audit_services.log_event(
                db,
                amo_id=str(schedule.amo_id),
                actor_user_id=actor_user_id,
                entity_type="qms_audit_schedule",
                entity_id=str(schedule.id),
                action="auditor_eligibility_blocked_materialization",
                before=before,
                after={
                    "automation_active": False,
                    "lifecycle_status": "SUSPENDED",
                    "assignment_gate": gate,
                },
                correlation_id=f"qms-planner-assignment-gate:{schedule.id}:{schedule.next_due_date.isoformat()}",
                metadata={"source": "quality-people-privileges"},
                critical=True,
            )
            return None, True
        return original(db, schedule=schedule, actor_user_id=actor_user_id)

    _planner._materialize_occurrence = guarded_materialize_occurrence
    _planner._qms_assignment_guard_installed = True


_install()
