from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_assignment_guard import evaluate_auditor_assignment
from .people_models import QualityIndependenceDeclaration
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit occurrence assignments"])
AssignmentRole = Literal["LEAD_AUDITOR", "OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"]
Declaration = Literal["INDEPENDENT", "CONFLICT", "REQUIRES_REVIEW"]


class AuditAssignmentUpdate(BaseModel):
    lead_auditor_user_id: str | None = Field(default=None, max_length=36)
    observer_auditor_user_id: str | None = Field(default=None, max_length=36)
    assistant_auditor_user_id: str | None = Field(default=None, max_length=36)
    reason: str = Field(min_length=8, max_length=4000)


class AuditIndependenceCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    declaration: Declaration
    relationship_to_subject: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=8, max_length=4000)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit occurrence not found.")
    return row


def _assignment_date(audit: models.QMSAudit) -> date:
    return audit.planned_start or audit.actual_start or date.today()


def _assignment_scope(audit: models.QMSAudit) -> str | None:
    return str(getattr(audit, "audit_scope_code", None) or "").strip() or None


def _evaluate(
    db: Session,
    *,
    audit: models.QMSAudit,
    amo_id: str,
    user_id: str,
    role: AssignmentRole,
) -> dict[str, Any]:
    return evaluate_auditor_assignment(
        db,
        amo_id=amo_id,
        user_id=user_id,
        assignment_role=role,
        as_of=_assignment_date(audit),
        assignment_scope_key=_assignment_scope(audit),
        context_type="AUDIT",
        context_id=str(audit.id),
        enforce_independence=True,
    )


def _blocked(results: list[dict[str, Any]]) -> None:
    failed = [row for row in results if not row.get("eligible")]
    if not failed:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Audit assignment is blocked by governed People & Privileges hard gates.",
            "assignments": failed,
            "required_action": "Resolve privilege, training, capacity or audit-specific independence before assigning the person.",
        },
    )


@router.get("/audits/{audit_id}/assignment-eligibility")
def audit_assignment_eligibility(
    audit_id: uuid.UUID,
    user_id: str = Query(min_length=1, max_length=36),
    assignment_role: AssignmentRole = Query(),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    return _evaluate(db, audit=audit, amo_id=ctx.amo_id, user_id=user_id, role=assignment_role)


@router.post("/audits/{audit_id}/independence", status_code=status.HTTP_201_CREATED)
def declare_audit_independence(
    audit_id: uuid.UUID,
    payload: AuditIndependenceCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id == payload.user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if user is None:
        raise HTTPException(status_code=422, detail="Selected person is inactive, belongs to another tenant, or does not exist.")

    existing = db.query(QualityIndependenceDeclaration).filter(
        QualityIndependenceDeclaration.amo_id == ctx.amo_id,
        QualityIndependenceDeclaration.user_id == payload.user_id,
        QualityIndependenceDeclaration.context_type == "AUDIT",
        QualityIndependenceDeclaration.context_id == str(audit_id),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="An independence declaration already exists for this person and audit. Preserve the historical declaration rather than overwriting it.")
    if payload.declaration == "CONFLICT" and not (payload.relationship_to_subject or "").strip():
        raise HTTPException(status_code=422, detail="A conflict declaration must describe the relationship to the audit subject.")
    row = QualityIndependenceDeclaration(
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        context_type="AUDIT",
        context_id=str(audit_id),
        declaration=payload.declaration,
        relationship_to_subject=(payload.relationship_to_subject or "").strip() or None,
        rationale=payload.rationale.strip(),
        source_references=payload.source_references,
        declared_by_user_id=ctx.user_id,
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
        "declared_at": row.declared_at.isoformat() if row.declared_at else None,
    }


@router.put("/audits/{audit_id}/assignments")
def update_audit_assignments(
    audit_id: uuid.UUID,
    payload: AuditAssignmentUpdate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    assignments: list[tuple[AssignmentRole, str]] = [
        ("LEAD_AUDITOR", payload.lead_auditor_user_id or ""),
        ("OBSERVER_AUDITOR", payload.observer_auditor_user_id or ""),
        ("ASSISTANT_AUDITOR", payload.assistant_auditor_user_id or ""),
    ]
    selected = [(role, user_id) for role, user_id in assignments if user_id]
    user_ids = [user_id for _, user_id in selected]
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(status_code=422, detail="The same person cannot hold more than one auditor role on the same occurrence.")

    results = [_evaluate(db, audit=audit, amo_id=ctx.amo_id, user_id=user_id, role=role) for role, user_id in selected]
    _blocked(results)

    previous = {
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
    }
    audit.lead_auditor_user_id = payload.lead_auditor_user_id or None
    audit.observer_auditor_user_id = payload.observer_auditor_user_id or None
    audit.assistant_auditor_user_id = payload.assistant_auditor_user_id or None
    db.commit()
    db.refresh(audit)
    return {
        "audit_id": str(audit.id),
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
        "previous_assignments": previous,
        "assignment_gate": results,
        "reason": payload.reason.strip(),
    }
