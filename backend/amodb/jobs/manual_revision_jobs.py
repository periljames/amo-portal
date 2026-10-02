"""Lease-owned processing for legacy Manual revision actions."""
from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.doc_control import knowledge_models as knowledge_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.pdf_reader_precompute import cached_pdf_inspection
from amodb.apps.manuals.office_layout import OfficeLayoutError, prepare_office_layout_pdf
from amodb.apps.platform import saas_models


JOB_TYPES = {"MANUAL_REVISION_PROCESS", "MANUAL_REVISION_OCR"}
_MIN_NATIVE_PAGE_CHARS = 24


def _revision(db: Session, job: saas_models.SaaSJob) -> tuple[manual_models.Tenant, manual_models.Manual, manual_models.ManualRevision]:
    payload = dict(job.payload_json or {})
    revision_id = str(payload.get("revision_id") or "").strip()
    manual_id = str(payload.get("manual_id") or "").strip()
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.id == revision_id,
        manual_models.ManualRevision.manual_id == manual_id,
    ).first()
    if revision is None:
        raise ValueError("Manual revision no longer exists")
    manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == revision.manual_id).first()
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.id == manual.tenant_id).first() if manual else None
    if manual is None or tenant is None or str(tenant.amo_id) != str(job.tenant_id):
        raise ValueError("Manual revision tenant scope is invalid")
    return tenant, manual, revision


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    job: saas_models.SaaSJob,
    action: str,
    revision_id: str,
    details: dict[str, Any],
) -> None:
    db.add(manual_models.ManualAuditLog(
        tenant_id=tenant.id,
        actor_id=job.created_by,
        action=action,
        entity_type="manual_revision",
        entity_id=revision_id,
        ip_device="durable-worker",
        diff_json={"job_id": job.id, **details},
    ))


