from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db

from .assurance_case_models import (
    QualityAssuranceCase,
    QualityAssuranceCaseEvent,
    QualityEffectivenessPlan,
    QualityInvestigationEntry,
)
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)

router = APIRouter(prefix="/assurance-cases", tags=["Quality assurance cases"])

CaseType = Literal["SIGNAL", "INVESTIGATION", "RECURRING_FINDING", "EFFECTIVENESS", "SUPPLIER", "REGULATORY", "OTHER"]
CaseStatus = Literal["OPEN", "INVESTIGATING", "ACTION_PENDING", "EFFECTIVENESS_REVIEW", "CLOSED", "CANCELLED"]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
InvestigationMethod = Literal["FIVE_WHYS", "ISHIKAWA", "CAUSAL_FACTOR", "BARRIER_ANALYSIS", "CHANGE_ANALYSIS", "HUMAN_ORGANIZATIONAL"]
EntryType = Literal["FACT", "HYPOTHESIS", "CAUSAL_CONCLUSION"]
Conclusion = Literal["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE", "INCONCLUSIVE"]


class CaseCreate(BaseModel):
    case_type: CaseType
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    severity: Severity = "MEDIUM"
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    regulatory_basis: list[dict[str, Any] | str] = Field(default_factory=list, max_length=100)
    owner_user_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None


class CaseTransition(BaseModel):
    status: CaseStatus
    reason: str = Field(min_length=8, max_length=4000)


class InvestigationEntryCreate(BaseModel):
    method: InvestigationMethod
    entry_type: EntryType
    sequence_no: int = Field(default=1, ge=1, le=1000)
    category: str | None = Field(default=None, max_length=80)
    prompt: str | None = Field(default=None, max_length=4000)
    statement: str = Field(min_length=3, max_length=12000)
    confidence: int | None = Field(default=None, ge=0, le=100)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    parent_entry_id: str | None = Field(default=None, max_length=36)


class EffectivenessPlanCreate(BaseModel):
    source_type: str | None = Field(default=None, max_length=48)
    source_id: str | None = Field(default=None, max_length=160)
    source_route: str | None = Field(default=None, max_length=500)
    expected_outcome: str = Field(min_length=8, max_length=8000)
    effectiveness_measure: str = Field(min_length=8, max_length=8000)
    verification_method: str = Field(min_length=8, max_length=8000)
    observation_window: str | None = Field(default=None, max_length=255)
    source_indicators: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    responsible_reviewer_user_id: str | None = Field(default=None, max_length=36)
    planned_review_date: date


class EffectivenessConclusionCreate(BaseModel):
    conclusion: Conclusion
    rationale: str = Field(min_length=8, max_length=8000)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, min_length=1, max_length=100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _case_ref() -> str:
    return f"ASC-{_utcnow().year % 100:02d}-{uuid.uuid4().hex[:8].upper()}"


def _assert_user(db: Session, *, amo_id: str, user_id: str | None) -> None:
    if not user_id:
        return
    exists = db.query(account_models.User.id).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not exists:
        raise HTTPException(status_code=422, detail="Selected user is inactive, belongs to another tenant, or does not exist.")


def _load_case(db: Session, *, amo_id: str, case_id: str, lock: bool = False) -> QualityAssuranceCase:
    query = db.query(QualityAssuranceCase).options(
        selectinload(QualityAssuranceCase.investigation_entries),
        selectinload(QualityAssuranceCase.effectiveness_plans),
        selectinload(QualityAssuranceCase.events),
    ).filter(QualityAssuranceCase.amo_id == amo_id, QualityAssuranceCase.id == case_id)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Assurance case not found.")
    return row


def _entry_dict(row: QualityInvestigationEntry) -> dict[str, Any]:
    return {
        "id": str(row.id), "method": row.method, "entry_type": row.entry_type,
        "sequence_no": row.sequence_no, "category": row.category, "prompt": row.prompt,
        "statement": row.statement, "confidence": row.confidence,
        "evidence_references": row.evidence_references or [], "parent_entry_id": row.parent_entry_id,
        "created_by_user_id": row.created_by_user_id, "created_at": row.created_at,
    }


