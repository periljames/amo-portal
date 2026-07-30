from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_service import create_documentation_record, serialize_execution_profile, serialize_record
from amodb.apps.doc_control.pdfium_service import PdfEngineError, PdfFlattenResult, flatten_pdf_bytes, inspect_pdf_bytes
from amodb.apps.doc_control.workspace_service import get_profile, require_manual_access
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .publications_fast_reader_router import _load_publication
from .router_legacy import _tenant_by_slug


router = APIRouter(prefix="/manuals", tags=["Controlled PDF Reader Engine"])

_EXECUTABLE_SUBMISSION_MODES = {"FILL_AND_SUBMIT", "DOWNLOAD_AND_UPLOAD", "PORTAL_SUBMISSION"}
_FILLABLE_EXECUTION_TYPES = {"PDF_ACROFORM", "HYBRID"}


def _safe_filename(value: str | None, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value or fallback).name).strip("._") or fallback
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


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


@lru_cache(maxsize=256)
def _inspect_source(path_value: str, source_sha256: str, size: int, modified_ns: int):
    del source_sha256, size, modified_ns
    return inspect_pdf_bytes(Path(path_value).read_bytes())


def _inspection(revision: models.ManualRevision):
    path = _source_path(revision)
    stat = path.stat()
    return _inspect_source(
        str(path),
        str(getattr(revision, "source_sha256", "") or ""),
        stat.st_size,
        stat.st_mtime_ns,
    )


def _capability_payload(profile: km.DocumentationExecutionProfile | None, inspection) -> dict:
    submission_mode = str(getattr(profile, "submission_mode", "DOWNLOAD_ONLY") or "DOWNLOAD_ONLY")
    execution_type = str(getattr(profile, "execution_type", "NONE") or "NONE")
    executable = bool(profile and submission_mode in _EXECUTABLE_SUBMISSION_MODES)
    can_fill = bool(
        executable
        and execution_type in _FILLABLE_EXECUTION_TYPES
        and inspection.has_acroform
        and inspection.can_flatten
        and not inspection.has_javascript
        and not inspection.is_dynamic_xfa
    )
    can_flatten = bool(executable and inspection.can_flatten and not inspection.has_javascript)
    reason = inspection.unsupported_reason
    if inspection.has_javascript:
        reason = "PDF JavaScript and automatic actions are disabled"
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


def process_completed_pdf(content: bytes, payload: dict) -> tuple[PdfFlattenResult, dict]:
    try:
        result = flatten_pdf_bytes(content)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    enriched = dict(payload or {})
    enriched["pdf_engine"] = {
        **result.metadata(),
        "output_mode": "FLATTENED_RECORD",
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
    return _capability_payload(execution, inspection)


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
    capabilities = _capability_payload(execution, _inspection(revision))
    if not capabilities["can_flatten"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be flattened")
    content = await artifact.read()
    try:
        result = flatten_pdf_bytes(content)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    filename = _safe_filename(artifact.filename, f"{manual.code}_FLATTENED.pdf")
    if "FLATTENED" not in filename.upper():
        filename = filename[:-4] + "_FLATTENED.pdf"
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PDF-Engine": result.engine,
        "X-PDF-Source-SHA256": result.source_sha256,
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
    capabilities = _capability_payload(execution, _inspection(revision))
    if not capabilities["can_submit"]:
        raise HTTPException(status_code=409, detail=capabilities["unsupported_reason"] or "This PDF cannot be submitted")
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Submission metadata must be a JSON object") from exc
    result, enriched_payload = process_completed_pdf(await artifact.read(), payload)
    record = create_documentation_record(
        db,
        manual_tenant=tenant,
        template=manual,
        revision=revision,
        profile=execution,
        actor_id=current_user.id,
        filename=_safe_filename(artifact.filename, f"{manual.code}_FLATTENED.pdf"),
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
                "source_sha256": result.source_sha256,
                "artifact_sha256": result.output_sha256,
                "pdf_engine": result.engine,
                "flattened_pages": result.flattened_pages,
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
    return _capability_payload(execution, _inspection(revision))
