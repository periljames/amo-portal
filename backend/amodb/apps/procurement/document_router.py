from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import document_models, document_schemas, document_service, service
from . import document_shared_storage


router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["procurement-documents"],
    dependencies=[Depends(require_module("finance_inventory"))],
)

DOCUMENT_UPLOAD_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.STORES_MANAGER,
    account_models.AccountRole.STOREKEEPER,
    account_models.AccountRole.STORES,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.PRODUCTION_ENGINEER,
    account_models.AccountRole.CERTIFYING_ENGINEER,
    account_models.AccountRole.CERTIFYING_TECHNICIAN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
    account_models.AccountRole.FINANCE_MANAGER,
    account_models.AccountRole.ACCOUNTS_OFFICER,
)
DOCUMENT_CONTROL_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
)
QUALITY_DOCUMENT_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
)


def _tenant(db: Session, *, amo_code: str, current_user: account_models.User) -> str:
    return service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=current_user)


def _serialize(record: document_models.ProcurementDocument, amo_code: str) -> document_schemas.ProcurementDocumentRead:
    return document_schemas.ProcurementDocumentRead(
        id=record.id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        document_type=record.document_type,
        title=record.title,
        document_number=record.document_number,
        revision=record.revision,
        document_date=record.document_date,
        source=record.source,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        physical_reference=record.physical_reference,
        physical_location=record.physical_location,
        external_system=record.external_system,
        external_reference=record.external_reference,
        external_url=record.external_url,
        dms_document_id=record.dms_document_id,
        dms_revision_id=record.dms_revision_id,
        notes=record.notes,
        is_quality_evidence=record.is_quality_evidence,
        qms_reference=record.qms_reference,
        verification_status=record.verification_status,
        verification_notes=record.verification_notes,
        verified_by_user_id=record.verified_by_user_id,
        verified_at=record.verified_at,
        status=record.status,
        uploaded_by_user_id=record.uploaded_by_user_id,
        uploaded_at=record.uploaded_at,
        voided_by_user_id=record.voided_by_user_id,
        voided_at=record.voided_at,
        void_reason=record.void_reason,
        download_url=(f"/api/maintenance/{amo_code}/procurement/documents/{record.id}/download" if record.stored_path else None),
    )


@router.get("/documents", response_model=List[document_schemas.ProcurementDocumentRead])
def procurement_documents_list(
    amo_code: str,
    entity_type: Optional[document_models.ProcurementDocumentEntityType] = None,
    entity_id: Optional[str] = None,
    active_only: bool = True,
    verification_status: Optional[document_models.ProcurementDocumentVerificationStatus] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    records = document_service.list_documents(
        db,
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        active_only=active_only,
        verification_status=verification_status,
        offset=offset,
        limit=limit,
    )
    return [_serialize(record, amo_code) for record in records]


@router.post("/documents", response_model=document_schemas.ProcurementDocumentRead, status_code=status.HTTP_201_CREATED)
def procurement_document_link(
    amo_code: str,
    entity_type: document_models.ProcurementDocumentEntityType = Form(...),
    entity_id: str = Form(...),
    document_type: str = Form(...),
    title: str = Form(...),
    source: document_models.ProcurementDocumentSource = Form(document_models.ProcurementDocumentSource.PHYSICAL_FORM),
    document_number: Optional[str] = Form(None),
    revision: Optional[str] = Form(None),
    document_date: Optional[date] = Form(None),
    physical_reference: Optional[str] = Form(None),
    physical_location: Optional[str] = Form(None),
    external_system: Optional[str] = Form(None),
    external_reference: Optional[str] = Form(None),
    external_url: Optional[str] = Form(None),
    dms_document_id: Optional[str] = Form(None),
    dms_revision_id: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_quality_evidence: bool = Form(False),
    qms_reference: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*DOCUMENT_UPLOAD_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    record: document_models.ProcurementDocument | None = None
    try:
        record = document_service.create_document(
        db,
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        document_type=document_type,
        title=title,
        source=source,
        actor_user_id=current_user.id,
        file=file,
        document_number=document_number,
        revision=revision,
        document_date=document_date,
        physical_reference=physical_reference,
        physical_location=physical_location,
        external_system=external_system,
        external_reference=external_reference,
        external_url=external_url,
        dms_document_id=dms_document_id,
        dms_revision_id=dms_revision_id,
        notes=notes,
        is_quality_evidence=is_quality_evidence,
        qms_reference=qms_reference,
        )
        if record.stored_path:
            document_shared_storage.promote_document_file(record)
        response = _serialize(record, amo_code)
        db.commit()
    except HTTPException:
        db.rollback()
        if record is not None:
            document_shared_storage.discard_promoted_file(record)
            document_service.discard_document_file(record)
        raise
    except Exception as exc:
        db.rollback()
        if record is not None:
            document_shared_storage.discard_promoted_file(record)
            document_service.discard_document_file(record)
        raise HTTPException(status_code=500, detail="The document evidence could not be committed.") from exc
    return response


@router.get("/documents/{document_id}/download")
def procurement_document_download(
    amo_code: str,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    record = document_service.get_document(db, amo_id=amo_id, document_id=document_id)
    path = document_shared_storage.materialize_document_file(record)
    return FileResponse(
        path=path,
        media_type=record.mime_type or "application/octet-stream",
        filename=record.original_filename or f"procurement-document-{record.id}",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-Procurement-Document-SHA256": record.sha256 or "",
        },
    )


@router.post("/documents/{document_id}/verify", response_model=document_schemas.ProcurementDocumentRead)
def procurement_document_verify(
    amo_code: str,
    document_id: int,
    payload: document_schemas.ProcurementDocumentVerify,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_DOCUMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    record = document_service.verify_document(
        db,
        amo_id=amo_id,
        document_id=document_id,
        outcome=payload.outcome,
        notes=payload.notes,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(record)
    return _serialize(record, amo_code)


@router.post("/documents/{document_id}/void", response_model=document_schemas.ProcurementDocumentRead)
def procurement_document_void(
    amo_code: str,
    document_id: int,
    payload: document_schemas.ProcurementDocumentVoid,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*DOCUMENT_CONTROL_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    record = document_service.void_document(
        db,
        amo_id=amo_id,
        document_id=document_id,
        reason=payload.reason,
        actor_user_id=current_user.id,
        actor_is_quality=current_user.role in set(QUALITY_DOCUMENT_ROLES) or current_user.is_superuser,
    )
    db.commit()
    db.refresh(record)
    return _serialize(record, amo_code)
