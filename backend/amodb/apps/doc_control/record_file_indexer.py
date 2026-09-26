"""Bounded record-file validation and derived indexing.

The immutable binary is stored before this worker runs. Indexing failures are
recorded on the asset and can be retried without changing its checksum.
"""
from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import text

from amodb.database import WriteSessionLocal

from . import records_vault_models as rm
from .document_text_extractor import _bounded, extract_document_text

logger = logging.getLogger(__name__)
MAX_INDEX_CHARS = int(os.getenv("DOCUMENT_TEXT_INDEX_MAX_CHARS", "2000000"))
MIME = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".txt": "text/plain", ".csv": "text/csv", ".eml": "message/rfc822",
    ".md": "text/markdown", ".json": "application/json", ".xml": "application/xml",
    ".html": "text/html", ".htm": "text/html",
}


def validate_record_file(path: Path, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in MIME:
        raise HTTPException(status_code=415, detail="Unsupported retained record file type")
    with path.open("rb") as source:
        head = source.read(16)
    signatures = {".pdf": b"%PDF", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
    if suffix in signatures and not head.startswith(signatures[suffix]):
        raise HTTPException(status_code=422, detail="File signature does not match its extension")
    package_entries = {".docx": "word/document.xml", ".pptx": "ppt/presentation.xml", ".xlsx": "xl/workbook.xml", ".xlsm": "xl/workbook.xml"}
    if suffix in package_entries:
        if not head.startswith(b"PK"):
            raise HTTPException(status_code=422, detail="Invalid Office file signature")
        try:
            with zipfile.ZipFile(path) as archive:
                if package_entries[suffix] not in archive.namelist():
                    raise HTTPException(status_code=422, detail="Office package does not match its extension")
                if len(archive.infolist()) > 10000 or sum(info.file_size for info in archive.infolist()) > 500 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Office package expands beyond the indexing limit")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=422, detail="Invalid Office package") from exc
    return MIME[suffix]


def extract_file(path: Path, filename: str, mime: str) -> tuple[str, dict]:
    suffix = path.suffix.lower()
    metadata: dict = {}
    if suffix == ".pdf":
        import fitz  # type: ignore
        values = []
        size = 0
        ocr_pages = 0
        warning = None
        with fitz.open(path) as pdf:
            metadata["page_count"] = len(pdf)
            for key in ("title", "author", "subject", "keywords", "creationDate"):
                if pdf.metadata.get(key):
                    metadata[key] = str(pdf.metadata[key])[:500]
            for page in pdf:
                value = page.get_text("text") or ""
                if len(value.strip()) < 30 and ocr_pages < int(os.getenv("DOCUMENT_OCR_MAX_PAGES", "50")):
                    try:
                        import pytesseract  # type: ignore
                        from PIL import Image  # type: ignore
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        value = pytesseract.image_to_string(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), timeout=20)
                        ocr_pages += 1
                    except (ImportError, RuntimeError, OSError, TimeoutError):
                        warning = "OCR unavailable for image-only pages"
                values.append(value)
                size += len(value)
                if size >= MAX_INDEX_CHARS:
                    break
        metadata["ocr_pages"] = ocr_pages
        result = _bounded("\n".join(values), "PYMUPDF_OCR" if ocr_pages else "PYMUPDF", warning)
    elif suffix in {".docx", ".pptx", ".xlsx", ".xlsm"}:
        values = []
        size = 0
        with zipfile.ZipFile(path) as archive:
            if "docProps/core.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("docProps/core.xml"))
                for child in root:
                    key = child.tag.rsplit("}", 1)[-1]
                    if key in {"title", "subject", "creator", "description", "keywords", "created", "modified", "lastModifiedBy"} and child.text:
                        metadata[key] = child.text[:500]
            prefixes = ("word/",) if suffix == ".docx" else (("ppt/slides/", "ppt/notesSlides/") if suffix == ".pptx" else ("xl/sharedStrings.xml", "xl/worksheets/"))
            for name in archive.namelist():
                if not name.startswith(prefixes) or not name.endswith(".xml") or archive.getinfo(name).file_size > 32 * 1024 * 1024:
                    continue
                root = ElementTree.fromstring(archive.read(name))
                for node in root.iter():
                    if node.text and node.text.strip():
                        values.append(node.text.strip())
                        size += len(values[-1])
                        if size >= MAX_INDEX_CHARS:
                            break
                if size >= MAX_INDEX_CHARS:
                    break
        result = _bounded("\n".join(values), "OOXML")
    elif suffix in {".png", ".jpg", ".jpeg"}:
        from PIL import Image  # type: ignore
        with Image.open(path) as picture:
            metadata.update(image_width=picture.width, image_height=picture.height)
            try:
                import pytesseract  # type: ignore
                result = _bounded(pytesseract.image_to_string(picture, timeout=20), "TESSERACT")
            except (ImportError, RuntimeError, OSError, TimeoutError):
                result = _bounded("", "METADATA_ONLY", "Image OCR unavailable")
    else:
        with path.open("rb") as source:
            result = extract_document_text(filename, source.read(MAX_INDEX_CHARS * 4 + 1), mime)
    return result.text, {**metadata, "text_index": {"status": "READY", "engine": result.engine, "truncated": result.truncated, "warning": result.warning}}


def _set_tenant(db, tenant_id: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


def index_record(tenant_id: str, record_id: str, root: Path) -> None:
    # Claim in a short transaction. OCR and Office parsing never hold a DB lock.
    with WriteSessionLocal() as db:
        query = db.query(rm.TenantRecordIndexJob).filter(
            rm.TenantRecordIndexJob.tenant_id == tenant_id,
            rm.TenantRecordIndexJob.record_asset_id == record_id,
            rm.TenantRecordIndexJob.status == "PENDING",
        )
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = query.first()
        if job is None:
            return
        _set_tenant(db, tenant_id)
        row = db.query(rm.TenantRecordAsset).filter(rm.TenantRecordAsset.tenant_id == tenant_id, rm.TenantRecordAsset.id == record_id).first()
        if row is None:
            job.status = "FAILED"
            job.error_summary = "Record asset is unavailable"
            db.commit()
            return
        filename, mime, stored_path = row.filename, row.mime_type, row.storage_path
        job.status = "RUNNING"
        from datetime import datetime, timezone
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    try:
        path = Path(stored_path).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise FileNotFoundError("Stored record is unavailable")
        text_value, extracted = extract_file(path, filename, mime)
        failure = None
    except Exception as exc:
        logger.exception("Record indexing failed for %s", record_id)
        failure = exc

    with WriteSessionLocal() as db:
        _set_tenant(db, tenant_id)
        row = db.query(rm.TenantRecordAsset).filter(rm.TenantRecordAsset.tenant_id == tenant_id, rm.TenantRecordAsset.id == record_id).first()
        job = db.query(rm.TenantRecordIndexJob).filter(
            rm.TenantRecordIndexJob.tenant_id == tenant_id,
            rm.TenantRecordIndexJob.record_asset_id == record_id,
        ).first()
        if row is None or job is None or job.status != "RUNNING":
            return
        if failure is None:
            base = str((row.metadata_json or {}).get("_index_base") or row.search_text)
            row.metadata_json = {**dict(row.metadata_json or {}), "extracted": {key: value for key, value in extracted.items() if key != "text_index"}, "text_index": extracted["text_index"]}
            row.search_text = (base + " " + " ".join(str(value) for value in extracted.values() if isinstance(value, str)) + " " + text_value)[:MAX_INDEX_CHARS]
            job.status = "READY"
            job.error_summary = None
        else:
            row.metadata_json = {**dict(row.metadata_json or {}), "text_index": {"status": "FAILED", "warning": type(failure).__name__}}
            job.status = "FAILED"
            job.error_summary = str(failure)[:500]
        db.commit()
