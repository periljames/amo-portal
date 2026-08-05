from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile, require_execution_scope
from amodb.apps.doc_control.knowledge_service import create_documentation_record, serialize_record
from amodb.apps.doc_control.pdf_capability_service import inspect_pdf_capabilities_bytes
from amodb.apps.doc_control.pdf_provenance_overlay import reject_visual_overlays
from amodb.apps.doc_control.pdf_safe_processing_service import (
    flatten_script_disabled_pdf_bytes,
    inspect_script_disabled_pdf_bytes,
    sanitize_pdf_javascript_bytes,
)
from amodb.apps.doc_control.pdfium_service import (
    MAX_PDF_BYTES,
    PdfEngineError,
    PdfFlattenResult,
    PdfInspection,
    validate_template_provenance,
)
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .pdf_reader_router import (
    _EXECUTABLE_SUBMISSION_MODES,
    _SIGNATURE_UNAVAILABLE,
    _capability_payload,
    _engine_http_error,
    _flattened_filename,
    _load_direct_context,
    _source_path,
    read_bounded_pdf_upload,
)


router = APIRouter(prefix="/manuals", tags=["Controlled PDF Reader Form Overrides"])
_SAFE_READER_CACHE_ROOT = Path(os.getenv("PDF_SAFE_READER_CACHE_DIR", "uploads/pdf-safe-reader-cache")).resolve()


def _capability_inspection(revision: models.ManualRevision) -> PdfInspection:
    """Verify custody, then perform only the checks needed to initialize the reader."""

    path = _source_path(revision)
    content = path.read_bytes()
    if len(content) > MAX_PDF_BYTES:
        raise PdfEngineError(
            "PDF_TOO_LARGE",
            f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            status_code=413,
        )
    recorded_sha256 = str(getattr(revision, "source_sha256", "") or "").strip().lower()
    if not recorded_sha256:
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISSING",
            "The immutable revision does not have a recorded source checksum",
            status_code=409,
        )
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_sha256, recorded_sha256):
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISMATCH",
            "The stored PDF bytes do not match the approved immutable revision checksum",
            status_code=409,
        )
    inspection = inspect_pdf_capabilities_bytes(content)
    if not hmac.compare_digest(inspection.source_sha256.lower(), recorded_sha256):
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISMATCH",
            "The PDF capability processor did not confirm the approved immutable revision checksum",
            status_code=409,
        )
    return inspection


def _safe_form_capabilities(
    profile,
    inspection: PdfInspection,
    *,
    execution_allowed: bool,
) -> dict[str, Any]:
    """Enable real AcroForms while forcing all embedded scripts out of execution."""

    payload = _capability_payload(profile, inspection, execution_allowed=execution_allowed)
    scoped = execution_allowed if profile is not None else True
    signature_required = bool(getattr(profile, "requires_signature", False))
    safe_acroform = bool(
        scoped
        and inspection.has_acroform
        and not inspection.is_dynamic_xfa
        and not inspection.encrypted
    )
    allow_download = bool(getattr(profile, "allow_download", True)) if profile is not None else True
    allow_draft = bool(getattr(profile, "allow_save_draft", True)) if profile is not None else True
    submission_mode = str(getattr(profile, "submission_mode", "DOWNLOAD_ONLY") or "DOWNLOAD_ONLY")
    executable_submission = bool(
        profile
        and execution_allowed
        and submission_mode in _EXECUTABLE_SUBMISSION_MODES
        and not signature_required
    )
    source_has_javascript = bool(inspection.has_javascript)

    payload.update(
        {
            # The reader receives a script-disabled derivative when the source
            # contains JavaScript, so no script is executable in PDF.js.
            "has_javascript": False if source_has_javascript else inspection.has_javascript,
            "source_has_javascript": source_has_javascript,
            "javascript_policy": "DISABLED_AND_STRIPPED" if source_has_javascript else "NONE",
            "can_fill": safe_acroform,
            "can_save_draft": bool(safe_acroform and allow_draft),
            "can_download_original": allow_download,
            "can_download_working": bool(safe_acroform and allow_download),
            "can_flatten": bool(safe_acroform and not signature_required),
            "can_submit": bool(safe_acroform and executable_submission),
            "automatic_form_execution": bool(safe_acroform and profile is None),
            "form_download_mode": "CHANGED_FORM_PAGES" if safe_acroform else None,
        }
    )
    if safe_acroform and not signature_required:
        payload["unsupported_reason"] = None
    return payload


def _safe_reader_cache_path(revision: models.ManualRevision, source_sha256: str) -> Path:
    root = _SAFE_READER_CACHE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    target = (root / f"{source_sha256}.pdf").resolve()
    if target.parent != root:
        raise PdfEngineError("PDF_CACHE_PATH_INVALID", "Unsafe PDF reader cache path", status_code=500)
    if target.exists() and target.is_file() and target.stat().st_size > 4:
        return target

    source_content = _source_path(revision).read_bytes()
    sanitized = sanitize_pdf_javascript_bytes(source_content)
    if not sanitized.startswith(b"%PDF"):
        raise PdfEngineError("PDF_SANITIZE_OUTPUT_INVALID", "The script-disabled reader PDF is invalid", status_code=500)
    with tempfile.NamedTemporaryFile(prefix=f"{source_sha256}-", suffix=".tmp", dir=root, delete=False) as handle:
        temporary = Path(handle.name).resolve()
        handle.write(sanitized)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _normalized_widget_value(widget: Any) -> str:
    value = getattr(widget, "field_value", None)
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value).strip()


