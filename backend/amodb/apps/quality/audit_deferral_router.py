from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from .audit_deferral_models import QualityAuditDeferral, QualityAuditDeferralEvent
from .audit_programme_models import QualityAuditProgramme, QualityAuditProgrammeItem, QualityAuditUniverseItem
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit deferral governance"])
RiskRating = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DeferralDecision = Literal["APPROVE", "REJECT", "WITHDRAW"]


class DeferralCreate(BaseModel):
    programme_item_id: str = Field(min_length=1, max_length=36)
    revised_target_start: date
    revised_target_end: date | None = None
    reason: str = Field(min_length=8, max_length=4000)
    risk_rating: RiskRating
    risk_assessment: str = Field(min_length=8, max_length=8000)
    mitigations: list[dict[str, Any] | str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "DeferralCreate":
        if self.revised_target_end and self.revised_target_end < self.revised_target_start:
            raise ValueError("Revised target end cannot be before revised target start.")
        return self


class DeferralDecisionPayload(BaseModel):
    decision: DeferralDecision
    reason: str = Field(min_length=8, max_length=4000)


class DeferralApply(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(row: QualityAuditDeferral) -> dict[str, Any]:
    return {
        "status": row.status,
        "programme_id": row.programme_id,
        "programme_item_id": row.programme_item_id,
        "original_target_start": row.original_target_start.isoformat() if row.original_target_start else None,
        "original_target_end": row.original_target_end.isoformat() if row.original_target_end else None,
        "revised_target_start": row.revised_target_start.isoformat(),
        "revised_target_end": row.revised_target_end.isoformat() if row.revised_target_end else None,
        "risk_rating": row.risk_rating,
        "approval_required": row.approval_required,
        "repeated_deferral_count": row.repeated_deferral_count,
    }


def _event_dict(row: QualityAuditDeferralEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "snapshot": row.snapshot or {},
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _dict(row: QualityAuditDeferral) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "programme_id": row.programme_id,
        "programme_item_id": row.programme_item_id,
        "original_target_start": row.original_target_start,
        "original_target_end": row.original_target_end,
        "revised_target_start": row.revised_target_start,
        "revised_target_end": row.revised_target_end,
        "reason": row.reason,
        "risk_rating": row.risk_rating,
        "risk_assessment": row.risk_assessment,
        "mitigations": row.mitigations or [],
        "approval_required": row.approval_required,
        "repeated_deferral_count": row.repeated_deferral_count,
        "status": row.status,
        "requested_by_user_id": row.requested_by_user_id,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_reason": row.decision_reason,
        "applied_by_user_id": row.applied_by_user_id,
        "applied_at": row.applied_at,
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


def _add_event(db: Session, *, ctx: TenantContext, row: QualityAuditDeferral, event_type: str, reason: str) -> None:
    db.add(QualityAuditDeferralEvent(
        amo_id=ctx.amo_id,
        programme_item_id=row.programme_item_id,
        deferral_id=row.id,
        event_type=event_type,
        reason=reason.strip(),
        snapshot=_snapshot(row),
        actor_user_id=ctx.user_id,
    ))


def _load_item(db: Session, *, amo_id: str, item_id: str, lock: bool = False) -> tuple[QualityAuditProgramme, QualityAuditProgrammeItem, QualityAuditUniverseItem]:
    item_query = db.query(QualityAuditProgrammeItem).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
        QualityAuditProgrammeItem.id == item_id,
    )
    if lock:
        item_query = item_query.with_for_update()
    item = item_query.first()
    if item is None:
        raise HTTPException(status_code=404, detail="Audit programme requirement not found.")
    programme = db.query(QualityAuditProgramme).filter(
        QualityAuditProgramme.amo_id == amo_id,
        QualityAuditProgramme.id == item.programme_id,
    ).first()
    universe = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == amo_id,
        QualityAuditUniverseItem.id == item.universe_item_id,
    ).first()
    if programme is None or universe is None:
        raise HTTPException(status_code=409, detail="Programme requirement lineage is incomplete.")
    return programme, item, universe


def _approval_required(*, item: QualityAuditProgrammeItem, universe: QualityAuditUniverseItem, risk_rating: str, repeat_count: int) -> bool:
    return bool(
        item.mandatory_surveillance
        or universe.mandatory_surveillance
        or universe.risk_classification in {"HIGH", "CRITICAL"}
        or universe.regulatory_criticality in {"HIGH", "CRITICAL"}
        or risk_rating in {"HIGH", "CRITICAL"}
        or repeat_count > 0
    )


@router.get("/audit-deferrals")
def list_deferrals(
    programme_item_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuditDeferral).options(selectinload(QualityAuditDeferral.events)).filter(QualityAuditDeferral.amo_id == ctx.amo_id)
    if programme_item_id:
        query = query.filter(QualityAuditDeferral.programme_item_id == programme_item_id)
    rows = query.order_by(QualityAuditDeferral.requested_at.desc()).limit(250).all()
    return {"items": [_dict(row) for row in rows]}


@router.post("/audit-deferrals", status_code=status.HTTP_201_CREATED)
def request_deferral(
    payload: DeferralCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme, item, universe = _load_item(db, amo_id=ctx.amo_id, item_id=payload.programme_item_id, lock=True)
    if programme.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(status_code=409, detail="Only an APPROVED or ACTIVE programme requirement may be deferred.")
    if item.schedule_id is not None or item.state == "SCHEDULED":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This requirement is already linked to the authoritative Planner.",
                "schedule_id": str(item.schedule_id) if item.schedule_id else None,
                "required_action": "Use the versioned Planner reschedule workflow so conflict validation, notifications and schedule history remain authoritative.",
            },
        )
    if item.state not in {"PLANNED", "DEFERRED"}:
        raise HTTPException(status_code=409, detail=f"Programme requirement in state {item.state} cannot be deferred.")
    revised_end = payload.revised_target_end or payload.revised_target_start
    if payload.revised_target_start < programme.period_start or revised_end > programme.period_end:
        raise HTTPException(status_code=422, detail="Revised target dates must remain inside the approved programme period. Amend the programme if the requirement must move outside it.")
    if item.target_start and payload.revised_target_start <= item.target_start:
        raise HTTPException(status_code=422, detail="A deferral must move the target start later than the current governed target start.")

    open_request = db.query(QualityAuditDeferral.id).filter(
        QualityAuditDeferral.amo_id == ctx.amo_id,
        QualityAuditDeferral.programme_item_id == item.id,
        QualityAuditDeferral.status.in_(["REQUESTED", "APPROVED"]),
    ).first()
    if open_request is not None:
        raise HTTPException(status_code=409, detail="An unapplied deferral request already exists for this programme requirement.")
    repeat_count = db.query(QualityAuditDeferral.id).filter(
        QualityAuditDeferral.amo_id == ctx.amo_id,
        QualityAuditDeferral.programme_item_id == item.id,
        QualityAuditDeferral.status == "APPLIED",
    ).count()

    row = QualityAuditDeferral(
        amo_id=ctx.amo_id,
        programme_id=programme.id,
        programme_item_id=item.id,
        original_target_start=item.target_start,
        original_target_end=item.target_end,
        revised_target_start=payload.revised_target_start,
        revised_target_end=revised_end,
        reason=payload.reason.strip(),
        risk_rating=payload.risk_rating,
        risk_assessment=payload.risk_assessment.strip(),
        mitigations=list(payload.mitigations),
        approval_required=_approval_required(item=item, universe=universe, risk_rating=payload.risk_rating, repeat_count=repeat_count),
        repeated_deferral_count=repeat_count,
        status="REQUESTED",
        requested_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, ctx=ctx, row=row, event_type="REQUESTED", reason=payload.reason)
    db.commit()
    loaded = db.query(QualityAuditDeferral).options(selectinload(QualityAuditDeferral.events)).filter(
        QualityAuditDeferral.amo_id == ctx.amo_id,
        QualityAuditDeferral.id == row.id,
    ).one()
    return _dict(loaded)


