from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import domain_models as doc_control_models
from amodb.apps.doc_control.workspace_service import can_read_manual
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db, get_read_db, get_write_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _latest_release_events
from .audit_occurrence_completion_models import (
    QualityAuditClosingNarrative,
    QualityAuditDocumentRequestMetadata,
    QualityAuditMeeting,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit occurrence completion"])
public_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Audit Occurrence Collaboration"])

ControlledSourceSystem = Literal["QMS_LOCAL", "DOCUMENT_CONTROL"]
_CANONICAL_CONTROLLED_REVISION_STATUSES = {
    manual_models.ManualRevisionStatus.PUBLISHED,
    manual_models.ManualRevisionStatus.SUPERSEDED,
    manual_models.ManualRevisionStatus.ARCHIVED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _audit(db: Session, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit occurrence not found.")
    return row


def _normalise_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


class GovernedDocumentRequestCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    due_date: str | None = None
    request_type: Literal["DOCUMENT", "RECORD", "MANUAL", "FORM", "CERTIFICATE", "REGISTER", "OTHER"] = "DOCUMENT"
    linked_criterion: str | None = Field(default=None, max_length=4000)
    is_required: bool = True
    source_mode: Literal["UPLOAD", "CONTROLLED_DMS", "UPLOAD_OR_CONTROLLED"] = "UPLOAD_OR_CONTROLLED"

    # QMS_LOCAL is the compatibility default for older API clients. New frontend
    # flows explicitly choose DOCUMENT_CONTROL when they use the canonical library.
    controlled_source_system: ControlledSourceSystem = "QMS_LOCAL"
    controlled_document_id: uuid.UUID | None = None
    controlled_revision_id: uuid.UUID | None = None
    canonical_document_id: str | None = Field(default=None, max_length=36)
    canonical_revision_id: str | None = Field(default=None, max_length=36)


class GovernedDocumentRequestUpdate(BaseModel):
    status: Literal["REQUESTED", "UPLOADED", "ACCEPTED", "REJECTED", "WAIVED"] | None = None
    review_note: str | None = Field(default=None, max_length=8000)
    request_type: Literal["DOCUMENT", "RECORD", "MANUAL", "FORM", "CERTIFICATE", "REGISTER", "OTHER"] | None = None
    linked_criterion: str | None = Field(default=None, max_length=4000)
    is_required: bool | None = None
    source_mode: Literal["UPLOAD", "CONTROLLED_DMS", "UPLOAD_OR_CONTROLLED"] | None = None
    controlled_source_system: ControlledSourceSystem | None = None
    controlled_document_id: uuid.UUID | None = None
    controlled_revision_id: uuid.UUID | None = None
    canonical_document_id: str | None = Field(default=None, max_length=36)
    canonical_revision_id: str | None = Field(default=None, max_length=36)


class AuditMeetingCreate(BaseModel):
    meeting_type: Literal["OPENING", "CLOSING", "FOLLOW_UP", "OTHER"]
    scheduled_start: datetime
    scheduled_end: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    conference_url: str | None = Field(default=None, max_length=1024)
    agenda: str | None = Field(default=None, max_length=12000)
    status: Literal["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"] = "PLANNED"
    notes: str | None = Field(default=None, max_length=12000)


class AuditMeetingUpdate(BaseModel):
    meeting_type: Literal["OPENING", "CLOSING", "FOLLOW_UP", "OTHER"] | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    conference_url: str | None = Field(default=None, max_length=1024)
    agenda: str | None = Field(default=None, max_length=12000)
    status: Literal["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"] | None = None
    notes: str | None = Field(default=None, max_length=12000)


class ClosingNarrativeUpdate(BaseModel):
    conclusion: str | None = Field(default=None, max_length=30000)
    positive_practices: str | None = Field(default=None, max_length=30000)
    management_summary: str | None = Field(default=None, max_length=30000)


def _validate_controlled_source(
    db: Session,
    *,
    amo_id: str,
    document_id: uuid.UUID | None,
    revision_id: uuid.UUID | None,
) -> tuple[models.QMSDocument | None, models.QMSDocumentRevision | None]:
    """Validate the legacy Quality-local controlled-document source."""
    if revision_id is not None and document_id is None:
        raise HTTPException(status_code=422, detail="A Quality-local revision must be linked to its Quality-local document.")
    document = None
    revision = None
    if document_id is not None:
        document = db.query(models.QMSDocument).filter(
            models.QMSDocument.amo_id == amo_id,
            models.QMSDocument.id == document_id,
        ).first()
        if document is None:
            raise HTTPException(status_code=422, detail="Quality-local controlled document is not available in this tenant.")
    if revision_id is not None:
        revision = db.query(models.QMSDocumentRevision).filter(
            models.QMSDocumentRevision.amo_id == amo_id,
            models.QMSDocumentRevision.id == revision_id,
            models.QMSDocumentRevision.document_id == document_id,
        ).first()
        if revision is None:
            raise HTTPException(status_code=422, detail="Quality-local controlled revision does not belong to the selected document.")
    return document, revision


def _manual_tenant(db: Session, amo_id: str) -> manual_models.Tenant | None:
    return db.query(manual_models.Tenant).filter(manual_models.Tenant.amo_id == amo_id).first()


def _document_control_user(db: Session, *, amo_id: str, user_id: str | None) -> account_models.User | None:
    if not user_id:
        return None
    return db.query(account_models.User).filter(
        account_models.User.id == user_id,
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
    ).first()


def _validate_canonical_controlled_source(
    db: Session,
    *,
    amo_id: str,
    document_id: str | None,
    revision_id: str | None,
    user_id: str | None = None,
    require_revision: bool = False,
) -> tuple[manual_models.Manual | None, manual_models.ManualRevision | None]:
    """Validate a canonical Document Control document and exact controlled revision."""
    document_id = (document_id or "").strip() or None
    revision_id = (revision_id or "").strip() or None
    if revision_id and not document_id:
        raise HTTPException(status_code=422, detail="A canonical revision must be linked to its Document Control document.")
    if require_revision and document_id and not revision_id:
        raise HTTPException(status_code=422, detail="Canonical Document Control evidence must identify an exact controlled revision.")
    if not document_id:
        return None, None

    tenant = _manual_tenant(db, amo_id)
    if tenant is None:
        raise HTTPException(status_code=422, detail="Document Control is not configured for this tenant.")

    document = db.query(manual_models.Manual).filter(
        manual_models.Manual.id == document_id,
        manual_models.Manual.tenant_id == tenant.id,
    ).first()
    if document is None:
        raise HTTPException(status_code=422, detail="Canonical Document Control document is not available in this tenant.")

    if user_id is not None:
        user = _document_control_user(db, amo_id=amo_id, user_id=user_id)
        if user is None:
            raise HTTPException(status_code=403, detail="Document Control access could not be established for this user.")
        profile = db.query(doc_control_models.DocumentControlProfile).filter(
            doc_control_models.DocumentControlProfile.tenant_id == amo_id,
            doc_control_models.DocumentControlProfile.manual_id == document.id,
        ).first()
        if not can_read_manual(user, profile):
            raise HTTPException(status_code=403, detail="The selected Document Control record is restricted.")

    revision = None
    if revision_id:
        revision = db.query(manual_models.ManualRevision).filter(
            manual_models.ManualRevision.id == revision_id,
            manual_models.ManualRevision.manual_id == document.id,
        ).first()
        if revision is None:
            raise HTTPException(status_code=422, detail="Canonical revision does not belong to the selected Document Control document.")
        if revision.status_enum not in _CANONICAL_CONTROLLED_REVISION_STATUSES:
            raise HTTPException(
                status_code=422,
                detail="Audit evidence may reference only a published, superseded, or archived Document Control revision.",
            )
    return document, revision


def _validate_request_controlled_selection(
    db: Session,
    *,
    amo_id: str,
    user_id: str | None,
    source_mode: str,
    source_system: str,
    controlled_document_id: uuid.UUID | None,
    controlled_revision_id: uuid.UUID | None,
    canonical_document_id: str | None,
    canonical_revision_id: str | None,
) -> tuple[
    uuid.UUID | None,
    uuid.UUID | None,
    str | None,
    str | None,
]:
    if source_system not in {"QMS_LOCAL", "DOCUMENT_CONTROL"}:
        raise HTTPException(status_code=422, detail="Unknown controlled-document source system.")

    if source_mode == "UPLOAD":
        if any((controlled_document_id, controlled_revision_id, canonical_document_id, canonical_revision_id)):
            raise HTTPException(status_code=422, detail="Upload-only requests cannot carry controlled-document references.")
        return None, None, None, None

    if source_system == "QMS_LOCAL":
        if canonical_document_id or canonical_revision_id:
            raise HTTPException(status_code=422, detail="Canonical Document Control IDs cannot be stored as Quality-local references.")
        document, revision = _validate_controlled_source(
            db,
            amo_id=amo_id,
            document_id=controlled_document_id,
            revision_id=controlled_revision_id,
        )
        if source_mode == "CONTROLLED_DMS" and document is None:
            raise HTTPException(status_code=422, detail="A Quality-local controlled document is required for this request.")
        return (
            document.id if document else None,
            revision.id if revision else None,
            None,
            None,
        )

    if controlled_document_id or controlled_revision_id:
        raise HTTPException(status_code=422, detail="Quality-local UUIDs cannot be stored as canonical Document Control references.")
    document, revision = _validate_canonical_controlled_source(
        db,
        amo_id=amo_id,
        document_id=canonical_document_id,
        revision_id=canonical_revision_id,
        user_id=user_id,
        require_revision=bool(canonical_document_id),
    )
    if source_mode == "CONTROLLED_DMS" and (document is None or revision is None):
        raise HTTPException(
            status_code=422,
            detail="A canonical Document Control document and exact controlled revision are required for this request.",
        )
    return (
        None,
        None,
        document.id if document else None,
        revision.id if revision else None,
    )


def _doc_request_dict(row: models.QualityAuditDocumentRequest, metadata: QualityAuditDocumentRequestMetadata | None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "title": row.title,
        "description": row.description,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "file_ref": row.file_ref,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "request_type": metadata.request_type if metadata else "DOCUMENT",
        "linked_criterion": metadata.linked_criterion if metadata else None,
        "is_required": metadata.is_required if metadata else True,
        "source_mode": metadata.source_mode if metadata else "UPLOAD_OR_CONTROLLED",
        "controlled_source_system": metadata.controlled_source_system if metadata else "QMS_LOCAL",
        "controlled_document_id": str(metadata.controlled_document_id) if metadata and metadata.controlled_document_id else None,
        "controlled_revision_id": str(metadata.controlled_revision_id) if metadata and metadata.controlled_revision_id else None,
        "canonical_document_id": metadata.canonical_document_id if metadata else None,
        "canonical_revision_id": metadata.canonical_revision_id if metadata else None,
    }


def _meeting_dict(row: QualityAuditMeeting, *, public: bool = False) -> dict[str, Any]:
    payload = {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "meeting_type": row.meeting_type,
        "scheduled_start": row.scheduled_start.isoformat(),
        "scheduled_end": row.scheduled_end.isoformat() if row.scheduled_end else None,
        "location": row.location,
        "conference_url": row.conference_url,
        "agenda": row.agenda,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if not public:
        payload["notes"] = row.notes
    return payload


def _narrative_dict(row: QualityAuditClosingNarrative | None) -> dict[str, Any]:
    return {
        "conclusion": row.conclusion if row else None,
        "positive_practices": row.positive_practices if row else None,
        "management_summary": row.management_summary if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


@router.get("/audits/{audit_id}/governed-document-requests")
def list_governed_document_requests(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    rows = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == ctx.amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit_id,
    ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()
    metadata_rows = db.query(QualityAuditDocumentRequestMetadata).filter(
        QualityAuditDocumentRequestMetadata.amo_id == ctx.amo_id,
        QualityAuditDocumentRequestMetadata.audit_id == audit_id,
    ).all()
    metadata = {row.request_id: row for row in metadata_rows}
    return {"items": [_doc_request_dict(row, metadata.get(row.id)) for row in rows]}


@router.get("/audits/{audit_id}/document-control/documents")
def list_canonical_document_control_documents(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Expose the canonical Document Control library through a QMS-purpose bridge."""
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    tenant = _manual_tenant(db, ctx.amo_id)
    if tenant is None:
        return {"items": []}
    user = _document_control_user(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="Document Control access could not be established for this user.")

    documents = db.query(manual_models.Manual).filter(
        manual_models.Manual.tenant_id == tenant.id,
    ).order_by(manual_models.Manual.code.asc(), manual_models.Manual.title.asc()).all()
    document_ids = [row.id for row in documents]
    profiles = {
        row.manual_id: row
        for row in db.query(doc_control_models.DocumentControlProfile).filter(
            doc_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
            doc_control_models.DocumentControlProfile.manual_id.in_(document_ids or ["-"]),
        ).all()
    }
    items = []
    for document in documents:
        if not can_read_manual(user, profiles.get(document.id)):
            continue
        items.append({
            "id": document.id,
            "code": document.code,
            "title": document.title,
            "manual_type": document.manual_type,
            "status": document.status,
            "current_published_revision_id": document.current_published_rev_id,
        })
    return {"items": items}


@router.get("/audits/{audit_id}/document-control/documents/{document_id}/revisions")
def list_canonical_document_control_revisions(
    audit_id: uuid.UUID,
    document_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    document, _ = _validate_canonical_controlled_source(
        db,
        amo_id=ctx.amo_id,
        document_id=document_id,
        revision_id=None,
        user_id=ctx.user_id,
    )
    assert document is not None
    revisions = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.manual_id == document.id,
        manual_models.ManualRevision.status_enum.in_(tuple(_CANONICAL_CONTROLLED_REVISION_STATUSES)),
    ).order_by(
        manual_models.ManualRevision.created_at.desc(),
        manual_models.ManualRevision.id.desc(),
    ).all()
    return {
        "items": [
            {
                "id": revision.id,
                "document_id": document.id,
                "issue_number": revision.issue_number,
                "revision_number": revision.rev_number,
                "status": _enum_value(revision.status_enum),
                "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
                "source_sha256": revision.source_sha256,
            }
            for revision in revisions
        ]
    }


@router.post("/audits/{audit_id}/governed-document-requests", status_code=status.HTTP_201_CREATED)
def create_governed_document_request(
    audit_id: uuid.UUID,
    payload: GovernedDocumentRequestCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    from datetime import date

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    qms_document_id, qms_revision_id, canonical_document_id, canonical_revision_id = _validate_request_controlled_selection(
        db,
        amo_id=ctx.amo_id,
        user_id=ctx.user_id,
        source_mode=payload.source_mode,
        source_system=payload.controlled_source_system,
        controlled_document_id=payload.controlled_document_id,
        controlled_revision_id=payload.controlled_revision_id,
        canonical_document_id=payload.canonical_document_id,
        canonical_revision_id=payload.canonical_revision_id,
    )
    due_date = date.fromisoformat(payload.due_date) if payload.due_date else None
    row = models.QualityAuditDocumentRequest(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        due_date=due_date,
        status="REQUESTED",
        requested_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    metadata = QualityAuditDocumentRequestMetadata(
        request_id=row.id,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        request_type=payload.request_type,
        linked_criterion=(payload.linked_criterion or "").strip() or None,
        is_required=payload.is_required,
        source_mode=payload.source_mode,
        controlled_source_system=payload.controlled_source_system,
        controlled_document_id=qms_document_id,
        controlled_revision_id=qms_revision_id,
        canonical_document_id=canonical_document_id,
        canonical_revision_id=canonical_revision_id,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(metadata)
    db.commit()
    db.refresh(row)
    db.refresh(metadata)
    return _doc_request_dict(row, metadata)


@router.patch("/audits/{audit_id}/governed-document-requests/{request_id}")
def update_governed_document_request(
    audit_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: GovernedDocumentRequestUpdate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    row = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == ctx.amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit_id,
        models.QualityAuditDocumentRequest.id == request_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Document request not found.")
    metadata = db.query(QualityAuditDocumentRequestMetadata).filter(
        QualityAuditDocumentRequestMetadata.amo_id == ctx.amo_id,
        QualityAuditDocumentRequestMetadata.audit_id == audit_id,
        QualityAuditDocumentRequestMetadata.request_id == request_id,
    ).with_for_update().first()
    if metadata is None:
        metadata = QualityAuditDocumentRequestMetadata(
            request_id=request_id,
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            created_by_user_id=ctx.user_id,
        )
        db.add(metadata)

    update = payload.model_dump(exclude_unset=True)
    next_source_mode = update.get("source_mode", metadata.source_mode or "UPLOAD_OR_CONTROLLED")
    next_source_system = update.get("controlled_source_system", metadata.controlled_source_system or "QMS_LOCAL")
    next_qms_document_id = update.get("controlled_document_id", metadata.controlled_document_id)
    next_qms_revision_id = update.get("controlled_revision_id", metadata.controlled_revision_id)
    next_canonical_document_id = update.get("canonical_document_id", metadata.canonical_document_id)
    next_canonical_revision_id = update.get("canonical_revision_id", metadata.canonical_revision_id)

    # Switching repository is explicit and clears identities from the other source;
    # IDs are never coerced or relabelled between the two repositories.
    if next_source_mode == "UPLOAD":
        next_qms_document_id = None
        next_qms_revision_id = None
        next_canonical_document_id = None
        next_canonical_revision_id = None
    elif next_source_system == "QMS_LOCAL":
        next_canonical_document_id = None
        next_canonical_revision_id = None
    else:
        next_qms_document_id = None
        next_qms_revision_id = None

    qms_document_id, qms_revision_id, canonical_document_id, canonical_revision_id = _validate_request_controlled_selection(
        db,
        amo_id=ctx.amo_id,
        user_id=ctx.user_id,
        source_mode=next_source_mode,
        source_system=next_source_system,
        controlled_document_id=next_qms_document_id,
        controlled_revision_id=next_qms_revision_id,
        canonical_document_id=next_canonical_document_id,
        canonical_revision_id=next_canonical_revision_id,
    )

    if "status" in update and update["status"] is not None:
        row.status = update["status"]
        row.reviewed_by_user_id = ctx.user_id
        row.reviewed_at = _utcnow()
    if "review_note" in update:
        row.review_note = (update["review_note"] or "").strip() or None
    for field in ("request_type", "linked_criterion", "is_required"):
        if field in update:
            value = update[field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(metadata, field, value)

    metadata.source_mode = next_source_mode
    metadata.controlled_source_system = next_source_system
    metadata.controlled_document_id = qms_document_id
    metadata.controlled_revision_id = qms_revision_id
    metadata.canonical_document_id = canonical_document_id
    metadata.canonical_revision_id = canonical_revision_id
    metadata.updated_by_user_id = ctx.user_id
    metadata.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    db.refresh(metadata)
    return _doc_request_dict(row, metadata)


@router.get("/audits/{audit_id}/meetings")
def list_audit_meetings(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    rows = db.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.amo_id == ctx.amo_id,
        QualityAuditMeeting.audit_id == audit_id,
    ).order_by(QualityAuditMeeting.scheduled_start.asc()).all()
    return {"items": [_meeting_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/meetings", status_code=status.HTTP_201_CREATED)
def create_audit_meeting(
    audit_id: uuid.UUID,
    payload: AuditMeetingCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    start = _normalise_datetime(payload.scheduled_start)
    end = _normalise_datetime(payload.scheduled_end) if payload.scheduled_end else None
    if end and end < start:
        raise HTTPException(status_code=422, detail="Meeting end cannot be before its start.")
    row = QualityAuditMeeting(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        meeting_type=payload.meeting_type,
        scheduled_start=start,
        scheduled_end=end,
        location=(payload.location or "").strip() or None,
        conference_url=(payload.conference_url or "").strip() or None,
        agenda=(payload.agenda or "").strip() or None,
        status=payload.status,
        notes=(payload.notes or "").strip() or None,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _meeting_dict(row)


@router.patch("/audits/{audit_id}/meetings/{meeting_id}")
def update_audit_meeting(
    audit_id: uuid.UUID,
    meeting_id: uuid.UUID,
    payload: AuditMeetingUpdate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.amo_id == ctx.amo_id,
        QualityAuditMeeting.audit_id == audit_id,
        QualityAuditMeeting.id == meeting_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit meeting not found.")
    update = payload.model_dump(exclude_unset=True)
    for field, value in update.items():
        if field in {"scheduled_start", "scheduled_end"} and value is not None:
            value = _normalise_datetime(value)
        elif isinstance(value, str):
            value = value.strip() or None
        setattr(row, field, value)
    if row.scheduled_end and row.scheduled_end < row.scheduled_start:
        raise HTTPException(status_code=422, detail="Meeting end cannot be before its start.")
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _meeting_dict(row)


@router.get("/audits/{audit_id}/closing-narrative")
def get_closing_narrative(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    row = db.query(QualityAuditClosingNarrative).filter(
        QualityAuditClosingNarrative.amo_id == ctx.amo_id,
        QualityAuditClosingNarrative.audit_id == audit_id,
    ).first()
    return _narrative_dict(row)


@router.put("/audits/{audit_id}/closing-narrative")
def update_closing_narrative(
    audit_id: uuid.UUID,
    payload: ClosingNarrativeUpdate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, ctx.amo_id, audit_id)
    row = db.query(QualityAuditClosingNarrative).filter(
        QualityAuditClosingNarrative.amo_id == ctx.amo_id,
        QualityAuditClosingNarrative.audit_id == audit_id,
    ).with_for_update().first()
    if row is None:
        row = QualityAuditClosingNarrative(amo_id=ctx.amo_id, audit_id=audit_id)
        db.add(row)
    row.conclusion = (payload.conclusion or "").strip() or None
    row.positive_practices = (payload.positive_practices or "").strip() or None
    row.management_summary = (payload.management_summary or "").strip() or None
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _narrative_dict(row)


@public_router.get("/collaboration")
def get_public_occurrence_collaboration(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    scope = set(grant.scope_json or [])

    meetings = db.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.amo_id == grant.amo_id,
        QualityAuditMeeting.audit_id == grant.audit_id,
        QualityAuditMeeting.status != "CANCELLED",
    ).order_by(QualityAuditMeeting.scheduled_start.asc()).all()

    narrative = db.query(QualityAuditClosingNarrative).filter(
        QualityAuditClosingNarrative.amo_id == grant.amo_id,
        QualityAuditClosingNarrative.audit_id == grant.audit_id,
    ).first()

    cars: list[dict[str, Any]] = []
    if participant and participant.participant_type == "AUDITEE_GUEST" and ("car:respond" in scope or "audit:read_released_findings" in scope):
        latest_releases = _latest_release_events(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
        released_finding_ids = [finding_id for finding_id, event in latest_releases.items() if event.action == "RELEASED"]
        if released_finding_ids:
            rows = db.query(models.CorrectiveActionRequest, models.QMSAuditFinding).join(
                models.QMSAuditFinding,
                models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id,
            ).filter(
                models.CorrectiveActionRequest.amo_id == grant.amo_id,
                models.QMSAuditFinding.audit_id == grant.audit_id,
                models.QMSAuditFinding.id.in_(released_finding_ids),
            ).order_by(models.CorrectiveActionRequest.created_at.asc()).all()
            for car, finding in rows:
                cars.append({
                    "id": str(car.id),
                    "car_number": car.car_number,
                    "title": car.title,
                    "summary": car.summary,
                    "priority": _enum_value(car.priority),
                    "status": _enum_value(car.status),
                    "due_date": car.due_date.isoformat() if car.due_date else None,
                    "target_closure_date": car.target_closure_date.isoformat() if car.target_closure_date else None,
                    "closed_at": car.closed_at.isoformat() if car.closed_at else None,
                    "finding_id": str(finding.id),
                    "finding_ref": finding.finding_ref,
                })

    return {
        "meetings": [_meeting_dict(row, public=True) for row in meetings],
        "cars": cars,
        "closing_narrative": _narrative_dict(narrative),
    }
