from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.training import models as training_models
from amodb.apps.training.integration import current_training_evidence
from amodb.database import get_read_db, get_write_db

from . import models as quality_models
from .people_models import (
    QualityIndependenceDeclaration,
    QualityPrivilege,
    QualityPrivilegeDecision,
    QualityPrivilegeRule,
)
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)

router = APIRouter(prefix="/people", tags=["Quality people and privileges"])

PrivilegeType = Literal["AUDITOR", "LEAD_AUDITOR", "QUALITY_INSPECTOR", "AUTHORIZATION_REVIEWER", "CUSTOM"]
DecisionType = Literal["GRANT", "RENEW", "SUSPEND", "REINSTATE", "REVOKE", "EXPIRE", "REJECT"]
ContextType = Literal["AUDIT", "AUDIT_SCHEDULE", "PROGRAMME_ITEM", "ASSURANCE_CASE", "MISSION", "OTHER"]
Declaration = Literal["INDEPENDENT", "CONFLICT", "REQUIRES_REVIEW"]


class PrivilegeRuleCreate(BaseModel):
    privilege_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_\-]+$")
    title: str = Field(min_length=3, max_length=255)
    privilege_type: PrivilegeType
    description: str | None = None
    required_training_course_codes: list[str] = Field(default_factory=list, max_length=50)
    independence_required: bool = True
    max_concurrent_assignments: int | None = Field(default=None, ge=1, le=100)
    scope_schema: dict[str, Any] = Field(default_factory=dict)


class PrivilegeCreate(BaseModel):
    rule_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    scope_key: str = Field(default="GLOBAL", min_length=1, max_length=255)
    scope: dict[str, Any] = Field(default_factory=dict)
    limitations: list[dict[str, Any] | str] = Field(default_factory=list)


class PrivilegeDecisionCreate(BaseModel):
    decision_type: DecisionType
    rationale: str = Field(min_length=8, max_length=4000)
    effective_from: date | None = None
    expires_on: date | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class IndependenceCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    context_type: ContextType
    context_id: str = Field(min_length=1, max_length=160)
    declaration: Declaration
    relationship_to_subject: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=8, max_length=4000)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _person(db: Session, *, amo_id: str, user_id: str) -> account_models.User:
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not user:
        raise HTTPException(status_code=422, detail="Selected person is inactive, belongs to another tenant, or does not exist.")
    return user


def _rule(db: Session, *, amo_id: str, rule_id: str | None = None, privilege_code: str | None = None) -> QualityPrivilegeRule:
    query = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == amo_id)
    if rule_id:
        query = query.filter(QualityPrivilegeRule.id == rule_id)
    elif privilege_code:
        query = query.filter(QualityPrivilegeRule.privilege_code == privilege_code)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Quality privilege rule not found.")
    return row


def _training_evidence(db: Session, *, amo_id: str, user_id: str, required_codes: list[str], as_of: date) -> dict[str, Any]:
    return current_training_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required_codes=required_codes,
        as_of=as_of,
    )


def _independence_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required: bool,
    context_type: str | None,
    context_id: str | None,
) -> dict[str, Any]:
    if not required:
        return {"required": False, "passed": True, "declaration": None}
    if not context_type or not context_id:
        return {"required": True, "passed": None, "declaration": None, "message": "Assignment context is required to evaluate independence."}
    row = db.query(QualityIndependenceDeclaration).filter(
        QualityIndependenceDeclaration.amo_id == amo_id,
        QualityIndependenceDeclaration.user_id == user_id,
        QualityIndependenceDeclaration.context_type == context_type,
        QualityIndependenceDeclaration.context_id == context_id,
    ).first()
    if not row:
        return {"required": True, "passed": False, "declaration": None, "message": "No independence declaration exists for this assignment."}
    return {
        "required": True,
        "passed": row.declaration == "INDEPENDENT",
        "declaration": row.declaration,
        "declaration_id": str(row.id),
        "rationale": row.rationale,
        "declared_at": row.declared_at.isoformat(),
    }


