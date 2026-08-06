from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile
from amodb.apps.doc_control.pdfium_service import PdfEngineError
from amodb.database import get_db
from amodb.security import get_current_active_user

from .pdf_reader_form_override_router import (
    _engine_http_error,
    _load_direct_context,
    _safe_form_capabilities,
    _safe_reader_cache_path,
)
from .pdf_reader_precompute import cached_pdf_inspection


router = APIRouter(
    prefix="/manuals",
    tags=["Controlled PDF Reader Precomputed Capabilities"],
)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities")
async def precomputed_pdf_reader_capabilities(
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
        inspection = await run_in_threadpool(
            cached_pdf_inspection,
            revision,
            prepare_safe_reader=True,
        )
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc

    payload = _safe_form_capabilities(
        execution,
        inspection,
        execution_allowed=(
            can_execute_profile(current_user, execution)
            if execution is not None
            else True
        ),
    )
    if inspection.has_javascript:
        payload["reader_pdf_url"] = (
            f"/manuals/t/{tenant_slug.lower()}/{manual_id}/rev/{revision_id}/script-disabled.pdf"
            f"?v={inspection.source_sha256}"
        )
    return payload


@router.get(
    "/t/{tenant_slug}/{manual_id}/rev/{revision_id}/script-disabled.pdf",
    include_in_schema=False,
)
async def precomputed_script_disabled_reader_pdf(
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
        inspection = await run_in_threadpool(
            cached_pdf_inspection,
            revision,
            prepare_safe_reader=True,
        )
        path = await run_in_threadpool(
            _safe_reader_cache_path,
            revision,
            inspection.source_sha256,
        )
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
        "X-PDF-Capability-Cache": "checksum-keyed",
    }
    return FileResponse(path, media_type="application/pdf", headers=headers)