def _plan_dict(row: QualityEffectivenessPlan) -> dict[str, Any]:
    return {
        "id": str(row.id), "source_type": row.source_type, "source_id": row.source_id,
        "source_route": row.source_route, "expected_outcome": row.expected_outcome,
        "effectiveness_measure": row.effectiveness_measure, "verification_method": row.verification_method,
        "observation_window": row.observation_window, "source_indicators": row.source_indicators or [],
        "responsible_reviewer_user_id": row.responsible_reviewer_user_id,
        "planned_review_date": row.planned_review_date, "status": row.status, "conclusion": row.conclusion,
        "conclusion_rationale": row.conclusion_rationale, "conclusion_evidence": row.conclusion_evidence or [],
        "concluded_by_user_id": row.concluded_by_user_id, "concluded_at": row.concluded_at,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _event_dict(row: QualityAssuranceCaseEvent) -> dict[str, Any]:
    return {
        "id": str(row.id), "event_type": row.event_type, "reason": row.reason,
        "before_snapshot": row.before_snapshot, "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id, "created_at": row.created_at,
    }


def _case_dict(row: QualityAssuranceCase, *, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(row.id), "case_ref": row.case_ref, "case_type": row.case_type,
        "title": row.title, "description": row.description, "severity": row.severity,
        "status": row.status, "source_references": row.source_references or [],
        "regulatory_basis": row.regulatory_basis or [], "owner_user_id": row.owner_user_id,
        "due_date": row.due_date, "opened_at": row.opened_at, "closed_at": row.closed_at,
        "closed_by_user_id": row.closed_by_user_id, "closure_rationale": row.closure_rationale,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
    if detail:
        data["investigation_entries"] = [_entry_dict(item) for item in list(row.investigation_entries or [])]
        data["effectiveness_plans"] = [_plan_dict(item) for item in list(row.effectiveness_plans or [])]
        data["events"] = [_event_dict(item) for item in list(row.events or [])]
    return data


def _snapshot(row: QualityAssuranceCase) -> dict[str, Any]:
    return {"status": row.status, "severity": row.severity, "owner_user_id": row.owner_user_id, "due_date": row.due_date.isoformat() if row.due_date else None}


def _add_event(db: Session, *, row: QualityAssuranceCase, event_type: str, reason: str, actor_user_id: str, before: dict[str, Any] | None = None) -> None:
    db.add(QualityAssuranceCaseEvent(
        amo_id=row.amo_id,
        case_id=row.id,
        event_type=event_type,
        reason=reason,
        before_snapshot=before,
        after_snapshot=_snapshot(row),
        actor_user_id=actor_user_id,
        created_at=_utcnow(),
    ))


@router.get("")
def list_cases(
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    case_type: CaseType | None = None,
    severity: Severity | None = None,
    owner_user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAssuranceCase).filter(QualityAssuranceCase.amo_id == ctx.amo_id)
    if status_filter: query = query.filter(QualityAssuranceCase.status == status_filter)
    if case_type: query = query.filter(QualityAssuranceCase.case_type == case_type)
    if severity: query = query.filter(QualityAssuranceCase.severity == severity)
    if owner_user_id: query = query.filter(QualityAssuranceCase.owner_user_id == owner_user_id)
    total = query.count()
    rows = query.order_by(QualityAssuranceCase.updated_at.desc()).offset(offset).limit(limit).all()
    return {"items": [_case_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _assert_user(db, amo_id=ctx.amo_id, user_id=payload.owner_user_id)
    row = QualityAssuranceCase(
        amo_id=ctx.amo_id, case_ref=_case_ref(), case_type=payload.case_type,
        title=payload.title.strip(), description=payload.description, severity=payload.severity,
        status="OPEN", source_references=payload.source_references, regulatory_basis=payload.regulatory_basis,
        owner_user_id=payload.owner_user_id, due_date=payload.due_date,
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, row=row, event_type="CREATED", reason="Assurance case opened.", actor_user_id=ctx.user_id)
    db.commit()
    return _case_dict(_load_case(db, amo_id=ctx.amo_id, case_id=str(row.id)), detail=True)


@router.get("/{case_id}")
def get_case(
    case_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _case_dict(_load_case(db, amo_id=ctx.amo_id, case_id=case_id), detail=True)


@router.post("/{case_id}/transitions")
def transition_case(
    case_id: str,
    payload: CaseTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    allowed = {
        "OPEN": {"INVESTIGATING", "CANCELLED"},
        "INVESTIGATING": {"ACTION_PENDING", "EFFECTIVENESS_REVIEW", "CANCELLED"},
        "ACTION_PENDING": {"INVESTIGATING", "EFFECTIVENESS_REVIEW", "CANCELLED"},
        "EFFECTIVENESS_REVIEW": {"ACTION_PENDING", "CLOSED", "CANCELLED"},
        "CLOSED": {"OPEN"},
        "CANCELLED": {"OPEN"},
    }
    if payload.status == row.status or payload.status not in allowed.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Assurance case transition {row.status} → {payload.status} is not allowed.")
    if payload.status == "CLOSED":
        plans = list(row.effectiveness_plans or [])
        unconcluded = [plan for plan in plans if plan.status != "CONCLUDED"]
        if unconcluded:
            raise HTTPException(status_code=409, detail="Case cannot close while an effectiveness plan remains unconcluded.")
        conclusions = {plan.conclusion for plan in plans if plan.conclusion}
        if conclusions.intersection({"INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"}):
            raise HTTPException(status_code=409, detail="Case cannot close while the latest effectiveness conclusion is not effective.")
    before = _snapshot(row)
    row.status = payload.status
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    event_type = "STATUS_CHANGED"
    if payload.status == "CLOSED":
        row.closed_at = _utcnow(); row.closed_by_user_id = ctx.user_id; row.closure_rationale = payload.reason.strip(); event_type = "CLOSED"
    elif payload.status == "CANCELLED":
        event_type = "CANCELLED"
    elif row.closed_at:
        row.closed_at = None; row.closed_by_user_id = None; row.closure_rationale = None; event_type = "REOPENED"
    _add_event(db, row=row, event_type=event_type, reason=payload.reason.strip(), actor_user_id=ctx.user_id, before=before)
    db.commit()
    return _case_dict(_load_case(db, amo_id=ctx.amo_id, case_id=case_id), detail=True)


@router.post("/{case_id}/investigation", status_code=status.HTTP_201_CREATED)
def add_investigation_entry(
    case_id: str,
    payload: InvestigationEntryCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _load_case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if case.status in {"CLOSED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Closed or cancelled assurance cases cannot receive investigation statements.")
    if payload.parent_entry_id:
        parent = db.query(QualityInvestigationEntry.id).filter(
            QualityInvestigationEntry.amo_id == ctx.amo_id,
            QualityInvestigationEntry.case_id == case.id,
            QualityInvestigationEntry.id == payload.parent_entry_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=422, detail="Parent investigation entry does not belong to this case.")
    if payload.entry_type == "CAUSAL_CONCLUSION":
        facts = db.query(QualityInvestigationEntry.id).filter(
            QualityInvestigationEntry.amo_id == ctx.amo_id,
            QualityInvestigationEntry.case_id == case.id,
            QualityInvestigationEntry.entry_type == "FACT",
        ).count()
        if facts == 0 or not payload.evidence_references:
            raise HTTPException(
                status_code=409,
                detail="A causal conclusion requires at least one recorded FACT and explicit evidence references. Hypotheses cannot be promoted to root cause without evidence.",
            )
    entry = QualityInvestigationEntry(
        amo_id=ctx.amo_id, case_id=case.id, method=payload.method, entry_type=payload.entry_type,
        sequence_no=payload.sequence_no, category=payload.category, prompt=payload.prompt,
        statement=payload.statement.strip(), confidence=payload.confidence,
        evidence_references=payload.evidence_references, parent_entry_id=payload.parent_entry_id,
        created_by_user_id=ctx.user_id,
    )
    db.add(entry)
    if case.status == "OPEN": case.status = "INVESTIGATING"
    case.updated_by_user_id = ctx.user_id; case.updated_at = _utcnow()
    db.flush()
    _add_event(db, row=case, event_type="INVESTIGATION_ADDED", reason=f"{payload.entry_type} recorded using {payload.method}.", actor_user_id=ctx.user_id)
    db.commit()
    return _entry_dict(entry)


@router.post("/{case_id}/effectiveness-plans", status_code=status.HTTP_201_CREATED)
def create_effectiveness_plan(
    case_id: str,
    payload: EffectivenessPlanCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _load_case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    _assert_user(db, amo_id=ctx.amo_id, user_id=payload.responsible_reviewer_user_id)
    if case.status in {"CLOSED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Closed or cancelled cases cannot receive effectiveness plans.")
    if payload.planned_review_date < date.today():
        raise HTTPException(status_code=422, detail="The planned effectiveness review date cannot be in the past.")
    row = QualityEffectivenessPlan(
        amo_id=ctx.amo_id, case_id=case.id, source_type=payload.source_type,
        source_id=payload.source_id, source_route=payload.source_route,
        expected_outcome=payload.expected_outcome.strip(), effectiveness_measure=payload.effectiveness_measure.strip(),
        verification_method=payload.verification_method.strip(), observation_window=payload.observation_window,
        source_indicators=payload.source_indicators, responsible_reviewer_user_id=payload.responsible_reviewer_user_id,
        planned_review_date=payload.planned_review_date, status="PLANNED", created_by_user_id=ctx.user_id,
    )
    db.add(row)
    case.status = "EFFECTIVENESS_REVIEW"; case.updated_by_user_id = ctx.user_id; case.updated_at = _utcnow()
    db.flush()
    _add_event(db, row=case, event_type="EFFECTIVENESS_PLANNED", reason="Effectiveness plan created with explicit outcome, measure and verification method.", actor_user_id=ctx.user_id)
    db.commit()
    return _plan_dict(row)


@router.post("/{case_id}/effectiveness-plans/{plan_id}/conclusion")
def conclude_effectiveness(
    case_id: str,
    plan_id: str,
    payload: EffectivenessConclusionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _load_case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    plan = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == ctx.amo_id,
        QualityEffectivenessPlan.case_id == case.id,
        QualityEffectivenessPlan.id == plan_id,
    ).with_for_update().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Effectiveness plan not found.")
    if plan.status == "CONCLUDED":
        raise HTTPException(status_code=409, detail="Effectiveness conclusions are immutable. Reopen the case and create a new plan for a new observation window.")
    if plan.planned_review_date > date.today():
        raise HTTPException(status_code=409, detail="The planned observation window has not reached its review date.")
    plan.status = "CONCLUDED"; plan.conclusion = payload.conclusion; plan.conclusion_rationale = payload.rationale.strip()
    plan.conclusion_evidence = payload.evidence_references; plan.concluded_by_user_id = ctx.user_id; plan.concluded_at = _utcnow(); plan.updated_at = _utcnow()
    before = _snapshot(case)
    if payload.conclusion == "EFFECTIVE":
        case.status = "EFFECTIVENESS_REVIEW"
    else:
        case.status = "ACTION_PENDING"
    case.updated_by_user_id = ctx.user_id; case.updated_at = _utcnow()
    _add_event(
        db, row=case,
        event_type="EFFECTIVENESS_CONCLUDED" if payload.conclusion == "EFFECTIVE" else "ESCALATED",
        reason=f"Effectiveness concluded {payload.conclusion}: {payload.rationale.strip()}",
        actor_user_id=ctx.user_id, before=before,
    )
    db.commit()
    return {"case": _case_dict(_load_case(db, amo_id=ctx.amo_id, case_id=case_id), detail=True), "effectiveness_plan": _plan_dict(plan)}
