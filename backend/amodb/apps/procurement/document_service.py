from __future__ import annotations

import hashlib
import os
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import document_models, models


MAX_DOCUMENT_BYTES = int(os.getenv("PROCUREMENT_DOCUMENT_MAX_BYTES", str(25 * 1024 * 1024)))
DOCUMENT_ROOT = Path(os.getenv("PROCUREMENT_DOCUMENT_DIR", "uploads/procurement-documents")).resolve()
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MIME_BY_EXTENSION = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream", "application/zip"},
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream", "application/zip"},
    ".csv": {"text/csv", "text/plain", "application/csv", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".tif": {"image/tiff", "application/octet-stream"},
    ".tiff": {"image/tiff", "application/octet-stream"},
}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "application/csv",
    "application/zip",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/octet-stream",
}
ENTITY_MODELS = {
    document_models.ProcurementDocumentEntityType.REQUISITION: models.ProcurementRequisition,
    document_models.ProcurementDocumentEntityType.RFQ: models.ProcurementRFQ,
    document_models.ProcurementDocumentEntityType.QUOTE: models.ProcurementQuote,
    document_models.ProcurementDocumentEntityType.PURCHASE_ORDER: models.ProcurementPurchaseOrder,
    document_models.ProcurementDocumentEntityType.RECEIPT: models.ProcurementReceipt,
    document_models.ProcurementDocumentEntityType.SUPPLIER: models.ProcurementSupplier,
    document_models.ProcurementDocumentEntityType.QUALITY_HOLD: models.ProcurementQualityHold,
}


_PDF_MAGIC = b"%PDF-"
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_MAGIC = b"PK\x03\x04"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_TIFF_MAGICS = {b"II*\x00", b"MM\x00*"}


def _event(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: str | None,
    detail: dict,
) -> None:
    db.add(
        models.ProcurementEvent(
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            detail=detail,
        )
    )


def _safe_filename(filename: str | None) -> str:
    candidate = Path(filename or "document").name.strip()
    candidate = re.sub(r"[^A-Za-z0-9._ -]+", "_", candidate).strip(" .")
    return candidate[:180] or "document"