def _ocr_runtime_available() -> tuple[bool, str | None]:
    """Check the optional OCR runtime once, only when a sparse page needs it."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # noqa: F401  # type: ignore

        pytesseract.get_tesseract_version()
        return True, None
    except Exception as exc:
        return False, f"OCR runtime unavailable: {exc}"


def _ocr_page(page) -> tuple[str, str | None]:
    """OCR one sparse PDF page after the optional runtime has been verified."""
    try:
        import fitz  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return str(pytesseract.image_to_string(image) or "").strip(), None
    except Exception as exc:
        return "", f"OCR page failed: {exc}"


def _refresh_pdf_search_blocks(
    db: Session,
    *,
    revision: manual_models.ManualRevision,
) -> dict[str, Any]:
    """Rebuild derived searchable PDF blocks using native text first and OCR only for sparse pages."""
    source = Path(str(revision.source_storage_path or "")).resolve()
    if not source.is_file():
        raise ValueError("The immutable PDF source is unavailable")

    try:
        import fitz  # type: ignore
    except Exception as exc:
        raise ValueError("PyMuPDF is required for PDF text extraction") from exc

    page_text: dict[int, str] = {}
    page_engine: dict[int, str] = {}
    warnings: list[dict[str, Any]] = []
    native_pages = 0
    ocr_pages = 0
    unsearchable_pages = 0
    ocr_runtime_available: bool | None = None
    ocr_runtime_warning: str | None = None

    with fitz.open(source) as document:
        revision.source_page_count = document.page_count
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            native = str(page.get_text("text") or "").strip()
            selected = native
            engine = "PYMUPDF_NATIVE"
            if len(native) < _MIN_NATIVE_PAGE_CHARS:
                if ocr_runtime_available is None:
                    ocr_runtime_available, ocr_runtime_warning = _ocr_runtime_available()
                    if ocr_runtime_warning:
                        warnings.append({"page_number": page_number, "warning": ocr_runtime_warning[:500]})
                ocr_text = ""
                warning = None
                if ocr_runtime_available:
                    ocr_text, warning = _ocr_page(page)
                    if warning:
                        warnings.append({"page_number": page_number, "warning": warning[:500]})
                if len(ocr_text) > len(native):
                    selected = ocr_text
                    engine = "PYTESSERACT_OCR"
                    ocr_pages += 1
                elif native:
                    native_pages += 1
                else:
                    engine = "UNSEARCHABLE"
                    unsearchable_pages += 1
            else:
                native_pages += 1
            page_text[page_number] = selected
            page_engine[page_number] = engine

    sections = (
        db.query(manual_models.ManualSection)
        .filter(manual_models.ManualSection.revision_id == revision.id)
        .order_by(manual_models.ManualSection.order_index.asc())
        .all()
    )
    rebuilt_blocks = 0
    for section in sections:
        metadata = dict(section.metadata_json or {})
        start = int(metadata.get("page_start") or 0)
        end = int(metadata.get("page_end") or start or 0)
        if start <= 0:
            continue
        end = max(start, end)
        db.query(manual_models.ManualBlock).filter(
            manual_models.ManualBlock.section_id == section.id,
        ).delete(synchronize_session=False)
        section_ocr_pages: list[int] = []
        section_native_pages: list[int] = []
        section_missing_pages: list[int] = []
        for page_number in range(start, end + 1):
            text = str(page_text.get(page_number) or "").strip()
            engine = page_engine.get(page_number, "UNAVAILABLE")
            if engine == "PYTESSERACT_OCR":
                section_ocr_pages.append(page_number)
            elif text:
                section_native_pages.append(page_number)
            else:
                section_missing_pages.append(page_number)
            digest = hashlib.sha256(
                f"{revision.id}:{section.id}:{page_number}:{engine}:{text}".encode("utf-8")
            ).hexdigest()
            db.add(manual_models.ManualBlock(
                section_id=section.id,
                order_index=(page_number - start) + 1,
                block_type="page-text" if text else "page-empty",
                html_sanitized=f"<p>{escape(text)}</p>",
                text_plain=text,
                change_hash=digest,
            ))
            rebuilt_blocks += 1
        metadata["text_extraction"] = {
            "policy": "NATIVE_FIRST_PAGE_OCR_FALLBACK",
            "native_pages": section_native_pages,
            "ocr_pages": section_ocr_pages,
            "unsearchable_pages": section_missing_pages,
        }
        section.metadata_json = metadata

    db.add(revision)
    db.flush()
    return {
        "policy": "NATIVE_FIRST_PAGE_OCR_FALLBACK",
        "native_pages": native_pages,
        "ocr_pages": ocr_pages,
        "unsearchable_pages": unsearchable_pages,
        "rebuilt_blocks": rebuilt_blocks,
        "warnings": warnings[:50],
    }


def _process_revision(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    tenant, manual, revision = _revision(db, job)
    source_type = str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()
    result: dict[str, Any] = {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "source_type": source_type,
    }
    if source_type == "PDF":
        inspection = cached_pdf_inspection(revision, prepare_safe_reader=True)
        result["pdf"] = {
            "engine": inspection.engine,
            "page_count": inspection.page_count,
            "has_acroform": inspection.has_acroform,
            "has_javascript": inspection.has_javascript,
            "can_flatten": inspection.can_flatten,
        }
        result["search_text"] = _refresh_pdf_search_blocks(db, revision=revision)
    elif source_type in {"DOCX", "DOC", "ODT", "RTF"}:
        try:
            derivative = prepare_office_layout_pdf(revision)
            revision.source_page_count = derivative.page_count
            result["office_layout"] = {
                "status": "READY",
                "path": str(derivative.path),
                "page_count": derivative.page_count,
                "size_bytes": derivative.size_bytes,
                "source_sha256": derivative.source_sha256,
                "created": derivative.created,
            }
        except OfficeLayoutError as exc:
            # The original source and semantic reader stay available. Production
            # images include LibreOffice Writer, so this warning is actionable
            # without turning source ingestion into data loss.
            result["office_layout"] = {
                "status": "UNAVAILABLE",
                "error": str(exc),
            }

    index_job = db.query(knowledge_models.DocumentationIndexJob).filter(
        knowledge_models.DocumentationIndexJob.tenant_id == tenant.amo_id,
        knowledge_models.DocumentationIndexJob.revision_id == revision.id,
    ).first()
    if index_job is None:
        index_job = knowledge_models.DocumentationIndexJob(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            revision_id=revision.id,
        )
        db.add(index_job)
    if index_job.status != "RUNNING":
        index_job.status = "PENDING"
        index_job.source_sha256 = revision.source_sha256
        index_job.error_summary = None
        index_job.completed_at = None
    result["reference_indexing"] = "PENDING" if index_job.status != "RUNNING" else "RUNNING"
    _audit(
        db,
        tenant=tenant,
        job=job,
        action="revision.processing.completed",
        revision_id=revision.id,
        details=result,
    )
    db.flush()
    return result


def _process_ocr(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    tenant, manual, revision = _revision(db, job)
    source_type = str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()
    if source_type != "PDF":
        raise ValueError("Controlled OCR is available only for PDF revisions")
    source = Path(str(revision.source_storage_path or "")).resolve()
    if not source.is_file():
        raise ValueError("The immutable PDF source is unavailable")

    search_text = _refresh_pdf_search_blocks(db, revision=revision)

    # Imported lazily to avoid making router initialization depend on optional
    # OCR libraries. Approval-letter detection remains non-authoritative until
    # a controller completes the verification endpoint.
    from amodb.apps.manuals.core_router import (
        _extract_first_date,
        _extract_kcaa_reference,
        _extract_text_from_pdf_bytes,
    )

    extracted = _extract_text_from_pdf_bytes(source.read_bytes())
    detected_ref = _extract_kcaa_reference(extracted)
    detected_date = _extract_first_date(extracted)
    revision.ocr_detected_ref = detected_ref
    revision.ocr_detected_date = detected_date
    revision.ocr_verified_bool = False
    revision.ocr_verified_at = None
    db.add(revision)

    index_job = db.query(knowledge_models.DocumentationIndexJob).filter(
        knowledge_models.DocumentationIndexJob.tenant_id == tenant.amo_id,
        knowledge_models.DocumentationIndexJob.revision_id == revision.id,
    ).first()
    if index_job is None:
        index_job = knowledge_models.DocumentationIndexJob(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            revision_id=revision.id,
        )
        db.add(index_job)
    if index_job.status != "RUNNING":
        index_job.status = "PENDING"
        index_job.source_sha256 = revision.source_sha256
        index_job.error_summary = None
        index_job.completed_at = None

    result = {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "detected_ref": detected_ref,
        "detected_date": detected_date.isoformat() if detected_date else None,
        "text_characters": len(extracted),
        "verification_required": True,
        "search_text": search_text,
        "reference_indexing": "PENDING" if index_job.status != "RUNNING" else "RUNNING",
    }
    _audit(
        db,
        tenant=tenant,
        job=job,
        action="revision.ocr.completed",
        revision_id=revision.id,
        details=result,
    )
    db.flush()
    return result


def process_job(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    if job.job_type == "MANUAL_REVISION_PROCESS":
        return _process_revision(db, job)
    if job.job_type == "MANUAL_REVISION_OCR":
        return _process_ocr(db, job)
    raise ValueError(f"Unsupported Manual revision job type: {job.job_type}")
