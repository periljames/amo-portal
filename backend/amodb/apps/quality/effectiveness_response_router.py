from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
from .audit_source_link_models import QualityAuditSourceLink
from .effectiveness_response_models import QualityEffectivenessResponseAction, QualityEffectivenessResponseEvent
from .planner_assignment_guard_router import create_guarded_planner_audit_schedule
from .planner_schedule_router import PlannerAuditScheduleCreate
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context

router = APIRouter(tags=["Quality effectiveness response actions"])
ActionType = Literal["ADDITIONAL_ACTION", "FOLLOW_UP_AUDIT", "REOPEN_CAR", "MANAGEMENT_ESCALATION", "RISK_REASSESSMENT"]
ActionDecision = Literal["COMPLETE", "CANCEL"]


class EffectivenessResponseCreate(BaseModel):
    action_type: ActionType
    rationale: str = Field(min_length=8, max_length=4000)
    target_source_type: str | None = Field(default=None, max_length=64)
    target_source_id: str | None = Field(default=None, max_length=160)
    target_route: str | None = Field(default=None, max_length=500)
    due_date: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    schedule: PlannerAuditScheduleCreate | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "EffectivenessResponseCreate":
        if self.action_type == "FOLLOW_UP_AUDIT" and self.schedule is None:
            raise ValueError("FOLLOW_UP_AUDIT requires an authoritative Planner schedule payload.")
        if self.action_type != "FOLLOW_UP_AUDIT" and self.schedule is not None:
            raise ValueError("Only FOLLOW_UP_AUDIT accepts a Planner schedule payload.")
        return self


class EffectivenessResponseDecision(BaseModel):
    decision: ActionDecision
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _plan(db: Session, *, amo_id: str, case_id: str, plan_id: str) -> tuple[QualityAssuranceCase, QualityEffectivenessPlan]:
    case = db.query(QualityAssuranceCase).filter(
        QualityAssuranceCase.amo_id == amo_id,
        QualityAssuranceCase.id == case_id,
    ).first()
    plan = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == amo_id,
        QualityEffectivenessPlan.case_id == case_id,
        QualityEffectivenessPlan.id == plan_id,
    ).first()
    if case is None or plan is None:
        raise HTTPException(status_code=404, detail="Assurance case or effectiveness plan not found.")
    if plan.conclusion not in {"INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"}:
        raise HTTPException(
            status_code=409,
            detail="Downstream response actions are available only after an ineffective, partially effective or inconclusive effectiveness conclusion.",
        )
    return case, plan


def _snapshot(case: QualityAssuranceCase, plan: QualityEffectivenessPlan, action: QualityEffectivenessResponseAction | None = None) -> dict[str, Any]:
    return {
        "case_id": str(case.id),
        "case_ref": case.case_ref,
        "case_status": case.status,
        "effectiveness_plan_id": str(plan.id),
        "effectiveness_status": plan.status,
        "effectiveness_conclusion": plan.conclusion,
        "effectiveness_source_type": getattr(plan, "source_type", None),
        "effectiveness_source_id": getattr(plan, "source_id", None),
        "effectiveness_source_route": getattr(plan, "source_route", None),
        "response_action": {
            "id": str(action.id),
            "action_type": action.action_type,
            "status": action.status,
            "target_source_type": action.target_source_type,
            "target_source_id": action.target_source_id,
            "target_route": action.target_route,
            "schedule_id": str(action.schedule_id) if action.schedule_id else None,
        } if action else None,
        "captured_at": _utcnow().isoformat(),
    }


