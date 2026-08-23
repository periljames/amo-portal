"""Precedence routes that authorize both sides of linked-document references."""
from __future__ import annotations

import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile, require_execution_scope
from amodb.apps.doc_control.pdfium_service import PdfEngineError
from amodb.apps.doc_control.workspace_service import get_profile, require_manual_access
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import knowledge_reader_router as reader
from . import models
from .pdf_reader_router import (
    _engine_http_error,
    _inspection,
    process_completed_pdf,
    read_bounded_pdf_upload,
)
from .core_router import _tenant_by_slug


router = APIRouter(prefix="/manuals", tags=["Publications Knowledge Graph"])


def _enforce_reference_source_access(
    db: Session,
    *,
    tenant: models.Tenant,
    reference: km.DocumentationReference,
    user: account_models.User,
) -> models.Manual:
    source = (
        db.query(models.Manual)
        .filter(
            models.Manual.id == reference.source_manual_id,
            models.Manual.tenant_id == tenant.id,
        )
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="The reference source document is unavailable")
    require_manual_access(user, get_profile(db, tenant, source.id))
    return source


def _load_authorized_reference(
    db: Session,
    *,
    tenant: models.Tenant,
    reference_id: str,
    user: account_models.User,
) -> km.DocumentationReference:
    reference = (
        db.query(km.DocumentationReference)
        .filter(
            km.DocumentationReference.id == reference_id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
        )
        .first()
    )
    if not reference:
        raise HTTPException(status_code=404, detail="The document reference is unavailable")
    _enforce_reference_source_access(db, tenant=tenant, reference=reference, user=user)
    return reference


def _submission_payload(payload_json: str) -> dict:
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Submission metadata must be a JSON object") from exc


def _execution_profile_for_detail(db: Session, tenant: models.Tenant, detail: dict) -> km.DocumentationExecutionProfile | None:
    manual_id = str((detail.get("target") or {}).get("manual_id") or "")
    if not manual_id:
        return None
    return (
        db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
            km.DocumentationExecutionProfile.manual_id == manual_id,
        )
        .first()
    )


def _authorized_linked_detail(
    *,
    tenant: models.Tenant,
    tenant_slug: str,
    reference_id: str,
    db: Session,
    current_user: account_models.User,
) -> tuple[dict, km.DocumentationExecutionProfile | None]:
    detail = reader.linked_resource_detail(
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        db=db,
        current_user=current_user,
    )
    execution = _execution_profile_for_detail(db, tenant, detail)
    execution_allowed = can_execute_profile(current_user, execution)
    capabilities = dict(detail.get("capabilities") or {})
    capabilities["execute"] = bool(capabilities.get("execute") and execution_allowed)
    capabilities["save_draft"] = bool(capabilities.get("save_draft") and execution_allowed)
    detail["capabilities"] = capabilities
    return detail, execution


def _controlled_target_revision(db: Session, tenant: models.Tenant, detail: dict) -> models.ManualRevision:
    target = dict(detail.get("target") or {})
    manual_id = str(target.get("manual_id") or "")
    revision_id = str(target.get("revision_id") or "")
    revision = (
        db.query(models.ManualRevision)
        .join(models.Manual, models.Manual.id == models.ManualRevision.manual_id)
        .filter(
            models.Manual.id == manual_id,
            models.Manual.tenant_id == tenant.id,
            models.ManualRevision.id == revision_id,
            models.ManualRevision.manual_id == manual_id,
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="The effective controlled template revision is unavailable")
    return revision


@router.get("/t/{tenant_slug}/linked-resources/{reference_id}")
def linked_resource_detail_with_source_access(
    tenant_slug: str,
    reference_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The linked resource is outside the active AMO")
    _load_authorized_reference(
        db,
        tenant=tenant,
        reference_id=reference_id,
        user=current_user,
    )
    detail, _execution = _authorized_linked_detail(
        tenant=tenant,
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        db=db,
        current_user=current_user,
    )
    return detail


@router.post("/t/{tenant_slug}/linked-resources/{reference_id}/submit")
async def submit_linked_resource_with_source_access(
    tenant_slug: str,
    reference_id: str,
    request: Request,
    artifact: UploadFile = File(...),
    payload_json: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The linked resource is outside the active AMO")
    _load_authorized_reference(
        db,
        tenant=tenant,
        reference_id=reference_id,
        user=current_user,
    )
    detail, execution_profile = _authorized_linked_detail(
        tenant=tenant,
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        db=db,
        current_user=current_user,
    )
    require_execution_scope(current_user, execution_profile)
    if not bool((detail.get("capabilities") or {}).get("execute")):
        raise HTTPException(status_code=403, detail="This controlled resource is not executable")
    execution = ((detail.get("target") or {}).get("execution") or {})
    if bool(execution.get("requires_signature")):
        raise HTTPException(
            status_code=409,
            detail=(
                "This controlled workflow requires a validated digital signature, "
                "but trusted PDF signature validation is not configured"
            ),
        )

    revision = _controlled_target_revision(db, tenant, detail)
    try:
        source_inspection = await run_in_threadpool(_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc
    content = await read_bounded_pdf_upload(artifact)
    result, enriched_payload = await run_in_threadpool(
        process_completed_pdf,
        content,
        _submission_payload(payload_json),
        expected_source=source_inspection,
    )
    filename = artifact.filename or "completed-form.pdf"
    if "FLATTENED" not in filename.upper():
        filename = filename[:-4] + "_FLATTENED.pdf" if filename.lower().endswith(".pdf") else f"{filename}_FLATTENED.pdf"
    flattened_artifact = UploadFile(
        file=io.BytesIO(result.content),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )
    return await reader.submit_linked_resource(
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        request=request,
        artifact=flattened_artifact,
        payload_json=json.dumps(enriched_payload, separators=(",", ":"), sort_keys=True),
        db=db,
        current_user=current_user,
    )


__all__ = ["_enforce_reference_source_access", "router"]
