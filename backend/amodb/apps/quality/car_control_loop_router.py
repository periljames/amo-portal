from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db

from . import models
from .car_control_loop import MILESTONE_ORDER, closure_readiness, compute_car_health
from .car_control_loop_models import (
    QualityCARControlEvent,
    QualityCARControlProfile,
    QualityCARDeadlineChange,
    QualityCARDependency,
    QualityCARMilestone,
)
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)
from .transitions import transition_car

router = APIRouter(prefix="/cars/{car_id}/control-loop", tags=["Quality CAR control loop"])

MilestoneStatus = Literal["PLANNED", "IN_PROGRESS", "SUBMITTED", "ACCEPTED", "REJECTED", "BLOCKED", "COMPLETED", "WAIVED"]
DependencyType = Literal["INTERNAL", "EXTERNAL", "PROCUREMENT", "FACILITY", "RESOURCE", "SUPPLIER", "REGULATORY", "OTHER"]
DependencyStatus = Literal["OPEN", "MITIGATING", "MITIGATED", "RESOLVED", "ACCEPTED_RISK", "CANCELLED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DeadlineDecision = Literal["APPROVE", "REJECT"]

_MILESTONE_TITLES = {
    "RCA_SUBMISSION": "Root cause analysis submitted",
    "CAP_APPROVAL": "Corrective action plan approved",
    "IMPLEMENTATION_COMPLETE": "Corrective actions implemented",
    "EVIDENCE_COMPLETE": "Closure evidence complete",
    "EFFECTIVENESS_REVIEW": "Effectiveness review complete",
}
_MILESTONE_PERCENTAGES = {
    "RCA_SUBMISSION": 0.25,
    "CAP_APPROVAL": 0.45,
    "IMPLEMENTATION_COMPLETE": 0.75,
    "EVIDENCE_COMPLETE": 0.85,
    "EFFECTIVENESS_REVIEW": 1.0,
}


class MilestoneSeed(BaseModel):
    milestone_key: Literal["RCA_SUBMISSION", "CAP_APPROVAL", "IMPLEMENTATION_COMPLETE", "EVIDENCE_COMPLETE", "EFFECTIVENESS_REVIEW"]
    due_date: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)


class ControlLoopInitialize(BaseModel):
    accountable_owner_user_id: str | None = Field(default=None, max_length=36)
    final_due_date: date | None = None
    effectiveness_required: bool = True
    milestones: list[MilestoneSeed] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_milestones(self) -> "ControlLoopInitialize":
        keys = [item.milestone_key for item in self.milestones]
        if len(keys) != len(set(keys)):
            raise ValueError("Each milestone_key may be supplied only once.")
        return self


class ControlProfileUpdate(BaseModel):
    accountable_owner_user_id: str | None = Field(default=None, max_length=36)
    effectiveness_required: bool | None = None


class MilestoneUpdate(BaseModel):
    owner_user_id: str | None = Field(default=None, max_length=36)
    status: MilestoneStatus | None = None
    notes: str | None = Field(default=None, max_length=8000)
    evidence_ref: str | None = Field(default=None, max_length=1024)


class DependencyCreate(BaseModel):
    milestone_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    dependency_type: DependencyType = "OTHER"
    owner_user_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None
    risk_level: RiskLevel = "MEDIUM"
    blocks_closure: bool = False
    mitigation_plan: str | None = Field(default=None, max_length=8000)


class DependencyUpdate(BaseModel):
    milestone_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    dependency_type: DependencyType | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None
    risk_level: RiskLevel | None = None
    status: DependencyStatus | None = None
    blocks_closure: bool | None = None
    mitigation_plan: str | None = Field(default=None, max_length=8000)


class DeadlineChangeCreate(BaseModel):
    milestone_id: str | None = Field(default=None, max_length=36)
    requested_due_date: date
    reason: str = Field(min_length=8, max_length=8000)
    impact_statement: str | None = Field(default=None, max_length=8000)


class DeadlineChangeDecision(BaseModel):
    decision: DeadlineDecision
    review_note: str = Field(min_length=3, max_length=8000)


