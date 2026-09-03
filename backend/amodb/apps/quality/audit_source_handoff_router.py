from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from .audit_source_link_models import QualityAuditSourceLink
from .intelligence_models import QualitySignalObservation, QualitySignalRule
from .mission_models import QualityMission
from .planner_assignment_guard_router import _create_guarded_planner_audit_schedule
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .planner_schedule_router import PlannerAuditScheduleCreate, PlannerAuditScheduleResponse
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context

router = APIRouter(tags=["Quality audit source handoffs"])


class AuditHandoffCreate(BaseModel):
    rationale: str = Field(min_length=8, max_length=4000)
    schedule: PlannerAuditScheduleCreate


def _link_dict(row: QualityAuditSourceLink) -> dict[str, Any]:
    return {
        "id": str(row.id), "schedule_id": str(row.schedule_id), "source_type": row.source_type,
        "source_id": row.source_id, "source_route": row.source_route, "rationale": row.rationale,
        "source_snapshot": row.source_snapshot or {}, "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


def _record_link(db: Session, *, ctx: TenantContext, schedule_id: str, source_type: str, source_id: str,
                 source_route: str, rationale: str, source_snapshot: dict[str, Any]) -> None:
    db.add(QualityAuditSourceLink(
        amo_id=ctx.amo_id, schedule_id=uuid.UUID(schedule_id), source_type=source_type,
        source_id=source_id, source_route=source_route, rationale=rationale.strip(),
        source_snapshot=source_snapshot, created_by_user_id=ctx.user_id,
    ))
    db.flush()


def _mission_snapshot(mission: QualityMission) -> dict[str, Any]:
    gates = list(mission.gates or [])
    hard = [gate for gate in gates if gate.gate_type == "HARD"]
    return {
        "mission_id": str(mission.id), "mission_ref": mission.mission_ref,
        "mission_type": mission.mission_type, "title": mission.title, "status": mission.status,
        "risk_level": mission.risk_level,
        "hard_gates": {"passed": sum(1 for gate in hard if gate.status == "PASS"), "total": len(hard)},
    }


def _signal_snapshot(signal: QualitySignalObservation, rule: QualitySignalRule | None) -> dict[str, Any]:
    return {
        "signal_id": str(signal.id), "rule_id": str(signal.rule_id),
        "rule_code": rule.rule_code if rule else None, "metric": signal.metric,
        "observed_value": str(signal.observed_value), "threshold": str(signal.threshold),
        "operator": signal.operator, "triggered": signal.triggered, "severity": signal.severity,
        "explanation": signal.explanation, "source_snapshot": signal.source_snapshot or {},
        "source_references": signal.source_references or [], "state": signal.state,
    }


@router.get("/audit-source-links")
def list_audit_source_links(
    schedule_id: uuid.UUID | None = Query(default=None),
    audit_id: uuid.UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    resolved = schedule_id
    if audit_id is not None:
        occurrence = db.query(QMSPlannerScheduleMetadata).filter(
            QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
            QMSPlannerScheduleMetadata.audit_id == audit_id,
        ).first()
        resolved = occurrence.source_schedule_id if occurrence else None
    query = db.query(QualityAuditSourceLink).filter(QualityAuditSourceLink.amo_id == ctx.amo_id)
    if resolved is not None:
        query = query.filter(QualityAuditSourceLink.schedule_id == resolved)
    rows = query.order_by(QualityAuditSourceLink.created_at.asc()).limit(250).all()
    return {"items": [_link_dict(row) for row in rows], "schedule_id": str(resolved) if resolved else None}


@router.post("/missions/{mission_id}/audit-handoffs", response_model=PlannerAuditScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_mission_audit_handoff(
    mission_id: str, payload: AuditHandoffCreate, request: Request,
    ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = db.query(QualityMission).options(selectinload(QualityMission.gates)).filter(
        QualityMission.amo_id == ctx.amo_id, QualityMission.id == mission_id,
    ).first()
    if mission is None:
        raise HTTPException(status_code=404, detail="Quality Mission not found.")
    if mission.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="A cancelled Mission cannot generate an audit handoff.")
    schedule = _create_guarded_planner_audit_schedule(
        payload=payload.schedule,
        request=request,
        ctx=ctx,
        db=db,
        commit=False,
    )
    _record_link(
        db, ctx=ctx, schedule_id=str(schedule.id), source_type="MISSION", source_id=str(mission.id),
        source_route=f"/maintenance/{ctx.amo_code}/quality?workspace=missions&mission={mission.id}",
        rationale=payload.rationale, source_snapshot=_mission_snapshot(mission),
    )
    db.commit()
    return schedule


@router.post("/intelligence/signals/{signal_id}/audit-handoffs", response_model=PlannerAuditScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_signal_audit_handoff(
    signal_id: str, payload: AuditHandoffCreate, request: Request,
    ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    signal = db.query(QualitySignalObservation).filter(
        QualitySignalObservation.amo_id == ctx.amo_id, QualitySignalObservation.id == signal_id,
    ).first()
    if signal is None:
        raise HTTPException(status_code=404, detail="Quality intelligence signal not found.")
    if not signal.triggered or signal.state == "CLOSED":
        raise HTTPException(status_code=409, detail="Only an open triggered signal may generate a targeted audit handoff.")
    rule = db.query(QualitySignalRule).filter(
        QualitySignalRule.amo_id == ctx.amo_id, QualitySignalRule.id == signal.rule_id,
    ).first()
    schedule = _create_guarded_planner_audit_schedule(
        payload=payload.schedule,
        request=request,
        ctx=ctx,
        db=db,
        commit=False,
    )
    _record_link(
        db, ctx=ctx, schedule_id=str(schedule.id), source_type="SIGNAL", source_id=str(signal.id),
        source_route=f"/maintenance/{ctx.amo_code}/quality?workspace=intelligence&signal={signal.id}",
        rationale=payload.rationale, source_snapshot=_signal_snapshot(signal, rule),
    )
    db.commit()
    return schedule
