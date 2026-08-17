from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _append_access_event
from .audit_occurrence_completion_models import (
    QualityAuditCanonicalDocumentSubmission,
    QualityAuditControlledDocumentSubmission,
    QualityAuditDocumentRequestMetadata,
)
from .audit_occurrence_completion_router import (
    _validate_canonical_controlled_source,
    _validate_controlled_source,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit controlled document collaboration"])
public_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Audit Controlled Document Collaboration"])


class ControlledDocumentLinkCreate(BaseModel):
    source_system: Literal["QMS_LOCAL", "DOCUMENT_CONTROL"] = "QMS_LOCAL"
    document_id: str = Field(min_length=1, max_length=64)
    revision_id: str | None = Field(default=None, max_length=64)
    response_comment: str | None = Field(default=None, max_length=4000)


def _qms_submission_dict(row: QualityAuditControlledDocumentSubmission) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "request_id": str(row.request_id),
        "source_system": "QMS_LOCAL",
        "document_id": str(row.document_id),
        "revision_id": str(row.revision_id) if row.revision_id else None,
        "response_comment": row.response_comment,
        "created_at": row.created_at.isoformat(),
    }


def _canonical_submission_dict(row: QualityAuditCanonicalDocumentSubmission) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "request_id": str(row.request_id),
        "source_system": "DOCUMENT_CONTROL",
        "document_id": row.document_id,
        "revision_id": row.revision_id,
        "response_comment": row.response_comment,
        "created_at": row.created_at.isoformat(),
    }


def _latest_by_request(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[uuid.UUID, dict[str, Any]]:
    """Merge the two repositories without conflating their identity domains."""
    latest: dict[uuid.UUID, tuple[Any, dict[str, Any]]] = {}

    qms_rows = db.query(QualityAuditControlledDocumentSubmission).filter(
        QualityAuditControlledDocumentSubmission.amo_id == amo_id,
        QualityAuditControlledDocumentSubmission.audit_id == audit_id,
    ).order_by(QualityAuditControlledDocumentSubmission.created_at.asc()).all()
    for row in qms_rows:
        latest[row.request_id] = (row.created_at, _qms_submission_dict(row))

    canonical_rows = db.query(QualityAuditCanonicalDocumentSubmission).filter(
        QualityAuditCanonicalDocumentSubmission.amo_id == amo_id,
        QualityAuditCanonicalDocumentSubmission.audit_id == audit_id,
    ).order_by(QualityAuditCanonicalDocumentSubmission.created_at.asc()).all()
    for row in canonical_rows:
        previous = latest.get(row.request_id)
        if previous is None or previous[0] <= row.created_at:
            latest[row.request_id] = (row.created_at, _canonical_submission_dict(row))

    return {request_id: payload for request_id, (_created_at, payload) in latest.items()}


def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a valid Quality-local UUID.") from exc


@router.get("/audits/{audit_id}/controlled-document-submissions")
def list_controlled_document_submissions(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    latest = _latest_by_request(db, amo_id=ctx.amo_id, audit_id=audit_id)
    return {"items": list(latest.values())}


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
            "controlled_source_system": meta.controlled_source_system if meta else "QMS_LOCAL",
            # Only an explicitly selected document/revision is disclosed. This
            # endpoint never enumerates either tenant repository.
            "controlled_document_id": str(meta.controlled_document_id) if meta and meta.controlled_document_id else None,
            "controlled_revision_id": str(meta.controlled_revision_id) if meta and meta.controlled_revision_id else None,
            "canonical_document_id": meta.canonical_document_id if meta else None,
            "canonical_revision_id": meta.canonical_revision_id if meta else None,
            "controlled_submission": controlled,
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

    expected_source = metadata.controlled_source_system or "QMS_LOCAL"
    if payload.source_system != expected_source:
        raise HTTPException(
            status_code=403,
            detail="The submitted controlled-document source does not match the repository authorised for this request.",
        )

    comment = (payload.response_comment or "").strip() or None

    if expected_source == "QMS_LOCAL":
        document_id = _parse_uuid(payload.document_id, field_name="document_id")
        revision_id = _parse_uuid(payload.revision_id, field_name="revision_id") if payload.revision_id else None
        document, revision = _validate_controlled_source(
            db,
            amo_id=grant.amo_id,
            document_id=document_id,
            revision_id=revision_id,
        )
        if metadata.controlled_document_id and metadata.controlled_document_id != document_id:
            raise HTTPException(status_code=403, detail="This request permits only its explicitly selected Quality-local document.")
        if metadata.controlled_revision_id and metadata.controlled_revision_id != revision_id:
            raise HTTPException(status_code=403, detail="This request permits only its explicitly selected Quality-local revision.")

        row = QualityAuditControlledDocumentSubmission(
            amo_id=grant.amo_id,
            audit_id=grant.audit_id,
            request_id=request_id,
            participant_id=participant.id,
            document_id=document.id,
            revision_id=revision.id if revision else None,
            response_comment=comment,
        )
        db.add(row)
        db.flush()
        request.file_ref = f"QMS_LOCAL_CONTROLLED_LINK:{row.id}"
        event_text = f"Auditee linked Quality-local controlled evidence to preparation request {request_id}."
        response = _qms_submission_dict(row)
        submission_created_at = row.created_at
    else:
        if not metadata.canonical_document_id or not metadata.canonical_revision_id:
            raise HTTPException(
                status_code=409,
                detail="Quality must preselect an exact canonical Document Control revision before an auditee can link it.",
            )
        if payload.document_id != metadata.canonical_document_id:
            raise HTTPException(status_code=403, detail="This request permits only its explicitly selected Document Control document.")
        if payload.revision_id != metadata.canonical_revision_id:
            raise HTTPException(status_code=403, detail="This request permits only its explicitly selected Document Control revision.")

        document, revision = _validate_canonical_controlled_source(
            db,
            amo_id=grant.amo_id,
            document_id=payload.document_id,
            revision_id=payload.revision_id,
            require_revision=True,
        )
        assert document is not None and revision is not None
        canonical_row = QualityAuditCanonicalDocumentSubmission(
            amo_id=grant.amo_id,
            audit_id=grant.audit_id,
            request_id=request_id,
            participant_id=participant.id,
            document_id=document.id,
            revision_id=revision.id,
            response_comment=comment,
        )
        db.add(canonical_row)
        db.flush()
        request.file_ref = f"DOCUMENT_CONTROL_LINK:{canonical_row.id}"
        event_text = f"Auditee linked canonical Document Control evidence to preparation request {request_id}."
        response = _canonical_submission_dict(canonical_row)
        submission_created_at = canonical_row.created_at

    request.status = "UPLOADED"
    request.uploaded_at = submission_created_at
    _append_access_event(db, grant, "READ", event_text)
    db.commit()
    return response