class CloseControlLoop(BaseModel):
    evidence_ref: str | None = Field(default=None, max_length=1024)
    closure_reason: str = Field(min_length=8, max_length=8000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


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


def _load_car(db: Session, *, amo_id: str, car_id: str, lock: bool = False) -> models.CorrectiveActionRequest:
    query = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.amo_id == amo_id,
        models.CorrectiveActionRequest.id == car_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Corrective action request not found.")
    return row


def _load_profile(db: Session, *, amo_id: str, car_id: str, lock: bool = False) -> QualityCARControlProfile | None:
    query = db.query(QualityCARControlProfile).options(
        selectinload(QualityCARControlProfile.milestones),
    ).filter(
        QualityCARControlProfile.amo_id == amo_id,
        QualityCARControlProfile.car_id == car_id,
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _require_profile(db: Session, *, amo_id: str, car_id: str, lock: bool = False) -> QualityCARControlProfile:
    row = _load_profile(db, amo_id=amo_id, car_id=car_id, lock=lock)
    if row is None:
        raise HTTPException(status_code=409, detail="Initialize the CAR control loop before using staged controls.")
    return row


def _milestones(db: Session, *, amo_id: str, car_id: str) -> list[QualityCARMilestone]:
    return db.query(QualityCARMilestone).filter(
        QualityCARMilestone.amo_id == amo_id,
        QualityCARMilestone.car_id == car_id,
    ).order_by(QualityCARMilestone.phase_order.asc()).all()


def _dependencies(db: Session, *, amo_id: str, car_id: str) -> list[QualityCARDependency]:
    return db.query(QualityCARDependency).filter(
        QualityCARDependency.amo_id == amo_id,
        QualityCARDependency.car_id == car_id,
    ).order_by(QualityCARDependency.created_at.asc()).all()


def _deadline_changes(db: Session, *, amo_id: str, car_id: str) -> list[QualityCARDeadlineChange]:
    return db.query(QualityCARDeadlineChange).filter(
        QualityCARDeadlineChange.amo_id == amo_id,
        QualityCARDeadlineChange.car_id == car_id,
    ).order_by(QualityCARDeadlineChange.created_at.desc()).limit(250).all()


def _events(db: Session, *, amo_id: str, car_id: str) -> list[QualityCARControlEvent]:
    return db.query(QualityCARControlEvent).filter(
        QualityCARControlEvent.amo_id == amo_id,
        QualityCARControlEvent.car_id == car_id,
    ).order_by(QualityCARControlEvent.created_at.desc()).limit(500).all()


def _snapshot(*, car: models.CorrectiveActionRequest, profile: QualityCARControlProfile | None = None, milestone: QualityCARMilestone | None = None) -> dict[str, Any]:
    return {
        "car_id": str(car.id),
        "car_number": car.car_number,
        "car_status": str(_enum_value(car.status)),
        "accountable_owner_user_id": profile.accountable_owner_user_id if profile else None,
        "original_due_date": profile.original_due_date.isoformat() if profile else None,
        "current_due_date": profile.current_due_date.isoformat() if profile else None,
        "milestone": {
            "id": str(milestone.id),
            "milestone_key": milestone.milestone_key,
            "status": milestone.status,
            "owner_user_id": milestone.owner_user_id,
            "original_due_date": milestone.original_due_date.isoformat(),
            "current_due_date": milestone.current_due_date.isoformat(),
            "evidence_ref": milestone.evidence_ref,
        } if milestone else None,
        "captured_at": _utcnow().isoformat(),
    }


def _add_event(
    db: Session,
    *,
    car: models.CorrectiveActionRequest,
    profile: QualityCARControlProfile | None,
    event_type: str,
    reason: str,
    actor_user_id: str | None,
    milestone: QualityCARMilestone | None = None,
    severity: str = "INFO",
    event_key: str | None = None,
    system_generated: bool = False,
) -> QualityCARControlEvent:
    row = QualityCARControlEvent(
        amo_id=car.amo_id,
        car_id=car.id,
        milestone_id=milestone.id if milestone else None,
        event_key=event_key,
        event_type=event_type,
        severity=severity,
        reason=reason.strip(),
        snapshot=_snapshot(car=car, profile=profile, milestone=milestone),
        actor_user_id=actor_user_id,
        system_generated=system_generated,
        created_at=_utcnow(),
    )
    db.add(row)
    return row


def _milestone_dict(row: QualityCARMilestone) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "milestone_key": row.milestone_key,
        "phase_order": row.phase_order,
        "title": row.title,
        "owner_user_id": row.owner_user_id,
        "original_due_date": row.original_due_date,
        "current_due_date": row.current_due_date,
        "status": row.status,
        "notes": row.notes,
        "evidence_ref": row.evidence_ref,
        "completed_by_user_id": row.completed_by_user_id,
        "completed_at": row.completed_at,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _dependency_dict(row: QualityCARDependency) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "milestone_id": str(row.milestone_id) if row.milestone_id else None,
        "title": row.title,
        "description": row.description,
        "dependency_type": row.dependency_type,
        "owner_user_id": row.owner_user_id,
        "due_date": row.due_date,
        "risk_level": row.risk_level,
        "status": row.status,
        "blocks_closure": row.blocks_closure,
        "mitigation_plan": row.mitigation_plan,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _deadline_change_dict(row: QualityCARDeadlineChange) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "milestone_id": str(row.milestone_id) if row.milestone_id else None,
        "previous_due_date": row.previous_due_date,
        "requested_due_date": row.requested_due_date,
        "reason": row.reason,
        "impact_statement": row.impact_statement,
        "status": row.status,
        "requested_by_user_id": row.requested_by_user_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "review_note": row.review_note,
        "created_at": row.created_at,
    }


def _event_dict(row: QualityCARControlEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "milestone_id": str(row.milestone_id) if row.milestone_id else None,
        "event_key": row.event_key,
        "event_type": row.event_type,
        "severity": row.severity,
        "reason": row.reason,
        "snapshot": row.snapshot or {},
        "actor_user_id": row.actor_user_id,
        "system_generated": row.system_generated,
        "created_at": row.created_at,
    }


def _legacy_extension_dict(row: models.QualityCARExtensionRequest) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "requested_due_date": row.requested_due_date,
        "reason": row.reason,
        "status": row.status,
        "requested_by_user_id": row.requested_by_user_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "review_note": row.review_note,
        "created_at": row.created_at,
    }