def _widget_values(page: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    widgets = list(page.widgets() or [])
    for index, widget in enumerate(widgets):
        name = str(getattr(widget, "field_name", "") or f"widget-{index}")
        values[f"{name}:{index}"] = _normalized_widget_value(widget)
    return values


def _changed_form_pages(source_content: bytes, working_content: bytes) -> tuple[list[int], list[int]]:
    source = pymupdf.open(stream=source_content, filetype="pdf")
    working = pymupdf.open(stream=working_content, filetype="pdf")
    try:
        if source.page_count != working.page_count:
            raise HTTPException(status_code=409, detail="The working PDF page count no longer matches the controlled source")
        changed: list[int] = []
        form_pages: list[int] = []
        for index in range(working.page_count):
            source_values = _widget_values(source[index])
            working_values = _widget_values(working[index])
            if working_values:
                form_pages.append(index + 1)
            if source_values != working_values:
                changed.append(index + 1)
        return changed, form_pages
    finally:
        source.close()
        working.close()


def _parse_requested_pages(raw: str, page_count: int) -> list[int]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Completed form pages must be a JSON array") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=422, detail="Completed form pages must be a JSON array")
    pages: list[int] = []
    for value in payload:
        try:
            page = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Completed form page numbers must be integers") from exc
        if page < 1 or page > page_count:
            raise HTTPException(status_code=422, detail=f"Completed form page {page} is outside the source document")
        if page not in pages:
            pages.append(page)
    return sorted(pages)


def _extract_completed_pages(result: PdfFlattenResult, pages: list[int]) -> PdfFlattenResult:
    source = pymupdf.open(stream=result.content, filetype="pdf")
    output = pymupdf.open()
    try:
        for page in pages:
            output.insert_pdf(source, from_page=page - 1, to_page=page - 1, links=True, annots=True)
        content = output.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        output.close()
        source.close()
    return PdfFlattenResult(
        content=content,
        engine=result.engine,
        engine_version=result.engine_version,
        source_sha256=result.source_sha256,
        output_sha256=hashlib.sha256(content).hexdigest(),
        page_count=len(pages),
        form_type=result.form_type,
        flattened_pages=len(pages),
        unchanged_pages=0,
    )


def _completed_pages_filename(value: str | None, fallback: str) -> str:
    flattened = _flattened_filename(value, fallback)
    return flattened.replace("_FLATTENED.pdf", "_COMPLETED_PAGES.pdf")


def _process_script_disabled_pdf(
    source_content: bytes,
    working_content: bytes,
    payload: dict[str, Any],
    *,
    output_mode: str,
) -> tuple[PdfFlattenResult, dict[str, Any]]:
    try:
        expected = inspect_script_disabled_pdf_bytes(source_content)
        candidate = inspect_script_disabled_pdf_bytes(working_content)
        provenance = validate_template_provenance(expected, candidate)
        reject_visual_overlays(expected, candidate)
        result = flatten_script_disabled_pdf_bytes(working_content)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    enriched = dict(payload or {})
    enriched["pdf_engine"] = {
        **result.metadata(),
        "output_mode": output_mode,
        "script_policy": "DISABLED_AND_STRIPPED",
        "template_source_sha256": hashlib.sha256(source_content).hexdigest(),
        "template_provenance": provenance,
    }
    return result, enriched


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities")
def pdf_reader_capabilities_override(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, _manual, revision, execution = _load_direct_context(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    try:
        inspection = _capability_inspection(revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    payload = _safe_form_capabilities(
        execution,
        inspection,
        execution_allowed=can_execute_profile(current_user, execution) if execution is not None else True,
    )
    if inspection.has_javascript:
        payload["reader_pdf_url"] = (
            f"/manuals/t/{tenant_slug.lower()}/{manual_id}/rev/{revision_id}/script-disabled.pdf"
            f"?v={inspection.source_sha256}"
        )
    return payload


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/script-disabled.pdf", include_in_schema=False)
async def script_disabled_reader_pdf(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, manual, revision, _execution = _load_direct_context(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    try:
        inspection = await run_in_threadpool(_capability_inspection, revision)
        path = await run_in_threadpool(_safe_reader_cache_path, revision, inspection.source_sha256)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    safe_code = "_".join(str(manual.code or "publication").split())
    headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": f'inline; filename="{safe_code}_SCRIPT_DISABLED.pdf"',
        "X-Content-Type-Options": "nosniff",
        "X-Publication-Source": "script-disabled-working-template",
        "X-AcroForm-Policy": "fillable-no-scripting",
        "X-PDF-Template-SHA256": inspection.source_sha256,
    }
    return FileResponse(path, media_type="application/pdf", headers=headers)


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/flatten.pdf")
async def flatten_completed_form_pages(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    artifact: UploadFile = File(...),
    page_numbers_json: str = Form("[]"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, manual, revision, execution = _load_direct_context(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    if execution is not None:
        require_execution_scope(current_user, execution)
    if bool(getattr(execution, "requires_signature", False)):
        raise HTTPException(status_code=409, detail=_SIGNATURE_UNAVAILABLE)

    try:
        source_inspection = await run_in_threadpool(_capability_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    capabilities = _safe_form_capabilities(execution, source_inspection, execution_allowed=True)
    if not capabilities["can_flatten"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be flattened")

    working_content = await read_bounded_pdf_upload(artifact)
    source_content = await run_in_threadpool(_source_path(revision).read_bytes)
    changed_pages, form_pages = await run_in_threadpool(_changed_form_pages, source_content, working_content)
    requested_pages = _parse_requested_pages(page_numbers_json, source_inspection.page_count)
    requested_form_pages = [page for page in requested_pages if page in form_pages]
    selected_pages = changed_pages or requested_form_pages
    if source_inspection.has_acroform and not selected_pages:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "NO_COMPLETED_FORM_PAGES",
                "message": "Fill at least one form field before downloading completed pages.",
            },
        )

    result, _metadata = await run_in_threadpool(
        _process_script_disabled_pdf,
        source_content,
        working_content,
        {},
        output_mode="FLATTENED_COMPLETED_PAGES",
    )
    if selected_pages:
        result = await run_in_threadpool(_extract_completed_pages, result, selected_pages)

    filename = _completed_pages_filename(artifact.filename, f"{manual.code}_COMPLETED_PAGES.pdf")
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PDF-Engine": result.engine,
        "X-PDF-Script-Policy": "DISABLED_AND_STRIPPED",
        "X-PDF-Template-SHA256": source_inspection.source_sha256,
        "X-PDF-Working-SHA256": result.source_sha256,
        "X-PDF-Output-SHA256": result.output_sha256,
        "X-PDF-Source-Page-Count": str(source_inspection.page_count),
        "X-PDF-Page-Count": str(result.page_count),
        "X-PDF-Flattened-Pages": str(result.flattened_pages),
        "X-PDF-Selected-Pages": ",".join(str(page) for page in selected_pages),
    }
    return StreamingResponse(io.BytesIO(result.content), media_type="application/pdf", headers=headers)


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")
async def submit_script_disabled_working_copy(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    request: Request,
    artifact: UploadFile = File(...),
    payload_json: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant, manual, revision, execution = _load_direct_context(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    if not execution or execution.submission_mode not in _EXECUTABLE_SUBMISSION_MODES:
        raise HTTPException(status_code=409, detail="This controlled resource is not configured for retained-record submission")
    require_execution_scope(current_user, execution)
    if bool(execution.requires_signature):
        raise HTTPException(status_code=409, detail=_SIGNATURE_UNAVAILABLE)
    try:
        source_inspection = await run_in_threadpool(_capability_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    capabilities = _safe_form_capabilities(execution, source_inspection, execution_allowed=True)
    if not capabilities["can_submit"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be submitted")
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Submission metadata must be a JSON object") from exc

    working_content = await read_bounded_pdf_upload(artifact)
    source_content = await run_in_threadpool(_source_path(revision).read_bytes)
    result, enriched_payload = await run_in_threadpool(
        _process_script_disabled_pdf,
        source_content,
        working_content,
        payload,
        output_mode="FLATTENED_RECORD",
    )
    record = create_documentation_record(
        db,
        manual_tenant=tenant,
        template=manual,
        revision=revision,
        profile=execution,
        actor_id=current_user.id,
        filename=_flattened_filename(artifact.filename, f"{manual.code}_FLATTENED.pdf"),
        content=result.content,
        source_reference_id=None,
        payload=enriched_payload,
    )
    db.add(
        models.ManualAuditLog(
            tenant_id=tenant.id,
            actor_id=current_user.id,
            action="documentation.record.submitted.pdfium.script_disabled",
            entity_type="documentation_record",
            entity_id=record.id,
            ip_device=(
                f"{request.client.host if request.client else 'unknown'}::"
                f"{request.headers.get('user-agent', 'n/a')}"
            ),
            diff_json={
                "record_number": record.record_number,
                "template_manual_id": manual.id,
                "template_revision_id": revision.id,
                "template_source_sha256": source_inspection.source_sha256,
                "working_copy_sha256": result.source_sha256,
                "artifact_sha256": result.output_sha256,
                "pdf_engine": result.engine,
                "script_policy": "DISABLED_AND_STRIPPED",
                "flattened_pages": result.flattened_pages,
                "template_provenance": enriched_payload["pdf_engine"]["template_provenance"],
            },
        )
    )
    db.commit()
    db.refresh(record)
    response = serialize_record(record)
    response["download_url"] = f"/manuals/t/{tenant.slug}/records/{record.id}/artifact.pdf"
    return response
