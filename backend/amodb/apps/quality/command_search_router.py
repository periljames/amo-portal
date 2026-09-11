from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from . import models
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/command-search", tags=["Quality command search"])


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _audit_path(amo_code: str, audit_ref: str) -> str:
    return f"/maintenance/{amo_code}/quality/audits/{audit_ref}/setup"


def _car_path(amo_code: str, car_id: Any) -> str:
    return f"/maintenance/{amo_code}/quality/cars/{car_id}/overview"


def _finding_path(amo_code: str, finding_id: Any) -> str:
    return f"/maintenance/{amo_code}/quality/audits/register?tab=findings&focusId={finding_id}"


def _schedule_path(amo_code: str, schedule_id: Any) -> str:
    return f"/maintenance/{amo_code}/quality/calendar/week?focusId={schedule_id}"


@router.get("")
def command_search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=18, ge=1, le=40),
    view: str = Query(default="global", pattern="^(global|mine)$"),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Search tenant-scoped Quality entities for the global command palette.

    Exact/reference-like matches are deliberately ranked ahead of free-text
    matches. ``view=mine`` never accepts a client-supplied user id: the current
    authenticated user in ``TenantContext`` defines the personal scope.
    """

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    needle = q.strip()
    like = f"%{needle}%"
    prefix = f"{needle}%"
    results: list[dict[str, Any]] = []

    audit_query = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.deleted_at.is_(None),
        or_(
            models.QMSAudit.audit_ref.ilike(like),
            models.QMSAudit.title.ilike(like),
            models.QMSAudit.scope.ilike(like),
            models.QMSAudit.criteria.ilike(like),
        ),
    )
    if view == "mine":
        audit_query = audit_query.filter(
            or_(
                models.QMSAudit.lead_auditor_user_id == ctx.user_id,
                models.QMSAudit.assistant_auditor_user_id == ctx.user_id,
                models.QMSAudit.observer_auditor_user_id == ctx.user_id,
                models.QMSAudit.auditee_user_id == ctx.user_id,
            )
        )
    for audit in audit_query.order_by(models.QMSAudit.created_at.desc()).limit(limit).all():
        exact = audit.audit_ref.lower() == needle.lower()
        starts = audit.audit_ref.lower().startswith(needle.lower())
        results.append({
            "kind": "audit",
            "id": str(audit.id),
            "reference": audit.audit_ref,
            "title": audit.title,
            "subtitle": f"{_value(audit.kind)} audit · {_value(audit.status)}",
            "status": _value(audit.status),
            "path": _audit_path(ctx.amo_code, audit.audit_ref),
            "score": 120 if exact else 100 if starts else 70,
        })

    finding_query = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == ctx.amo_id,
        or_(
            models.QMSAuditFinding.finding_ref.ilike(like),
            models.QMSAuditFinding.requirement_ref.ilike(like),
            models.QMSAuditFinding.description.ilike(like),
        ),
    )
    if view == "mine":
        finding_query = finding_query.join(models.QMSAudit, models.QMSAudit.id == models.QMSAuditFinding.audit_id).filter(
            or_(
                models.QMSAudit.lead_auditor_user_id == ctx.user_id,
                models.QMSAudit.assistant_auditor_user_id == ctx.user_id,
                models.QMSAudit.observer_auditor_user_id == ctx.user_id,
                models.QMSAudit.auditee_user_id == ctx.user_id,
                models.QMSAuditFinding.created_by_user_id == ctx.user_id,
                models.QMSAuditFinding.verified_by_user_id == ctx.user_id,
            )
        )
    for finding in finding_query.order_by(models.QMSAuditFinding.created_at.desc()).limit(limit).all():
        reference = finding.finding_ref or finding.requirement_ref or "Finding"
        exact = reference.lower() == needle.lower()
        starts = reference.lower().startswith(needle.lower())
        results.append({
            "kind": "finding",
            "id": str(finding.id),
            "reference": reference,
            "title": finding.description[:140],
            "subtitle": f"{_value(finding.level)} · {_value(finding.finding_type)}",
            "status": "CLOSED" if finding.closed_at else "OPEN",
            "path": _finding_path(ctx.amo_code, finding.id),
            "score": 115 if exact else 95 if starts else 60,
        })

    schedule_query = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
        or_(
            models.QMSAuditSchedule.title.ilike(like),
            models.QMSAuditSchedule.scope.ilike(like),
            models.QMSAuditSchedule.criteria.ilike(like),
            models.QMSAuditSchedule.auditee.ilike(like),
        ),
    )
    if view == "mine":
        schedule_query = schedule_query.filter(
            or_(
                models.QMSAuditSchedule.lead_auditor_user_id == ctx.user_id,
                models.QMSAuditSchedule.assistant_auditor_user_id == ctx.user_id,
                models.QMSAuditSchedule.observer_auditor_user_id == ctx.user_id,
                models.QMSAuditSchedule.auditee_user_id == ctx.user_id,
            )
        )
    for schedule in schedule_query.order_by(models.QMSAuditSchedule.next_due_date.asc()).limit(limit).all():
        results.append({
            "kind": "schedule",
            "id": str(schedule.id),
            "reference": schedule.audit_scope_code or "Schedule",
            "title": schedule.title,
            "subtitle": f"Due {schedule.next_due_date.isoformat()} · {_value(schedule.frequency)}",
            "status": "ACTIVE" if schedule.is_active else "INACTIVE",
            "path": _schedule_path(ctx.amo_code, schedule.id),
            "score": 55,
        })

    # QualityCAR is intentionally discovered dynamically because the legacy CAR
    # model name is kept stable by the existing module but has changed across
    # migrations. Searching it when present keeps this endpoint schema tolerant.
    car_model = getattr(models, "CAR", None) or getattr(models, "QualityCAR", None)
    if car_model is not None:
        car_query = db.query(car_model).filter(
            car_model.amo_id == ctx.amo_id,
            or_(car_model.car_number.ilike(like), car_model.title.ilike(like)),
        )
        if view == "mine" and hasattr(car_model, "assigned_to_user_id"):
            car_query = car_query.filter(car_model.assigned_to_user_id == ctx.user_id)
        for car in car_query.order_by(car_model.created_at.desc()).limit(limit).all():
            ref = str(getattr(car, "car_number", "CAR"))
            results.append({
                "kind": "car",
                "id": str(car.id),
                "reference": ref,
                "title": str(getattr(car, "title", ref)),
                "subtitle": f"Corrective action · {_value(getattr(car, 'status', ''))}",
                "status": _value(getattr(car, "status", "")),
                "path": _car_path(ctx.amo_code, car.id),
                "score": 118 if ref.lower() == needle.lower() else 98 if ref.lower().startswith(needle.lower()) else 65,
            })

    ordered = sorted(results, key=lambda item: (-int(item["score"]), item["kind"], item["title"].lower()))[:limit]
    for item in ordered:
        item.pop("score", None)

    return {
        "query": needle,
        "view": view,
        "items": ordered,
    }