def _workload_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
    capacity: int | None,
) -> dict[str, Any]:
    window_start = on_date - timedelta(days=90)
    window_end = on_date + timedelta(days=90)
    schedules = db.query(quality_models.QMSAuditSchedule, QMSPlannerScheduleMetadata).join(
        QMSPlannerScheduleMetadata,
        QMSPlannerScheduleMetadata.schedule_id == quality_models.QMSAuditSchedule.id,
    ).filter(
        quality_models.QMSAuditSchedule.amo_id == amo_id,
        quality_models.QMSAuditSchedule.is_active.is_(True),
        quality_models.QMSAuditSchedule.deleted_at.is_(None),
        quality_models.QMSAuditSchedule.next_due_date >= window_start,
        quality_models.QMSAuditSchedule.next_due_date <= window_end,
        QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
    ).limit(1000).all()

    assignments: list[dict[str, Any]] = []
    for schedule, metadata in schedules:
        schedule_users = {
            str(value)
            for value in [
                schedule.lead_auditor_user_id,
                schedule.observer_auditor_user_id,
                schedule.assistant_auditor_user_id,
                *_json_list(metadata.attendee_user_ids_json),
            ]
            if value
        }
        if user_id not in schedule_users:
            continue
        end_date = schedule.next_due_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1)
        if schedule.next_due_date <= on_date <= end_date:
            assignments.append({
                "schedule_id": str(schedule.id),
                "title": schedule.title,
                "start_date": schedule.next_due_date.isoformat(),
                "end_date": end_date.isoformat(),
                "source_route": f"/quality/audits/plan?schedule={schedule.id}",
            })
    count = len(assignments)
    return {
        "date": on_date.isoformat(),
        "active_assignments": count,
        "max_concurrent_assignments": capacity,
        "passed": capacity is None or count < capacity,
        "assignments": assignments,
    }


def evaluate_eligibility(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    rule: QualityPrivilegeRule,
    as_of: date,
    context_type: str | None = None,
    context_id: str | None = None,
    require_active_privilege: bool = True,
) -> dict[str, Any]:
    user = _person(db, amo_id=amo_id, user_id=user_id)
    training = _training_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required_codes=list(rule.required_training_course_codes or []),
        as_of=as_of,
    )
    independence = _independence_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required=bool(rule.independence_required),
        context_type=context_type,
        context_id=context_id,
    )
    workload = _workload_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=as_of,
        capacity=rule.max_concurrent_assignments,
    )
    privilege = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == amo_id,
        QualityPrivilege.user_id == user_id,
        QualityPrivilege.privilege_code == rule.privilege_code,
        QualityPrivilege.status == "ACTIVE",
    ).order_by(QualityPrivilege.updated_at.desc()).first()
    privilege_passed = bool(privilege)
    if privilege and privilege.effective_from and privilege.effective_from > as_of:
        privilege_passed = False
    if privilege and privilege.expires_on and privilege.expires_on < as_of:
        privilege_passed = False

    hard_gates = {
        "workforce_active": True,
        "training_current_verified": bool(training["passed"]),
        "independence": independence["passed"] is not False,
        "capacity": bool(workload["passed"]),
        "active_privilege": privilege_passed if require_active_privilege else True,
    }
    return {
        "eligible": all(hard_gates.values()),
        "as_of": as_of.isoformat(),
        "person": {
            "user_id": str(user.id),
            "full_name": str(getattr(user, "full_name", "") or "").strip() or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": getattr(user, "email", None),
            "role": _enum_value(getattr(user, "role", None)),
        },
        "rule": {
            "id": str(rule.id),
            "privilege_code": rule.privilege_code,
            "title": rule.title,
            "privilege_type": rule.privilege_type,
        },
        "hard_gates": hard_gates,
        "training": training,
        "independence": independence,
        "workload": workload,
        "active_privilege": {
            "id": str(privilege.id),
            "status": privilege.status,
            "effective_from": privilege.effective_from.isoformat() if privilege and privilege.effective_from else None,
            "expires_on": privilege.expires_on.isoformat() if privilege and privilege.expires_on else None,
        } if privilege else None,
    }


def _rule_dict(row: QualityPrivilegeRule) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "privilege_code": row.privilege_code,
        "title": row.title,
        "privilege_type": row.privilege_type,
        "description": row.description,
        "required_training_course_codes": list(row.required_training_course_codes or []),
        "independence_required": bool(row.independence_required),
        "max_concurrent_assignments": row.max_concurrent_assignments,
        "scope_schema": row.scope_schema or {},
        "is_active": bool(row.is_active),
        "updated_at": row.updated_at,
    }


