from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, noload, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.database import get_read_db, get_write_db
from amodb.user_id import generate_user_id

from . import models as qms_models
from .people_authorization_models import (
    QualityAppointment,
    QualityAuthorizationCase,
    QualityAuthorizationCaseEvent,
    QualityAuthorizationEvidence,
    QualityAuthorizationReview,
    QualityControlledExemption,
)
from .people_competence import cap_privilege_expires_on, evaluate_qms_competence_for_privilege
from .people_models import QualityPrivilege, QualityPrivilegeDecision, QualityPrivilegeRule
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    has_quality_permission,
    require_quality_permission,
    require_quality_write_permission,
    set_postgres_tenant_context,
)


router = APIRouter(prefix="/people", tags=["Quality authorization control"])

CaseStatus = Literal[
    "NOMINATED", "UNDER_REVIEW", "DEVELOPMENT", "AWAITING_EVIDENCE",
    "READY_FOR_DECISION", "RETURNED", "APPROVED", "REJECTED", "CANCELLED",
]
CaseDecision = Literal["APPROVE", "REJECT", "RETURN"]
LifecycleDecision = Literal["SUSPEND", "REVOKE", "REINSTATE", "RENEW"]
ReviewOutcome = Literal["CONTINUE", "CONTINUE_WITH_CONDITIONS", "SUSPEND", "REVOKE", "REQUIRES_ACTION"]
EvidenceType = Literal[
    "TRAINING_RECORD", "COMPETENCE_ASSESSMENT", "PRIOR_AUTHORIZATION",
    "AUDIT_EXPERIENCE", "COMPETENCE_PACKAGE", "ANNUAL_REVIEW",
    "CONTROLLED_EXEMPTION", "APPOINTMENT_LETTER", "OTHER",
]
OBSERVER_AUDIT_DEVELOPMENT_TARGET = 3
MANAGEMENT_CASE_STATUSES = {"NOMINATED", "UNDER_REVIEW", "DEVELOPMENT", "AWAITING_EVIDENCE", "READY_FOR_DECISION", "RETURNED"}
TERMINAL_CASE_STATUSES = {"APPROVED", "REJECTED", "CANCELLED"}


class AuthorizationCaseCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    requested_rule_id: str = Field(min_length=1, max_length=36)
    requested_scope_key: str = Field(default="GLOBAL", max_length=255)
    requested_scope: dict[str, Any] = Field(default_factory=dict)
    nomination_reason: str = Field(min_length=8, max_length=4000)


class AuthorizationCaseBatchCreate(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=100)
    requested_rule_id: str = Field(min_length=1, max_length=36)
    nomination_reason: str = Field(min_length=8, max_length=4000)


class AuthorizationCasePrepare(BaseModel):
    status: Literal["UNDER_REVIEW", "DEVELOPMENT", "AWAITING_EVIDENCE", "RETURNED"] | None = None
    recommendation: str | None = Field(default=None, max_length=8000)
    reason: str = Field(min_length=8, max_length=4000)


class AuthorizationCaseSubmit(BaseModel):
    recommendation: str = Field(min_length=8, max_length=8000)
    reason: str = Field(min_length=8, max_length=4000)


class AuthorizationCaseDecisionCreate(BaseModel):
    decision: CaseDecision
    reason: str = Field(min_length=12, max_length=8000)
    effective_from: date | None = None
    expires_on: date | None = None
    next_review_due: date | None = None
    incomplete_development_basis: str | None = Field(default=None, max_length=8000)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    confirmed: bool = False


class LifecycleDecisionCreate(BaseModel):
    decision: LifecycleDecision
    reason: str = Field(min_length=12, max_length=8000)
    effective_date: date
    expires_on: date | None = None
    next_review_due: date | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    confirmed: bool = False


class AuthorizationReviewCreate(BaseModel):
    review_outcome: ReviewOutcome
    review_reason: str = Field(min_length=12, max_length=8000)
    next_review_due: date | None = None
    review_evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    review_notes: str | None = Field(default=None, max_length=8000)
    confirmed: bool = False


class EvidenceReferenceCreate(BaseModel):
    evidence_type: EvidenceType
    label: str = Field(min_length=2, max_length=255)
    source_module: str | None = Field(default=None, max_length=64)
    source_reference: dict[str, Any] = Field(default_factory=dict)


