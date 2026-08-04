from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile, require_execution_scope
from amodb.apps.doc_control.pdfium_service import PdfEngineError, PdfFlattenResult, PdfInspection
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .pdf_reader_router import (
    _SIGNATURE_UNAVAILABLE,
    _capability_payload,
    _engine_http_error,
    _flattened_filename,
    _inspection,
    _load_direct_context,
    _source_path,
    process_completed_pdf,
    read_bounded_pdf_upload,
)
from .pdf_static_overlay_router import static_overlay_capabilities


router = APIRouter(prefix="/manuals", tags=["Controlled PDF Reader Form Overrides"])


def _safe_form_capabilities(
    profile,
    inspection: PdfInspection,
    *,
    execution_allowed: bool,
) -> dict[str, Any]:
    """Allow safe AcroForm execution without requiring a separate setup record.

    Manual access remains mandatory. An existing execution profile still controls
    scope, draft retention, downloads, signatures, and retained-record submission.
    When no profile exists, a non-scripted AcroForm is treated as a local working
    document: the immutable source is never edited and only completed form pages
    may be flattened for download.
    """

    payload = _capability_payload(profile, inspection, execution_allowed=execution_allowed)
    scoped = execution_allowed if profile is not None else True
    signature_required = bool(getattr(profile, "requires_signature", False))
    safe_acroform = bool(
        scoped
        and inspection.has_acroform
        and inspection.can_flatten
        and not inspection.has_javascript
        and not inspection.is_dynamic_xfa
        and not inspection.encrypted
    )
    allow_download = bool(getattr(profile, "allow_download", True)) if profile is not None else True
    allow_draft = bool(getattr(profile, "allow_save_draft", True)) if profile is not None else True

    payload.update(
        {
            "can_fill": safe_acroform,
            "can_save_draft": bool(safe_acroform and allow_draft),
            "can_download_original": allow_download,
            "can_download_working": bool(safe_acroform and allow_download),
            "can_flatten": bool((payload.get("can_flatten") or safe_acroform) and not signature_required),
            "automatic_form_execution": bool(safe_acroform and profile is None),
            "form_download_mode": "CHANGED_FORM_PAGES" if safe_acroform else None,
        }
    )
    if safe_acroform and not signature_required:
        payload["unsupported_reason"] = None
    return payload


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
        inspection = _inspection(revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    execution_allowed = can_execute_profile(current_user, execution) if execution is not None else True
    payload = _safe_form_capabilities(
        execution,
        inspection,
        execution_allowed=execution_allowed,
    )
    overlay = static_overlay_capabilities(
        current_user,
        execution,
        has_javascript=inspection.has_javascript,
        is_dynamic_xfa=inspection.is_dynamic_xfa,
        encrypted=inspection.encrypted,
    )
    payload.update(overlay)
    if overlay["can_overlay_fill"] and not inspection.has_acroform:
        payload["unsupported_reason"] = None
    return payload


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
        source_inspection = await run_in_threadpool(_inspection, revision)
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
        process_completed_pdf,
        working_content,
        {},
        expected_source=source_inspection,
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
        "X-PDF-Template-SHA256": source_inspection.source_sha256,
        "X-PDF-Working-SHA256": result.source_sha256,
        "X-PDF-Output-SHA256": result.output_sha256,
        "X-PDF-Source-Page-Count": str(source_inspection.page_count),
        "X-PDF-Page-Count": str(result.page_count),
        "X-PDF-Flattened-Pages": str(result.flattened_pages),
        "X-PDF-Selected-Pages": ",".join(str(page) for page in selected_pages),
    }
    return StreamingResponse(io.BytesIO(result.content), media_type="application/pdf", headers=headers)
