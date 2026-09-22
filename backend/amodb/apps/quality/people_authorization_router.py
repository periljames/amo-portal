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


@router.get("/authorization-workspace")
def authorization_workspace(
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    perms = _permissions(db, ctx)
    management = _management_access(db, ctx)

    user_query = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_system_account.is_(False),
    )
    if not management:
        user_query = user_query.filter(account_models.User.id == ctx.user_id)
    users = user_query.order_by(account_models.User.full_name.asc()).limit(1000).all()
    names = {str(user.id): _person_name(user) for user in users}

    rules = db.query(QualityPrivilegeRule).filter(
        QualityPrivilegeRule.amo_id == ctx.amo_id,
    ).order_by(QualityPrivilegeRule.title.asc()).all()
    rules_by_id = {str(rule.id): rule for rule in rules}

    privileges_query = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id)
    if not management:
        privileges_query = privileges_query.filter(QualityPrivilege.user_id == ctx.user_id)
    privileges = privileges_query.order_by(QualityPrivilege.updated_at.desc()).all()
    current_by_user: dict[str, QualityPrivilege] = {}
    for item in privileges:
        if item.status in {"ACTIVE", "SUSPENDED"} and str(item.user_id) not in current_by_user:
            current_by_user[str(item.user_id)] = item

    appointment_query = db.query(QualityAppointment).filter(
        QualityAppointment.amo_id == ctx.amo_id,
        QualityAppointment.status == "ACTIVE",
    )
    if not management:
        appointment_query = appointment_query.filter(QualityAppointment.user_id == ctx.user_id)
    appointment_by_user = {str(row.user_id): row for row in appointment_query.all()}

    latest_reviews: dict[str, QualityAuthorizationReview] = {}
    review_query = db.query(QualityAuthorizationReview).filter(QualityAuthorizationReview.amo_id == ctx.amo_id)
    if not management and privileges:
        review_query = review_query.filter(QualityAuthorizationReview.privilege_id.in_([row.id for row in privileges]))
    for review in review_query.order_by(QualityAuthorizationReview.reviewed_at.desc()).all():
        latest_reviews.setdefault(str(review.privilege_id), review)

    people = []
    today = date.today()
    for user in users:
        current = current_by_user.get(str(user.id))
        rule = rules_by_id.get(str(current.rule_id)) if current else None
        appointment = appointment_by_user.get(str(user.id))
        review = latest_reviews.get(str(current.id)) if current else None
        review_due = review.next_review_due if review else None
        if review_due and review_due < today:
            next_action = "Authorization review overdue"
        elif current and current.status == "SUSPENDED":
            next_action = "Reassessment required"
        elif current and current.expires_on and current.expires_on <= today:
            next_action = "Authorization expired"
        elif current:
            next_action = "Monitor"
        else:
            next_action = "Nominate / prepare case" if perms["can_prepare"] else "No active Quality authorization"
        people.append({
            "user_id": str(user.id),
            "name": _person_name(user),
            "home_role": _enum(user.role) or None,
            "department": _person_snapshot(db, user).get("department"),
            "quality_function": appointment.title if appointment else (_appointment_title(rule) if rule else None),
            "authorization": _authorization_label(rule) if rule else None,
            "authorization_id": str(current.id) if current else None,
            "status": current.status if current else "NOT_AUTHORIZED",
            "scope": "Global" if current and str(current.scope_key).upper() == "GLOBAL" else (str(current.scope_key) if current else None),
            "expires_on": current.expires_on.isoformat() if current and current.expires_on else None,
            "review_due": review_due.isoformat() if review_due else None,
            "next_action": next_action,
        })

    case_query = db.query(QualityAuthorizationCase).options(selectinload(QualityAuthorizationCase.requested_rule)).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
    )
    if not management:
        case_query = case_query.filter(QualityAuthorizationCase.user_id == ctx.user_id)
    cases = case_query.order_by(QualityAuthorizationCase.updated_at.desc()).limit(500).all()
    case_actor_ids = {
        str(value)
        for row in cases
        for value in (row.nominated_by_user_id, row.recommendation_by_user_id, row.decided_by_user_id)
        if value
    }
    names.update(_actor_names(db, amo_id=ctx.amo_id, ids=case_actor_ids))
    case_items = [_case_summary(db, amo_id=ctx.amo_id, row=row, names=names) for row in cases]

    active = sum(1 for row in privileges if row.status == "ACTIVE")
    suspended = sum(1 for row in privileges if row.status == "SUSPENDED")
    ready = sum(1 for row in cases if row.status == "READY_FOR_DECISION")
    development = sum(1 for row in cases if row.status == "DEVELOPMENT")
    reviews_due = sum(1 for review in latest_reviews.values() if review.next_review_due and review.next_review_due <= today)
    conditional_query = db.query(QualityControlledExemption).filter(
        QualityControlledExemption.amo_id == ctx.amo_id,
        QualityControlledExemption.status == "ACTIVE",
        QualityControlledExemption.effective_from <= today,
        QualityControlledExemption.expires_on >= today,
    )
    if not management:
        conditional_query = conditional_query.filter(QualityControlledExemption.person_user_id == ctx.user_id)
    conditional = conditional_query.count()

    action_required = []
    for item in case_items:
        if item["status"] in {"READY_FOR_DECISION", "AWAITING_EVIDENCE", "RETURNED", "DEVELOPMENT"}:
            action_required.append({
                "person": item["person"],
                "authorization": item["authorization"],
                "issue": item["next_action"],
                "due": None,
                "case_id": item["id"],
            })
    for person in people:
        if person["next_action"] not in {"Monitor", "No active Quality authorization"}:
            action_required.append({
                "person": person["name"],
                "authorization": person["authorization"] or "Quality authorization",
                "issue": person["next_action"],
                "due": person["review_due"] or person["expires_on"],
                "authorization_id": person["authorization_id"],
            })

    return {
        "permissions": perms,
        "overview": {
            "active_authorizations": active,
            "ready_for_decision": ready,
            "reviews_due": reviews_due,
            "suspended": suspended,
            "in_development": development,
            "conditional_authorizations": conditional,
            "action_required": action_required[:100],
        },
        "people": people,
        "cases": case_items,
        "rules": [
            {
                "id": str(rule.id),
                "title": _authorization_label(rule),
                "description": rule.description,
                "privilege_type": rule.privilege_type,
                "is_active": bool(rule.is_active),
                "scope": "Global",
                "developmental": _developmental(rule),
            }
            for rule in rules
        ],
    }


