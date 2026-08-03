from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import document_schemas, document_service, service

router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["procurement documents"],
    dependencies=[Depends(require_module("finance_inventory"))],
)

DOCUMENT_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.STORES_MANAGER,
    account_models.AccountRole.STOREKEEPER,
    account_models.AccountRole.STORES,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.PRODUCTION_ENGINEER,
    account_models.AccountRole.CERTIFYING_ENGINEER,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
    account_models.AccountRole.FINANCE_MANAGER,
    account_models.AccountRole.ACCOUNTS_OFFICER,
)
QUALITY_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
)


def _amo_id(db: Session, amo_code: str, current_user: account_models.User) -> str:
    return service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=current_user)


@router.get("/documents", response_model=List[document_schemas.ProcurementDocumentRead])
def procurement_documents_list(
    amo_code: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(db, amo_code, current_user)
    return [
        document_service.serialize(item, amo_code)
        for item in document_service.list_documents(
            db,
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    ]


@router.post("/documents/upload", response_model=document_schemas.ProcurementDocumentRead, status_code=status.HTTP_201_CREATED)
async def procurement_document_upload(
    amo_code: str,
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    document_kind: str = Form(...),
    title: str = Form(...),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*DOCUMENT_ROLES)),
):
    amo_id = _amo_id(db, amo_code, current_user)
    record = await document_service.upload_document(
        db,
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        document_kind=document_kind,
        title=title,
        notes=notes,
        file=file,
        actor_user_id=current_user.id,
    )
    return document_service.serialize(record, amo_code)


@router.post("/documents/link", response_model=document_schemas.ProcurementDocumentRead, status_code=status.HTTP_201_CREATED)
def procurement_document_link(
    amo_code: str,
    payload: document_schemas.ProcurementDocumentLinkCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*DOCUMENT_ROLES)),
):
    amo_id = _amo_id(db, amo_code, current_user)
    record = document_service.link_document(db, amo_id=amo_id, payload=payload, actor_user_id=current_user.id)
    return document_service.serialize(record, amo_code)


@router.get("/documents/{document_id}/download")
def procurement_document_download(
    amo_code: str,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(db, amo_code, current_user)
    record = document_service.get_document(db, amo_id=amo_id, document_id=document_id)
    path = Path(record.storage_path or "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The stored document file is unavailable.")
    return FileResponse(path, media_type=record.mime_type or "application/octet-stream", filename=record.file_name or path.name)


@router.post("/documents/{document_id}/verify", response_model=document_schemas.ProcurementDocumentRead)
def procurement_document_verify(
    amo_code: str,
    document_id: int,
    payload: document_schemas.ProcurementDocumentVerify,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _amo_id(db, amo_code, current_user)
    record = document_service.verify_document(
        db,
        amo_id=amo_id,
        document_id=document_id,
        verified=payload.verified,
        note=payload.note,
        actor_user_id=current_user.id,
    )
    return document_service.serialize(record, amo_code)
