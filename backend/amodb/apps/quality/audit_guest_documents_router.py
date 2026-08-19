from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db, get_write_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant
from .audit_guest_document_models import QualityAuditDocumentSubmission
from .audit_guest_document_storage import resolve_guest_document, store_guest_document
from .router import public_router
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit document submissions"])
_public_extension = APIRouter(prefix="/quality", tags=["Quality / External Audit Documents"])


def _request_for_audit(db: Session, *, amo_id: str, audit_id: uuid.UUID, request_id: uuid.UUID) -> models.QualityAuditDocumentRequest:
    row = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit_id,
        models.QualityAuditDocumentRequest.id == request_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit document request not found.")
    return row


def _serialize(row: QualityAuditDocumentSubmission) -> dict[str, object]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "document_request_id": str(row.document_request_id),
        "source_type": row.source_type,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "sha256": row.sha256,
        "response_comment": row.response_comment,
        "participant_id": row.participant_id,
        "submitted_by_user_id": row.submitted_by_user_id,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/audits/{audit_id}/document-requests/{request_id}/submissions")
def list_document_submissions(
    audit_id: uuid.UUID,
    request_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _request_for_audit(db, amo_id=ctx.amo_id, audit_id=audit_id, request_id=request_id)
    rows = db.query(QualityAuditDocumentSubmission).filter(
        QualityAuditDocumentSubmission.amo_id == ctx.amo_id,
        QualityAuditDocumentSubmission.audit_id == audit_id,
        QualityAuditDocumentSubmission.document_request_id == request_id,
    ).order_by(QualityAuditDocumentSubmission.created_at.desc()).all()
    return {"items": [_serialize(row) for row in rows]}


@router.get("/audits/{audit_id}/document-requests/{request_id}/submissions/{submission_id}/download")
def download_document_submission(
    audit_id: uuid.UUID,
    request_id: uuid.UUID,
    submission_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _request_for_audit(db, amo_id=ctx.amo_id, audit_id=audit_id, request_id=request_id)
    row = db.query(QualityAuditDocumentSubmission).filter(
        QualityAuditDocumentSubmission.amo_id == ctx.amo_id,
        QualityAuditDocumentSubmission.audit_id == audit_id,
        QualityAuditDocumentSubmission.document_request_id == request_id,
        QualityAuditDocumentSubmission.id == submission_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit document submission not found.")
    path = resolve_guest_document(row.storage_ref)
    return FileResponse(path, filename=row.filename, media_type=row.content_type or "application/octet-stream")


@_public_extension.post("/audit-access/document-requests/{request_id}/submit", status_code=status.HTTP_201_CREATED)
async def submit_guest_document(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    response_comment: str | None = Form(default=None, max_length=4000),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
):
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    if "audit:document_submit" not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access does not permit document submission.")
    request_row = _request_for_audit(
        db,
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        request_id=request_id,
    )
    if request_row.status in {"ACCEPTED", "WAIVED"}:
        raise HTTPException(status_code=409, detail="This document request no longer accepts submissions.")

    stored = await store_guest_document(
        file,
        amo_id=str(grant.amo_id),
        audit_id=str(grant.audit_id),
        request_id=str(request_id),
    )
    submission = QualityAuditDocumentSubmission(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        document_request_id=request_id,
        participant_id=grant.participant_id,
        source_type="UPLOAD",
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        storage_ref=stored.storage_ref,
        response_comment=(response_comment or "").strip() or None,
        submitted_by_user_id=None,
    )
    db.add(submission)
    db.flush()

    request_row.status = "UPLOADED"
    request_row.file_ref = f"audit-submission:{submission.id}"
    request_row.uploaded_at = submission.created_at
    request_row.uploaded_by_user_id = None
    db.commit()
    db.refresh(submission)
    return _serialize(submission)


# Public extension shares the same purpose-bound HTTP-only audit session created
# by audit_external_access_router. It never accepts tenant/audit IDs from the
# browser; both are derived from the verified grant.
public_router.routes[0:0] = list(_public_extension.routes)
