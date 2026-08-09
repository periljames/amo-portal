from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from . import models
from .audit_programme_models import QualityAuditProgrammeItem, QualityAuditUniverseItem
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(tags=["Quality planner strategic views"])


def _quarter(month: int) -> int:
    return ((month - 1) // 3) + 1


def _user_name(user: account_models.User | None, user_id: str) -> str:
    if user is None:
        return user_id
    return (
        str(getattr(user, "full_name", "") or "").strip()
        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        or str(getattr(user, "email", "") or "").strip()
        or user_id
    )


def _department(user: account_models.User | None) -> str:
    if user is None:
        return "Unresolved personnel"
    for key in ("department_name", "department", "department_code", "department_id"):
        value = getattr(user, key, None)
        if value:
            return str(value)
    return "Unassigned department"


def _programme_states(db: Session, amo_id: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for universe_id, state in db.query(
        QualityAuditProgrammeItem.universe_item_id,
        QualityAuditProgrammeItem.state,
    ).filter(QualityAuditProgrammeItem.amo_id == amo_id).limit(10000).all():
        result[str(universe_id)].append(str(state))
    return result


def _universe_item(row: QualityAuditUniverseItem, states: list[str]) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "label": row.display_label,
        "entity_type": row.entity_type,
        "source_owner_module": row.source_owner_module,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_route": row.source_route,
        "risk_classification": row.risk_classification,
        "regulatory_criticality": row.regulatory_criticality,
        "mandatory_surveillance": bool(row.mandatory_surveillance),
        "surveillance_interval_days": row.surveillance_interval_days,
        "programme_states": states,
    }


@router.get("/planner/strategic")
def planner_strategic_view(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)

    schedules = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.next_due_date >= date(year, 1, 1),
        models.QMSAuditSchedule.next_due_date <= date(year, 12, 31),
    ).order_by(models.QMSAuditSchedule.next_due_date.asc()).limit(5000).all()

    month_counts = {month: 0 for month in range(1, 13)}
    quarter_counts = {quarter: 0 for quarter in range(1, 5)}
    status_counts: Counter[str] = Counter()
    workload: Counter[str] = Counter()
    location_counts: Counter[str] = Counter()
    assigned_user_ids: set[str] = set()

    for schedule in schedules:
        month = schedule.next_due_date.month
        month_counts[month] += 1
        quarter_counts[_quarter(month)] += 1
        status_counts[str(schedule.lifecycle_status or "ACTIVE")] += 1
        location_counts[str(schedule.location or "Unspecified location")] += 1
        for user_id in (
            schedule.lead_auditor_user_id,
            schedule.observer_auditor_user_id,
            schedule.assistant_auditor_user_id,
        ):
            if user_id:
                key = str(user_id)
                assigned_user_ids.add(key)
                workload[key] += 1

    users = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id.in_(list(assigned_user_ids)) if assigned_user_ids else False,
    ).all() if assigned_user_ids else []
    user_map = {str(user.id): user for user in users}
    department_counts: Counter[str] = Counter()
    for user_id, count in workload.items():
        department_counts[_department(user_map.get(user_id))] += count

    states = _programme_states(db, ctx.amo_id)
    universe = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.active.is_(True),
    ).order_by(QualityAuditUniverseItem.display_label.asc()).limit(2000).all()

    supplier_terms = ("supplier", "vendor", "procurement", "contractor", "subcontractor")
    regulator_terms = ("regulator", "authority", "approval", "commitment", "regulatory")
    supplier_items: list[dict[str, Any]] = []
    regulatory_items: list[dict[str, Any]] = []
    for row in universe:
        haystack = " ".join((str(row.entity_type or ""), str(row.source_owner_module or ""), str(row.source_type or ""))).lower()
        item = _universe_item(row, states.get(str(row.id), []))
        if any(term in haystack for term in supplier_terms):
            supplier_items.append(item)
        if row.mandatory_surveillance or row.regulatory_criticality in {"HIGH", "CRITICAL"} or any(term in haystack for term in regulator_terms):
            regulatory_items.append(item)

    unresolved_departments = sum(count for department, count in department_counts.items() if department in {"Unassigned department", "Unresolved personnel"})
    return {
        "year": year,
        "timezone_name": "Africa/Nairobi",
        "schedule_count": len(schedules),
        "months": [{"month": month, "schedule_count": month_counts[month]} for month in range(1, 13)],
        "quarters": [{"quarter": quarter, "schedule_count": quarter_counts[quarter]} for quarter in range(1, 5)],
        "lifecycle_states": dict(status_counts),
        "auditor_workload": [
            {
                "user_id": user_id,
                "name": _user_name(user_map.get(user_id), user_id),
                "department": _department(user_map.get(user_id)),
                "schedule_count": count,
            }
            for user_id, count in sorted(workload.items(), key=lambda item: (-item[1], _user_name(user_map.get(item[0]), item[0]).lower()))
        ],
        "department_coverage": [
            {"department": department, "assigned_audit_slots": count}
            for department, count in sorted(department_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ],
        "location_coverage": [
            {"location": location, "schedule_count": count}
            for location, count in sorted(location_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ],
        "supplier_surveillance": supplier_items,
        "regulatory_commitments": regulatory_items,
        "data_quality": {
            "unresolved_department_assignments": unresolved_departments,
            "statement": "Coverage counts are derived from authoritative Planner assignments and Audit Universe lineage; missing personnel department data is surfaced rather than inferred.",
        },
    }