class ControlledExemptionCreate(BaseModel):
    criterion: str = Field(min_length=2, max_length=255)
    reason_normal_compliance_impossible: str = Field(min_length=12, max_length=8000)
    equivalent_evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    limitations: list[Any] = Field(default_factory=list, max_length=100)
    supervision_required: bool = False
    supervisor_user_id: str | None = Field(default=None, max_length=36)
    conditions: list[Any] = Field(default_factory=list, max_length=100)
    effective_from: date
    expires_on: date
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    confirmed: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _person_name(user: account_models.User | None) -> str:
    if user is None:
        return "Person unavailable"
    return (
        str(getattr(user, "full_name", "") or "").strip()
        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        or str(getattr(user, "email", "") or "").strip()
        or "Person unavailable"
    )


def _actor_names(db: Session, *, amo_id: str, ids: set[str]) -> dict[str, str]:
    clean = {str(item) for item in ids if item}
    if not clean:
        return {}
    rows = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_(clean),
    ).all()
    return {str(row.id): _person_name(row) for row in rows}


def _person(db: Session, *, amo_id: str, user_id: str, active_only: bool = False) -> account_models.User:
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_system_account.is_(False),
    )
    if active_only:
        query = query.filter(account_models.User.is_active.is_(True))
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Person not found in this AMO.")
    return row


