from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile, require_execution_scope
from amodb.apps.doc_control.knowledge_service import create_documentation_record, serialize_execution_profile, serialize_record
from amodb.apps.doc_control.pdf_provenance_overlay import reject_visual_overlays
from amodb.apps.doc_control.pdfium_service import (
    MAX_PDF_BYTES,
    PdfEngineError,
    PdfFlattenResult,
    PdfInspection,
    flatten_pdf_bytes,
    inspect_pdf_bytes,
    validate_template_provenance,
)
from amodb.apps.doc_control.workspace_service import require_manual_access
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .publications_fast_reader_router import _load_publication
from .core_router import _tenant_by_slug


router = APIRouter(prefix="/manuals", tags=["Controlled PDF Reader Engine"])

_EXECUTABLE_SUBMISSION_MODES = {"FILL_AND_SUBMIT", "DOWNLOAD_AND_UPLOAD", "PORTAL_SUBMISSION"}
_FILLABLE_EXECUTION_TYPES = {"PDF_ACROFORM", "HYBRID"}
_SIGNATURE_UNAVAILABLE = (
    "This controlled workflow requires a validated digital signature, "
    "but trusted PDF signature validation is not configured"
)
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _safe_filename(value: str | None, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value or fallback).name).strip("._") or fallback
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


def _flattened_filename(value: str | None, fallback: str) -> str:
    filename = _safe_filename(value, fallback)
    if "FLATTENED" not in filename.upper():
        filename = f"{filename[:-4]}_FLATTENED.pdf"
    return filename


async def read_bounded_pdf_upload(artifact: UploadFile) -> bytes:
    declared_size = getattr(artifact, "size", None)
    if declared_size is not None and int(declared_size) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "PDF_TOO_LARGE",
                "message": f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            },
        )
    content = bytearray()
    while True:
        chunk = await artifact.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "PDF_TOO_LARGE",
                    "message": f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
                },
            )
    return bytes(content)


def _source_path(revision: models.ManualRevision) -> Path:
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    path = Path(raw).resolve() if raw else None
    if not path or not path.exists() or not path.is_file() or path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=409, detail="This revision does not have an exact PDF source")
    return path


def _execution_profile(db: Session, tenant_id: str, manual_id: str) -> km.DocumentationExecutionProfile | None:
    return (
        db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant_id,
            km.DocumentationExecutionProfile.manual_id == manual_id,
        )
        .first()
    )


def _inspect_source(path_value: str, source_sha256: str, size: int, modified_ns: int) -> PdfInspection:
    """Verify and inspect the current bytes without trusting mutable filesystem metadata.

    ``size`` and ``modified_ns`` remain explicit inputs for diagnostics and backwards
    compatibility, but custody validation deliberately does not cache on them. Every
    call re-reads and re-hashes the immutable source before the PDF processor runs.
    """

    del modified_ns
    if size > MAX_PDF_BYTES:
        raise PdfEngineError(
            "PDF_TOO_LARGE",
            f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            status_code=413,
        )
    expected_sha256 = str(source_sha256 or "").strip().lower()
    if not expected_sha256:
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISSING",
            "The immutable revision does not have a recorded source checksum",
            status_code=409,
        )
    content = Path(path_value).read_bytes()
    if len(content) > MAX_PDF_BYTES:
        raise PdfEngineError(
            "PDF_TOO_LARGE",
            f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            status_code=413,
        )
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISMATCH",
            "The stored PDF bytes do not match the approved immutable revision checksum",
            status_code=409,
        )
    inspection = inspect_pdf_bytes(content)
    if not hmac.compare_digest(inspection.source_sha256.lower(), expected_sha256):
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISMATCH",
            "The PDF processor did not confirm the approved immutable revision checksum",
            status_code=409,
        )
    return inspection


def _clear_source_inspection_cache() -> None:
    """Compatibility hook: source custody inspection is intentionally uncached."""


setattr(_inspect_source, "cache_clear", _clear_source_inspection_cache)


def _inspection(revision: models.ManualRevision) -> PdfInspection:
    path = _source_path(revision)
    stat = path.stat()
    return _inspect_source(
        str(path),
        str(getattr(revision, "source_sha256", "") or ""),
        stat.st_size,
        stat.st_mtime_ns,
    )


