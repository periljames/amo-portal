from __future__ import annotations

import hashlib
import os
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services

from . import document_models, models


MAX_DOCUMENT_BYTES = int(os.getenv("PROCUREMENT_DOCUMENT_MAX_BYTES", str(25 * 1024 * 1024)))
DOCUMENT_ROOT = Path(os.getenv("PROCUREMENT_DOCUMENT_DIR", "/srv/amo/uploads/procurement-documents")).resolve()
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
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_user_id=actor_user_id,
            after_json=detail,
        ),
    )


def _clean(value: str | None, limit: int | None = None) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    return cleaned[:limit] if limit else cleaned


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
        sample = path.read_bytes()[:4096]
        if b"\x00" in sample:
            raise HTTPException(status_code=415, detail="The uploaded CSV contains binary data.")
        try:
            sample.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="The uploaded CSV must be UTF-8 encoded.") from exc
        return
    raise HTTPException(status_code=415, detail="The uploaded document type is not allowed.")


def _validate_entity(db: Session, *, amo_id: str, entity_type: document_models.ProcurementDocumentEntityType, entity_id: str) -> None:
    model = ENTITY_MODELS[entity_type]
    try:
        numeric_id = int(entity_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The linked Procurement record identifier is invalid.") from exc
    exists = db.query(model.id).filter(model.amo_id == amo_id, model.id == numeric_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="The linked Procurement record was not found in this tenant.")


def _validate_external_url(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="External document URL must be a valid HTTP or HTTPS address.")
    return cleaned


def _validate_linkage(
    *,
    source: document_models.ProcurementDocumentSource,
    file: UploadFile | None,
    physical_reference: str | None,
    external_system: str | None,
    external_reference: str | None,
    external_url: str | None,
    dms_document_id: str | None,
) -> None:
    has_file = bool(file and file.filename)
    has_physical = bool(_clean(physical_reference))
    has_external = bool(_clean(external_reference) or _clean(external_url))
    has_dms = bool(_clean(dms_document_id))
    if not any([has_file, has_physical, has_external, has_dms]):
        raise HTTPException(
            status_code=422,
            detail="Provide a retained file, physical record reference, external-system reference, or DMS document link.",
        )
    if source == document_models.ProcurementDocumentSource.PHYSICAL_FORM and not (has_file or has_physical):
        raise HTTPException(status_code=422, detail="Physical-form evidence requires a scan or physical record reference.")
    if source == document_models.ProcurementDocumentSource.DMS_CONTROLLED and not has_dms:
        raise HTTPException(status_code=422, detail="A controlled DMS link requires the DMS document identifier.")
    if source == document_models.ProcurementDocumentSource.EXTERNAL_SOFTWARE and not (_clean(external_system) and has_external):
        raise HTTPException(status_code=422, detail="External-software evidence requires the system name and its record reference or URL.")


def _write_file(
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType,
    entity_id: str,
    file: UploadFile,
) -> tuple[Path, str, str, int, str]:
    original_name = _safe_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload PDF, Word, Excel, CSV, JPEG, PNG, or TIFF files only.")
    mime_type = _normalised_mime(file)
    if mime_type not in MIME_BY_EXTENSION[extension]:
        raise HTTPException(status_code=415, detail="The file MIME type does not match the selected document format.")

    target_dir = DOCUMENT_ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", amo_id) / entity_type.value.lower() / re.sub(r"[^A-Za-z0-9_-]", "_", entity_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / f"{uuid4().hex}_{original_name}").resolve()
    try:
        target_path.relative_to(DOCUMENT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="The document storage path is invalid.") from exc

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
                    raise HTTPException(status_code=413, detail="The selected document exceeds the 25 MB limit.")
                digest.update(chunk)
                handle.write(chunk)
        if size_bytes <= 0:
            raise HTTPException(status_code=422, detail="The selected document is empty.")
        _validate_signature(target_path, extension)
        return target_path, original_name, mime_type, size_bytes, digest.hexdigest()
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


def create_document(
    db: Session,
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType,
    entity_id: str,
    document_type: str,
    title: str,
    source: document_models.ProcurementDocumentSource,
    actor_user_id: str | None,
    file: UploadFile | None = None,
    document_number: str | None = None,
    revision: str | None = None,
    document_date: date | None = None,
    physical_reference: str | None = None,
    physical_location: str | None = None,
    external_system: str | None = None,
    external_reference: str | None = None,
    external_url: str | None = None,
    dms_document_id: str | None = None,
    dms_revision_id: str | None = None,
    notes: str | None = None,
    is_quality_evidence: bool = False,
    qms_reference: str | None = None,
) -> document_models.ProcurementDocument:
    entity_id = _clean(entity_id, 128) or ""
    title = _clean(title, 255) or ""
    document_type = (_clean(document_type, 64) or "OTHER").upper()
    if not entity_id or not title:
        raise HTTPException(status_code=422, detail="Linked record and document title are required.")
    if is_quality_evidence and not _clean(qms_reference):
        raise HTTPException(
            status_code=422,
            detail="Quality evidence requires a QMS, audit, CAR, inspection, or release reference.",
        )
    _validate_entity(db, amo_id=amo_id, entity_type=entity_type, entity_id=entity_id)
    external_url = _validate_external_url(external_url)
    _validate_linkage(
        source=source,
        file=file,
        physical_reference=physical_reference,
        external_system=external_system,
        external_reference=external_reference,
        external_url=external_url,
        dms_document_id=dms_document_id,
    )

    target_path: Path | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    try:
        if file and file.filename:
            target_path, original_filename, mime_type, size_bytes, sha256 = _write_file(
                amo_id=amo_id,
                entity_type=entity_type,
                entity_id=entity_id,
                file=file,
            )
            duplicate = (
                db.query(document_models.ProcurementDocument.id)
                .filter(
                    document_models.ProcurementDocument.amo_id == amo_id,
                    document_models.ProcurementDocument.entity_type == entity_type,
                    document_models.ProcurementDocument.entity_id == entity_id,
                    document_models.ProcurementDocument.sha256 == sha256,
                    document_models.ProcurementDocument.status == document_models.ProcurementDocumentStatus.ACTIVE,
                )
                .first()
            )
            if duplicate:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=409, detail="This exact document is already linked to the selected Procurement record.")

        verification_status = (
            document_models.ProcurementDocumentVerificationStatus.PENDING
            if is_quality_evidence
            else document_models.ProcurementDocumentVerificationStatus.NOT_REQUIRED
        )
        record = document_models.ProcurementDocument(
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
            document_type=document_type,
            title=title,
            document_number=_clean(document_number, 128),
            revision=_clean(revision, 64),
            document_date=document_date,
            source=source,
            original_filename=original_filename,
            stored_path=str(target_path) if target_path else None,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            physical_reference=_clean(physical_reference, 255),
            physical_location=_clean(physical_location, 255),
            external_system=_clean(external_system, 128),
            external_reference=_clean(external_reference, 255),
            external_url=external_url,
            dms_document_id=_clean(dms_document_id, 64),
            dms_revision_id=_clean(dms_revision_id, 64),
            notes=_clean(notes),
            is_quality_evidence=is_quality_evidence,
            qms_reference=_clean(qms_reference, 128),
            verification_status=verification_status,
            uploaded_by_user_id=actor_user_id,
        )
        db.add(record)
        db.flush()
        _event(
            db,
            amo_id=amo_id,
            entity_type="ProcurementDocument",
            entity_id=str(record.id),
            action="link_document",
            actor_user_id=actor_user_id,
            detail={
                "linked_entity_type": entity_type.value,
                "linked_entity_id": entity_id,
                "document_type": document_type,
                "source": source.value,
                "has_file": bool(target_path),
                "sha256": sha256,
                "physical_reference": record.physical_reference,
                "external_reference": record.external_reference,
                "dms_document_id": record.dms_document_id,
                "quality_evidence": is_quality_evidence,
            },
        )
        return record
    except Exception:
        if target_path is not None:
            target_path.unlink(missing_ok=True)
        raise


