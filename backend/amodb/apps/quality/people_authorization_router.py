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


class ControlledExemptionRevoke(BaseModel):
    reason: str = Field(min_length=12, max_length=8000)
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


def _open_case_exists(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    rule: QualityPrivilegeRule,
) -> bool:
    query = (
        db.query(QualityAuthorizationCase.id)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityAuthorizationCase.requested_rule_id)
        .filter(
            QualityAuthorizationCase.amo_id == amo_id,
            QualityAuthorizationCase.user_id == user_id,
            QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
        )
    )
    if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        query = query.filter(QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]))
    else:
        query = query.filter(QualityAuthorizationCase.requested_rule_id == rule.id)
    return query.first() is not None


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


def _next_review_due(db: Session, *, amo_id: str, privilege_id: str | None) -> date | None:
    """Return the current governed review due date without inventing a review event."""

    if not privilege_id:
        return None
    latest = _latest_review(db, amo_id=amo_id, privilege_id=privilege_id)
    if latest is not None:
        return latest.next_review_due
    approved_case = (
        db.query(QualityAuthorizationCase)
        .filter(
            QualityAuthorizationCase.amo_id == amo_id,
            QualityAuthorizationCase.current_privilege_id == privilege_id,
            QualityAuthorizationCase.status == "APPROVED",
            QualityAuthorizationCase.next_review_due.is_not(None),
        )
        .order_by(QualityAuthorizationCase.decided_at.desc())
        .first()
    )
    return approved_case.next_review_due if approved_case else None


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


def _can_view_tenant_authorization_register(db: Session, ctx: TenantContext) -> bool:
    return any(
        has_quality_permission(db, ctx, permission)
        for permission in (
            "qms.authorization.prepare",
            "qms.authorization.approve",
            "qms.authorization.review",
            "qms.authorization.exemption.approve",
            "qms.authorization.policy.manage",
            "qms.authorization.oversight",
        )
    )


def _require_self_or_register_access(db: Session, ctx: TenantContext, person_user_id: str) -> None:
    if str(person_user_id) == str(ctx.user_id):
        return
    if _can_view_tenant_authorization_register(db, ctx):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You can only view your own Quality authorization record.",
    )


def _permissions(db: Session, ctx: TenantContext) -> dict[str, bool]:
    register_access = _can_view_tenant_authorization_register(db, ctx)
    return {
        "can_view": has_quality_permission(db, ctx, "qms.people.view"),
        "can_prepare": has_quality_permission(db, ctx, "qms.authorization.prepare"),
        "can_approve": has_quality_permission(db, ctx, "qms.authorization.approve"),
        "can_review": has_quality_permission(db, ctx, "qms.authorization.review"),
        "can_approve_exemption": has_quality_permission(db, ctx, "qms.authorization.exemption.approve"),
        "can_manage_policy": has_quality_permission(db, ctx, "qms.authorization.policy.manage"),
        "can_oversight": has_quality_permission(db, ctx, "qms.authorization.oversight"),
        "self_service_only": not register_access,
    }


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


@router.get("/authorization-control/overview")
def authorization_overview(
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    register_access = _can_view_tenant_authorization_register(db, ctx)
    privilege_query = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
    )
    case_query = db.query(QualityAuthorizationCase).filter(
        QualityAuthorizationCase.amo_id == ctx.amo_id,
        QualityAuthorizationCase.status.in_(MANAGEMENT_CASE_STATUSES),
    )
    exemption_query = db.query(QualityControlledExemption).filter(
        QualityControlledExemption.amo_id == ctx.amo_id,
        QualityControlledExemption.status == "ACTIVE",
        QualityControlledExemption.expires_on >= today,
    )
    if not register_access:
        privilege_query = privilege_query.filter(QualityPrivilege.user_id == ctx.user_id)
        case_query = case_query.filter(QualityAuthorizationCase.user_id == ctx.user_id)
        exemption_query = exemption_query.filter(QualityControlledExemption.person_user_id == ctx.user_id)
    privileges = privilege_query.all()
    open_cases = case_query.all()
    active_exemptions = exemption_query.count()
    due_reviews = sum(
        1
        for privilege in privileges
        if privilege.status in {"ACTIVE", "SUSPENDED"}
        and (due := _next_review_due(db, amo_id=ctx.amo_id, privilege_id=str(privilege.id))) is not None
        and due <= today
    )
    status_counts = {"ACTIVE": 0, "SUSPENDED": 0, "REVOKED": 0, "EXPIRED": 0, "DRAFT": 0}
    expiring = 0
    for item in privileges:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        if item.status == "ACTIVE" and item.expires_on and 0 <= (item.expires_on - today).days <= 60:
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
    if not _can_view_tenant_authorization_register(db, ctx):
        query = query.filter(account_models.User.id == ctx.user_id)
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
    _require_self_or_register_access(db, ctx, user_id)
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
            "next_review_due": (
                due.isoformat()
                if (due := _next_review_due(db, amo_id=ctx.amo_id, privilege_id=str(privilege.id)))
                else None
            ),
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
    if not _can_view_tenant_authorization_register(db, ctx):
        query = query.filter(QualityAuthorizationCase.user_id == ctx.user_id)
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
    if _open_case_exists(db, amo_id=ctx.amo_id, user_id=payload.user_id, rule=rule):
        raise HTTPException(
            status_code=409,
            detail="This person already has an open case for this Quality authorization family.",
        )

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
        if _open_case_exists(db, amo_id=ctx.amo_id, user_id=user_id, rule=rule):
            skipped.append({"person": _person_name(user), "reason": "Open case already exists for this authorization family."})
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
    _require_self_or_register_access(db, ctx, str(row.user_id))
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