def _result(db: Session, *, car: models.CorrectiveActionRequest, profile: QualityCARControlProfile | None = None) -> dict[str, Any]:
    profile = profile or _load_profile(db, amo_id=car.amo_id, car_id=str(car.id))
    milestones = _milestones(db, amo_id=car.amo_id, car_id=str(car.id)) if profile else []
    dependencies = _dependencies(db, amo_id=car.amo_id, car_id=str(car.id)) if profile else []
    legacy_extensions = db.query(models.QualityCARExtensionRequest).filter(
        models.QualityCARExtensionRequest.amo_id == car.amo_id,
        models.QualityCARExtensionRequest.car_id == car.id,
    ).order_by(models.QualityCARExtensionRequest.created_at.desc()).limit(250).all()
    health = compute_car_health(
        today=date.today(),
        car_status=str(_enum_value(car.status)),
        final_due_date=profile.current_due_date if profile else (car.target_closure_date or car.due_date),
        accountable_owner_user_id=profile.accountable_owner_user_id if profile else car.assigned_to_user_id,
        milestones=milestones,
        dependencies=dependencies,
    )
    readiness = closure_readiness(
        milestones=milestones,
        dependencies=dependencies,
        effectiveness_required=bool(profile.effectiveness_required) if profile else True,
    ) if profile else {"ready": False, "blockers": [{"code": "CONTROL_LOOP_NOT_INITIALIZED", "message": "Initialize the staged CAR control loop before closure."}]}
    return {
        "initialized": profile is not None,
        "car": {
            "id": str(car.id),
            "car_number": car.car_number,
            "title": car.title,
            "summary": car.summary,
            "program": str(_enum_value(car.program)),
            "priority": str(_enum_value(car.priority)),
            "status": str(_enum_value(car.status)),
            "assigned_to_user_id": car.assigned_to_user_id,
            "due_date": car.due_date,
            "target_closure_date": car.target_closure_date,
            "finding_id": str(car.finding_id) if car.finding_id else None,
        },
        "profile": {
            "id": str(profile.id),
            "accountable_owner_user_id": profile.accountable_owner_user_id,
            "original_due_date": profile.original_due_date,
            "current_due_date": profile.current_due_date,
            "effectiveness_required": profile.effectiveness_required,
            "initialized_from": profile.initialized_from,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        } if profile else None,
        "milestones": [_milestone_dict(row) for row in milestones],
        "dependencies": [_dependency_dict(row) for row in dependencies],
        "deadline_changes": [_deadline_change_dict(row) for row in _deadline_changes(db, amo_id=car.amo_id, car_id=str(car.id))] if profile else [],
        "legacy_extension_history": [_legacy_extension_dict(row) for row in legacy_extensions],
        "events": [_event_dict(row) for row in _events(db, amo_id=car.amo_id, car_id=str(car.id))] if profile else [],
        "health": health.as_dict(),
        "closure_readiness": readiness,
    }