def _normalised_mime(file: UploadFile) -> str:
    return str(file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()


def _validate_signature(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        prefix = handle.read(16)

    if extension == ".pdf":
        if not prefix.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF document.")
        return
    if extension in {".doc", ".xls"}:
        if not prefix.startswith(_OLE_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded legacy Office document is invalid.")
        return
    if extension in {".docx", ".xlsx"}:
        if not prefix.startswith(_ZIP_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded Office document package is invalid.")
        try:
            with zipfile.ZipFile(path) as package:
                names = set(package.namelist())
                required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
                if "[Content_Types].xml" not in names or required not in names:
                    raise HTTPException(status_code=415, detail="The uploaded Office document package is invalid.")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=415, detail="The uploaded Office document package is corrupt.") from exc
        return
    if extension in {".jpg", ".jpeg"}:
        if not prefix.startswith(_JPEG_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded image is not a valid JPEG file.")
        return
    if extension == ".png":
        if not prefix.startswith(_PNG_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded image is not a valid PNG file.")
        return
    if extension in {".tif", ".tiff"}:
        if prefix[:4] not in _TIFF_MAGICS:
            raise HTTPException(status_code=415, detail="The uploaded image is not a valid TIFF file.")
        return
    if extension == ".csv":
        sample = path.read_bytes()[:65536]
        if b"\x00" in sample:
            raise HTTPException(status_code=415, detail="The uploaded CSV contains binary data.")
        return
    raise HTTPException(status_code=415, detail="Document extension is not allowed.")


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _assert_entity_exists(
    db: Session,
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType,
    entity_id: str,
) -> None:
    model = ENTITY_MODELS[entity_type]
    try:
        numeric_id = int(entity_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The linked Procurement record ID must be numeric.") from exc
    exists = (
        db.query(model.id)
        .filter(model.amo_id == amo_id, model.id == numeric_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="The linked Procurement record was not found.")


def _document_path(record: document_models.ProcurementDocument) -> Path:
    candidate = Path(record.stored_path).resolve()
    try:
        candidate.relative_to(DOCUMENT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="The retained document path is invalid.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="The retained document file is unavailable.")
    return candidate


def list_documents(
    db: Session,
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType | None = None,
    entity_id: str | None = None,
    active_only: bool = True,
    limit: int = 200,
) -> list[document_models.ProcurementDocument]:
    query = db.query(document_models.ProcurementDocument).filter(
        document_models.ProcurementDocument.amo_id == amo_id,
    )
    if entity_type:
        query = query.filter(document_models.ProcurementDocument.entity_type == entity_type)
    if entity_id:
        query = query.filter(document_models.ProcurementDocument.entity_id == str(entity_id))
    if active_only:
        query = query.filter(document_models.ProcurementDocument.status == document_models.ProcurementDocumentStatus.ACTIVE)
    return query.order_by(document_models.ProcurementDocument.uploaded_at.desc()).limit(min(max(limit, 1), 500)).all()


def create_document(
    db: Session,
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType,
    entity_id: str,
    document_type: str,
    title: str,
    source: document_models.ProcurementDocumentSource,
    file: UploadFile,
    actor_user_id: str | None,
    document_number: str | None = None,
    revision: str | None = None,
    document_date: date | None = None,
    notes: str | None = None,
    is_quality_evidence: bool = False,
    qms_reference: str | None = None,
) -> document_models.ProcurementDocument:
    _assert_entity_exists(db, amo_id=amo_id, entity_type=entity_type, entity_id=entity_id)
    original_name = _safe_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported document type. Upload PDF, Word, Excel, CSV, JPEG, PNG, or TIFF files.",
        )
    mime_type = _normalised_mime(file)
    if mime_type not in ALLOWED_MIME_TYPES or mime_type not in MIME_BY_EXTENSION[extension]:
        raise HTTPException(status_code=415, detail="The uploaded document MIME type does not match the file extension.")
    normalised_title = title.strip()
    normalised_type = document_type.strip().upper()
    if not normalised_title or not normalised_type:
        raise HTTPException(status_code=422, detail="Document title and type are required.")

    target_dir = DOCUMENT_ROOT / str(amo_id) / entity_type.value.lower() / str(entity_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}_{original_name}"
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with target_path.open("xb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_DOCUMENT_BYTES:
                    raise HTTPException(status_code=413, detail="The document exceeds the 25 MB upload limit.")
                digest.update(chunk)
                handle.write(chunk)
        if size_bytes <= 0:
            raise HTTPException(status_code=422, detail="The selected document is empty.")
        _validate_signature(target_path, extension)

        duplicate = (
            db.query(document_models.ProcurementDocument.id)
            .filter(
                document_models.ProcurementDocument.amo_id == amo_id,
                document_models.ProcurementDocument.entity_type == entity_type,
                document_models.ProcurementDocument.entity_id == str(entity_id),
                document_models.ProcurementDocument.sha256 == digest.hexdigest(),
                document_models.ProcurementDocument.status == document_models.ProcurementDocumentStatus.ACTIVE,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="This exact document is already linked to the selected Procurement record.")

        record = document_models.ProcurementDocument(
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            document_type=normalised_type,
            title=normalised_title,
            document_number=document_number.strip() if document_number else None,
            revision=revision.strip() if revision else None,
            document_date=document_date,
            source=source,
            original_filename=original_name,
            stored_path=str(target_path),
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            notes=notes.strip() if notes else None,
            is_quality_evidence=is_quality_evidence,
            qms_reference=qms_reference.strip() if qms_reference else None,
            uploaded_by_user_id=actor_user_id,
        )
        db.add(record)
        db.flush()
        _event(
            db,
            amo_id=amo_id,
            entity_type="ProcurementDocument",
            entity_id=str(record.id),
            action="upload",
            actor_user_id=actor_user_id,
            detail={
                "linked_entity_type": entity_type.value,
                "linked_entity_id": str(entity_id),
                "document_type": normalised_type,
                "filename": original_name,
                "size_bytes": size_bytes,
                "sha256": digest.hexdigest(),
                "quality_evidence": is_quality_evidence,
            },
        )
        return record
    except HTTPException:
        _safe_unlink(target_path)
        raise
    except Exception as exc:
        _safe_unlink(target_path)
        raise HTTPException(status_code=500, detail="The Procurement document could not be retained.") from exc


def get_document(
    db: Session,
    *,
    amo_id: str,
    document_id: int,
) -> document_models.ProcurementDocument:
    record = (
        db.query(document_models.ProcurementDocument)
        .filter(
            document_models.ProcurementDocument.amo_id == amo_id,
            document_models.ProcurementDocument.id == document_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Procurement document was not found.")
    return record


def get_document_file(record: document_models.ProcurementDocument) -> Path:
    return _document_path(record)


def void_document(
    db: Session,
    *,
    amo_id: str,
    document_id: int,
    reason: str,
    actor_user_id: str | None,
    actor_is_quality: bool = False,
) -> document_models.ProcurementDocument:
    record = get_document(db, amo_id=amo_id, document_id=document_id)
    if record.status == document_models.ProcurementDocumentStatus.VOID:
        raise HTTPException(status_code=409, detail="The Procurement document is already void.")
    if record.is_quality_evidence and not actor_is_quality:
        raise HTTPException(status_code=403, detail="Only Quality may void a record flagged as Quality evidence.")
    record.status = document_models.ProcurementDocumentStatus.VOID
    record.void_reason = reason.strip()
    record.voided_by_user_id = actor_user_id
    record.voided_at = datetime.utcnow()
    db.add(record)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementDocument",
        entity_id=str(record.id),
        action="void",
        actor_user_id=actor_user_id,
        detail={"reason": record.void_reason, "sha256": record.sha256},
    )
    return record


def discard_document_file(record: document_models.ProcurementDocument) -> None:
    _safe_unlink(Path(record.stored_path))