def _record_privilege_decision(
    db: Session,
    *,
    ctx: TenantContext,
    privilege: QualityPrivilege,
    decision_type: str,
    resulting_status: str,
    reason: str,
    effective_from: date | None,
    expires_on: date | None,
    eligibility_snapshot: dict[str, Any],
    source_references: list[dict[str, Any]],
) -> QualityPrivilegeDecision:
    decision = QualityPrivilegeDecision(
        amo_id=ctx.amo_id,
        privilege_id=privilege.id,
        decision_type=decision_type,
        resulting_status=resulting_status,
        rationale=reason.strip(),
        eligibility_snapshot=eligibility_snapshot,
        source_references=source_references,
        effective_from=effective_from,
        expires_on=expires_on,
        decided_by_user_id=ctx.user_id,
        decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    privilege.latest_decision_id = decision.id
    privilege.status = resulting_status
    privilege.effective_from = effective_from
    privilege.expires_on = expires_on
    privilege.updated_by_user_id = ctx.user_id
    privilege.updated_at = _utcnow()
    return decision


def _retire_other_live_auditor_authorizations(
    db: Session,
    *,
    ctx: TenantContext,
    user_id: str,
    keep_privilege_id: str,
    scope_key: str,
    reason: str,
) -> None:
    rows = (
        db.query(QualityPrivilege, QualityPrivilegeRule)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id == user_id,
            QualityPrivilege.id != keep_privilege_id,
            QualityPrivilege.scope_key == scope_key,
            QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
            QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]),
        )
        .all()
    )
    for privilege, rule in rows:
        before = _privilege_snapshot(privilege, rule)
        _record_privilege_decision(
            db, ctx=ctx, privilege=privilege, decision_type="CHANGE",
            resulting_status="REVOKED", reason=reason,
            effective_from=privilege.effective_from, expires_on=privilege.expires_on,
            eligibility_snapshot={"superseded_by_authorization_change": keep_privilege_id},
            source_references=[{"type": "AUTHORIZATION_CHANGE", "replacement_privilege_id": keep_privilege_id}],
        )
        _decision_event(
            db, ctx=ctx, entity_type="qms.authorization", entity_id=str(privilege.id),
            action="SUPERSEDED_BY_AUTHORIZATION_CHANGE", before=before,
            after={**_privilege_snapshot(privilege, rule), "status": "REVOKED"}, reason=reason,
        )


