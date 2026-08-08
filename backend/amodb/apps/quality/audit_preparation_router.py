from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_preparation_models import QualityAuditPreparationEvent, QualityAuditPreparationRevision
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit preparation governance"])


class PreparationRevisionCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)
    preparation_scope: str | None = Field(default=None, max_length=8000)


class PreparationIssue(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _capture_sources(db: Session, *, amo_id: str, audit: models.QMSAudit) -> dict[str, Any]:
    checklist = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit.id,
    ).order_by(
        models.QualityAuditChecklistItem.section.asc(),
        models.QualityAuditChecklistItem.sort_order.asc(),
        models.QualityAuditChecklistItem.created_at.asc(),
    ).all()
    requests = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit.id,
    ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()

    audit_snapshot = {
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "domain": _enum_value(audit.domain),
        "kind": _enum_value(audit.kind),
        "status": _enum_value(audit.status),
        "scope": audit.scope,
        "criteria": audit.criteria,
        "audit_scope_id": str(audit.audit_scope_id) if audit.audit_scope_id else None,
        "audit_scope_code": audit.audit_scope_code,
        "auditee": audit.auditee,
        "auditee_user_id": audit.auditee_user_id,
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
        "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
        "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
    }
    checklist_snapshot = [
        {
            "id": str(item.id),
            "section": item.section,
            "checklist_ref": item.checklist_ref,
            "requirement_ref": item.requirement_ref,
            "prompt": item.prompt,
            "response_status": item.response_status,
            "objective_evidence": item.objective_evidence,
            "finding_id": str(item.finding_id) if item.finding_id else None,
            "assigned_to_user_id": item.assigned_to_user_id,
            "sort_order": item.sort_order,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in checklist
    ]
    request_snapshot = [
        {
            "id": str(item.id),
            "title": item.title,
            "description": item.description,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status,
            "file_ref": item.file_ref,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in requests
    ]
    source_references = [
        {"source_type": "QMS_AUDIT", "source_id": str(audit.id), "source_route": f"/quality/audit/{audit.id}/run"},
        *[
            {"source_type": "QUALITY_AUDIT_CHECKLIST_ITEM", "source_id": str(item.id), "source_route": f"/quality/audit/{audit.id}/run"}
            for item in checklist
        ],
        *[
            {"source_type": "QUALITY_AUDIT_DOCUMENT_REQUEST", "source_id": str(item.id), "source_route": f"/quality/audit/{audit.id}/run"}
            for item in requests
        ],
    ]
    fingerprint_payload = {
        "audit": audit_snapshot,
        "checklist": checklist_snapshot,
        "document_requests": request_snapshot,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "audit_snapshot": audit_snapshot,
        "checklist_snapshot": checklist_snapshot,
        "document_request_snapshot": request_snapshot,
        "source_references": source_references,
        "source_fingerprint": fingerprint,
    }


def _event_dict(row: QualityAuditPreparationEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _revision_dict(row: QualityAuditPreparationRevision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "revision_no": row.revision_no,
        "status": row.status,
        "preparation_scope": row.preparation_scope,
        "audit_snapshot": row.audit_snapshot or {},
        "checklist_snapshot": row.checklist_snapshot or [],
        "document_request_snapshot": row.document_request_snapshot or [],
        "source_references": row.source_references or [],
        "source_fingerprint": row.source_fingerprint,
        "change_reason": row.change_reason,
        "supersedes_revision_id": row.supersedes_revision_id,
        "issued_by_user_id": row.issued_by_user_id,
        "issued_at": row.issued_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


@router.get("/audits/{audit_id}/preparation-revisions")
def list_preparation_revisions(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditPreparationRevision).options(
        selectinload(QualityAuditPreparationRevision.events)
    ).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).limit(100).all()
    return {"items": [_revision_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/preparation-revisions", status_code=status.HTTP_201_CREATED)
def create_preparation_revision(
    audit_id: uuid.UUID,
    payload: PreparationRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    latest = db.query(QualityAuditPreparationRevision).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status == "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A draft preparation revision already exists. Issue it or discard the draft through the governed workflow before creating another revision.",
        )
    captured = _capture_sources(db, amo_id=ctx.amo_id, audit=audit)
    row = QualityAuditPreparationRevision(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        status="DRAFT",
        preparation_scope=payload.preparation_scope,
        **captured,
        change_reason=payload.reason.strip(),
        supersedes_revision_id=str(latest.id) if latest else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    db.add(QualityAuditPreparationEvent(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_id=row.id,
        event_type="CREATED",
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    ))
    db.commit()
    return _revision_dict(
        db.query(QualityAuditPreparationRevision).options(selectinload(QualityAuditPreparationRevision.events)).filter(
            QualityAuditPreparationRevision.amo_id == ctx.amo_id,
            QualityAuditPreparationRevision.id == row.id,
        ).one()
    )


@router.post("/audits/{audit_id}/preparation-revisions/{revision_id}/issue")
def issue_preparation_revision(
    audit_id: uuid.UUID,
    revision_id: str,
    payload: PreparationIssue,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditPreparationRevision).options(
        selectinload(QualityAuditPreparationRevision.events)
    ).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
        QualityAuditPreparationRevision.id == revision_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit preparation revision not found.")
    if row.status != "DRAFT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a DRAFT preparation revision may be issued.")
    current = _capture_sources(db, amo_id=ctx.amo_id, audit=audit)
    if current["source_fingerprint"] != row.source_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The live audit preparation sources changed after this draft snapshot was created.",
                "draft_fingerprint": row.source_fingerprint,
                "current_fingerprint": current["source_fingerprint"],
                "required_action": "Create a fresh preparation revision so the issued snapshot matches the current controlled checklist, audit criteria and document requests.",
            },
        )
    row.status = "ISSUED"
    row.issued_by_user_id = ctx.user_id
    row.issued_at = _utcnow()
    db.add(QualityAuditPreparationEvent(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_id=row.id,
        event_type="ISSUED",
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    ))
    db.commit()
    db.refresh(row)
    return _revision_dict(row)