@router.get("/authorization-cases")
def list_authorization_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    management = _management_access(db, ctx)
    query = db.query(QualityAuthorizationCase).options(selectinload(QualityAuthorizationCase.requested_rule)).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
    )
    if not management:
        query = query.filter(QualityAuthorizationCase.user_id == ctx.user_id)
    if status_filter:
        query = query.filter(QualityAuthorizationCase.status == status_filter.upper())
    rows = query.order_by(QualityAuthorizationCase.updated_at.desc()).limit(500).all()
    names = _actor_names(
        db,
        amo_id=ctx.amo_id,
        ids={str(value) for row in rows for value in (row.user_id, row.nominated_by_user_id) if value},
    )
    return {"items": [_case_summary(db, amo_id=ctx.amo_id, row=row, names=names) for row in rows]}


@router.post("/authorization-cases", status_code=status.HTTP_201_CREATED)
def create_authorization_case(
    payload: AuthorizationCaseCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    user = _person(db, amo_id=ctx.amo_id, user_id=payload.user_id, active_only=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.requested_rule_id)
    if not rule.is_active:
        raise HTTPException(status_code=422, detail="Choose an active Quality authorization type.")
    scope_key = str(payload.requested_scope_key or "GLOBAL").strip().upper()
    if scope_key != "GLOBAL":
        raise HTTPException(status_code=422, detail="Only the governed Global authorization scope is currently available.")

    current = None
    if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        rank_rule_ids = [
            item[0] for item in db.query(QualityPrivilegeRule.id).filter(
                QualityPrivilegeRule.amo_id == ctx.amo_id,
                QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]),
            ).all()
        ]
        current = db.query(QualityPrivilege).filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id == user.id,
            QualityPrivilege.scope_key == scope_key,
            QualityPrivilege.rule_id.in_(rank_rule_ids),
            QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
        ).first()
    if current is None:
        current = db.query(QualityPrivilege).filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id == user.id,
            QualityPrivilege.rule_id == rule.id,
            QualityPrivilege.scope_key == scope_key,
            QualityPrivilege.status.in_(["DRAFT", "ACTIVE", "SUSPENDED"]),
        ).first()

    case_type = "NEW_AUTHORIZATION"
    if current:
        case_type = "CHANGE_AUTHORIZATION" if str(current.rule_id) != str(rule.id) else ("REINSTATEMENT" if current.status == "SUSPENDED" else "RENEWAL")

    open_case = db.query(QualityAuthorizationCase).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
        QualityAuthorizationCase.user_id == user.id,
        QualityAuthorizationCase.status.in_(list(MANAGEMENT_CASE_STATUSES)),
    ).first()
    if open_case:
        raise HTTPException(status_code=409, detail="This person already has an open Quality authorization case. Continue that case instead of creating a duplicate.")

    current_rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(current.rule_id)) if current else None
    row = QualityAuthorizationCase(
        amo_id=ctx.amo_id,
        user_id=user.id,
        current_privilege_id=current.id if current else None,
        requested_rule_id=rule.id,
        case_type=case_type,
        status="NOMINATED",
        requested_scope_key=scope_key,
        requested_scope=payload.requested_scope,
        nomination_date=date.today(),
        nominated_by_user_id=ctx.user_id,
        person_snapshot=_person_snapshot(db, user),
        current_authorization_snapshot=_privilege_snapshot(current, current_rule),
        requested_authorization_snapshot={
            "authorization": _authorization_label(rule),
            "quality_function": _appointment_title(rule),
            "scope": "Global",
            "developmental": _developmental(rule),
        },
        source_references=[],
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=current, case=row)
    row.readiness_snapshot = readiness
    _case_event(
        db, ctx=ctx, row=row, action="NOMINATED", previous_status=None,
        reason=payload.nomination_reason,
        after={"status": row.status, "authorization": _authorization_label(rule)},
    )
    db.commit()
    return {"case_id": str(row.id), "status": row.status, "readiness": readiness}


