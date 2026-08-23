from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.knowledge_indexer import index_revision_background
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import core_router as core
from .pdf_reader_precompute import precompute_pdf_reader_assets


router = APIRouter(prefix="/manuals", tags=["Manual Upload RBAC"])


def _require_upload_scope(
    db: Session,
    *,
    tenant_slug: str,
    current_user: account_models.User,
) -> None:
    core._require_manual_control_user(current_user)
    tenant = core._tenant_by_slug(db, tenant_slug)
    if (
        not getattr(current_user, "is_superuser", False)
        and str(current_user.amo_id or "") != str(tenant.amo_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="The requested tenant is outside the active AMO context",
        )


@router.post("/t/{tenant_slug}/upload-docx/preview", include_in_schema=False)
async def preview_docx_upload_guarded(
    tenant_slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_upload_scope(db, tenant_slug=tenant_slug, current_user=current_user)
    return await core.preview_docx_upload(
        tenant_slug=tenant_slug,
        file=file,
        db=db,
        current_user=current_user,
    )


@router.post("/t/{tenant_slug}/upload-pdf/preview", include_in_schema=False)
async def preview_pdf_upload_guarded(
    tenant_slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_upload_scope(db, tenant_slug=tenant_slug, current_user=current_user)
    return await core.preview_pdf_upload(
        tenant_slug=tenant_slug,
        file=file,
        db=db,
        current_user=current_user,
    )


@router.post("/t/{tenant_slug}/upload-docx", include_in_schema=False)
async def upload_docx_revision_guarded(
    tenant_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Form(...),
    title: str = Form(...),
    rev_number: str = Form(...),
    manual_type: str = Form("GENERAL"),
    owner_role: str = Form("Library"),
    issue_number: str = Form(""),
    effective_date: str | None = Form(None),
    change_log: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_upload_scope(db, tenant_slug=tenant_slug, current_user=current_user)
    result = await core.upload_docx_revision(
        tenant_slug=tenant_slug,
        request=request,
        code=code,
        title=title,
        rev_number=rev_number,
        manual_type=manual_type,
        owner_role=owner_role,
        issue_number=issue_number,
        effective_date=effective_date,
        change_log=change_log,
        file=file,
        db=db,
        current_user=current_user,
    )
    background_tasks.add_task(index_revision_background, result["revision_id"])
    return {**result, "reference_index_status": "PENDING"}


@router.post("/t/{tenant_slug}/upload-pdf", include_in_schema=False)
async def upload_pdf_revision_guarded(
    tenant_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Form(...),
    title: str = Form(...),
    rev_number: str = Form(...),
    manual_type: str = Form("GENERAL"),
    owner_role: str = Form("Library"),
    issue_number: str = Form(""),
    effective_date: str | None = Form(None),
    change_log: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_upload_scope(db, tenant_slug=tenant_slug, current_user=current_user)
    result = await core.upload_pdf_revision(
        tenant_slug=tenant_slug,
        request=request,
        code=code,
        title=title,
        rev_number=rev_number,
        manual_type=manual_type,
        owner_role=owner_role,
        issue_number=issue_number,
        effective_date=effective_date,
        change_log=change_log,
        file=file,
        db=db,
        current_user=current_user,
    )
    revision_id = result["revision_id"]
    # Capability inspection and any script-disabled derivative are materialized
    # while the uploaded revision is being indexed, not when a reader opens it.
    background_tasks.add_task(precompute_pdf_reader_assets, revision_id)
    background_tasks.add_task(index_revision_background, revision_id)
    return {
        **result,
        "reference_index_status": "PENDING",
        "pdf_reader_precompute_status": "PENDING",
    }
