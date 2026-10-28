"""Tenant-gated Office reading rendition status, retry and human verification."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.workspace_service import (
    audit, can_read_manual, get_manual, get_profile, get_revision,
    require_control_user, resolve_tenant,
)
from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models
from .office_layout import precompute_office_layout_assets, office_layout_pdf_path
from .office_rendition import rendition_payload, now

router = APIRouter(prefix="/manuals", tags=["Office rendition"])


class VerifyRendition(BaseModel):
    expected_pdf_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")
    note: str = Field(min_length=8, max_length=2000)


def _context(db, tenant_slug, manual_id, revision_id, user):
    tenant = resolve_tenant(db, tenant_slug, user)
    manual = get_manual(db, tenant, manual_id)
    revision = get_revision(db, manual, revision_id)
    return tenant, manual, revision


def _office_source(revision):
    value = str(getattr(revision.source_type_enum, "value", revision.source_type_enum) or "").upper()
    if value not in {"DOCX", "DOC", "ODT", "RTF"}:
        raise HTTPException(status_code=409, detail="The selected revision is not an Office document")


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/layout-status")
def layout_status(
    tenant_slug: str, manual_id: str, revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant, _manual, revision = _context(db, tenant_slug, manual_id, revision_id, user)
    if not can_read_manual(user, get_profile(db, tenant, manual_id)):
        raise HTTPException(status_code=403, detail="Document access denied")
    _office_source(revision)
    return rendition_payload(db, revision) or {"status": "QUEUED", "attempts": 0}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/layout-retry", status_code=202)
def retry_layout(
    tenant_slug: str, manual_id: str, revision_id: str,
    request: Request, background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant, _manual, revision = _context(db, tenant_slug, manual_id, revision_id, user)
    _office_source(revision)
    state = rendition_payload(db, revision)
    if state.get("status") == "PROCESSING":
        return {"status": "PROCESSING"}
    if state.get("status") in {"READY", "REVIEW_REQUIRED"}:
        raise HTTPException(status_code=409, detail="The rendition already exists; verify it or raise a controlled correction.")
    if not revision.source_storage_path or not Path(revision.source_storage_path).is_file():
        raise HTTPException(status_code=404, detail="The original Office source is unavailable")
    audit(db, tenant, request, "document.rendition.retry_requested", "manual_revision", revision.id, {"previous_status": state.get("status")})
    db.commit()
    background_tasks.add_task(precompute_office_layout_assets, revision.id)
    return {"status": "QUEUED"}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/layout-verify")
def verify_layout(
    tenant_slug: str, manual_id: str, revision_id: str,
    payload: VerifyRendition, request: Request,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant, _manual, revision = _context(db, tenant_slug, manual_id, revision_id, user)
    _office_source(revision)
    status = rendition_payload(db, revision)
    if status.get("status") not in {"READY", "REVIEW_REQUIRED"}:
        raise HTTPException(status_code=409, detail="No valid Office PDF rendition is available for verification")
    if status.get("pdf_sha256") != payload.expected_pdf_sha256.lower():
        raise HTTPException(status_code=409, detail="The PDF rendition changed; reload before verifying")
    row = db.query(models.ManualRendition).filter(
        models.ManualRendition.revision_id == revision.id,
        models.ManualRendition.rendition_type == "PDF",
    ).one()
    row.verified_by = str(user.id)
    row.verified_at = now()
    row.verification_note = payload.note.strip()
    audit(db, tenant, request, "document.rendition.verified", "manual_revision", revision.id, {
        "source_sha256": row.source_sha256, "pdf_sha256": row.pdf_sha256, "note": row.verification_note,
    })
    db.commit()
    return rendition_payload(db, revision)
