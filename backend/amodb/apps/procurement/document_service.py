from __future__ import annotations

import hashlib
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import document_models, document_schemas

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
DOCUMENT_ROOT = Path(os.getenv("PROCUREMENT_DOCUMENT_DIR", "storage/procurement-documents"))
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "image/jpeg",
    "image/png",
    "application/octet-stream",
}
ENTITY_TYPES = {"REQUISITION", "RFQ", "QUOTE", "PURCHASE_ORDER", "RECEIPT", "SUPPLIER", "QUALITY_HOLD", "INVOICE_MATCH"}


def normalize_entity_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported procurement document entity type.")
    return normalized


def _safe_name(value: str | None) -> str:
    name = Path(value or "document").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name[:180] or "document"


def _validate_signature(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        prefix = handle.read(8)
    if extension == ".pdf" and not prefix.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")
    if extension in {".doc", ".xls"} and prefix != bytes.fromhex("D0CF11E0A1B11AE1"):
        raise HTTPException(status_code=415, detail="The uploaded legacy Office document is invalid.")
    if extension in {".docx", ".xlsx"}:
        if not prefix.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=415, detail="The uploaded Office package is invalid.")
        try:
            with zipfile.ZipFile(path) as package:
                if "[Content_Types].xml" not in package.namelist():
                    raise HTTPException(status_code=415, detail="The uploaded Office package is corrupt.")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=415, detail="The uploaded Office package is corrupt.") from exc
    if extension == ".png" and not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PNG image.")
    if extension in {".jpg", ".jpeg"} and not prefix.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid JPEG image.")


def serialize(document: document_models.ProcurementDocument, amo_code: str) -> document_schemas.ProcurementDocumentRead:
    value = document_schemas.ProcurementDocumentRead.model_validate(document)
    if document.storage_path:
        value.download_url = f"/api/maintenance/{amo_code}/procurement/documents/{document.id}/download"
    return value


def list_documents(db: Session, *, amo_id: str, entity_type: str | None, entity_id: str | None, limit: int):
    query = db.query(document_models.ProcurementDocument).filter(
        document_models.ProcurementDocument.amo_id == amo_id,
        document_models.ProcurementDocument.status == "ACTIVE",
    )
    if entity_type:
        query = query.filter(document_models.ProcurementDocument.entity_type == normalize_entity_type(entity_type))
    if entity_id:
        query = query.filter(document_models.ProcurementDocument.entity_id == entity_id)
    return query.order_by(document_models.ProcurementDocument.created_at.desc()).limit(min(max(limit, 1), 500)).all()


async def upload_document(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    document_kind: str,
    title: str,
    notes: str | None,
    file: UploadFile,
    actor_user_id: str | None,
):
    normalized_entity = normalize_entity_type(entity_type)
    original_name = _safe_name(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload PDF, Word, Excel, CSV, JPEG, or PNG only.")
    mime_type = (file.content_type or "application/octet-stream").lower().split(";", 1)[0]
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="The document MIME type is not allowed.")

    target_dir = DOCUMENT_ROOT / amo_id / normalized_entity.lower() / str(entity_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}_{original_name}"
    size_bytes = 0
    digest = hashlib.sha256()
    try:
        with target_path.open("xb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_DOCUMENT_BYTES:
                    raise HTTPException(status_code=413, detail="Document exceeds the 25MB limit.")
                digest.update(chunk)
                handle.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=422, detail="The uploaded document is empty.")
        _validate_signature(target_path, extension)
        record = document_models.ProcurementDocument(
            amo_id=amo_id,
            entity_type=normalized_entity,
            entity_id=str(entity_id),
            document_kind=document_kind.strip().upper(),
            title=title.strip(),
            source_type="UPLOADED",
            file_name=original_name,
            storage_path=str(target_path.resolve()),
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            notes=notes,
            uploaded_by_user_id=actor_user_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except HTTPException:
        db.rollback()
        target_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="The procurement document could not be saved.") from exc


def link_document(db: Session, *, amo_id: str, payload: document_schemas.ProcurementDocumentLinkCreate, actor_user_id: str | None):
    record = document_models.ProcurementDocument(
        amo_id=amo_id,
        entity_type=normalize_entity_type(payload.entity_type),
        entity_id=payload.entity_id,
        document_kind=payload.document_kind.strip().upper(),
        title=payload.title.strip(),
        source_type=payload.source_type,
        physical_reference=payload.physical_reference,
        physical_location=payload.physical_location,
        dms_document_id=payload.dms_document_id,
        dms_revision_id=payload.dms_revision_id,
        notes=payload.notes,
        uploaded_by_user_id=actor_user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_document(db: Session, *, amo_id: str, document_id: int):
    record = db.query(document_models.ProcurementDocument).filter(
        document_models.ProcurementDocument.amo_id == amo_id,
        document_models.ProcurementDocument.id == document_id,
        document_models.ProcurementDocument.status == "ACTIVE",
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Procurement document was not found.")
    return record


def verify_document(db: Session, *, amo_id: str, document_id: int, verified: bool, note: str | None, actor_user_id: str | None):
    record = get_document(db, amo_id=amo_id, document_id=document_id)
    record.is_verified = verified
    record.verified_by_user_id = actor_user_id if verified else None
    record.verified_at = datetime.utcnow() if verified else None
    if note:
        record.notes = "\n".join(filter(None, [record.notes, f"Quality verification: {note}"]))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