def _decision_dict(row: QualityPrivilegeDecision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "decision_type": row.decision_type,
        "resulting_status": row.resulting_status,
        "rationale": row.rationale,
        "eligibility_snapshot": row.eligibility_snapshot,
        "source_references": row.source_references,
        "effective_from": row.effective_from,
        "expires_on": row.expires_on,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
    }


def _privilege_dict(row: QualityPrivilege, *, include_history: bool = False) -> dict[str, Any]:
    data = {
        "id": str(row.id),
        "rule_id": str(row.rule_id),
        "user_id": str(row.user_id),
        "privilege_code": row.privilege_code,
        "scope_key": row.scope_key,
        "scope": row.scope or {},
        "limitations": row.limitations or [],
        "status": row.status,
        "effective_from": row.effective_from,
        "expires_on": row.expires_on,
        "latest_decision_id": row.latest_decision_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_history:
        data["decisions"] = [_decision_dict(item) for item in list(row.decisions or [])]
    return data


@router.get("/summary")
def people_summary(
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    active = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "ACTIVE").count()
    expiring = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.status == "ACTIVE",
        QualityPrivilege.expires_on.is_not(None),
        QualityPrivilege.expires_on >= today,
        QualityPrivilege.expires_on <= today + timedelta(days=60),
    ).count()
    suspended = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "SUSPENDED").count()
    conflicts = db.query(QualityIndependenceDeclaration).filter(
        QualityIndependenceDeclaration.amo_id == ctx.amo_id,
        QualityIndependenceDeclaration.declaration.in_(["CONFLICT", "REQUIRES_REVIEW"]),
    ).count()
    return {"active_privileges": active, "expiring_within_60_days": expiring, "suspended_privileges": suspended, "independence_exceptions": conflicts}


