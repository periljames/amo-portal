from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _append_access_event
from .audit_occurrence_completion_models import (
    QualityAuditControlledDocumentSubmission,
    QualityAuditDocumentRequestMetadata,
)
from .audit_occurrence_completion_router import _validate_controlled_source
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit controlled document collaboration"])
public_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Audit Controlled Document Collaboration"])


class ControlledDocumentLinkCreate(BaseModel):
    document_id: uuid.UUID
    revision_id: uuid.UUID | None = None
    response_comment: str | None = Field(default=None, max_length=4000)


def _submission_dict(row: QualityAuditControlledDocumentSubmission) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "request_id": str(row.request_id),
        "document_id": str(row.document_id),
        "revision_id": str(row.revision_id) if row.revision_id else None,
        "response_comment": row.response_comment,
        "created_at": row.created_at.isoformat(),
    }


def _latest_by_request(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[uuid.UUID, QualityAuditControlledDocumentSubmission]:
    rows = db.query(QualityAuditControlledDocumentSubmission).filter(
        QualityAuditControlledDocumentSubmission.amo_id == amo_id,
        QualityAuditControlledDocumentSubmission.audit_id == audit_id,
    ).order_by(QualityAuditControlledDocumentSubmission.created_at.asc()).all()
    latest: dict[uuid.UUID, QualityAuditControlledDocumentSubmission] = {}
    for row in rows:
        latest[row.request_id] = row
    return latest


@router.get("/audits/{audit_id}/controlled-document-submissions")
def list_controlled_document_submissions(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    latest = _latest_by_request(db, amo_id=ctx.amo_id, audit_id=audit_id)
    return {"items": [_submission_dict(row) for row in latest.values()]}


@public_router.get("/governed-document-requests")
def public_governed_document_requests(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    if "audit:document_submit" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access does not permit preparation responses.")
    rows = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == grant.amo_id,
        models.QualityAuditDocumentRequest.audit_id == grant.audit_id,
    ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()
    metadata_rows = db.query(QualityAuditDocumentRequestMetadata).filter(
        QualityAuditDocumentRequestMetadata.amo_id == grant.amo_id,
        QualityAuditDocumentRequestMetadata.audit_id == grant.audit_id,
    ).all()
    metadata = {row.request_id: row for row in metadata_rows}
    latest = _latest_by_request(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
    items: list[dict[str, Any]] = []
    for row in rows:
        meta = metadata.get(row.id)
        controlled = latest.get(row.id)
        items.append({
            "id": str(row.id),
            "title": row.title,
            "description": row.description,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "status": row.status,
            "review_note": row.review_note,
            "request_type": meta.request_type if meta else "DOCUMENT",
            "linked_criterion": meta.linked_criterion if meta else None,
            "is_required": meta.is_required if meta else True,
            "source_mode": meta.source_mode if meta else "UPLOAD_OR_CONTROLLED",
            # Only an explicitly selected request document/revision is disclosed.
            # This endpoint never enumerates the tenant DMS library.
            "controlled_document_id": str(meta.controlled_document_id) if meta and meta.controlled_document_id else None,
            "controlled_revision_id": str(meta.controlled_revision_id) if meta and meta.controlled_revision_id else None,
            "controlled_submission": _submission_dict(controlled) if controlled else None,
        })
    return {"items": items}


@public_router.post("/document-requests/{request_id}/link-controlled", status_code=status.HTTP_201_CREATED)
def link_controlled_document_to_request(
    request_id: uuid.UUID,
    payload: ControlledDocumentLinkCreate,
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    if participant is None or participant.participant_type != "AUDITEE_GUEST":
        raise HTTPException(status_code=403, detail="Only the purpose-bound auditee may answer this preparation request.")
    if "audit:document_submit" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access does not permit preparation responses.")

    request = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == grant.amo_id,
        models.QualityAuditDocumentRequest.audit_id == grant.audit_id,
        models.QualityAuditDocumentRequest.id == request_id,
    ).with_for_update().first()
    metadata = db.query(QualityAuditDocumentRequestMetadata).filter(
        QualityAuditDocumentRequestMetadata.amo_id == grant.amo_id,
        QualityAuditDocumentRequestMetadata.audit_id == grant.audit_id,
        QualityAuditDocumentRequestMetadata.request_id == request_id,
    ).first()
    if request is None or metadata is None:
        raise HTTPException(status_code=404, detail="Preparation request not found.")
    if metadata.source_mode not in {"CONTROLLED_DMS", "UPLOAD_OR_CONTROLLED"}:
        raise HTTPException(status_code=409, detail="This preparation request accepts file upload only.")

    document, revision = _validate_controlled_source(
        db,
        amo_id=grant.amo_id,
        document_id=payload.document_id,
        revision_id=payload.revision_id,
    )
    if metadata.controlled_document_id and metadata.controlled_document_id != payload.document_id:
        raise HTTPException(status_code=403, detail="This request permits only its explicitly selected controlled document.")
    if metadata.controlled_revision_id and metadata.controlled_revision_id != payload.revision_id:
        raise HTTPException(status_code=403, detail="This request permits only its explicitly selected controlled revision.")

    row = QualityAuditControlledDocumentSubmission(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        request_id=request_id,
        participant_id=participant.id,
        document_id=document.id,
        revision_id=revision.id if revision else None,
        response_comment=(payload.response_comment or "").strip() or None,
    )
    db.add(row)
    db.flush()
    request.status = "UPLOADED"
    request.uploaded_at = row.created_at
    request.file_ref = f"CONTROLLED_DMS_LINK:{row.id}"
    _append_access_event(db, grant, "READ", f"Auditee linked controlled DMS evidence to preparation request {request_id}.")
    db.commit()
    db.refresh(row)
    return _submission_dict(row)
