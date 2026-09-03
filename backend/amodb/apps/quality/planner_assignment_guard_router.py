from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from . import models as quality_models
from .audit_assignment_guard import evaluate_auditor_assignment, evaluate_schedule_auditors
from .people_default_rules import ensure_default_quality_privilege_rules
from .audit_programme_schedule_router import _schedule_programme_requirement
from .planner_schedule_router import (
    PlannerAuditScheduleCreate,
    PlannerAuditScheduleResponse,
    PlannerAuditScheduleStateUpdate,
    _change_schedule_state,
    _create_planner_audit_schedule,
)
from .tenant_security import TenantContext, assert_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality governed auditor assignment"])

AssignmentRole = Literal["LEAD_AUDITOR", "OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"]
ContextType = Literal["AUDIT", "AUDIT_SCHEDULE", "PROGRAMME_ITEM", "ASSURANCE_CASE", "MISSION", "OTHER"]


class AuditorEligibilityPreflight(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    assignment_role: AssignmentRole
    assignment_date: date
    assignment_scope_key: str | None = Field(default=None, max_length=255)
    context_type: ContextType | None = None
    context_id: str | None = Field(default=None, max_length=160)
    enforce_independence: bool = True
    exclude_schedule_id: str | None = Field(default=None, max_length=64)


def _raise_assignment_blocked(*, result: dict, operation: str) -> None:
    if result.get("eligible"):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": f"{operation} is blocked by governed auditor eligibility requirements.",
            "assignment_gate": result,
            "required_action": "Resolve the failed People & Privileges hard gates before continuing.",
        },
    )


def _preflight_payload_auditors(
    db: Session,
    *,
    amo_id: str,
    payload: PlannerAuditScheduleCreate,
    context_type: str | None,
    context_id: str | None,
    enforce_independence: bool,
) -> list[dict]:
    assignments = [
        ("LEAD_AUDITOR", payload.lead_auditor_user_id),
        ("OBSERVER_AUDITOR", payload.observer_auditor_user_id),
        ("ASSISTANT_AUDITOR", payload.assistant_auditor_user_id),
    ]
    results: list[dict] = []
    for role, user_id in assignments:
        if not user_id:
            continue
        result = evaluate_auditor_assignment(
            db,
            amo_id=amo_id,
            user_id=str(user_id),
            assignment_role=role,
            as_of=payload.next_due_date,
            assignment_scope_key=payload.audit_scope_code,
            context_type=context_type,
            context_id=context_id,
            enforce_independence=enforce_independence,
        )
        _raise_assignment_blocked(result=result, operation="Audit scheduling")
        results.append(result)
    return results


@router.post("/integrations/calendar/auditor-eligibility")
def auditor_eligibility_preflight(
    payload: AuditorEligibilityPreflight,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    ensure_default_quality_privilege_rules(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    db.flush()
    result = evaluate_auditor_assignment(
        db,
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        assignment_role=payload.assignment_role,
        as_of=payload.assignment_date,
        assignment_scope_key=payload.assignment_scope_key,
        context_type=payload.context_type,
        context_id=payload.context_id,
        enforce_independence=payload.enforce_independence,
        exclude_schedule_id=payload.exclude_schedule_id,
    )
    db.commit()
    return result


def _create_guarded_planner_audit_schedule(
    payload: PlannerAuditScheduleCreate,
    request: Request,
    ctx: TenantContext,
    db: Session,
    *,
    commit: bool,
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    assessments = _preflight_payload_auditors(
        db,
        amo_id=ctx.amo_id,
        payload=payload,
        context_type=None,
        context_id=None,
        enforce_independence=False,
    )
    governed_pending = [
        result
        for result in assessments
        if result.get("governance_configured") and result.get("independence_pending")
    ]
    if payload.automation_active and governed_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Active audit scheduling is blocked until required auditor independence declarations can be tied to the schedule.",
                "assignment_gate": governed_pending,
                "required_action": "Create the schedule with automation_active=false, record each required AUDIT_SCHEDULE independence declaration using the returned schedule ID, then resume the schedule. Resume is hard-gated and rechecks privilege, training, scope, capacity and independence.",
            },
        )
    return _create_planner_audit_schedule(
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
        commit=commit,
    )


@router.post(
    "/integrations/calendar/audit-schedules",
    response_model=PlannerAuditScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_guarded_planner_audit_schedule(
    payload: PlannerAuditScheduleCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    return _create_guarded_planner_audit_schedule(
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
        commit=True,
    )


@router.post(
    "/integrations/calendar/audit-schedules/{schedule_id}/resume",
    response_model=PlannerAuditScheduleResponse,
)
def resume_guarded_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    schedule = db.query(quality_models.QMSAuditSchedule).filter(
        quality_models.QMSAuditSchedule.amo_id == ctx.amo_id,
        quality_models.QMSAuditSchedule.id == schedule_id,
        quality_models.QMSAuditSchedule.deleted_at.is_(None),
    ).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
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
    _raise_assignment_blocked(result=gate, operation="Schedule activation")
    return _change_schedule_state(
        schedule_id=schedule_id,
        active=True,
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
    )


@router.post(
    "/audit-programmes/{programme_id}/items/{item_id}/schedule",
    response_model=PlannerAuditScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_guarded_programme_requirement(
    programme_id: str,
    item_id: str,
    payload: PlannerAuditScheduleCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _preflight_payload_auditors(
        db,
        amo_id=ctx.amo_id,
        payload=payload,
        context_type="PROGRAMME_ITEM",
        context_id=item_id,
        enforce_independence=True,
    )
    return _schedule_programme_requirement(
        programme_id=programme_id,
        item_id=item_id,
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
    )