@router.post("/authorization-cases/batch", status_code=status.HTTP_201_CREATED)
def create_authorization_cases_batch(
    payload: AuthorizationCaseBatchCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Batch nomination creates individual cases only; it never grants authorization."""

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.requested_rule_id)
    if not rule.is_active:
        raise HTTPException(status_code=422, detail="Choose an active Quality authorization type.")
    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for user_id in dict.fromkeys(payload.user_ids):
        user = db.query(account_models.User).filter(
            account_models.User.amo_id == ctx.amo_id,
            account_models.User.id == user_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).first()
        if user is None:
            skipped.append({"person": "Unavailable person", "reason": "Inactive or not found in this AMO."})
            continue
        open_case = db.query(QualityAuthorizationCase).filter(
            QualityAuthorizationCase.amo_id == ctx.amo_id,
            QualityAuthorizationCase.user_id == user.id,
            QualityAuthorizationCase.status.in_(list(MANAGEMENT_CASE_STATUSES)),
        ).first()
        if open_case:
            skipped.append({"person": _person_name(user), "reason": "An open authorization case already exists."})
            continue
        row = QualityAuthorizationCase(
            amo_id=ctx.amo_id,
            user_id=user.id,
            requested_rule_id=rule.id,
            case_type="NEW_AUTHORIZATION",
            status="NOMINATED",
            requested_scope_key="GLOBAL",
            requested_scope={},
            nomination_date=date.today(),
            nominated_by_user_id=ctx.user_id,
            person_snapshot=_person_snapshot(db, user),
            current_authorization_snapshot={},
            requested_authorization_snapshot={
                "authorization": _authorization_label(rule),
                "quality_function": _appointment_title(rule),
                "scope": "Global",
                "developmental": _developmental(rule),
            },
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(row)
        db.flush()
        row.readiness_snapshot = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, case=row)
        _case_event(
            db, ctx=ctx, row=row, action="NOMINATED", previous_status=None,
            reason=payload.nomination_reason,
            after={"status": row.status, "authorization": _authorization_label(rule)},
        )
        created.append({"case_id": str(row.id), "person": _person_name(user)})
    db.commit()
    return {"created": created, "skipped": skipped, "granted": 0}


@router.get("/authorization-cases/{case_id}")
def get_authorization_case(
    case_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _case(db, amo_id=ctx.amo_id, case_id=case_id)
    if not _management_access(db, ctx) and str(row.user_id) != str(ctx.user_id):
        raise HTTPException(status_code=403, detail="This authorization case is not available to this user.")
    user = _person(db, amo_id=ctx.amo_id, user_id=str(row.user_id))
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(row.requested_rule_id))
    current = _privilege(db, amo_id=ctx.amo_id, privilege_id=str(row.current_privilege_id)) if row.current_privilege_id else None
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=current, case=row)
    evidence = _evidence_rows(db, amo_id=ctx.amo_id, case_id=str(row.id))
    events = db.query(QualityAuthorizationCaseEvent).filter(
        QualityAuthorizationCaseEvent.amo_id == ctx.amo_id,
        QualityAuthorizationCaseEvent.case_id == row.id,
    ).order_by(QualityAuthorizationCaseEvent.occurred_at.asc()).all()
    actor_ids = {
        str(value)
        for value in [row.nominated_by_user_id, row.recommendation_by_user_id, row.decided_by_user_id, *[event.actor_user_id for event in events]]
        if value
    }
    names = _actor_names(db, amo_id=ctx.amo_id, ids=actor_ids)
    return {
        "id": str(row.id),
        "person": _person_snapshot(db, user),
        "quality_function": (row.requested_authorization_snapshot or {}).get("quality_function") or _appointment_title(rule),
        "requested_authorization": _authorization_label(rule),
        "requested_scope": "Global",
        "case_type": row.case_type,
        "status": row.status,
        "nomination_date": row.nomination_date.isoformat(),
        "nominator": names.get(str(row.nominated_by_user_id), "Recorded nominator"),
        "current_authorization": _privilege_snapshot(current, _rule(db, amo_id=ctx.amo_id, rule_id=str(current.rule_id)) if current else None),
        "readiness": readiness,
        "evidence": [_evidence_dict(item) for item in evidence],
        "recommendation": row.recommendation,
        "recommended_by": names.get(str(row.recommendation_by_user_id)) if row.recommendation_by_user_id else None,
        "decision": row.decision,
        "decision_reason": row.decision_reason,
        "decided_by": names.get(str(row.decided_by_user_id)) if row.decided_by_user_id else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "expires_on": row.expires_on.isoformat() if row.expires_on else None,
        "next_review_due": row.next_review_due.isoformat() if row.next_review_due else None,
        "history": [
            {
                "action": event.action,
                "from": event.previous_status,
                "to": event.new_status,
                "reason": event.reason,
                "actor": names.get(str(event.actor_user_id), "Recorded actor"),
                "at": event.occurred_at.isoformat() if event.occurred_at else None,
            }
            for event in events
        ],
        "permissions": _permissions(db, ctx),
    }


@router.get("/authorization-control/overview")
def authorization_overview(
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    privileges = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
    ).all()
    open_cases = db.query(QualityAuthorizationCase).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
        QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
    ).all()
    active_exemptions = db.query(QualityControlledExemption).filter(
        QualityControlledExemption.amo_id == ctx.amo_id,
        QualityControlledExemption.status == "ACTIVE",
        QualityControlledExemption.expires_on >= today,
    ).count()
    due_reviews = db.query(QualityAuthorizationReview).filter(
        QualityAuthorizationReview.amo_id == ctx.amo_id,
        QualityAuthorizationReview.next_review_due.is_not(None),
        QualityAuthorizationReview.next_review_due <= today,
    ).count()
    status_counts = {"ACTIVE": 0, "SUSPENDED": 0, "REVOKED": 0, "EXPIRED": 0, "DRAFT": 0}
    expiring = 0
    for item in privileges:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        if item.status == "ACTIVE" and item.expires_on and today <= item.expires_on <= today.replace(year=today.year + 1):
            if (item.expires_on - today).days <= 60:
                expiring += 1
    attention = [
        {
            "type": "Authorization case",
            "person": (row.person_snapshot or {}).get("name") or "Person unavailable",
            "authorization": (row.requested_authorization_snapshot or {}).get("authorization"),
            "status": row.status,
            "reason": "Final Quality decision required" if row.status == "READY_FOR_DECISION" else "Case preparation is incomplete",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in sorted(open_cases, key=lambda item: item.updated_at or _utcnow(), reverse=True)[:12]
    ]
    return {
        "permissions": _permissions(db, ctx),
        "metrics": {
            "active_authorizations": status_counts.get("ACTIVE", 0),
            "suspended_authorizations": status_counts.get("SUSPENDED", 0),
            "expiring_within_60_days": expiring,
            "open_authorization_cases": len(open_cases),
            "reviews_due": due_reviews,
            "active_controlled_exemptions": active_exemptions,
        },
        "attention": attention,
    }


@router.get("/authorization-control/people")
def authorization_people(
    search: str | None = Query(default=None, max_length=100),
    include_inactive: bool = False,
    limit: int = Query(default=250, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_system_account.is_(False),
    )
    if not include_inactive:
        query = query.filter(account_models.User.is_active.is_(True))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(pattern),
            account_models.User.first_name.ilike(pattern),
            account_models.User.last_name.ilike(pattern),
            account_models.User.email.ilike(pattern),
            account_models.User.staff_code.ilike(pattern),
        ))
    users = query.order_by(account_models.User.full_name.asc()).limit(limit).all()
    user_ids = [str(row.id) for row in users]
    privileges = (
        db.query(QualityPrivilege, QualityPrivilegeRule)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id.in_(user_ids) if user_ids else False,
        )
        .all()
        if user_ids else []
    )
    privilege_by_user: dict[str, list[tuple[QualityPrivilege, QualityPrivilegeRule]]] = {}
    for privilege, rule in privileges:
        privilege_by_user.setdefault(str(privilege.user_id), []).append((privilege, rule))
    open_cases = (
        db.query(QualityAuthorizationCase)
        .filter(
            QualityAuthorizationCase.amo_id == ctx.amo_id,
            QualityAuthorizationCase.user_id.in_(user_ids) if user_ids else False,
            QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
        )
        .all()
        if user_ids else []
    )
    case_count: dict[str, int] = {}
    for row in open_cases:
        case_count[str(row.user_id)] = case_count.get(str(row.user_id), 0) + 1
    items: list[dict[str, Any]] = []
    for user in users:
        auths = privilege_by_user.get(str(user.id), [])
        active_auths = [
            {
                "authorization": _authorization_label(rule),
                "status": privilege.status,
                "scope": "Global" if str(privilege.scope_key or "").upper() == "GLOBAL" else privilege.scope_key,
                "expires_on": privilege.expires_on.isoformat() if privilege.expires_on else None,
            }
            for privilege, rule in auths
            if privilege.status in {"ACTIVE", "SUSPENDED"}
        ]
        items.append({
            "key": str(user.id),
            "name": _person_name(user),
            "staff_code": getattr(user, "staff_code", None),
            "home_role": _enum(getattr(user, "role", None)) or None,
            "department": _person_snapshot(db, user).get("department"),
            "workforce_status": "Active" if user.is_active else "Inactive",
            "authorizations": active_auths,
            "open_cases": case_count.get(str(user.id), 0),
        })
    return {"items": items, "total": len(items)}


@router.get("/authorization-control/people/{user_id}")
def authorization_person_detail(
    user_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    user = _person(db, amo_id=ctx.amo_id, user_id=user_id)
    rows = (
        db.query(QualityPrivilege, QualityPrivilegeRule)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.user_id == user_id)
        .order_by(QualityPrivilege.updated_at.desc())
        .all()
    )
    authorizations = []
    for privilege, rule in rows:
        readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=privilege)
        latest_review = _latest_review(db, amo_id=ctx.amo_id, privilege_id=str(privilege.id))
        authorizations.append({
            "key": str(privilege.id),
            **_privilege_snapshot(privilege, rule),
            "authorization": _authorization_label(rule),
            "readiness": readiness,
            "last_reviewed": latest_review.last_reviewed.isoformat() if latest_review else None,
            "next_review_due": latest_review.next_review_due.isoformat() if latest_review and latest_review.next_review_due else None,
        })
    cases = db.query(QualityAuthorizationCase).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
        QualityAuthorizationCase.user_id == user_id,
    ).order_by(QualityAuthorizationCase.created_at.desc()).limit(50).all()
    ids = {
        str(value)
        for row in cases
        for value in (row.nominated_by_user_id, row.recommendation_by_user_id, row.decided_by_user_id)
        if value
    }
    names = _actor_names(db, amo_id=ctx.amo_id, ids=ids)
    appointments = db.query(QualityAppointment).filter(
        QualityAppointment.amo_id == ctx.amo_id,
        QualityAppointment.user_id == user_id,
    ).order_by(QualityAppointment.created_at.desc()).all()
    return {
        "person": _person_snapshot(db, user),
        "appointments": [
            {
                "function": row.title,
                "status": row.status,
                "effective_from": row.effective_from.isoformat() if row.effective_from else None,
                "effective_until": row.effective_until.isoformat() if row.effective_until else None,
            }
            for row in appointments
        ],
        "authorizations": authorizations,
        "cases": [_case_summary(db, amo_id=ctx.amo_id, row=row, names=names) for row in cases],
        "audit_participation": _audit_participation(db, amo_id=ctx.amo_id, user_id=user_id),
    }


@router.get("/authorization-control/cases")
def list_authorization_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=250, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuthorizationCase).options(selectinload(QualityAuthorizationCase.requested_rule)).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
    )
    if status_filter:
        query = query.filter(QualityAuthorizationCase.status == status_filter.upper())
    rows = query.order_by(QualityAuthorizationCase.updated_at.desc()).limit(limit).all()
    if search and search.strip():
        term = search.strip().lower()
        rows = [
            row for row in rows
            if term in str((row.person_snapshot or {}).get("name") or "").lower()
            or term in str((row.requested_authorization_snapshot or {}).get("authorization") or "").lower()
            or term in str(row.status or "").lower()
        ]
    actor_ids = {
        str(value)
        for row in rows
        for value in (row.nominated_by_user_id, row.recommendation_by_user_id, row.decided_by_user_id)
        if value
    }
    names = _actor_names(db, amo_id=ctx.amo_id, ids=actor_ids)
    return {"items": [_case_summary(db, amo_id=ctx.amo_id, row=row, names=names) for row in rows], "total": len(rows)}


@router.post("/authorization-control/cases", status_code=status.HTTP_201_CREATED)
def create_authorization_case(
    payload: AuthorizationCaseCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    user = _person(db, amo_id=ctx.amo_id, user_id=payload.user_id, active_only=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.requested_rule_id)
    if not rule.is_active:
        raise HTTPException(status_code=409, detail="This Quality authorization type is inactive.")
    existing_case = db.query(QualityAuthorizationCase.id).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
        QualityAuthorizationCase.user_id == payload.user_id,
        QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
    ).first()
    if existing_case:
        raise HTTPException(status_code=409, detail="This person already has an open Quality authorization case.")

    scope_key = str(payload.requested_scope_key or "GLOBAL").strip().upper() or "GLOBAL"
    live_query = (
        db.query(QualityPrivilege, QualityPrivilegeRule)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id == payload.user_id,
            QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
        )
    )
    if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        live_query = live_query.filter(QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]))
    else:
        live_query = live_query.filter(QualityPrivilege.rule_id == rule.id)
    current_pair = live_query.order_by(QualityPrivilege.updated_at.desc()).first()
    current = current_pair[0] if current_pair else None
    current_rule = current_pair[1] if current_pair else None
    historical_target = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.user_id == payload.user_id,
        QualityPrivilege.rule_id == rule.id,
        QualityPrivilege.scope_key == scope_key,
    ).order_by(QualityPrivilege.updated_at.desc()).first()
    linked = current or historical_target

    if current and current.rule_id != rule.id:
        case_type = "CHANGE_AUTHORIZATION"
    elif current and current.status == "SUSPENDED":
        case_type = "REINSTATEMENT"
    elif current and current.rule_id == rule.id:
        case_type = "RENEWAL"
    else:
        case_type = "NEW_AUTHORIZATION"

    row = QualityAuthorizationCase(
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        current_privilege_id=linked.id if linked else None,
        requested_rule_id=rule.id,
        case_type=case_type,
        status="NOMINATED",
        requested_scope_key=scope_key,
        requested_scope=payload.requested_scope,
        nomination_date=date.today(),
        nominated_by_user_id=ctx.user_id,
        person_snapshot=_person_snapshot(db, user),
        current_authorization_snapshot=_privilege_snapshot(current, current_rule),
        requested_authorization_snapshot={
            "authorization": _authorization_label(rule),
            "scope": "Global" if scope_key == "GLOBAL" else scope_key,
            "developmental": _developmental(rule),
        },
        readiness_snapshot={},
        source_references=[],
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=current, case=row)
    row.readiness_snapshot = readiness
    _case_event(
        db, ctx=ctx, row=row, action="NOMINATED", previous_status=None,
        reason=payload.nomination_reason,
        after={"status": row.status, "authorization": _authorization_label(rule), "readiness": readiness},
    )
    db.commit()
    return {"case": _case_summary(db, amo_id=ctx.amo_id, row=row, names=_actor_names(db, amo_id=ctx.amo_id, ids={ctx.user_id})), "readiness": readiness}


@router.post("/authorization-control/cases/batch", status_code=status.HTTP_201_CREATED)
def create_authorization_cases_batch(
    payload: AuthorizationCaseBatchCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.requested_rule_id)
    if not rule.is_active:
        raise HTTPException(status_code=409, detail="This Quality authorization type is inactive.")
    unique_ids = list(dict.fromkeys(str(value).strip() for value in payload.user_ids if str(value).strip()))
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for user_id in unique_ids:
        user = db.query(account_models.User).filter(
            account_models.User.amo_id == ctx.amo_id,
            account_models.User.id == user_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).first()
        if user is None:
            skipped.append({"person": "Unavailable person", "reason": "Inactive or unavailable workforce record."})
            continue
        open_case = db.query(QualityAuthorizationCase.id).filter(
            QualityAuthorizationCase.amo_id == ctx.amo_id,
            QualityAuthorizationCase.user_id == user_id,
            QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
        ).first()
        if open_case:
            skipped.append({"person": _person_name(user), "reason": "Open authorization case already exists."})
            continue
        scope_key = "GLOBAL"
        current_pair = (
            db.query(QualityPrivilege, QualityPrivilegeRule)
            .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
            .filter(
                QualityPrivilege.amo_id == ctx.amo_id,
                QualityPrivilege.user_id == user_id,
                QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
                QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]) if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"} else QualityPrivilege.rule_id == rule.id,
            )
            .order_by(QualityPrivilege.updated_at.desc())
            .first()
        )
        current = current_pair[0] if current_pair else None
        current_rule = current_pair[1] if current_pair else None
        row = QualityAuthorizationCase(
            amo_id=ctx.amo_id,
            user_id=user_id,
            current_privilege_id=current.id if current else None,
            requested_rule_id=rule.id,
            case_type="CHANGE_AUTHORIZATION" if current and current.rule_id != rule.id else ("REINSTATEMENT" if current and current.status == "SUSPENDED" else ("RENEWAL" if current else "NEW_AUTHORIZATION")),
            status="NOMINATED",
            requested_scope_key=scope_key,
            requested_scope={},
            nomination_date=date.today(),
            nominated_by_user_id=ctx.user_id,
            person_snapshot=_person_snapshot(db, user),
            current_authorization_snapshot=_privilege_snapshot(current, current_rule),
            requested_authorization_snapshot={"authorization": _authorization_label(rule), "scope": "Global", "developmental": _developmental(rule)},
            readiness_snapshot={},
            source_references=[],
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(row)
        db.flush()
        readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=current, case=row)
        row.readiness_snapshot = readiness
        _case_event(
            db, ctx=ctx, row=row, action="NOMINATED", previous_status=None,
            reason=payload.nomination_reason,
            after={"status": row.status, "authorization": _authorization_label(rule), "readiness": readiness},
        )
        created.append({"person": _person_name(user), "case_id": str(row.id)})
    db.commit()
    return {"created": created, "skipped": skipped, "created_count": len(created), "skipped_count": len(skipped)}


@router.get("/authorization-control/cases/{case_id}")
def get_authorization_case(
    case_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _case(db, amo_id=ctx.amo_id, case_id=case_id)
    user = _person(db, amo_id=ctx.amo_id, user_id=str(row.user_id))
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(row.requested_rule_id))
    current = row.current_privilege
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=current, case=row)
    events = db.query(QualityAuthorizationCaseEvent).filter(
        QualityAuthorizationCaseEvent.amo_id == ctx.amo_id,
        QualityAuthorizationCaseEvent.case_id == row.id,
    ).order_by(QualityAuthorizationCaseEvent.occurred_at.asc()).all()
    evidences = _evidence_rows(db, amo_id=ctx.amo_id, case_id=str(row.id))
    actor_ids = {
        str(value)
        for value in [
            row.nominated_by_user_id, row.recommendation_by_user_id, row.decided_by_user_id,
            *[item.actor_user_id for item in events],
        ] if value
    }
    names = _actor_names(db, amo_id=ctx.amo_id, ids=actor_ids)
    exemption = _active_exemption(db, amo_id=ctx.amo_id, case_id=str(row.id))
    return {
        "case": {
            **_case_summary(db, amo_id=ctx.amo_id, row=row, names=names),
            "person": row.person_snapshot,
            "current_authorization": row.current_authorization_snapshot or {},
            "requested_authorization": row.requested_authorization_snapshot or {},
            "recommendation": row.recommendation,
            "recommendation_by": names.get(str(row.recommendation_by_user_id)) if row.recommendation_by_user_id else None,
            "recommendation_at": row.recommendation_at.isoformat() if row.recommendation_at else None,
            "decision": row.decision,
            "decision_reason": row.decision_reason,
            "decided_by": names.get(str(row.decided_by_user_id)) if row.decided_by_user_id else None,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "expires_on": row.expires_on.isoformat() if row.expires_on else None,
            "next_review_due": row.next_review_due.isoformat() if row.next_review_due else None,
        },
        "readiness": readiness,
        "evidence": [_evidence_dict(item) for item in evidences],
        "controlled_exemption": _exemption_dict(exemption, _actor_names(db, amo_id=ctx.amo_id, ids={str(exemption.approved_by_user_id), str(exemption.supervisor_user_id)} if exemption else set())),
        "history": [
            {
                "action": event.action,
                "from": event.previous_status,
                "to": event.new_status,
                "reason": event.reason,
                "actor": names.get(str(event.actor_user_id), "Recorded actor"),
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            }
            for event in events
        ],
        "permissions": _permissions(db, ctx),
    }


@router.patch("/authorization-control/cases/{case_id}/preparation")
def prepare_authorization_case(
    case_id: str,
    payload: AuthorizationCasePrepare,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if row.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="A completed authorization case cannot be edited.")
    before = {"status": row.status, "recommendation": row.recommendation}
    previous = row.status
    if payload.status:
        row.status = payload.status
    elif row.status == "NOMINATED":
        row.status = "UNDER_REVIEW"
    if payload.recommendation is not None:
        row.recommendation = payload.recommendation.strip() or None
        row.recommendation_by_user_id = ctx.user_id
        row.recommendation_at = _utcnow()
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    user = _person(db, amo_id=ctx.amo_id, user_id=str(row.user_id))
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(row.requested_rule_id))
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=row.current_privilege, case=row)
    row.readiness_snapshot = readiness
    _case_event(
        db, ctx=ctx, row=row, action="PREPARATION_UPDATED", previous_status=previous,
        reason=payload.reason, before=before,
        after={"status": row.status, "recommendation": row.recommendation, "readiness": readiness},
    )
    db.commit()
    return {"status": row.status, "readiness": readiness}


@router.post("/authorization-control/cases/{case_id}/submit")
def submit_authorization_case(
    case_id: str,
    payload: AuthorizationCaseSubmit,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if row.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="A completed authorization case cannot be resubmitted.")
    user = _person(db, amo_id=ctx.amo_id, user_id=str(row.user_id), active_only=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(row.requested_rule_id))
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=row.current_privilege, case=row)
    if readiness["hard_blockers"]:
        raise HTTPException(status_code=409, detail={"message": "Authorization case has unresolved hard blockers.", "readiness": readiness})
    previous = row.status
    row.status = "READY_FOR_DECISION"
    row.recommendation = payload.recommendation.strip()
    row.recommendation_by_user_id = ctx.user_id
    row.recommendation_at = _utcnow()
    row.readiness_snapshot = readiness
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    _case_event(
        db, ctx=ctx, row=row, action="SUBMITTED_FOR_DECISION", previous_status=previous,
        reason=payload.reason,
        after={"status": row.status, "recommendation": row.recommendation, "readiness": readiness},
    )
    db.commit()
    return {"status": row.status, "readiness": readiness}