def _capability_payload(
    profile: km.DocumentationExecutionProfile | None,
    inspection: PdfInspection,
    *,
    execution_allowed: bool = True,
) -> dict:
    submission_mode = str(getattr(profile, "submission_mode", "DOWNLOAD_ONLY") or "DOWNLOAD_ONLY")
    execution_type = str(getattr(profile, "execution_type", "NONE") or "NONE")
    executable = bool(profile and execution_allowed and submission_mode in _EXECUTABLE_SUBMISSION_MODES)
    signature_required = bool(getattr(profile, "requires_signature", False))
    can_fill = bool(
        executable
        and execution_type in _FILLABLE_EXECUTION_TYPES
        and inspection.has_acroform
        and inspection.can_flatten
        and not inspection.has_javascript
        and not inspection.is_dynamic_xfa
    )
    can_flatten = bool(
        executable
        and not signature_required
        and inspection.can_flatten
        and not inspection.has_javascript
    )
    reason = inspection.unsupported_reason
    if inspection.has_javascript:
        reason = "PDF JavaScript and automatic actions are disabled"
    elif profile is not None and not execution_allowed:
        reason = "This controlled resource is outside your execution scope"
    elif signature_required:
        reason = _SIGNATURE_UNAVAILABLE
    elif profile is None:
        reason = "No Document Control execution profile is configured"
    elif submission_mode == "DOWNLOAD_ONLY":
        reason = "This controlled resource is configured for download only"
    elif execution_type in _FILLABLE_EXECUTION_TYPES and not inspection.has_acroform:
        reason = "No AcroForm fields were detected"
    return {
        "execution": serialize_execution_profile(profile),
        "renderer": "PDF.js",
        "processor": inspection.engine,
        "processor_version": inspection.engine_version,
        "source_sha256": inspection.source_sha256,
        "page_count": inspection.page_count,
        "has_acroform": inspection.has_acroform,
        "has_javascript": inspection.has_javascript,
        "is_dynamic_xfa": inspection.is_dynamic_xfa,
        "encrypted": inspection.encrypted,
        "unsupported_reason": reason,
        "can_fill": can_fill,
        "can_save_draft": bool(can_fill and profile and profile.allow_save_draft),
        "can_download_original": bool(profile.allow_download if profile else True),
        "can_download_working": bool(can_fill and profile and profile.allow_download),
        "can_flatten": can_flatten,
        "can_submit": bool(executable and can_flatten),
    }


def _engine_http_error(exc: PdfEngineError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def process_completed_pdf(
    content: bytes,
    payload: dict,
    *,
    expected_source: PdfInspection,
    output_mode: str = "FLATTENED_RECORD",
) -> tuple[PdfFlattenResult, dict]:
    try:
        candidate = inspect_pdf_bytes(content)
        provenance = validate_template_provenance(expected_source, candidate)
        reject_visual_overlays(expected_source, candidate)
        result = flatten_pdf_bytes(content)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    enriched = dict(payload or {})
    enriched["pdf_engine"] = {
        **result.metadata(),
        "output_mode": output_mode,
        "template_provenance": provenance,
    }
    return result, enriched


def _load_direct_context(
    db: Session,
    *,
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    current_user: account_models.User,
):
    tenant, manual, revision, control_profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    require_manual_access(current_user, control_profile)
    execution = _execution_profile(db, str(tenant.amo_id), manual.id)
    return tenant, manual, revision, execution


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities")
def pdf_reader_capabilities(
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
    return _capability_payload(
        execution,
        inspection,
        execution_allowed=can_execute_profile(current_user, execution),
    )


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/flatten.pdf")
async def flatten_reader_working_copy(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    artifact: UploadFile = File(...),
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
    require_execution_scope(current_user, execution)
    if bool(getattr(execution, "requires_signature", False)):
        raise HTTPException(status_code=409, detail=_SIGNATURE_UNAVAILABLE)
    try:
        source_inspection = await run_in_threadpool(_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    capabilities = _capability_payload(execution, source_inspection, execution_allowed=True)
    if not capabilities["can_flatten"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be flattened")
    content = await read_bounded_pdf_upload(artifact)
    result, _metadata = await run_in_threadpool(
        process_completed_pdf,
        content,
        {},
        expected_source=source_inspection,
        output_mode="FLATTENED_DOWNLOAD",
    )
    filename = _flattened_filename(artifact.filename, f"{manual.code}_FLATTENED.pdf")
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PDF-Engine": result.engine,
        "X-PDF-Template-SHA256": source_inspection.source_sha256,
        "X-PDF-Working-SHA256": result.source_sha256,
        "X-PDF-Output-SHA256": result.output_sha256,
        "X-PDF-Page-Count": str(result.page_count),
        "X-PDF-Flattened-Pages": str(result.flattened_pages),
    }
    return StreamingResponse(io.BytesIO(result.content), media_type="application/pdf", headers=headers)


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/submit-record")
async def submit_reader_working_copy(
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
        source_inspection = await run_in_threadpool(_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    capabilities = _capability_payload(execution, source_inspection, execution_allowed=True)
    if not capabilities["can_submit"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be submitted")
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Submission metadata must be a JSON object") from exc
    content = await read_bounded_pdf_upload(artifact)
    result, enriched_payload = await run_in_threadpool(
        process_completed_pdf,
        content,
        payload,
        expected_source=source_inspection,
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
            action="documentation.record.submitted.pdfium",
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


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-engine-health", include_in_schema=False)
def pdf_engine_health(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The requested PDF is outside the active AMO")
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
    return _capability_payload(
        execution,
        inspection,
        execution_allowed=can_execute_profile(current_user, execution),
    )