@router.get("/rules")
def list_rules(
    include_inactive: bool = False,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == ctx.amo_id)
    if not include_inactive:
        query = query.filter(QualityPrivilegeRule.is_active.is_(True))
    rows = query.order_by(QualityPrivilegeRule.title.asc()).limit(250).all()
    return {"items": [_rule_dict(row) for row in rows]}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: PrivilegeRuleCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    code = payload.privilege_code.strip().upper()
    if db.query(QualityPrivilegeRule.id).filter(QualityPrivilegeRule.amo_id == ctx.amo_id, QualityPrivilegeRule.privilege_code == code).first():
        raise HTTPException(status_code=409, detail="A privilege rule with this code already exists.")
    row = QualityPrivilegeRule(
        amo_id=ctx.amo_id,
        privilege_code=code,
        title=payload.title.strip(),
        privilege_type=payload.privilege_type,
        description=payload.description,
        required_training_course_codes=sorted({value.strip().upper() for value in payload.required_training_course_codes if value.strip()}),
        independence_required=payload.independence_required,
        max_concurrent_assignments=payload.max_concurrent_assignments,
        scope_schema=payload.scope_schema,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_dict(row)


@router.get("/privileges")
def list_privileges(
    user_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityPrivilege).options(selectinload(QualityPrivilege.decisions)).filter(QualityPrivilege.amo_id == ctx.amo_id)
    if user_id:
        query = query.filter(QualityPrivilege.user_id == user_id)
    if status_filter:
        query = query.filter(QualityPrivilege.status == status_filter.upper())
    rows = query.order_by(QualityPrivilege.updated_at.desc()).limit(500).all()
    return {"items": [_privilege_dict(row, include_history=True) for row in rows]}


@router.post("/privileges", status_code=status.HTTP_201_CREATED)
def create_privilege(
    payload: PrivilegeCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.rule_id)
    _person(db, amo_id=ctx.amo_id, user_id=payload.user_id)
    scope_key = payload.scope_key.strip() or "GLOBAL"
    existing = db.query(QualityPrivilege.id).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.user_id == payload.user_id,
        QualityPrivilege.privilege_code == rule.privilege_code,
        QualityPrivilege.scope_key == scope_key,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This person already has this privilege/scope record; use a governed decision to change it.")
    row = QualityPrivilege(
        amo_id=ctx.amo_id,
        rule_id=rule.id,
        user_id=payload.user_id,
        privilege_code=rule.privilege_code,
        scope_key=scope_key,
        scope=payload.scope,
        limitations=payload.limitations,
        status="DRAFT",
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _privilege_dict(row)


@router.get("/eligibility")
def get_eligibility(
    user_id: str,
    privilege_code: str,
    as_of: date | None = None,
    context_type: ContextType | None = None,
    context_id: str | None = None,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, privilege_code=privilege_code.strip().upper())
    return evaluate_eligibility(
        db,
        amo_id=ctx.amo_id,
        user_id=user_id,
        rule=rule,
        as_of=as_of or date.today(),
        context_type=context_type,
        context_id=context_id,
        require_active_privilege=True,
    )


@router.post("/privileges/{privilege_id}/decisions", status_code=status.HTTP_201_CREATED)
def decide_privilege(
    privilege_id: str,
    payload: PrivilegeDecisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = db.query(QualityPrivilege).options(selectinload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.id == privilege_id,
    ).with_for_update().first()
    if not privilege:
        raise HTTPException(status_code=404, detail="Quality privilege not found.")
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))

    resulting_status = {
        "GRANT": "ACTIVE",
        "RENEW": "ACTIVE",
        "REINSTATE": "ACTIVE",
        "SUSPEND": "SUSPENDED",
        "REVOKE": "REVOKED",
        "EXPIRE": "EXPIRED",
        "REJECT": "DRAFT",
    }[payload.decision_type]
    if payload.expires_on and payload.effective_from and payload.expires_on < payload.effective_from:
        raise HTTPException(status_code=422, detail="Privilege expiry cannot precede its effective date.")

    eligibility = evaluate_eligibility(
        db,
        amo_id=ctx.amo_id,
        user_id=str(privilege.user_id),
        rule=rule,
        as_of=payload.effective_from or date.today(),
        require_active_privilege=False,
    )
    if payload.decision_type in {"GRANT", "RENEW", "REINSTATE"}:
        grant_gates = dict(eligibility["hard_gates"])
        grant_gates.pop("active_privilege", None)
        # Independence is assignment-specific. A privilege may be granted without
        # declaring independence from an audit that does not yet exist.
        grant_gates.pop("independence", None)
        if not all(grant_gates.values()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Hard source-backed eligibility gates do not allow this privilege decision.", "eligibility": eligibility},
            )

    decision = QualityPrivilegeDecision(
        amo_id=ctx.amo_id,
        privilege_id=privilege.id,
        decision_type=payload.decision_type,
        resulting_status=resulting_status,
        rationale=payload.rationale.strip(),
        eligibility_snapshot=eligibility,
        source_references=payload.source_references,
        effective_from=payload.effective_from,
        expires_on=payload.expires_on,
        decided_by_user_id=ctx.user_id,
        decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    privilege.status = resulting_status
    if payload.effective_from is not None:
        privilege.effective_from = payload.effective_from
    if payload.expires_on is not None:
        privilege.expires_on = payload.expires_on
    privilege.latest_decision_id = decision.id
    privilege.updated_by_user_id = ctx.user_id
    privilege.updated_at = _utcnow()
    db.commit()
    db.refresh(privilege)
    return {"privilege": _privilege_dict(privilege), "decision": _decision_dict(decision)}


@router.post("/independence", status_code=status.HTTP_201_CREATED)
def declare_independence(
    payload: IndependenceCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _person(db, amo_id=ctx.amo_id, user_id=payload.user_id)
    existing = db.query(QualityIndependenceDeclaration.id).filter(
        QualityIndependenceDeclaration.amo_id == ctx.amo_id,
        QualityIndependenceDeclaration.user_id == payload.user_id,
        QualityIndependenceDeclaration.context_type == payload.context_type,
        QualityIndependenceDeclaration.context_id == payload.context_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="An independence declaration already exists for this person and context. Preserve it and create a new governed assignment/context if circumstances change.",
        )
    if payload.declaration == "CONFLICT" and not (payload.relationship_to_subject or "").strip():
        raise HTTPException(status_code=422, detail="A conflict declaration must describe the relationship to the audit subject.")
    row = QualityIndependenceDeclaration(
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_id=payload.context_id,
        declaration=payload.declaration,
        relationship_to_subject=payload.relationship_to_subject,
        rationale=payload.rationale.strip(),
        source_references=payload.source_references,
        declared_by_user_id=ctx.user_id,
        declared_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "context_type": row.context_type,
        "context_id": row.context_id,
        "declaration": row.declaration,
        "relationship_to_subject": row.relationship_to_subject,
        "rationale": row.rationale,
        "source_references": row.source_references,
        "declared_by_user_id": row.declared_by_user_id,
        "declared_at": row.declared_at,
    }