def _ensure_appointment(
    db: Session,
    *,
    ctx: TenantContext,
    row: QualityAuthorizationCase,
    rule: QualityPrivilegeRule,
    effective_from: date,
) -> QualityAppointment:
    title = _appointment_title(rule)
    family_codes = (
        {"AUDITOR", "LEAD_AUDITOR"}
        if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}
        else {rule.privilege_type}
    )
    active_rows = (
        db.query(QualityAppointment)
        .filter(
            QualityAppointment.amo_id == ctx.amo_id,
            QualityAppointment.user_id == row.user_id,
            QualityAppointment.function_code.in_(family_codes),
            QualityAppointment.status == "ACTIVE",
        )
        .order_by(QualityAppointment.created_at.desc())
        .all()
    )
    appointment = next(
        (
            item
            for item in active_rows
            if item.function_code == rule.privilege_type and item.title == title
        ),
        None,
    )
    for item in active_rows:
        if appointment is not None and item.id == appointment.id:
            continue
        item.status = "SUPERSEDED"
        item.effective_until = effective_from
        item.updated_by_user_id = ctx.user_id
        item.updated_at = _utcnow()

    if appointment is None:
        appointment = QualityAppointment(
            amo_id=ctx.amo_id,
            user_id=row.user_id,
            function_code=rule.privilege_type,
            title=title,
            status="ACTIVE",
            effective_from=effective_from,
            source_references=[{"type": "AUTHORIZATION_CASE", "case_id": str(row.id)}],
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(appointment)
        db.flush()
    row.appointment_id = appointment.id
    return appointment

def _activate_case_authorization(
    db: Session,
    *,
    ctx: TenantContext,
    row: QualityAuthorizationCase,
    rule: QualityPrivilegeRule,
    user: account_models.User,
    readiness: dict[str, Any],
    reason: str,
    effective_from: date,
    expires_on: date | None,
    source_references: list[dict[str, Any]],
) -> QualityPrivilege:
    scope_key = str(row.requested_scope_key or "GLOBAL").upper()
    target = db.query(QualityPrivilege).options(selectinload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.user_id == row.user_id,
        QualityPrivilege.rule_id == rule.id,
        QualityPrivilege.scope_key == scope_key,
    ).order_by(QualityPrivilege.updated_at.desc()).first()
    current = row.current_privilege

    training_snapshot = readiness.get("training") or {}
    exemption = _active_exemption(db, amo_id=ctx.amo_id, case_id=str(row.id), as_of=effective_from)
    if expires_on is None:
        raw_training = evaluate_qms_competence_for_privilege(
            db, amo_id=ctx.amo_id, user_id=str(user.id), rule=rule, as_of=effective_from
        )
        expires_on = cap_privilege_expires_on(None, raw_training, as_of=effective_from)
    else:
        raw_training = evaluate_qms_competence_for_privilege(
            db, amo_id=ctx.amo_id, user_id=str(user.id), rule=rule, as_of=effective_from
        )
        expires_on = cap_privilege_expires_on(expires_on, raw_training, as_of=effective_from)
    if exemption is not None:
        expires_on = min(expires_on, exemption.expires_on) if expires_on else exemption.expires_on

    if target is None:
        # Authorization changes create a new governed authorization record.
        # The previous authorization is retained and explicitly superseded below;
        # its historical identity is never rewritten into the new rank/type.
        target = QualityPrivilege(
            amo_id=ctx.amo_id,
            rule_id=rule.id,
            user_id=row.user_id,
            privilege_code=rule.privilege_code,
            scope_key=scope_key,
            scope=dict(row.requested_scope or {}),
            limitations=[],
            status="DRAFT",
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(target)
        db.flush()

    previous_snapshot = _privilege_snapshot(target, rule)
    scope = dict(row.requested_scope or {})
    if exemption is not None:
        scope["controlled_exemption"] = {
            "exemption_id": str(exemption.id),
            "criterion": exemption.criterion,
            "conditions": list(exemption.conditions or []),
            "limitations": list(exemption.limitations or []),
            "supervision_required": bool(exemption.supervision_required),
            "supervisor_user_id": exemption.supervisor_user_id,
            "effective_from": exemption.effective_from.isoformat(),
            "expires_on": exemption.expires_on.isoformat(),
            "approved_by_user_id": exemption.approved_by_user_id,
            "approved_at": exemption.approved_at.isoformat() if exemption.approved_at else None,
        }
    target.rule_id = rule.id
    target.privilege_code = rule.privilege_code
    target.scope_key = scope_key
    target.scope = scope
    target.limitations = list(exemption.limitations or []) if exemption else list(target.limitations or [])

    decision_type = (
        "CHANGE" if row.case_type == "CHANGE_AUTHORIZATION"
        else "REINSTATE" if target.status == "SUSPENDED" or row.case_type == "REINSTATEMENT"
        else "RENEW" if row.case_type == "RENEWAL"
        else "GRANT"
    )
    _record_privilege_decision(
        db, ctx=ctx, privilege=target, decision_type=decision_type,
        resulting_status="ACTIVE", reason=reason,
        effective_from=effective_from, expires_on=expires_on,
        eligibility_snapshot={
            "case_id": str(row.id),
            "readiness": readiness,
            "training": training_snapshot,
            "developmental_authorization": _developmental(rule),
            "controlled_exemption_id": str(exemption.id) if exemption else None,
        },
        source_references=[
            {"type": "AUTHORIZATION_CASE", "case_id": str(row.id)},
            *source_references,
        ],
    )
    if exemption is not None:
        exemption.privilege_id = target.id
    if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        _retire_other_live_auditor_authorizations(
            db, ctx=ctx, user_id=str(row.user_id), keep_privilege_id=str(target.id),
            scope_key=scope_key, reason=f"Authorization changed through case {row.id}. {reason}",
        )
    _ensure_appointment(db, ctx=ctx, row=row, rule=rule, effective_from=effective_from)
    _decision_event(
        db, ctx=ctx, entity_type="qms.authorization", entity_id=str(target.id),
        action=decision_type, before=previous_snapshot,
        after=_privilege_snapshot(target, rule), reason=reason,
    )
    return target


@router.post("/authorization-control/cases/{case_id}/decision")
def decide_authorization_case(
    case_id: str,
    payload: AuthorizationCaseDecisionCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.approve")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Final authorization decisions require explicit confirmation.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if row.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="This authorization case already has a final decision.")
    previous = row.status
    if payload.decision == "RETURN":
        row.status = "RETURNED"
        row.decision = "RETURNED"
        row.decision_reason = payload.reason.strip()
        row.decided_by_user_id = ctx.user_id
        row.decided_at = _utcnow()
        row.updated_by_user_id = ctx.user_id
        row.updated_at = _utcnow()
        _case_event(
            db, ctx=ctx, row=row, action="RETURNED_FOR_MORE_EVIDENCE",
            previous_status=previous, reason=payload.reason,
            after={"status": row.status, "decision": row.decision},
            source_references=payload.source_references,
        )
        db.commit()
        return {"status": row.status}

    if row.status != "READY_FOR_DECISION":
        raise HTTPException(status_code=409, detail="Submit the case for decision before recording a final decision.")

    user = _person(db, amo_id=ctx.amo_id, user_id=str(row.user_id), active_only=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(row.requested_rule_id))
    effective_from = payload.effective_from or date.today()
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=row.current_privilege, case=row, as_of=effective_from)

    if payload.decision == "REJECT":
        row.status = "REJECTED"
        row.decision = "REJECTED"
        row.decision_reason = payload.reason.strip()
        row.decided_by_user_id = ctx.user_id
        row.decided_at = _utcnow()
        row.readiness_snapshot = readiness
        row.updated_by_user_id = ctx.user_id
        row.updated_at = _utcnow()
        _case_event(
            db, ctx=ctx, row=row, action="REJECTED", previous_status=previous,
            reason=payload.reason,
            after={"status": row.status, "decision": row.decision, "readiness": readiness},
            source_references=payload.source_references,
        )
        db.commit()
        return {"status": row.status, "readiness": readiness}

    if readiness["hard_blockers"]:
        raise HTTPException(status_code=409, detail={"message": "Hard source-backed authorization blockers remain unresolved.", "readiness": readiness})
    if payload.expires_on and payload.expires_on < effective_from:
        raise HTTPException(status_code=422, detail="Authorization expiry cannot precede its effective date.")
    if payload.next_review_due and payload.next_review_due < effective_from:
        raise HTTPException(status_code=422, detail="Next review date cannot precede authorization effective date.")

    development = readiness.get("development") or {}
    incomplete_development = int(development.get("observed_audits") or 0) < int(development.get("target") or OBSERVER_AUDIT_DEVELOPMENT_TARGET)
    if row.case_type == "CHANGE_AUTHORIZATION" and rule.privilege_type == "AUDITOR" and not _developmental(rule) and incomplete_development:
        # Three observer audits are evidence, not an inflexible gate. Preserve the
        # approving manager's rationale whenever the target was not completed.
        if not str(payload.incomplete_development_basis or "").strip():
            raise HTTPException(
                status_code=422,
                detail="Record the approval basis when promoting before the three-observer-audit development target is complete.",
            )
        payload.source_references.append({
            "type": "INCOMPLETE_DEVELOPMENT_TARGET_APPROVAL",
            "observed_audits": development.get("observed_audits"),
            "target": development.get("target"),
            "basis": payload.incomplete_development_basis.strip(),
        })

    privilege = _activate_case_authorization(
        db, ctx=ctx, row=row, rule=rule, user=user, readiness=readiness,
        reason=payload.reason, effective_from=effective_from,
        expires_on=payload.expires_on, source_references=payload.source_references,
    )
    row.status = "APPROVED"
    row.decision = "APPROVED"
    row.decision_reason = payload.reason.strip()
    row.decided_by_user_id = ctx.user_id
    row.decided_at = _utcnow()
    row.effective_from = privilege.effective_from
    row.expires_on = privilege.expires_on
    row.next_review_due = payload.next_review_due
    row.current_privilege_id = privilege.id
    row.readiness_snapshot = readiness
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    _case_event(
        db, ctx=ctx, row=row, action="APPROVED", previous_status=previous,
        reason=payload.reason,
        after={
            "status": row.status,
            "decision": row.decision,
            "authorization": _privilege_snapshot(privilege, rule),
            "next_review_due": payload.next_review_due.isoformat() if payload.next_review_due else None,
        },
        source_references=payload.source_references,
    )
    db.commit()
    return {
        "status": row.status,
        "authorization": {
            "key": str(privilege.id),
            **_privilege_snapshot(privilege, rule),
        },
        "readiness": readiness,
    }


@router.post("/authorization-control/authorizations/{privilege_id}/lifecycle")
def authorization_lifecycle_decision(
    privilege_id: str,
    payload: LifecycleDecisionCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.approve")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Authorization lifecycle decisions require explicit confirmation.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = _privilege(db, amo_id=ctx.amo_id, privilege_id=privilege_id, lock=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))
    before = _privilege_snapshot(privilege, rule)
    current = privilege.status
    allowed = {
        "SUSPEND": {"ACTIVE"},
        "REVOKE": {"ACTIVE", "SUSPENDED"},
        "REINSTATE": {"SUSPENDED"},
        "RENEW": {"ACTIVE", "EXPIRED"},
    }
    if current not in allowed[payload.decision]:
        raise HTTPException(status_code=409, detail=f"{payload.decision.title()} is not valid from {current}.")
    if payload.decision == "REINSTATE" and current == "REVOKED":
        raise HTTPException(status_code=409, detail="Revoked authorizations cannot be reinstated. Create a new authorization case.")

    user = _person(db, amo_id=ctx.amo_id, user_id=str(privilege.user_id), active_only=True)
    activation = payload.decision in {"REINSTATE", "RENEW"}
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=privilege, as_of=payload.effective_date)
    if activation and readiness["hard_blockers"]:
        raise HTTPException(status_code=409, detail={"message": "Hard source-backed authorization blockers remain unresolved.", "readiness": readiness})
    resulting = {"SUSPEND": "SUSPENDED", "REVOKE": "REVOKED", "REINSTATE": "ACTIVE", "RENEW": "ACTIVE"}[payload.decision]
    expires_on = payload.expires_on if activation else privilege.expires_on
    if activation:
        raw_training = evaluate_qms_competence_for_privilege(
            db, amo_id=ctx.amo_id, user_id=str(privilege.user_id), rule=rule, as_of=payload.effective_date
        )
        expires_on = cap_privilege_expires_on(expires_on, raw_training, as_of=payload.effective_date)
    _record_privilege_decision(
        db, ctx=ctx, privilege=privilege, decision_type=payload.decision,
        resulting_status=resulting, reason=payload.reason,
        effective_from=payload.effective_date if activation else privilege.effective_from,
        expires_on=expires_on,
        eligibility_snapshot=readiness if activation else {"lifecycle_only": True, "affected_assignments": readiness.get("affected_assignments")},
        source_references=payload.source_references,
    )
    _decision_event(
        db, ctx=ctx, entity_type="qms.authorization", entity_id=str(privilege.id),
        action=payload.decision, before=before, after=_privilege_snapshot(privilege, rule), reason=payload.reason,
    )
    if payload.next_review_due:
        review = QualityAuthorizationReview(
            amo_id=ctx.amo_id,
            privilege_id=privilege.id,
            last_reviewed=payload.effective_date,
            next_review_due=payload.next_review_due,
            review_outcome="CONTINUE" if resulting == "ACTIVE" else ("SUSPEND" if resulting == "SUSPENDED" else "REVOKE"),
            review_reason=payload.reason,
            reviewed_by_user_id=ctx.user_id,
            reviewed_at=_utcnow(),
            review_evidence=payload.source_references,
            review_notes=f"Review date recorded with {payload.decision.lower()} decision.",
            before_snapshot=before,
            after_snapshot=_privilege_snapshot(privilege, rule),
        )
        db.add(review)
    db.commit()
    return {
        "authorization": {"key": str(privilege.id), **_privilege_snapshot(privilege, rule)},
        "affected_assignments": readiness.get("affected_assignments") or [],
    }


@router.get("/authorization-control/reviews")
def list_authorization_reviews(
    due_only: bool = False,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = (
        db.query(QualityAuthorizationReview, QualityPrivilege, QualityPrivilegeRule, account_models.User)
        .join(QualityPrivilege, QualityPrivilege.id == QualityAuthorizationReview.privilege_id)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .join(account_models.User, account_models.User.id == QualityPrivilege.user_id)
        .filter(QualityAuthorizationReview.amo_id == ctx.amo_id)
    )
    if not _can_view_tenant_authorization_register(db, ctx):
        query = query.filter(QualityPrivilege.user_id == ctx.user_id)
    if due_only:
        query = query.filter(
            QualityAuthorizationReview.next_review_due.is_not(None),
            QualityAuthorizationReview.next_review_due <= date.today(),
        )
    rows = query.order_by(QualityAuthorizationReview.reviewed_at.desc()).limit(500).all()
    actor_ids = {str(review.reviewed_by_user_id) for review, _p, _r, _u in rows if review.reviewed_by_user_id}
    names = _actor_names(db, amo_id=ctx.amo_id, ids=actor_ids)
    return {
        "items": [
            _review_dict(review, names, authorization=_authorization_label(rule), person=_person_name(user))
            for review, _privilege_row, rule, user in rows
        ]
    }


@router.post("/authorization-control/authorizations/{privilege_id}/reviews", status_code=status.HTTP_201_CREATED)
def create_authorization_review(
    privilege_id: str,
    payload: AuthorizationReviewCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.review")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Periodic authorization reviews require explicit confirmation.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = _privilege(db, amo_id=ctx.amo_id, privilege_id=privilege_id, lock=True)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))
    user = _person(db, amo_id=ctx.amo_id, user_id=str(privilege.user_id))
    before = _privilege_snapshot(privilege, rule)
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=privilege)
    if payload.next_review_due and payload.next_review_due < date.today():
        raise HTTPException(status_code=422, detail="Next review due date cannot be in the past.")
    review = QualityAuthorizationReview(
        amo_id=ctx.amo_id,
        privilege_id=privilege.id,
        last_reviewed=date.today(),
        next_review_due=payload.next_review_due,
        review_outcome=payload.review_outcome,
        review_reason=payload.review_reason.strip(),
        reviewed_by_user_id=ctx.user_id,
        reviewed_at=_utcnow(),
        review_evidence=payload.review_evidence,
        review_notes=payload.review_notes,
        before_snapshot=before,
        after_snapshot={**before, "review_outcome": payload.review_outcome},
    )
    db.add(review)
    db.flush()
    if payload.review_outcome in {"SUSPEND", "REVOKE"}:
        if payload.review_outcome == "SUSPEND" and privilege.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="Only an active authorization can be suspended.")
        if payload.review_outcome == "REVOKE" and privilege.status not in {"ACTIVE", "SUSPENDED"}:
            raise HTTPException(status_code=409, detail="Only an active or suspended authorization can be revoked.")
        _record_privilege_decision(
            db, ctx=ctx, privilege=privilege, decision_type=payload.review_outcome,
            resulting_status="SUSPENDED" if payload.review_outcome == "SUSPEND" else "REVOKED",
            reason=payload.review_reason,
            effective_from=privilege.effective_from, expires_on=privilege.expires_on,
            eligibility_snapshot={"periodic_review": readiness},
            source_references=[{"type": "AUTHORIZATION_REVIEW", "review_id": str(review.id)}, *payload.review_evidence],
        )
    _decision_event(
        db, ctx=ctx, entity_type="qms.authorization.review", entity_id=str(review.id),
        action=payload.review_outcome, before=before,
        after={**_privilege_snapshot(privilege, rule), "next_review_due": payload.next_review_due.isoformat() if payload.next_review_due else None},
        reason=payload.review_reason,
    )
    db.commit()
    names = _actor_names(db, amo_id=ctx.amo_id, ids={ctx.user_id})
    return {"review": _review_dict(review, names, authorization=_authorization_label(rule), person=_person_name(user)), "readiness": readiness}


def _create_controlled_exemption(
    db: Session,
    *,
    ctx: TenantContext,
    payload: ControlledExemptionCreate,
    person_user_id: str,
    authorization_type: str,
    case_id: str | None = None,
    privilege: QualityPrivilege | None = None,
) -> QualityControlledExemption:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Controlled exemptions require explicit final confirmation.")
    if payload.expires_on < payload.effective_from:
        raise HTTPException(status_code=422, detail="Controlled exemption expiry cannot precede its effective date.")
    if not payload.equivalent_evidence:
        raise HTTPException(status_code=422, detail="Record equivalent evidence supporting the controlled exemption.")
    if payload.supervision_required and not payload.supervisor_user_id:
        raise HTTPException(status_code=422, detail="Select a supervisor when supervision is required.")
    if payload.supervisor_user_id:
        _person(db, amo_id=ctx.amo_id, user_id=payload.supervisor_user_id, active_only=True)
    if not payload.conditions:
        raise HTTPException(status_code=422, detail="At least one operating condition is required for a controlled exemption.")
    existing = db.query(QualityControlledExemption).filter(
        QualityControlledExemption.amo_id == ctx.amo_id,
        QualityControlledExemption.person_user_id == person_user_id,
        QualityControlledExemption.authorization_type == authorization_type,
        QualityControlledExemption.status == "ACTIVE",
        QualityControlledExemption.expires_on >= date.today(),
    ).all()
    for item in existing:
        item.status = "SUPERSEDED"
    row = QualityControlledExemption(
        amo_id=ctx.amo_id,
        case_id=case_id,
        privilege_id=privilege.id if privilege else None,
        person_user_id=person_user_id,
        authorization_type=authorization_type,
        criterion=payload.criterion.strip(),
        reason_normal_compliance_impossible=payload.reason_normal_compliance_impossible.strip(),
        equivalent_evidence=payload.equivalent_evidence,
        limitations=payload.limitations,
        supervision_required=payload.supervision_required,
        supervisor_user_id=payload.supervisor_user_id,
        conditions=payload.conditions,
        effective_from=payload.effective_from,
        expires_on=payload.expires_on,
        source_references=payload.source_references,
        status="ACTIVE",
        approved_by_user_id=ctx.user_id,
        approved_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    if privilege is not None:
        scope = dict(privilege.scope or {})
        scope["controlled_exemption"] = {
            "exemption_id": str(row.id),
            "criterion": row.criterion,
            "conditions": list(row.conditions or []),
            "limitations": list(row.limitations or []),
            "supervision_required": bool(row.supervision_required),
            "supervisor_user_id": row.supervisor_user_id,
            "effective_from": row.effective_from.isoformat(),
            "expires_on": row.expires_on.isoformat(),
            "approved_by_user_id": row.approved_by_user_id,
            "approved_at": row.approved_at.isoformat(),
        }
        privilege.scope = scope
        privilege.limitations = [*list(privilege.limitations or []), *list(row.limitations or [])]
        privilege.updated_by_user_id = ctx.user_id
        privilege.updated_at = _utcnow()
    _decision_event(
        db, ctx=ctx, entity_type="qms.authorization.controlled_exemption", entity_id=str(row.id),
        action="APPROVED", before={},
        after={"criterion": row.criterion, "effective_from": row.effective_from.isoformat(), "expires_on": row.expires_on.isoformat(), "conditions": row.conditions},
        reason=row.reason_normal_compliance_impossible,
    )
    return row


@router.post("/authorization-control/cases/{case_id}/controlled-exemptions", status_code=status.HTTP_201_CREATED)
def create_case_controlled_exemption(
    case_id: str,
    payload: ControlledExemptionCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.exemption.approve")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if case.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="Controlled exemptions cannot be added to a completed authorization case.")
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(case.requested_rule_id))
    row = _create_controlled_exemption(
        db, ctx=ctx, payload=payload, person_user_id=str(case.user_id),
        authorization_type=_authorization_label(rule), case_id=str(case.id),
        privilege=case.current_privilege if case.current_privilege and case.current_privilege.status == "ACTIVE" else None,
    )
    user = _person(db, amo_id=ctx.amo_id, user_id=str(case.user_id))
    readiness = _readiness(db, amo_id=ctx.amo_id, user=user, rule=rule, privilege=case.current_privilege, case=case)
    case.readiness_snapshot = readiness
    previous = case.status
    if not readiness["hard_blockers"] and case.status in {"AWAITING_EVIDENCE", "RETURNED"}:
        case.status = "UNDER_REVIEW"
    _case_event(
        db, ctx=ctx, row=case, action="CONTROLLED_EXEMPTION_APPROVED",
        previous_status=previous, reason=payload.reason_normal_compliance_impossible,
        after={"status": case.status, "exemption_id": str(row.id), "readiness": readiness},
        source_references=payload.source_references,
    )
    db.commit()
    names = _actor_names(db, amo_id=ctx.amo_id, ids={ctx.user_id, str(row.supervisor_user_id or "")})
    return {"controlled_exemption": _exemption_dict(row, names), "readiness": readiness}


@router.post("/authorization-control/authorizations/{privilege_id}/controlled-exemptions", status_code=status.HTTP_201_CREATED)
def create_authorization_controlled_exemption(
    privilege_id: str,
    payload: ControlledExemptionCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.exemption.approve")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = _privilege(db, amo_id=ctx.amo_id, privilege_id=privilege_id, lock=True)
    if privilege.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Controlled exemptions can only be attached to an active authorization.")
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))
    row = _create_controlled_exemption(
        db, ctx=ctx, payload=payload, person_user_id=str(privilege.user_id),
        authorization_type=_authorization_label(rule), privilege=privilege,
    )
    db.commit()
    names = _actor_names(db, amo_id=ctx.amo_id, ids={ctx.user_id, str(row.supervisor_user_id or "")})
    return {"controlled_exemption": _exemption_dict(row, names)}


@router.post("/authorization-control/controlled-exemptions/{exemption_id}/revoke")
def revoke_controlled_exemption(
    exemption_id: str,
    payload: ControlledExemptionRevoke,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.exemption.approve")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Controlled exemption revocation requires explicit confirmation.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = (
        db.query(QualityControlledExemption)
        .filter(
            QualityControlledExemption.amo_id == ctx.amo_id,
            QualityControlledExemption.id == exemption_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Controlled exemption not found.")
    if row.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only an active controlled exemption can be revoked.")
    before = _exemption_dict(row)
    row.status = "REVOKED"
    row.revoked_by_user_id = ctx.user_id
    row.revoked_at = _utcnow()
    row.revoke_reason = payload.reason.strip()
    if row.privilege_id:
        privilege = _privilege(db, amo_id=ctx.amo_id, privilege_id=str(row.privilege_id), lock=True)
        scope = dict(privilege.scope or {})
        active_scope = scope.get("controlled_exemption")
        if isinstance(active_scope, dict):
            scoped_id = str(active_scope.get("exemption_id") or "")
            same_legacy_record = (
                not scoped_id
                and str(active_scope.get("criterion") or "") == row.criterion
                and str(active_scope.get("expires_on") or "") == row.expires_on.isoformat()
            )
            if scoped_id == str(row.id) or same_legacy_record:
                scope.pop("controlled_exemption", None)
                privilege.scope = scope
                privilege.updated_by_user_id = ctx.user_id
                privilege.updated_at = _utcnow()
    _decision_event(
        db, ctx=ctx,
        entity_type="qms.authorization.controlled_exemption",
        entity_id=str(row.id),
        action="REVOKED",
        before=before or {},
        after={"status": row.status, "revoked_at": row.revoked_at.isoformat()},
        reason=payload.reason,
    )
    db.commit()
    names = _actor_names(db, amo_id=ctx.amo_id, ids={ctx.user_id, str(row.supervisor_user_id or "")})
    return {"controlled_exemption": _exemption_dict(row, names)}


@router.post("/authorization-control/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_case_evidence_reference(
    case_id: str,
    payload: EvidenceReferenceCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if case.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="Evidence cannot be added to a completed authorization case.")
    row = QualityAuthorizationEvidence(
        amo_id=ctx.amo_id,
        case_id=case.id,
        evidence_type=payload.evidence_type,
        label=payload.label.strip(),
        source_module=payload.source_module,
        source_reference=payload.source_reference,
        status="ACTIVE",
        uploaded_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    previous = case.status
    if case.status in {"NOMINATED", "AWAITING_EVIDENCE", "RETURNED"}:
        case.status = "UNDER_REVIEW"
    _case_event(
        db, ctx=ctx, row=case, action="EVIDENCE_LINKED", previous_status=previous,
        reason=f"Evidence linked: {payload.label.strip()}",
        after={"status": case.status, "evidence_type": payload.evidence_type, "label": payload.label.strip()},
    )
    db.commit()
    return _evidence_dict(row)


@router.post("/authorization-control/cases/{case_id}/evidence-file", status_code=status.HTTP_201_CREATED)
async def upload_case_evidence_file(
    case_id: str,
    file: UploadFile = File(...),
    label: str = Form(...),
    evidence_type: EvidenceType = Form(default="OTHER"),
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.prepare")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    case = _case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)
    if case.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="Evidence cannot be added to a completed authorization case.")
    root = Path(os.getenv("QUALITY_AUTHORIZATION_UPLOAD_DIR", "uploads/quality/authorizations")).resolve()
    folder = root / ctx.amo_id / str(case.id)
    folder.mkdir(parents=True, exist_ok=True)
    file_id = generate_user_id()
    original = file.filename or "authorization-evidence.bin"
    suffix = "".join(Path(original).suffixes)[-20:]
    destination = folder / f"{file_id}{suffix}"
    digest = hashlib.sha256()
    size = 0
    maximum = int(os.getenv("QUALITY_AUTHORIZATION_MAX_UPLOAD_BYTES", "52428800") or "52428800")
    with destination.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if maximum and size > maximum:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Authorization evidence file is too large.")
            digest.update(chunk)
            output.write(chunk)
    row = QualityAuthorizationEvidence(
        id=file_id,
        amo_id=ctx.amo_id,
        case_id=case.id,
        evidence_type=evidence_type,
        label=label.strip() or original,
        source_module="QUALITY",
        source_reference={"case_id": str(case.id)},
        original_filename=original,
        storage_path=str(destination),
        content_type=file.content_type,
        size_bytes=size,
        sha256=digest.hexdigest(),
        status="ACTIVE",
        uploaded_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    previous = case.status
    if case.status in {"NOMINATED", "AWAITING_EVIDENCE", "RETURNED"}:
        case.status = "UNDER_REVIEW"
    _case_event(
        db, ctx=ctx, row=case, action="EVIDENCE_UPLOADED", previous_status=previous,
        reason=f"Authorization evidence uploaded: {row.label}",
        after={"status": case.status, "evidence_type": evidence_type, "label": row.label},
    )
    db.commit()
    return _evidence_dict(row)


@router.get("/authorization-control/evidence/{evidence_id}/download")
def download_authorization_evidence(
    evidence_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuthorizationEvidence).filter(
        QualityAuthorizationEvidence.amo_id == ctx.amo_id,
        QualityAuthorizationEvidence.id == evidence_id,
        QualityAuthorizationEvidence.status == "ACTIVE",
    ).first()
    if row is None or not row.storage_path:
        raise HTTPException(status_code=404, detail="Authorization evidence file not found.")
    if not _can_view_tenant_authorization_register(db, ctx):
        owner_user_id = None
        if row.case_id:
            owner_user_id = db.query(QualityAuthorizationCase.user_id).filter(
                QualityAuthorizationCase.amo_id == ctx.amo_id,
                QualityAuthorizationCase.id == row.case_id,
            ).scalar()
        elif row.privilege_id:
            owner_user_id = db.query(QualityPrivilege.user_id).filter(
                QualityPrivilege.amo_id == ctx.amo_id,
                QualityPrivilege.id == row.privilege_id,
            ).scalar()
        _require_self_or_register_access(db, ctx, str(owner_user_id or ""))
    path = Path(row.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=409, detail="Authorization evidence file is missing from storage.")
    if row.sha256 and hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256.lower():
        raise HTTPException(status_code=409, detail="Authorization evidence failed integrity verification.")
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.original_filename or "authorization-evidence",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/authorization-control/authorizations")
def list_authorizations(
    status_filter: str | None = Query(default=None, alias="status"),
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = (
        db.query(QualityPrivilege, QualityPrivilegeRule, account_models.User)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .join(account_models.User, account_models.User.id == QualityPrivilege.user_id)
        .filter(QualityPrivilege.amo_id == ctx.amo_id)
    )
    if not _can_view_tenant_authorization_register(db, ctx):
        query = query.filter(QualityPrivilege.user_id == ctx.user_id)
    if status_filter:
        query = query.filter(QualityPrivilege.status == status_filter.upper())
    rows = query.order_by(QualityPrivilege.updated_at.desc()).limit(500).all()
    items = []
    for privilege, rule, user in rows:
        review = _latest_review(db, amo_id=ctx.amo_id, privilege_id=str(privilege.id))
        items.append({
            "key": str(privilege.id),
            "person": _person_name(user),
            "authorization": _authorization_label(rule),
            "status": privilege.status,
            "scope": "Global" if str(privilege.scope_key or "").upper() == "GLOBAL" else privilege.scope_key,
            "effective_from": privilege.effective_from.isoformat() if privilege.effective_from else None,
            "expires_on": privilege.expires_on.isoformat() if privilege.expires_on else None,
            "last_reviewed": review.last_reviewed.isoformat() if review else None,
            "next_review_due": (
                due.isoformat()
                if (due := _next_review_due(db, amo_id=ctx.amo_id, privilege_id=str(privilege.id)))
                else None
            ),
            "limitations": list(privilege.limitations or []),
        })
    return {"items": items}


@router.get("/authorization-control/authorizations/{privilege_id}/record")
def authorization_record(
    privilege_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_read_db),
):
    from html import escape
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = _privilege(db, amo_id=ctx.amo_id, privilege_id=privilege_id)
    _require_self_or_register_access(db, ctx, str(privilege.user_id))
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))
    person = _person(db, amo_id=ctx.amo_id, user_id=str(privilege.user_id))
    reviews = db.query(QualityAuthorizationReview).filter(
        QualityAuthorizationReview.amo_id == ctx.amo_id,
        QualityAuthorizationReview.privilege_id == privilege.id,
    ).order_by(QualityAuthorizationReview.reviewed_at.asc()).all()
    names = _actor_names(
        db, amo_id=ctx.amo_id,
        ids={
            str(value)
            for value in [
                *[item.decided_by_user_id for item in privilege.decisions],
                *[item.reviewed_by_user_id for item in reviews],
            ] if value
        },
    )
    output = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph("Quality Authorization Record", styles["Title"]), Spacer(1, 16)]
    facts = [
        ("Person", _person_name(person)),
        ("Quality authorization", _authorization_label(rule)),
        ("Status", privilege.status.title()),
        ("Scope", "Global" if str(privilege.scope_key or "").upper() == "GLOBAL" else privilege.scope_key),
        ("Effective from", privilege.effective_from or "Not set"),
        ("Expires", privilege.expires_on or "Not set"),
    ]
    for label, value in facts:
        story.append(Paragraph(f"<b>{escape(str(label))}:</b> {escape(str(value))}", styles["Normal"]))
        story.append(Spacer(1, 6))
    if privilege.limitations:
        story.append(Paragraph(f"<b>Limitations:</b> {escape('; '.join(str(item) for item in privilege.limitations))}", styles["Normal"]))
        story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Decision history</b>", styles["Heading2"]))
    for item in privilege.decisions:
        actor = names.get(str(item.decided_by_user_id), "Recorded decision authority")
        story.append(Paragraph(
            escape(f"{item.decided_at:%d %b %Y} — {item.decision_type.title()} — {actor}: {item.rationale}"),
            styles["Normal"],
        ))
        story.append(Spacer(1, 5))
    if reviews:
        story.append(Paragraph("<b>Periodic reviews</b>", styles["Heading2"]))
        for item in reviews:
            actor = names.get(str(item.reviewed_by_user_id), "Recorded reviewer")
            next_due = item.next_review_due.isoformat() if item.next_review_due else "Not set"
            story.append(Paragraph(
                escape(f"{item.last_reviewed.isoformat()} — {item.review_outcome.replace('_', ' ').title()} — {actor}; next review {next_due}: {item.review_reason}"),
                styles["Normal"],
            ))
            story.append(Spacer(1, 5))
    SimpleDocTemplate(output).build(story)
    return Response(
        output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="quality-authorization-record.pdf"', "Cache-Control": "no-store"},
    )