@router.post("/audit-deferrals/{deferral_id}/decision")
def decide_deferral(
    deferral_id: str,
    payload: DeferralDecisionPayload,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditDeferral).options(selectinload(QualityAuditDeferral.events)).filter(
        QualityAuditDeferral.amo_id == ctx.amo_id,
        QualityAuditDeferral.id == deferral_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit deferral not found.")
    if row.status != "REQUESTED":
        raise HTTPException(status_code=409, detail="Only a REQUESTED deferral may receive a decision.")
    if payload.decision == "WITHDRAW":
        if row.requested_by_user_id and str(row.requested_by_user_id) != str(ctx.user_id):
            raise HTTPException(status_code=403, detail="Only the requester may withdraw this deferral.")
        row.status = "WITHDRAWN"
        event = "WITHDRAWN"
    elif payload.decision == "APPROVE":
        if row.requested_by_user_id and str(row.requested_by_user_id) == str(ctx.user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The requester cannot approve their own audit deferral.",
            )
        row.status = "APPROVED"
        event = "APPROVED"
    else:
        row.status = "REJECTED"
        event = "REJECTED"
    row.decided_by_user_id = ctx.user_id
    row.decided_at = _utcnow()
    row.decision_reason = payload.reason.strip()
    _add_event(db, ctx=ctx, row=row, event_type=event, reason=payload.reason)
    db.commit()
    db.refresh(row)
    return _dict(row)


@router.post("/audit-deferrals/{deferral_id}/apply")
def apply_deferral(
    deferral_id: str,
    payload: DeferralApply,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditDeferral).options(selectinload(QualityAuditDeferral.events)).filter(
        QualityAuditDeferral.amo_id == ctx.amo_id,
        QualityAuditDeferral.id == deferral_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit deferral not found.")
    allowed = row.status == "APPROVED" or (row.status == "REQUESTED" and not row.approval_required)
    if not allowed:
        raise HTTPException(status_code=409, detail="This deferral requires approval before the revised target window can be applied.")
    programme, item, _ = _load_item(db, amo_id=ctx.amo_id, item_id=row.programme_item_id, lock=True)
    if programme.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The programme revision is no longer active for deferral application.",
        )
    if item.schedule_id is not None or item.state == "SCHEDULED":
        raise HTTPException(status_code=409, detail="The requirement became scheduled while the deferral was pending. Use the authoritative Planner reschedule workflow instead.")
    revised_end = row.revised_target_end or row.revised_target_start
    if row.revised_target_start < programme.period_start or revised_end > programme.period_end:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approved programme period changed and no longer contains this deferral window. Create a new request against the current revision.",
        )
    current_start = item.target_start.isoformat() if item.target_start else None
    current_end = item.target_end.isoformat() if item.target_end else None
    expected_start = row.original_target_start.isoformat() if row.original_target_start else None
    expected_end = row.original_target_end.isoformat() if row.original_target_end else None
    if current_start != expected_start or current_end != expected_end:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Programme requirement dates changed after this deferral was requested.",
                "requested_against": {"start": expected_start, "end": expected_end},
                "current": {"start": current_start, "end": current_end},
                "required_action": "Withdraw this stale request and create a new deferral against the current requirement.",
            },
        )
    item.target_start = row.revised_target_start
    item.target_end = revised_end
    item.deferral_reason = row.reason
    item.state = "DEFERRED"
    item.updated_by_user_id = ctx.user_id
    item.updated_at = _utcnow()
    row.status = "APPLIED"
    row.applied_by_user_id = ctx.user_id
    row.applied_at = _utcnow()
    _add_event(db, ctx=ctx, row=row, event_type="APPLIED", reason=payload.reason)
    db.commit()
    db.refresh(row)
    return _dict(row)
