from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from .audit_programme_models import (
    QualityAuditProgramme,
    QualityAuditProgrammeEvent,
    QualityAuditProgrammeItem,
    QualityAuditUniverseItem,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/audit-programmes", tags=["Quality audit programme"])

ProgrammeStatus = Literal["DRAFT", "UNDER_REVIEW", "APPROVED", "ACTIVE", "SUPERSEDED", "CLOSED"]
ProgrammeMethodology = Literal["COMPLIANCE", "PERFORMANCE", "RISK"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
EntityType = Literal[
    "DEPARTMENT", "FACILITY", "STATION", "SUPPLIER", "CONTRACTOR", "PROCESS",
    "CAPABILITY", "APPROVAL_RATING", "AIRCRAFT_TYPE", "PERSONNEL_GROUP", "OTHER",
]
AuditType = Literal[
    "INTERNAL", "DEPARTMENTAL", "TECHNICAL", "WORK_PACK", "SUPPLIER", "CONTRACTED_FUNCTION",
    "FACILITY", "PERSONNEL", "PRODUCT", "PROCESS", "REGULATORY", "SPECIAL", "REACTIVE", "FOLLOW_UP",
]
Recurrence = Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "CUSTOM", "RISK_TRIGGERED"]
ProgrammeItemState = Literal["PLANNED", "SCHEDULED", "COMPLETED", "DEFERRED", "CANCELLED", "FOLLOW_UP_REQUIRED"]


class ProgrammeCreate(BaseModel):
    programme_year: int = Field(ge=2000, le=2200)
    title: str = Field(min_length=3, max_length=255)
    programme_methodology: ProgrammeMethodology = "COMPLIANCE"
    methodology_rationale: str | None = Field(default=None, max_length=4000)
    objectives: list[str] = Field(default_factory=list)
    regulatory_basis: list[str | dict[str, Any]] = Field(default_factory=list)
    period_start: date
    period_end: date
    owner_user_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ProgrammePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    programme_methodology: ProgrammeMethodology | None = None
    methodology_rationale: str | None = Field(default=None, max_length=4000)
    objectives: list[str] | None = None
    regulatory_basis: list[str | dict[str, Any]] | None = None
    period_start: date | None = None
    period_end: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    reason: str = Field(min_length=3)


class ProgrammeTransition(BaseModel):
    target_status: ProgrammeStatus
    reason: str = Field(min_length=3)


class ProgrammeAmendment(BaseModel):
    reason: str = Field(min_length=3)
    title: str | None = Field(default=None, min_length=3, max_length=255)


class UniverseCreate(BaseModel):
    entity_type: EntityType
    display_label: str = Field(min_length=2, max_length=255)
    source_owner_module: str = Field(min_length=2, max_length=80)
    source_type: str = Field(min_length=2, max_length=64)
    source_id: str = Field(min_length=1, max_length=160)
    source_route: str | None = Field(default=None, max_length=500)
    risk_classification: RiskLevel = "MEDIUM"
    regulatory_criticality: RiskLevel = "MEDIUM"
    surveillance_interval_days: int | None = Field(default=None, ge=1, le=3650)
    mandatory_surveillance: bool = False
    notes: str | None = None


class UniversePatch(BaseModel):
    display_label: str | None = Field(default=None, min_length=2, max_length=255)
    source_route: str | None = Field(default=None, max_length=500)
    risk_classification: RiskLevel | None = None
    regulatory_criticality: RiskLevel | None = None
    surveillance_interval_days: int | None = Field(default=None, ge=1, le=3650)
    mandatory_surveillance: bool | None = None
    active: bool | None = None
    notes: str | None = None


class ProgrammeItemCreate(BaseModel):
    universe_item_id: str = Field(max_length=36)
    audit_type: AuditType
    title: str = Field(min_length=3, max_length=255)
    purpose: str | None = None
    scope: str = Field(min_length=3)
    criteria: list[str | dict[str, Any]] = Field(default_factory=list)
    mandatory_surveillance: bool = False
    recurrence: Recurrence = "ONE_TIME"
    custom_interval_days: int | None = Field(default=None, ge=1, le=3650)
    target_start: date | None = None
    target_end: date | None = None
    prioritization_basis: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.target_start and self.target_end and self.target_end < self.target_start:
            raise ValueError("target_end must be on or after target_start")
        if self.recurrence == "CUSTOM" and not self.custom_interval_days:
            raise ValueError("CUSTOM recurrence requires custom_interval_days")
        return self


class ProgrammeItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    purpose: str | None = None
    scope: str | None = Field(default=None, min_length=3)
    criteria: list[str | dict[str, Any]] | None = None
    mandatory_surveillance: bool | None = None
    recurrence: Recurrence | None = None
    custom_interval_days: int | None = Field(default=None, ge=1, le=3650)
    target_start: date | None = None
    target_end: date | None = None
    prioritization_basis: list[dict[str, Any]] | None = None
    state: ProgrammeItemState | None = None
    deferral_reason: str | None = None
    cancellation_reason: str | None = None
    reason: str = Field(min_length=3)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _programme_ref(year: int, revision: int) -> tuple[str, str]:
    series = f"AP-{year}-{uuid.uuid4().hex[:8].upper()}"
    return f"{series}-R{revision:02d}", series


def _universe_dict(item: QualityAuditUniverseItem) -> dict[str, Any]:
    return {
        "id": str(item.id), "entity_type": item.entity_type, "display_label": item.display_label,
        "source_owner_module": item.source_owner_module, "source_type": item.source_type,
        "source_id": item.source_id, "source_route": item.source_route,
        "risk_classification": item.risk_classification,
        "regulatory_criticality": item.regulatory_criticality,
        "surveillance_interval_days": item.surveillance_interval_days,
        "mandatory_surveillance": item.mandatory_surveillance, "active": item.active,
        "notes": item.notes, "created_at": item.created_at, "updated_at": item.updated_at,
    }


def _item_dict(item: QualityAuditProgrammeItem) -> dict[str, Any]:
    return {
        "id": str(item.id), "programme_id": str(item.programme_id),
        "universe_item_id": str(item.universe_item_id), "audit_type": item.audit_type,
        "title": item.title, "purpose": item.purpose, "scope": item.scope, "criteria": item.criteria,
        "mandatory_surveillance": item.mandatory_surveillance, "recurrence": item.recurrence,
        "custom_interval_days": item.custom_interval_days, "target_start": item.target_start,
        "target_end": item.target_end, "state": item.state,
        "prioritization_basis": item.prioritization_basis,
        "deferral_reason": item.deferral_reason, "cancellation_reason": item.cancellation_reason,
        "auditable_entity": _universe_dict(item.universe_item) if item.universe_item else None,
        "created_at": item.created_at, "updated_at": item.updated_at,
    }


def _programme_snapshot(programme: QualityAuditProgramme) -> dict[str, Any]:
    return {
        "id": str(programme.id), "programme_ref": programme.programme_ref,
        "programme_series": programme.programme_series, "programme_year": programme.programme_year,
        "revision_no": programme.revision_no, "title": programme.title,
        "programme_methodology": programme.programme_methodology,
        "methodology_rationale": programme.methodology_rationale,
        "objectives": programme.objectives, "regulatory_basis": programme.regulatory_basis,
        "status": programme.status, "period_start": programme.period_start.isoformat(),
        "period_end": programme.period_end.isoformat(), "owner_user_id": programme.owner_user_id,
        "supersedes_programme_id": programme.supersedes_programme_id,
    }


def _programme_readiness(programme: QualityAuditProgramme) -> dict[str, Any]:
    items = list(programme.items or [])
    blockers: list[dict[str, str]] = []
    if not items:
        blockers.append({"code": "NO_REQUIREMENTS", "message": "Add at least one governed audit requirement before approval."})
    if programme.programme_methodology == "COMPLIANCE" and not list(programme.regulatory_basis or []):
        blockers.append({"code": "NO_COMPLIANCE_BASIS", "message": "Compliance-based programmes require at least one regulatory, standard or manual basis."})
    for item in items:
        if not item.target_start or not item.target_end:
            blockers.append({"code": "MISSING_TARGET_WINDOW", "message": f"{item.title}: set a target start and end window."})
        elif item.target_start < programme.period_start or item.target_end > programme.period_end:
            blockers.append({"code": "OUTSIDE_PROGRAMME_PERIOD", "message": f"{item.title}: target window must remain inside the programme period."})
        if not list(item.criteria or []):
            blockers.append({"code": "MISSING_CRITERIA", "message": f"{item.title}: add the audit criteria before approval."})
    mandatory = [item for item in items if item.mandatory_surveillance]
    high_risk = [
        item for item in items
        if item.universe_item and item.universe_item.risk_classification in {"HIGH", "CRITICAL"}
    ]
    return {
        "ready_for_approval": not blockers,
        "blockers": blockers,
        "requirement_count": len(items),
        "mandatory_requirement_count": len(mandatory),
        "mandatory_unscheduled_count": sum(1 for item in mandatory if item.state == "PLANNED"),
        "high_risk_requirement_count": len(high_risk),
        "unscheduled_requirement_count": sum(1 for item in items if item.state == "PLANNED"),
    }


def _programme_dict(programme: QualityAuditProgramme, *, detail: bool = False) -> dict[str, Any]:
    items = list(programme.items or [])
    counts = {state: 0 for state in ["PLANNED", "SCHEDULED", "COMPLETED", "DEFERRED", "CANCELLED", "FOLLOW_UP_REQUIRED"]}
    for item in items:
        counts[item.state] = counts.get(item.state, 0) + 1
    result: dict[str, Any] = {
        **_programme_snapshot(programme),
        "owner_user_id": programme.owner_user_id,
        "approved_by_user_id": programme.approved_by_user_id, "approved_at": programme.approved_at,
        "activated_at": programme.activated_at, "closed_at": programme.closed_at,
        "created_at": programme.created_at, "updated_at": programme.updated_at,
        "metrics": {
            "planned_audit_count": len(items), "completed_audit_count": counts["COMPLETED"],
            "deferred_audit_count": counts["DEFERRED"], "cancelled_audit_count": counts["CANCELLED"],
            "follow_up_audit_count": counts["FOLLOW_UP_REQUIRED"], "scheduled_audit_count": counts["SCHEDULED"],
            "unscheduled_audit_count": counts["PLANNED"],
        },
        "readiness": _programme_readiness(programme),
    }
    if detail:
        result["items"] = [_item_dict(item) for item in items]
        result["events"] = [
            {"id": str(event.id), "event_type": event.event_type, "reason": event.reason,
             "before_snapshot": event.before_snapshot, "after_snapshot": event.after_snapshot,
             "actor_user_id": event.actor_user_id, "created_at": event.created_at}
            for event in list(programme.events or [])
        ]
    return result


def _query(db: Session, amo_id: str):
    return db.query(QualityAuditProgramme).filter(QualityAuditProgramme.amo_id == amo_id)


def _load_programme(db: Session, amo_id: str, programme_id: str, *, for_update: bool = False) -> QualityAuditProgramme:
    query = (_query(db, amo_id)
             .options(selectinload(QualityAuditProgramme.items).selectinload(QualityAuditProgrammeItem.universe_item),
                      selectinload(QualityAuditProgramme.events))
             .filter(QualityAuditProgramme.id == programme_id))
    if for_update:
        query = query.with_for_update()
    programme = query.first()
    if not programme:
        raise HTTPException(status_code=404, detail="Audit programme not found.")
    return programme


def _event(db: Session, programme: QualityAuditProgramme, ctx: TenantContext, event_type: str, reason: str,
           before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    db.add(QualityAuditProgrammeEvent(
        amo_id=ctx.amo_id, programme_id=programme.id, event_type=event_type, reason=reason.strip(),
        before_snapshot=before, after_snapshot=after, actor_user_id=ctx.user_id, created_at=_utcnow(),
    ))


def _assert_editable(programme: QualityAuditProgramme) -> None:
    if programme.status not in {"DRAFT", "UNDER_REVIEW"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Approved or active programme revisions are immutable. Create an amendment revision instead.")


def _validate_item_window(programme: QualityAuditProgramme, start: date | None, end: date | None) -> None:
    if start and start < programme.period_start:
        raise HTTPException(status_code=422, detail="target_start must be inside the audit programme period")
    if end and end > programme.period_end:
        raise HTTPException(status_code=422, detail="target_end must be inside the audit programme period")


@router.get("")
def list_programmes(
    year: int | None = Query(default=None, ge=2000, le=2200),
    status_filter: ProgrammeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = _query(db, ctx.amo_id).options(
        selectinload(QualityAuditProgramme.items).selectinload(QualityAuditProgrammeItem.universe_item)
    )
    if year is not None: query = query.filter(QualityAuditProgramme.programme_year == year)
    if status_filter: query = query.filter(QualityAuditProgramme.status == status_filter)
    total = int(query.order_by(None).count())
    rows = query.order_by(QualityAuditProgramme.programme_year.desc(), QualityAuditProgramme.revision_no.desc()).offset(offset).limit(limit).all()
    return {"items": [_programme_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_programme(payload: ProgrammeCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    ref, series = _programme_ref(payload.programme_year, 1); now = _utcnow()
    row = QualityAuditProgramme(
        amo_id=ctx.amo_id, programme_ref=ref, programme_series=series, programme_year=payload.programme_year,
        revision_no=1, title=payload.title.strip(), programme_methodology=payload.programme_methodology,
        methodology_rationale=payload.methodology_rationale.strip() if payload.methodology_rationale else None,
        objectives=payload.objectives, regulatory_basis=payload.regulatory_basis, status="DRAFT",
        period_start=payload.period_start, period_end=payload.period_end, owner_user_id=payload.owner_user_id or ctx.user_id,
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
    )
    db.add(row); db.flush(); _event(db, row, ctx, "CREATED", "Audit programme created.", None, _programme_snapshot(row)); db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, str(row.id)), detail=True)


@router.get("/{programme_id}")
def get_programme(programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


@router.patch("/{programme_id}")
def patch_programme(programme_id: str, payload: ProgrammePatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_programme(db, ctx.amo_id, programme_id, for_update=True); _assert_editable(row); before = _programme_snapshot(row)
    updates = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if "methodology_rationale" in updates and updates["methodology_rationale"] is not None:
        updates["methodology_rationale"] = updates["methodology_rationale"].strip() or None
    for field, value in updates.items(): setattr(row, field, value)
    if row.period_end < row.period_start: raise HTTPException(status_code=422, detail="period_end must be on or after period_start")
    for item in list(row.items or []):
        _validate_item_window(row, item.target_start, item.target_end)
    row.updated_by_user_id = ctx.user_id; row.updated_at = _utcnow()
    _event(db, row, ctx, "UPDATED", payload.reason, before, _programme_snapshot(row)); db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"UNDER_REVIEW"}, "UNDER_REVIEW": {"DRAFT", "APPROVED"},
    "APPROVED": {"ACTIVE", "SUPERSEDED"}, "ACTIVE": {"SUPERSEDED", "CLOSED"},
    "SUPERSEDED": set(), "CLOSED": set(),
}
_EVENT_BY_TARGET = {"UNDER_REVIEW": "SUBMITTED_FOR_REVIEW", "DRAFT": "RETURNED_TO_DRAFT", "APPROVED": "APPROVED",
                    "ACTIVE": "ACTIVATED", "SUPERSEDED": "SUPERSEDED", "CLOSED": "CLOSED"}


@router.post("/{programme_id}/transitions")
def transition_programme(programme_id: str, payload: ProgrammeTransition,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if payload.target_status not in _TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Audit programme cannot transition from {row.status} to {payload.target_status}.")
    if payload.target_status == "APPROVED":
        readiness = _programme_readiness(row)
        if not readiness["ready_for_approval"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Audit programme is not ready for approval.",
                    "blockers": readiness["blockers"],
                },
            )
    before = _programme_snapshot(row); now = _utcnow(); row.status = payload.target_status
    if row.status == "APPROVED": row.approved_by_user_id = ctx.user_id; row.approved_at = now
    if row.status == "ACTIVE": row.activated_at = now
    if row.status == "CLOSED": row.closed_at = now
    row.updated_by_user_id = ctx.user_id; row.updated_at = now
    _event(db, row, ctx, _EVENT_BY_TARGET[row.status], payload.reason, before, _programme_snapshot(row))
    if row.status == "APPROVED" and row.supersedes_programme_id:
        prior = _query(db, ctx.amo_id).filter(QualityAuditProgramme.id == row.supersedes_programme_id).with_for_update().first()
        if prior and prior.status in {"APPROVED", "ACTIVE"}:
            old_before = _programme_snapshot(prior); prior.status = "SUPERSEDED"; prior.updated_by_user_id = ctx.user_id; prior.updated_at = now
            _event(db, prior, ctx, "SUPERSEDED", f"Superseded by approved revision {row.programme_ref}.", old_before, _programme_snapshot(prior))
    db.commit(); set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


@router.post("/{programme_id}/amendments", status_code=status.HTTP_201_CREATED)
def create_amendment(programme_id: str, payload: ProgrammeAmendment,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    prior = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if prior.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(status_code=409, detail="Only APPROVED or ACTIVE programme revisions can be amended.")
    existing = _query(db, ctx.amo_id).filter(QualityAuditProgramme.programme_series == prior.programme_series).order_by(QualityAuditProgramme.revision_no.desc()).first()
    next_revision = int(existing.revision_no) + 1; now = _utcnow()
    row = QualityAuditProgramme(
        amo_id=ctx.amo_id, programme_ref=f"{prior.programme_series}-R{next_revision:02d}", programme_series=prior.programme_series,
        programme_year=prior.programme_year, revision_no=next_revision, title=(payload.title or prior.title).strip(),
        programme_methodology=prior.programme_methodology, methodology_rationale=prior.methodology_rationale,
        objectives=list(prior.objectives or []), regulatory_basis=list(prior.regulatory_basis or []), status="DRAFT",
        period_start=prior.period_start, period_end=prior.period_end, owner_user_id=prior.owner_user_id,
        supersedes_programme_id=prior.id, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
        created_at=now, updated_at=now,
    )
    db.add(row); db.flush()
    for item in list(prior.items or []):
        db.add(QualityAuditProgrammeItem(
            amo_id=ctx.amo_id, programme_id=row.id, universe_item_id=item.universe_item_id, audit_type=item.audit_type,
            title=item.title, purpose=item.purpose, scope=item.scope, criteria=list(item.criteria or []),
            mandatory_surveillance=item.mandatory_surveillance, recurrence=item.recurrence,
            custom_interval_days=item.custom_interval_days, target_start=item.target_start, target_end=item.target_end,
            state="PLANNED", prioritization_basis=list(item.prioritization_basis or []),
            created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
        ))
    _event(db, row, ctx, "AMENDMENT_CREATED", payload.reason, _programme_snapshot(prior), _programme_snapshot(row)); db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, str(row.id)), detail=True)


@router.get("/universe/items")
def list_universe(entity_type: EntityType | None = None, active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id)
    if entity_type: query = query.filter(QualityAuditUniverseItem.entity_type == entity_type)
    if active is not None: query = query.filter(QualityAuditUniverseItem.active.is_(active))
    total = int(query.order_by(None).count()); rows = query.order_by(QualityAuditUniverseItem.display_label.asc()).offset(offset).limit(limit).all()
    return {"items": [_universe_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total}


@router.post("/universe/items", status_code=status.HTTP_201_CREATED)
def create_universe_item(payload: UniverseCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    duplicate = db.query(QualityAuditUniverseItem.id).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.source_owner_module == payload.source_owner_module,
        QualityAuditUniverseItem.source_type == payload.source_type,
        QualityAuditUniverseItem.source_id == payload.source_id,
    ).first()
    if duplicate: raise HTTPException(status_code=409, detail="This authoritative source record is already in the Audit Universe.")
    now = _utcnow(); row = QualityAuditUniverseItem(
        amo_id=ctx.amo_id, **payload.model_dump(), created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
        created_at=now, updated_at=now,
    )
    db.add(row); db.commit(); db.refresh(row); return _universe_dict(row)


@router.patch("/universe/items/{universe_item_id}")
def patch_universe_item(universe_item_id: str, payload: UniversePatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.id == universe_item_id).with_for_update().first()
    if not row: raise HTTPException(status_code=404, detail="Audit Universe item not found.")
    for field, value in payload.model_dump(exclude_unset=True).items(): setattr(row, field, value)
    row.updated_by_user_id = ctx.user_id; row.updated_at = _utcnow(); db.commit(); db.refresh(row); return _universe_dict(row)


@router.post("/{programme_id}/items", status_code=status.HTTP_201_CREATED)
def add_programme_item(programme_id: str, payload: ProgrammeItemCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id, for_update=True); _assert_editable(programme)
    universe = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.id == payload.universe_item_id, QualityAuditUniverseItem.active.is_(True)).first()
    if not universe: raise HTTPException(status_code=422, detail="Select an active Audit Universe item from this tenant.")
    _validate_item_window(programme, payload.target_start, payload.target_end)
    now = _utcnow(); row = QualityAuditProgrammeItem(
        amo_id=ctx.amo_id, programme_id=programme.id, **payload.model_dump(), state="PLANNED",
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
    )
    db.add(row); db.flush(); _event(db, programme, ctx, "ITEM_ADDED", f"Added audit requirement: {row.title}", None,
        {"item_id": str(row.id), "title": row.title, "universe_item_id": str(row.universe_item_id), "audit_type": row.audit_type})
    db.commit(); set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _item_dict(db.query(QualityAuditProgrammeItem).options(selectinload(QualityAuditProgrammeItem.universe_item)).filter(
        QualityAuditProgrammeItem.amo_id == ctx.amo_id, QualityAuditProgrammeItem.id == row.id).one())


@router.patch("/{programme_id}/items/{item_id}")
def patch_programme_item(programme_id: str, item_id: str, payload: ProgrammeItemPatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id, for_update=True); _assert_editable(programme)
    row = db.query(QualityAuditProgrammeItem).filter(QualityAuditProgrammeItem.amo_id == ctx.amo_id,
        QualityAuditProgrammeItem.programme_id == programme.id, QualityAuditProgrammeItem.id == item_id).with_for_update().first()
    if not row: raise HTTPException(status_code=404, detail="Audit programme item not found.")
    before = {"title": row.title, "state": row.state, "target_start": str(row.target_start) if row.target_start else None,
              "target_end": str(row.target_end) if row.target_end else None}
    updates = payload.model_dump(exclude_unset=True, exclude={"reason"})
    candidate_state = updates.get("state", row.state)
    if candidate_state == "DEFERRED" and not str(updates.get("deferral_reason", row.deferral_reason) or "").strip():
        raise HTTPException(status_code=422, detail="Deferring an audit requirement requires a reason.")
    if candidate_state == "CANCELLED" and not str(updates.get("cancellation_reason", row.cancellation_reason) or "").strip():
        raise HTTPException(status_code=422, detail="Cancelling an audit requirement requires a reason.")
    for field, value in updates.items(): setattr(row, field, value)
    if row.target_start and row.target_end and row.target_end < row.target_start:
        raise HTTPException(status_code=422, detail="target_end must be on or after target_start")
    _validate_item_window(programme, row.target_start, row.target_end)
    if row.recurrence == "CUSTOM" and not row.custom_interval_days:
        raise HTTPException(status_code=422, detail="CUSTOM recurrence requires custom_interval_days")
    row.updated_by_user_id = ctx.user_id; row.updated_at = _utcnow()
    after = {"title": row.title, "state": row.state, "target_start": str(row.target_start) if row.target_start else None,
             "target_end": str(row.target_end) if row.target_end else None}
    _event(db, programme, ctx, "ITEM_UPDATED", payload.reason, before, after); db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _item_dict(db.query(QualityAuditProgrammeItem).options(selectinload(QualityAuditProgrammeItem.universe_item)).filter(
        QualityAuditProgrammeItem.amo_id == ctx.amo_id, QualityAuditProgrammeItem.id == row.id).one())