def _event_dict(row: QualityEffectivenessResponseEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "snapshot": row.snapshot or {},
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _action_dict(row: QualityEffectivenessResponseAction) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "case_id": row.case_id,
        "effectiveness_plan_id": row.effectiveness_plan_id,
        "action_type": row.action_type,
        "status": row.status,
        "rationale": row.rationale,
        "target_source_type": row.target_source_type,
        "target_source_id": row.target_source_id,
        "target_route": row.target_route,
        "schedule_id": str(row.schedule_id) if row.schedule_id else None,
        "due_date": row.due_date,
        "owner_user_id": row.owner_user_id,
        "source_snapshot": row.source_snapshot or {},
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "completed_by_user_id": row.completed_by_user_id,
        "completed_at": row.completed_at,
        "completion_reason": row.completion_reason,
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


def _add_event(db: Session, *, ctx: TenantContext, row: QualityEffectivenessResponseAction, event_type: str, reason: str, snapshot: dict[str, Any]) -> None:
    db.add(QualityEffectivenessResponseEvent(
        amo_id=ctx.amo_id,
        case_id=row.case_id,
        response_action_id=row.id,
        event_type=event_type,
        reason=reason.strip(),
        snapshot=snapshot,
        actor_user_id=ctx.user_id,
    ))


@router.get("/assurance-cases/{case_id}/effectiveness-responses")
def list_effectiveness_responses(
    case_id: str,
    plan_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = db.query(QualityAssuranceCase.id).filter(QualityAssuranceCase.amo_id == ctx.amo_id, QualityAssuranceCase.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Assurance case not found.")
    query = db.query(QualityEffectivenessResponseAction).options(selectinload(QualityEffectivenessResponseAction.events)).filter(
        QualityEffectivenessResponseAction.amo_id == ctx.amo_id,
        QualityEffectivenessResponseAction.case_id == case_id,
    )
    if plan_id:
        query = query.filter(QualityEffectivenessResponseAction.effectiveness_plan_id == plan_id)
    rows = query.order_by(QualityEffectivenessResponseAction.created_at.desc()).limit(250).all()
    return {"items": [_action_dict(row) for row in rows]}


@router.post("/assurance-cases/{case_id}/effectiveness-plans/{plan_id}/responses", status_code=status.HTTP_201_CREATED)
def create_effectiveness_response(
    case_id: str,
    plan_id: str,
    payload: EffectivenessResponseCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case, plan = _plan(db, amo_id=ctx.amo_id, case_id=case_id, plan_id=plan_id)

    target_source_type = payload.target_source_type or getattr(plan, "source_type", None)
    target_source_id = payload.target_source_id or getattr(plan, "source_id", None)
    target_route = payload.target_route or getattr(plan, "source_route", None)
    schedule_id = None
    schedule = None

    if payload.action_type == "REOPEN_CAR":
        if str(target_source_type or "").upper() != "CAR" or not target_source_id:
            raise HTTPException(
                status_code=422,
                detail="REOPEN_CAR requires the effectiveness plan or request to identify the authoritative CAR source. The response remains an explicit obligation; it does not silently overwrite CAR history.",
            )
        target_route = target_route or f"/maintenance/{ctx.amo_code}/quality/cars/{target_source_id}"
    elif payload.action_type == "FOLLOW_UP_AUDIT":
        schedule = create_guarded_planner_audit_schedule(payload=payload.schedule, request=request, ctx=ctx, db=db)  # type: ignore[arg-type]
        schedule_id = schedule.id
        target_source_type = "AUDIT_SCHEDULE"
        target_source_id = str(schedule.id)
        target_route = f"/maintenance/{ctx.amo_code}/quality/calendar/week"
        db.add(QualityAuditSourceLink(
            amo_id=ctx.amo_id,
            schedule_id=schedule.id,
            source_type="ASSURANCE_CASE",
            source_id=str(case.id),
            source_route=f"/maintenance/{ctx.amo_code}/quality?workspace=assurance&case={case.id}",
            rationale=payload.rationale.strip(),
            source_snapshot=_snapshot(case, plan),
            created_by_user_id=ctx.user_id,
            created_at=_utcnow(),
        ))
    elif payload.action_type == "MANAGEMENT_ESCALATION":
        target_source_type = target_source_type or "MANAGEMENT_REVIEW"
        target_route = target_route or f"/maintenance/{ctx.amo_code}/quality?workspace=assurance&case={case.id}"
    elif payload.action_type == "RISK_REASSESSMENT":
        target_source_type = target_source_type or "RISK"
        target_route = target_route or f"/maintenance/{ctx.amo_code}/quality?workspace=assurance&case={case.id}"
    else:
        target_source_type = target_source_type or "ASSURANCE_CASE"
        target_source_id = target_source_id or str(case.id)
        target_route = target_route or f"/maintenance/{ctx.amo_code}/quality?workspace=assurance&case={case.id}"

    row = QualityEffectivenessResponseAction(
        amo_id=ctx.amo_id,
        case_id=case.id,
        effectiveness_plan_id=plan.id,
        action_type=payload.action_type,
        status="OPEN",
        rationale=payload.rationale.strip(),
        target_source_type=target_source_type,
        target_source_id=target_source_id,
        target_route=target_route,
        schedule_id=schedule_id,
        due_date=payload.due_date,
        owner_user_id=payload.owner_user_id,
        source_snapshot=_snapshot(case, plan),
        created_by_user_id=ctx.user_id,
        created_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    snapshot = _snapshot(case, plan, row)
    row.source_snapshot = snapshot
    _add_event(db, ctx=ctx, row=row, event_type="OPENED", reason=payload.rationale, snapshot=snapshot)
    db.commit()
    loaded = db.query(QualityEffectivenessResponseAction).options(selectinload(QualityEffectivenessResponseAction.events)).filter(QualityEffectivenessResponseAction.id == row.id).one()
    result = _action_dict(loaded)
    if schedule is not None:
        result["planner_schedule"] = schedule.model_dump(mode="json")
    return result


@router.post("/assurance-cases/{case_id}/effectiveness-responses/{response_id}/decision")
def decide_effectiveness_response(
    case_id: str,
    response_id: str,
    payload: EffectivenessResponseDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityEffectivenessResponseAction).options(selectinload(QualityEffectivenessResponseAction.events)).filter(
        QualityEffectivenessResponseAction.amo_id == ctx.amo_id,
        QualityEffectivenessResponseAction.case_id == case_id,
        QualityEffectivenessResponseAction.id == response_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Effectiveness response action not found.")
    if row.status != "OPEN":
        raise HTTPException(status_code=409, detail="Only an OPEN effectiveness response action may be completed or cancelled.")
    case = db.query(QualityAssuranceCase).filter(QualityAssuranceCase.amo_id == ctx.amo_id, QualityAssuranceCase.id == case_id).first()
    plan = db.query(QualityEffectivenessPlan).filter(QualityEffectivenessPlan.amo_id == ctx.amo_id, QualityEffectivenessPlan.id == row.effectiveness_plan_id).first()
    if case is None or plan is None:
        raise HTTPException(status_code=409, detail="Effectiveness response lineage is incomplete.")
    row.status = "COMPLETED" if payload.decision == "COMPLETE" else "CANCELLED"
    row.completed_by_user_id = ctx.user_id
    row.completed_at = _utcnow()
    row.completion_reason = payload.reason.strip()
    snapshot = _snapshot(case, plan, row)
    _add_event(db, ctx=ctx, row=row, event_type=row.status, reason=payload.reason, snapshot=snapshot)
    db.commit()
    db.refresh(row)
    return _action_dict(row)