def _rule(db: Session, *, amo_id: str, rule_id: str) -> QualityPrivilegeRule:
    row = db.query(QualityPrivilegeRule).filter(
        QualityPrivilegeRule.amo_id == amo_id,
        QualityPrivilegeRule.id == rule_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Quality authorization type not found.")
    return row


def _case(db: Session, *, amo_id: str, case_id: str, lock: bool = False) -> QualityAuthorizationCase:
    query = db.query(QualityAuthorizationCase).options(
        selectinload(QualityAuthorizationCase.current_privilege)
    ).filter(
        QualityAuthorizationCase.amo_id == amo_id,
        QualityAuthorizationCase.id == case_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Authorization case not found.")
    return row


def _privilege(db: Session, *, amo_id: str, privilege_id: str, lock: bool = False) -> QualityPrivilege:
    query = db.query(QualityPrivilege).options(
        noload(QualityPrivilege.rule),
        selectinload(QualityPrivilege.decisions),
    ).filter(
        QualityPrivilege.amo_id == amo_id,
        QualityPrivilege.id == privilege_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Quality authorization not found.")
    return row


def _scope_schema(rule: QualityPrivilegeRule) -> dict[str, Any]:
    return dict(rule.scope_schema or {}) if isinstance(rule.scope_schema, dict) else {}


def _developmental(rule: QualityPrivilegeRule) -> bool:
    return rule.privilege_type == "AUDITOR" and _scope_schema(rule).get("supervised_development") is True


def _authorization_label(rule: QualityPrivilegeRule) -> str:
    if rule.privilege_type == "LEAD_AUDITOR":
        return "Lead Auditor"
    if rule.privilege_type == "AUDITOR":
        return "Observer / Trainee Auditor" if _developmental(rule) else "Auditor"
    if rule.privilege_type == "QUALITY_INSPECTOR":
        return "Quality Assurance Inspector"
    if rule.privilege_type == "AUTHORIZATION_REVIEWER":
        return "Quality Authorization Reviewer"
    return str(rule.title or "Quality authorization")


def _appointment_title(rule: QualityPrivilegeRule) -> str:
    if rule.privilege_type == "LEAD_AUDITOR":
        return "Lead Internal Quality Auditor"
    if rule.privilege_type == "AUDITOR":
        return "Observer / Trainee Auditor" if _developmental(rule) else "Internal Quality Auditor"
    return _authorization_label(rule)


def _person_snapshot(db: Session, user: account_models.User) -> dict[str, Any]:
    department_name = None
    department_id = getattr(user, "department_id", None)
    if department_id:
        department = db.query(account_models.Department).filter(
            account_models.Department.amo_id == user.amo_id,
            account_models.Department.id == department_id,
        ).first()
        department_name = getattr(department, "name", None) if department else None
    return {
        "name": _person_name(user),
        "home_role": _enum(getattr(user, "role", None)) or None,
        "department": department_name,
        "staff_code": getattr(user, "staff_code", None),
        "active": bool(getattr(user, "is_active", False)),
    }


def _privilege_snapshot(row: QualityPrivilege | None, rule: QualityPrivilegeRule | None = None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "authorization": _authorization_label(rule) if rule else None,
        "status": row.status,
        "scope": "Global" if str(row.scope_key or "").upper() == "GLOBAL" else str(row.scope_key or ""),
        "limitations": list(row.limitations or []),
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "expires_on": row.expires_on.isoformat() if row.expires_on else None,
    }


def _audit_participation(db: Session, *, amo_id: str, user_id: str) -> dict[str, Any]:
    audits = (
        db.query(qms_models.QMSAudit)
        .filter(
            qms_models.QMSAudit.amo_id == amo_id,
            qms_models.QMSAudit.deleted_at.is_(None),
            (
                (qms_models.QMSAudit.lead_auditor_user_id == user_id)
                | (qms_models.QMSAudit.observer_auditor_user_id == user_id)
                | (qms_models.QMSAudit.assistant_auditor_user_id == user_id)
            ),
        )
        .order_by(qms_models.QMSAudit.planned_start.desc().nullslast(), qms_models.QMSAudit.created_at.desc())
        .limit(100)
        .all()
    )
    items: list[dict[str, Any]] = []
    observed_completed = 0
    for audit in audits:
        roles: list[str] = []
        if audit.lead_auditor_user_id == user_id:
            roles.append("Lead Auditor")
        if audit.observer_auditor_user_id == user_id:
            roles.append("Observer / Trainee Auditor")
            if audit.actual_end is not None:
                observed_completed += 1
        if audit.assistant_auditor_user_id == user_id:
            roles.append("Assistant Auditor")
        items.append({
            "reference": audit.audit_ref,
            "title": audit.title,
            "status": _enum(audit.status),
            "roles": roles,
            "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
            "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
            "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
        })
    return {"items": items, "observed_completed": observed_completed, "observed_target": OBSERVER_AUDIT_DEVELOPMENT_TARGET}


def _affected_assignments(db: Session, *, amo_id: str, user_id: str) -> list[dict[str, Any]]:
    today = date.today()
    audits = (
        db.query(qms_models.QMSAudit)
        .filter(
            qms_models.QMSAudit.amo_id == amo_id,
            qms_models.QMSAudit.deleted_at.is_(None),
            qms_models.QMSAudit.actual_end.is_(None),
            or_(qms_models.QMSAudit.planned_end.is_(None), qms_models.QMSAudit.planned_end >= today),
            (
                (qms_models.QMSAudit.lead_auditor_user_id == user_id)
                | (qms_models.QMSAudit.observer_auditor_user_id == user_id)
                | (qms_models.QMSAudit.assistant_auditor_user_id == user_id)
            ),
        )
        .order_by(qms_models.QMSAudit.planned_start.asc().nullslast())
        .limit(50)
        .all()
    )
    out: list[dict[str, Any]] = []
    for audit in audits:
        if audit.lead_auditor_user_id == user_id:
            role = "Lead Auditor"
        elif audit.assistant_auditor_user_id == user_id:
            role = "Assistant Auditor"
        else:
            role = "Observer / Trainee Auditor"
        out.append({
            "reference": audit.audit_ref,
            "title": audit.title,
            "role": role,
            "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
            "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
        })
    return out


def _training_projection(training: dict[str, Any], *, developmental: bool) -> dict[str, Any]:
    satisfied = {str(code).upper() for code in training.get("satisfied") or []}
    expired = {str(code).upper() for code in training.get("expired") or []}
    rows = [row for row in (training.get("tracked_records") or training.get("records") or []) if isinstance(row, dict)]
    validity: dict[str, str | None] = {}
    for row in rows:
        code = str(row.get("course_code") or "").upper()
        if code and code not in validity:
            validity[code] = row.get("valid_until")
    required = [str(code) for code in training.get("required") or []]
    courses = []
    for code in required:
        upper = code.upper()
        if upper in satisfied:
            state = "Current"
        elif upper in expired:
            state = "Expired"
        else:
            state = "Incomplete"
        courses.append({"course": code, "status": state, "valid_until": validity.get(upper)})
    passed = bool(training.get("passed"))
    label = "Current" if passed else ("Due" if expired else "Incomplete")
    return {
        "status": label,
        "current": passed,
        "developmental_exception": developmental and not passed,
        "courses": courses,
        "required": required,
        "missing": [str(code) for code in training.get("missing") or []],
    }


def _active_exemption(
    db: Session,
    *,
    amo_id: str,
    privilege_id: str | None = None,
    case_id: str | None = None,
    as_of: date | None = None,
) -> QualityControlledExemption | None:
    day = as_of or date.today()
    query = db.query(QualityControlledExemption).filter(
        QualityControlledExemption.amo_id == amo_id,
        QualityControlledExemption.status == "ACTIVE",
        QualityControlledExemption.effective_from <= day,
        QualityControlledExemption.expires_on >= day,
    )
    if case_id:
        query = query.filter(QualityControlledExemption.case_id == case_id)
    elif privilege_id:
        query = query.filter(QualityControlledExemption.privilege_id == privilege_id)
    else:
        return None
    return query.order_by(QualityControlledExemption.expires_on.desc()).first()


def _latest_review(db: Session, *, amo_id: str, privilege_id: str | None) -> QualityAuthorizationReview | None:
    if not privilege_id:
        return None
    return (
        db.query(QualityAuthorizationReview)
        .filter(
            QualityAuthorizationReview.amo_id == amo_id,
            QualityAuthorizationReview.privilege_id == privilege_id,
        )
        .order_by(QualityAuthorizationReview.reviewed_at.desc())
        .first()
    )


def _evidence_rows(db: Session, *, amo_id: str, case_id: str | None = None, privilege_id: str | None = None) -> list[QualityAuthorizationEvidence]:
    query = db.query(QualityAuthorizationEvidence).filter(
        QualityAuthorizationEvidence.amo_id == amo_id,
        QualityAuthorizationEvidence.status == "ACTIVE",
    )
    if case_id:
        query = query.filter(QualityAuthorizationEvidence.case_id == case_id)
    elif privilege_id:
        query = query.filter(QualityAuthorizationEvidence.privilege_id == privilege_id)
    else:
        return []
    return query.order_by(QualityAuthorizationEvidence.created_at.desc()).all()


def _evidence_dict(row: QualityAuthorizationEvidence) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "type": row.evidence_type,
        "label": row.label,
        "source_module": row.source_module,
        "source_reference": row.source_reference or {},
        "has_file": bool(row.storage_path),
        "filename": row.original_filename,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _exemption_dict(row: QualityControlledExemption | None, names: dict[str, str] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    names = names or {}
    return {
        "id": str(row.id),
        "status": row.status,
        "authorization": row.authorization_type,
        "criterion": row.criterion,
        "reason": row.reason_normal_compliance_impossible,
        "equivalent_evidence": list(row.equivalent_evidence or []),
        "limitations": list(row.limitations or []),
        "supervision_required": bool(row.supervision_required),
        "supervisor": names.get(str(row.supervisor_user_id)) if row.supervisor_user_id else None,
        "conditions": list(row.conditions or []),
        "effective_from": row.effective_from.isoformat(),
        "expires_on": row.expires_on.isoformat(),
        "approved_by": names.get(str(row.approved_by_user_id), "Recorded decision authority"),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


def _readiness(
    db: Session,
    *,
    amo_id: str,
    user: account_models.User,
    rule: QualityPrivilegeRule,
    privilege: QualityPrivilege | None = None,
    case: QualityAuthorizationCase | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    day = as_of or date.today()
    developmental = _developmental(rule)
    training = evaluate_qms_competence_for_privilege(
        db,
        amo_id=amo_id,
        user_id=str(user.id),
        rule=rule,
        as_of=day,
    )
    training_projection = _training_projection(training, developmental=developmental)
    participation = _audit_participation(db, amo_id=amo_id, user_id=str(user.id))
    exemption = _active_exemption(
        db,
        amo_id=amo_id,
        privilege_id=str(privilege.id) if privilege else None,
        case_id=str(case.id) if case else None,
        as_of=day,
    )
    blockers: list[dict[str, str]] = []
    if not bool(user.is_active):
        blockers.append({"code": "workforce_inactive", "message": "The person is not active in Workforce."})
    if not bool(rule.is_active):
        blockers.append({"code": "authorization_type_inactive", "message": "This Quality authorization type is inactive."})
    if not developmental and not bool(training.get("passed")):
        if exemption is None or exemption.criterion not in {"training_current_verified", "required_training", "competence_currency"}:
            blockers.append({"code": "training_current_verified", "message": "Required Training is not currently verified and current."})
    if privilege is not None and privilege.status == "REVOKED":
        blockers.append({"code": "authorization_revoked", "message": "A revoked authorization cannot be reinstated; create a new authorization case."})
    latest_review = _latest_review(db, amo_id=amo_id, privilege_id=str(privilege.id) if privilege else None)
    review = None
    if latest_review:
        review = {
            "last_reviewed": latest_review.last_reviewed.isoformat(),
            "next_review_due": latest_review.next_review_due.isoformat() if latest_review.next_review_due else None,
            "outcome": latest_review.review_outcome,
            "reason": latest_review.review_reason,
            "reviewed_at": latest_review.reviewed_at.isoformat() if latest_review.reviewed_at else None,
        }
    return {
        "authorization": _authorization_label(rule),
        "as_of": day.isoformat(),
        "status": "Blocked" if blockers else ("In development" if developmental else "Ready for decision"),
        "hard_blockers": blockers,
        "training": training_projection,
        "development": {
            "observed_audits": participation["observed_completed"],
            "target": OBSERVER_AUDIT_DEVELOPMENT_TARGET,
            "progress_label": f"{participation['observed_completed']} / {OBSERVER_AUDIT_DEVELOPMENT_TARGET}",
            "target_is_hard_gate": False,
            "supervision_required": developmental,
            "audit_participation": participation["items"],
        },
        "annual_review": review,
        "controlled_exemption": _exemption_dict(exemption),
        "affected_assignments": _affected_assignments(db, amo_id=amo_id, user_id=str(user.id)),
    }


def _case_event(
    db: Session,
    *,
    ctx: TenantContext,
    row: QualityAuthorizationCase,
    action: str,
    previous_status: str | None,
    reason: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> QualityAuthorizationCaseEvent:
    event = QualityAuthorizationCaseEvent(
        amo_id=ctx.amo_id,
        case_id=row.id,
        action=action,
        previous_status=previous_status,
        new_status=row.status,
        reason=reason.strip(),
        before_snapshot=before or {},
        after_snapshot=after or {},
        source_references=source_references or [],
        actor_user_id=ctx.user_id,
        occurred_at=_utcnow(),
    )
    db.add(event)
    db.add(audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.authorization.case",
        entity_id=str(row.id),
        action=action,
        actor_user_id=ctx.user_id,
        before=before or {"status": previous_status},
        after=after or {"status": row.status},
        metadata_json={
            "module": "quality",
            "caseStatus": row.status,
            "reason": reason.strip(),
            "authorizationType": (row.requested_authorization_snapshot or {}).get("authorization"),
        },
    ))
    return event


def _decision_event(
    db: Session,
    *,
    ctx: TenantContext,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    reason: str,
) -> None:
    db.add(audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=ctx.user_id,
        before=before,
        after=after,
        metadata_json={"module": "quality", "reason": reason.strip()},
    ))


def _permissions(db: Session, ctx: TenantContext) -> dict[str, bool]:
    return {
        "can_view": has_quality_permission(db, ctx, "qms.people.view"),
        "can_prepare": has_quality_permission(db, ctx, "qms.authorization.prepare"),
        "can_approve": has_quality_permission(db, ctx, "qms.authorization.approve"),
        "can_review": has_quality_permission(db, ctx, "qms.authorization.review"),
        "can_approve_exemption": has_quality_permission(db, ctx, "qms.authorization.exemption.approve"),
        "can_manage_policy": has_quality_permission(db, ctx, "qms.authorization.policy.manage"),
        "can_oversight": has_quality_permission(db, ctx, "qms.authorization.oversight"),
    }


def _management_access(db: Session, ctx: TenantContext) -> bool:
    perms = _permissions(db, ctx)
    return any(perms[key] for key in ("can_prepare", "can_approve", "can_review", "can_manage_policy", "can_oversight"))


def _case_summary(
    db: Session,
    *,
    amo_id: str,
    row: QualityAuthorizationCase,
    names: dict[str, str],
) -> dict[str, Any]:
    rule = row.requested_rule or _rule(db, amo_id=amo_id, rule_id=str(row.requested_rule_id))
    return {
        "id": str(row.id),
        "person": (row.person_snapshot or {}).get("name") or names.get(str(row.user_id), "Person unavailable"),
        "home_role": (row.person_snapshot or {}).get("home_role"),
        "department": (row.person_snapshot or {}).get("department"),
        "authorization": _authorization_label(rule),
        "case_type": row.case_type,
        "status": row.status,
        "nomination_date": row.nomination_date.isoformat(),
        "nominator": names.get(str(row.nominated_by_user_id), "Recorded nominator"),
        "recommendation": row.recommendation,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "next_action": (
            "Decision required" if row.status == "READY_FOR_DECISION"
            else "Evidence / preparation" if row.status in {"NOMINATED", "UNDER_REVIEW", "DEVELOPMENT", "AWAITING_EVIDENCE", "RETURNED"}
            else "Complete"
        ),
    }


def _review_dict(row: QualityAuthorizationReview, names: dict[str, str], authorization: str | None = None, person: str | None = None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "person": person,
        "authorization": authorization,
        "last_reviewed": row.last_reviewed.isoformat(),
        "next_review_due": row.next_review_due.isoformat() if row.next_review_due else None,
        "outcome": row.review_outcome,
        "reason": row.review_reason,
        "reviewed_by": names.get(str(row.reviewed_by_user_id), "Recorded reviewer"),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "notes": row.review_notes,
        "evidence": list(row.review_evidence or []),
    }


