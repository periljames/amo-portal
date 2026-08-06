"""Tenant-local scheduling for controlled Workforce offboarding."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..accounts import models as account_models
from ..audit import services as audit_services
from . import governance_models


def tenant_today(db, *, amo_id: str):
    time_zone = db.query(account_models.AMO.time_zone).filter(account_models.AMO.id == amo_id).scalar() or "UTC"
    try:
        zone = ZoneInfo(time_zone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.now(timezone.utc).astimezone(zone).date()


def schedule_offboarding(db, *, amo_id: str, user, payload, actor_user_id: str):
    from . import governance_mutations

    plan = db.query(governance_models.WorkforceOffboardingPlan).filter(
        governance_models.WorkforceOffboardingPlan.amo_id == amo_id,
        governance_models.WorkforceOffboardingPlan.user_id == user.id,
        governance_models.WorkforceOffboardingPlan.effective_on == payload["effective_on"],
    ).with_for_update().first()
    created = plan is None
    if plan is None:
        plan = governance_models.WorkforceOffboardingPlan(
            amo_id=amo_id,
            user_id=user.id,
            effective_on=payload["effective_on"],
            requested_by_user_id=actor_user_id,
        )
        db.add(plan)
    plan.reason = payload["offboarding_reason"].strip()
    plan.revoke_access = bool(payload.get("revoke_access", True))
    plan.end_contracts = bool(payload.get("end_contracts", True))
    plan.remove_groups = bool(payload.get("remove_groups", True))
    plan.status = "SCHEDULED"
    plan.completed_at = None
    db.flush()
    if plan.effective_on <= tenant_today(db, amo_id=amo_id):
        governance_mutations._execute_offboarding(db, plan=plan, actor_user_id=actor_user_id)
    return (
        "SUCCEEDED",
        "OFFBOARDING_SCHEDULED" if plan.status == "SCHEDULED" else "OFFBOARDING_COMPLETED",
        "Offboarding plan created" if created else "Offboarding plan updated",
        {"offboarding_plan_id": str(plan.id), "effective_on": str(plan.effective_on), "status": plan.status},
    )


def apply_due_offboarding(db, *, limit: int = 100) -> int:
    from . import governance_mutations

    # UTC +/- 14 hours means a tenant-local date can be at most one day ahead.
    candidate_cutoff = datetime.now(timezone.utc).date() + timedelta(days=1)
    plans = db.query(governance_models.WorkforceOffboardingPlan).filter(
        governance_models.WorkforceOffboardingPlan.status == "SCHEDULED",
        governance_models.WorkforceOffboardingPlan.effective_on <= candidate_cutoff,
    ).order_by(
        governance_models.WorkforceOffboardingPlan.effective_on.asc(),
        governance_models.WorkforceOffboardingPlan.id.asc(),
    ).limit(max(1, min(limit * 4, 4000))).with_for_update(skip_locked=True).all()
    completed = 0
    for plan in plans:
        if completed >= limit:
            break
        if plan.effective_on > tenant_today(db, amo_id=str(plan.amo_id)):
            continue
        if governance_mutations._execute_offboarding(db, plan=plan):
            completed += 1
            audit_services.log_event(
                db,
                amo_id=str(plan.amo_id),
                actor_user_id=plan.requested_by_user_id,
                entity_type="WorkforceOffboardingPlan",
                entity_id=str(plan.id),
                action="complete",
                after={"user_id": str(plan.user_id), "effective_on": str(plan.effective_on)},
                metadata={"module": "workforce", "automated": True, "tenant_local_date": True},
            )
    return completed