def list_documents(
    db: Session,
    *,
    amo_id: str,
    entity_type: document_models.ProcurementDocumentEntityType | None = None,
    entity_id: str | None = None,
    active_only: bool = True,
    verification_status: document_models.ProcurementDocumentVerificationStatus | None = None,
    offset: int = 0,
    limit: int = 200,
) -> list[document_models.ProcurementDocument]:
    query = db.query(document_models.ProcurementDocument).filter(document_models.ProcurementDocument.amo_id == amo_id)
    if entity_type:
        query = query.filter(document_models.ProcurementDocument.entity_type == entity_type)
    if entity_id:
        query = query.filter(document_models.ProcurementDocument.entity_id == str(entity_id))
    if active_only:
        query = query.filter(document_models.ProcurementDocument.status == document_models.ProcurementDocumentStatus.ACTIVE)
    if verification_status:
        query = query.filter(document_models.ProcurementDocument.verification_status == verification_status)
    bounded_offset = max(offset, 0)
    bounded_limit = min(max(limit, 1), 500)
    return (
        query.order_by(
            document_models.ProcurementDocument.uploaded_at.desc(),
            document_models.ProcurementDocument.id.desc(),
        )
        .offset(bounded_offset)
        .limit(bounded_limit)
        .all()
    )


def get_document(db: Session, *, amo_id: str, document_id: int) -> document_models.ProcurementDocument:
    record = (
        db.query(document_models.ProcurementDocument)
        .filter(
            document_models.ProcurementDocument.amo_id == amo_id,
            document_models.ProcurementDocument.id == document_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="The Procurement document was not found.")
    return record


def get_document_file(record: document_models.ProcurementDocument) -> Path:
    if not record.stored_path:
        raise HTTPException(status_code=409, detail="This evidence record is a reference link and has no retained file to download.")
    path = Path(record.stored_path).resolve()
    try:
        path.relative_to(DOCUMENT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="The retained document path is outside controlled storage.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The retained document file is unavailable.")
    return path


def discard_document_file(record: document_models.ProcurementDocument) -> None:
    if not record.stored_path:
        return
    path = Path(record.stored_path).resolve()
    try:
        path.relative_to(DOCUMENT_ROOT)
    except ValueError:
        return
    path.unlink(missing_ok=True)


def verify_document(
    db: Session,
    *,
    amo_id: str,
    document_id: int,
    outcome: document_models.ProcurementDocumentVerificationStatus,
    notes: str,
    actor_user_id: str | None,
) -> document_models.ProcurementDocument:
    if outcome not in {
        document_models.ProcurementDocumentVerificationStatus.VERIFIED,
        document_models.ProcurementDocumentVerificationStatus.REJECTED,
    }:
        raise HTTPException(status_code=422, detail="Quality verification outcome must be VERIFIED or REJECTED.")
    record = (
        db.query(document_models.ProcurementDocument)
        .filter(
            document_models.ProcurementDocument.amo_id == amo_id,
            document_models.ProcurementDocument.id == document_id,
        )
        .with_for_update()
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="The Procurement document was not found.")
    if record.status != document_models.ProcurementDocumentStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="A void document cannot be verified.")
    if not record.is_quality_evidence:
        raise HTTPException(status_code=409, detail="Only evidence submitted for Quality review can receive a Quality decision.")
    if record.verification_status != document_models.ProcurementDocumentVerificationStatus.PENDING:
        raise HTTPException(status_code=409, detail="The Quality evidence already has a final verification decision.")
    if not actor_user_id:
        raise HTTPException(status_code=403, detail="An authenticated Quality user is required for verification.")
    if record.uploaded_by_user_id and str(record.uploaded_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The evidence uploader cannot verify or reject the same evidence.")
    record.verification_status = outcome
    record.verification_notes = notes.strip()
    record.verified_by_user_id = actor_user_id
    record.verified_at = datetime.utcnow()
    db.add(record)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementDocument",
        entity_id=str(record.id),
        action="quality_verify_document",
        actor_user_id=actor_user_id,
        detail={"outcome": outcome.value, "notes": record.verification_notes},
    )
    return record


def void_document(
    db: Session,
    *,
    amo_id: str,
    document_id: int,
    reason: str,
    actor_user_id: str | None,
    actor_is_quality: bool,
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
        action="void_document",
        actor_user_id=actor_user_id,
        detail={"reason": record.void_reason, "retained": True},
    )
    return record