def _assert_milestone(db: Session, *, amo_id: str, car_id: str, milestone_id: str, lock: bool = False) -> QualityCARMilestone:
    query = db.query(QualityCARMilestone).filter(
        QualityCARMilestone.amo_id == amo_id,
        QualityCARMilestone.car_id == car_id,
        QualityCARMilestone.id == milestone_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="CAR control milestone not found.")
    return row


@router.get("")
def get_control_loop(
    car_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id)
    return _result(db, car=car)


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
def initialize_control_loop(
    car_id: str,
    payload: ControlLoopInitialize,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    existing = _load_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    if existing is not None:
        return _result(db, car=car, profile=existing)

    owner = payload.accountable_owner_user_id if "accountable_owner_user_id" in payload.model_fields_set else car.assigned_to_user_id
    _assert_user(db, amo_id=ctx.amo_id, user_id=owner)
    authoritative_due = car.target_closure_date or car.due_date
    if payload.final_due_date is not None and authoritative_due is not None and payload.final_due_date != authoritative_due:
        raise HTTPException(
            status_code=422,
            detail="The staged control loop must initialize from the authoritative CAR deadline. Use the governed CAR extension workflow to revise an existing deadline.",
        )
    final_due = authoritative_due or payload.final_due_date
    if final_due is None:
        raise HTTPException(status_code=422, detail="A controlled final due date is required to initialize the CAR control loop.")
    if authoritative_due is None:
        car.target_closure_date = final_due
    opened_on = car.created_at.date() if car.created_at else date.today()
    if final_due < opened_on:
        raise HTTPException(status_code=422, detail="The controlled final due date cannot precede the CAR creation date.")

    profile = QualityCARControlProfile(
        amo_id=ctx.amo_id,
        car_id=car.id,
        accountable_owner_user_id=owner,
        original_due_date=final_due,
        current_due_date=final_due,
        effectiveness_required=payload.effectiveness_required,
        initialized_from="CAR",
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(profile)
    db.flush()

    explicit = {item.milestone_key: item for item in payload.milestones}
    span = max(0, (final_due - opened_on).days)
    previous_due = opened_on
    for phase_order, key in enumerate(MILESTONE_ORDER, start=1):
        seed = explicit.get(key)
        owner_user_id = (seed.owner_user_id if seed else None) or owner
        _assert_user(db, amo_id=ctx.amo_id, user_id=owner_user_id)
        default_due = opened_on + timedelta(days=round(span * _MILESTONE_PERCENTAGES[key]))
        milestone_due = seed.due_date if seed and seed.due_date else default_due
        if milestone_due < previous_due or milestone_due > final_due:
            raise HTTPException(
                status_code=422,
                detail=f"{key} due date must preserve lifecycle order and cannot exceed the controlled final deadline.",
            )
        previous_due = milestone_due
        milestone = QualityCARMilestone(
            amo_id=ctx.amo_id,
            profile_id=profile.id,
            car_id=car.id,
            milestone_key=key,
            phase_order=phase_order,
            title=_MILESTONE_TITLES[key],
            owner_user_id=owner_user_id,
            original_due_date=milestone_due,
            current_due_date=milestone_due,
            status="PLANNED",
        )
        db.add(milestone)

    _add_event(
        db,
        car=car,
        profile=profile,
        event_type="CONTROL_LOOP_INITIALIZED",
        reason="Staged RCA/CAPA control loop initialized with preserved baseline deadlines.",
        actor_user_id=ctx.user_id,
        severity="ACTION_REQUIRED",
    )
    db.commit()
    return _result(db, car=_load_car(db, amo_id=ctx.amo_id, car_id=car_id), profile=_load_profile(db, amo_id=ctx.amo_id, car_id=car_id))


@router.patch("/profile")
def update_control_profile(
    car_id: str,
    payload: ControlProfileUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    if "accountable_owner_user_id" in payload.model_fields_set:
        _assert_user(db, amo_id=ctx.amo_id, user_id=payload.accountable_owner_user_id)
        profile.accountable_owner_user_id = payload.accountable_owner_user_id
    if payload.effectiveness_required is not None:
        profile.effectiveness_required = payload.effectiveness_required
    profile.updated_by_user_id = ctx.user_id
    _add_event(db, car=car, profile=profile, event_type="CONTROL_PROFILE_UPDATED", reason="CAR accountability or effectiveness controls were updated.", actor_user_id=ctx.user_id)
    db.commit()
    return _result(db, car=car, profile=profile)


@router.patch("/milestones/{milestone_id}")
def update_milestone(
    car_id: str,
    milestone_id: str,
    payload: MilestoneUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    row = _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=milestone_id, lock=True)

    if "owner_user_id" in payload.model_fields_set:
        _assert_user(db, amo_id=ctx.amo_id, user_id=payload.owner_user_id)
        row.owner_user_id = payload.owner_user_id
    if payload.notes is not None:
        row.notes = payload.notes.strip() or None
    if payload.evidence_ref is not None:
        row.evidence_ref = payload.evidence_ref.strip() or None
    if payload.status is not None:
        row.status = payload.status
        if payload.status in {"COMPLETED", "ACCEPTED", "WAIVED"}:
            row.completed_by_user_id = ctx.user_id
            row.completed_at = _utcnow()
            if payload.status in {"ACCEPTED", "WAIVED"}:
                row.reviewed_by_user_id = ctx.user_id
                row.reviewed_at = _utcnow()
        else:
            row.completed_by_user_id = None
            row.completed_at = None
            if payload.status not in {"REJECTED"}:
                row.reviewed_by_user_id = None
                row.reviewed_at = None
        if payload.status in {"ACCEPTED", "REJECTED"}:
            row.reviewed_by_user_id = ctx.user_id
            row.reviewed_at = _utcnow()

    _add_event(
        db,
        car=car,
        profile=profile,
        milestone=row,
        event_type="MILESTONE_UPDATED",
        reason=f"{row.title} updated to {row.status}.",
        actor_user_id=ctx.user_id,
        severity="WARNING" if row.status in {"REJECTED", "BLOCKED"} else "INFO",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


@router.post("/dependencies", status_code=status.HTTP_201_CREATED)
def create_dependency(
    car_id: str,
    payload: DependencyCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    if payload.milestone_id:
        _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=payload.milestone_id)
    _assert_user(db, amo_id=ctx.amo_id, user_id=payload.owner_user_id)
    row = QualityCARDependency(
        amo_id=ctx.amo_id,
        car_id=car.id,
        milestone_id=payload.milestone_id,
        title=payload.title.strip(),
        description=payload.description,
        dependency_type=payload.dependency_type,
        owner_user_id=payload.owner_user_id,
        due_date=payload.due_date,
        risk_level=payload.risk_level,
        status="OPEN",
        blocks_closure=payload.blocks_closure,
        mitigation_plan=payload.mitigation_plan,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(
        db,
        car=car,
        profile=profile,
        event_type="DEPENDENCY_OPENED",
        reason=f"Dependency opened: {row.title}.",
        actor_user_id=ctx.user_id,
        severity="CRITICAL" if row.risk_level == "CRITICAL" else "WARNING" if row.blocks_closure or row.risk_level == "HIGH" else "ACTION_REQUIRED",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


@router.patch("/dependencies/{dependency_id}")
def update_dependency(
    car_id: str,
    dependency_id: str,
    payload: DependencyUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    row = db.query(QualityCARDependency).filter(
        QualityCARDependency.amo_id == ctx.amo_id,
        QualityCARDependency.car_id == car_id,
        QualityCARDependency.id == dependency_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="CAR dependency not found.")

    values = payload.model_dump(exclude_unset=True)
    if "milestone_id" in values and values["milestone_id"]:
        _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=values["milestone_id"])
    if "owner_user_id" in values:
        _assert_user(db, amo_id=ctx.amo_id, user_id=values["owner_user_id"])
    for key, value in values.items():
        if key in {"title", "description", "mitigation_plan"} and isinstance(value, str):
            value = value.strip() or None
        setattr(row, key, value)
    row.updated_by_user_id = ctx.user_id
    _add_event(
        db,
        car=car,
        profile=profile,
        event_type="DEPENDENCY_UPDATED",
        reason=f"Dependency updated: {row.title} ({row.status}).",
        actor_user_id=ctx.user_id,
        severity="CRITICAL" if row.status not in {"RESOLVED", "MITIGATED", "ACCEPTED_RISK", "CANCELLED"} and row.risk_level == "CRITICAL" else "INFO",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


@router.post("/deadline-changes", status_code=status.HTTP_201_CREATED)
def request_deadline_change(
    car_id: str,
    payload: DeadlineChangeCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    milestone = None
    previous_due = profile.current_due_date
    if payload.milestone_id:
        milestone = _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=payload.milestone_id, lock=True)
        previous_due = milestone.current_due_date
    if payload.requested_due_date <= previous_due:
        raise HTTPException(status_code=422, detail="A deadline extension must move the controlled due date later than its current value.")
    if milestone is not None and payload.requested_due_date > profile.current_due_date:
        raise HTTPException(status_code=422, detail="A milestone deadline cannot extend beyond the current final CAR deadline.")
    pending = db.query(QualityCARDeadlineChange.id).filter(
        QualityCARDeadlineChange.amo_id == ctx.amo_id,
        QualityCARDeadlineChange.car_id == car.id,
        QualityCARDeadlineChange.milestone_id == (milestone.id if milestone else None),
        QualityCARDeadlineChange.status == "PENDING",
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="A pending deadline change already exists for this controlled deadline.")
    row = QualityCARDeadlineChange(
        amo_id=ctx.amo_id,
        car_id=car.id,
        milestone_id=milestone.id if milestone else None,
        previous_due_date=previous_due,
        requested_due_date=payload.requested_due_date,
        reason=payload.reason.strip(),
        impact_statement=payload.impact_statement,
        status="PENDING",
        requested_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(
        db,
        car=car,
        profile=profile,
        milestone=milestone,
        event_type="DEADLINE_CHANGE_REQUESTED",
        reason=payload.reason,
        actor_user_id=ctx.user_id,
        severity="ACTION_REQUIRED",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


@router.post("/deadline-changes/{change_id}/decision")
def decide_deadline_change(
    car_id: str,
    change_id: str,
    payload: DeadlineChangeDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    row = db.query(QualityCARDeadlineChange).filter(
        QualityCARDeadlineChange.amo_id == ctx.amo_id,
        QualityCARDeadlineChange.car_id == car.id,
        QualityCARDeadlineChange.id == change_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Deadline change request not found.")
    if row.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only a pending deadline change may be decided.")

    milestone = None
    if row.milestone_id:
        milestone = _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=str(row.milestone_id), lock=True)
    if payload.decision == "APPROVE":
        if milestone is not None:
            milestone.current_due_date = row.requested_due_date
        else:
            profile.current_due_date = row.requested_due_date
            car.target_closure_date = row.requested_due_date
        row.status = "APPROVED"
    else:
        row.status = "REJECTED"
    row.reviewed_by_user_id = ctx.user_id
    row.reviewed_at = _utcnow()
    row.review_note = payload.review_note.strip()
    profile.updated_by_user_id = ctx.user_id
    _add_event(
        db,
        car=car,
        profile=profile,
        milestone=milestone,
        event_type=f"DEADLINE_CHANGE_{row.status}",
        reason=payload.review_note,
        actor_user_id=ctx.user_id,
        severity="WARNING" if row.status == "REJECTED" else "INFO",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


def _event_exists(db: Session, *, car_id: str, event_key: str) -> bool:
    return db.query(QualityCARControlEvent.id).filter(
        QualityCARControlEvent.car_id == car_id,
        QualityCARControlEvent.event_key == event_key,
    ).first() is not None


def _notify_owner(db: Session, *, ctx: TenantContext, car: models.CorrectiveActionRequest, recipient_user_id: str | None, message: str, severity: str) -> None:
    if not recipient_user_id:
        return
    db.add(models.QMSNotification(
        amo_id=ctx.amo_id,
        user_id=recipient_user_id,
        message=message,
        severity=severity,
        created_by_user_id=ctx.user_id,
        action_url=f"/maintenance/{ctx.amo_code}/quality/cars/{car.id}",
        action_label="Open CAR control loop",
        entity_type="quality.car",
        entity_id=str(car.id),
    ))


@router.post("/evaluate")
def evaluate_control_loop(
    car_id: str,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    today = date.today()
    created = 0

    for milestone in _milestones(db, amo_id=ctx.amo_id, car_id=car_id):
        if milestone.status in {"ACCEPTED", "COMPLETED", "WAIVED"}:
            continue
        days = (milestone.current_due_date - today).days
        if days < -7:
            stage, severity, notification_severity = "CRITICAL_OVERDUE", "CRITICAL", "WARNING"
        elif days < 0:
            stage, severity, notification_severity = "OVERDUE", "WARNING", "WARNING"
        elif days <= 3:
            stage, severity, notification_severity = "FINAL_WARNING", "WARNING", "WARNING"
        elif days <= 7:
            stage, severity, notification_severity = "DUE_SOON", "ACTION_REQUIRED", "ACTION_REQUIRED"
        elif days <= 14:
            stage, severity, notification_severity = "REMINDER", "ACTION_REQUIRED", "ACTION_REQUIRED"
        else:
            continue
        event_key = f"milestone:{milestone.id}:{milestone.current_due_date.isoformat()}:{stage}"
        if _event_exists(db, car_id=car_id, event_key=event_key):
            continue
        descriptor = "overdue by" if days < 0 else "due in"
        count = abs(days) if days < 0 else days
        message = f"{milestone.title} is {descriptor} {count} day(s)."
        _add_event(
            db,
            car=car,
            profile=profile,
            milestone=milestone,
            event_type=f"MILESTONE_{stage}",
            reason=message,
            actor_user_id=ctx.user_id,
            severity=severity,
            event_key=event_key,
            system_generated=True,
        )
        _notify_owner(db, ctx=ctx, car=car, recipient_user_id=milestone.owner_user_id or profile.accountable_owner_user_id, message=message, severity=notification_severity)
        created += 1

    for dependency in _dependencies(db, amo_id=ctx.amo_id, car_id=car_id):
        if dependency.status in {"RESOLVED", "MITIGATED", "ACCEPTED_RISK", "CANCELLED"}:
            continue
        if dependency.risk_level not in {"HIGH", "CRITICAL"} and not dependency.blocks_closure:
            continue
        stage = "CRITICAL" if dependency.risk_level == "CRITICAL" else "BLOCKER"
        event_key = f"dependency:{dependency.id}:{dependency.status}:{dependency.risk_level}:{stage}"
        if _event_exists(db, car_id=car_id, event_key=event_key):
            continue
        message = f"Open {dependency.risk_level.lower()}-risk dependency requires action: {dependency.title}."
        _add_event(
            db,
            car=car,
            profile=profile,
            event_type=f"DEPENDENCY_{stage}",
            reason=message,
            actor_user_id=ctx.user_id,
            severity="CRITICAL" if dependency.risk_level == "CRITICAL" else "WARNING",
            event_key=event_key,
            system_generated=True,
        )
        _notify_owner(db, ctx=ctx, car=car, recipient_user_id=dependency.owner_user_id or profile.accountable_owner_user_id, message=message, severity="WARNING")
        created += 1

    health = compute_car_health(
        today=today,
        car_status=str(_enum_value(car.status)),
        final_due_date=profile.current_due_date,
        accountable_owner_user_id=profile.accountable_owner_user_id,
        milestones=_milestones(db, amo_id=ctx.amo_id, car_id=car_id),
        dependencies=_dependencies(db, amo_id=ctx.amo_id, car_id=car_id),
    )
    if health.state in {"OVERDUE", "CRITICAL"} and str(_enum_value(car.status)) not in {"CLOSED", "CANCELLED", "ESCALATED"}:
        transition_car(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            car=car,
            target_status="ESCALATED",
            evidence_ref=None,
        )
        car.escalated_at = _utcnow()

    db.commit()
    result = _result(db, car=car, profile=profile)
    result["new_events_created"] = created
    return result


@router.post("/close")
def close_control_loop(
    car_id: str,
    payload: CloseControlLoop,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    milestones = _milestones(db, amo_id=ctx.amo_id, car_id=car_id)
    dependencies = _dependencies(db, amo_id=ctx.amo_id, car_id=car_id)
    readiness = closure_readiness(
        milestones=milestones,
        dependencies=dependencies,
        effectiveness_required=profile.effectiveness_required,
    )
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail={"message": "CAR control-loop closure gates are not satisfied.", "blockers": readiness["blockers"]})

    evidence_ref = (payload.evidence_ref or "").strip()
    if not evidence_ref:
        for key in ("EFFECTIVENESS_REVIEW", "EVIDENCE_COMPLETE"):
            evidence_ref = next((str(item.evidence_ref).strip() for item in milestones if item.milestone_key == key and item.evidence_ref), "")
            if evidence_ref:
                break
    if not evidence_ref:
        raise HTTPException(status_code=422, detail="Closure evidence is required.")

    current = str(_enum_value(car.status))
    if current == "CANCELLED":
        raise HTTPException(status_code=409, detail="A cancelled CAR cannot be closed without first returning it to the active governed workflow.")
    sequence = {
        "DRAFT": ["OPEN", "IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED"],
        "OPEN": ["IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED"],
        "IN_PROGRESS": ["PENDING_VERIFICATION", "CLOSED"],
        "PENDING_VERIFICATION": ["CLOSED"],
        "ESCALATED": ["PENDING_VERIFICATION", "CLOSED"],
        "CLOSED": [],
    }.get(current)
    if sequence is None:
        raise HTTPException(status_code=409, detail=f"Unsupported CAR status for controlled closure: {current}")
    for target in sequence:
        transition_car(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            car=car,
            target_status=target,
            evidence_ref=evidence_ref if target in {"PENDING_VERIFICATION", "CLOSED"} else None,
        )
    car.evidence_ref = evidence_ref
    # Preserve the canonical accepted-close side effects used by the existing
    # Quality CAR workflow (authoritative RCA/CAPA acceptance, evidence
    # verification, linked finding/CAP closeout and related task closure).
    from .router import _close_accepted_car_workflow

    _close_accepted_car_workflow(db, car, actor_user_id=ctx.user_id)
    _add_event(
        db,
        car=car,
        profile=profile,
        event_type="CONTROL_LOOP_CLOSED",
        reason=payload.closure_reason,
        actor_user_id=ctx.user_id,
        severity="INFO",
    )
    db.commit()
    return _result(db, car=car, profile=profile)
