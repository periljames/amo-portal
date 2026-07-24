from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from .audit_lifecycle import _create_checklist_version, _create_report_draft
from .audit_lifecycle_schemas import QualityAuditSafeOut
from .router import _current_amo_id, _get_audit_for_amo, _serialize_audit, router


_extension_router = APIRouter(
    prefix="/quality",
    tags=["Quality / audit lifecycle compatibility"],
    dependencies=[Depends(require_module("quality"))],
)


@_extension_router.post("/audits/{audit_id}/checklist", response_model=QualityAuditSafeOut)
def legacy_upload_checklist_with_safe_audit_response(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Retain the historic QMSAuditOut-shaped response while versioning the file."""

    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    existing_versions = _create_checklist_version.__globals__["_latest_checklist_versions"](db, audit.id)
    _create_checklist_version(
        audit=audit,
        current_user=current_user,
        db=db,
        request=request,
        file=file,
        lifecycle_status="COMMITTED" if existing_versions else "SOURCE",
        source_type="COMPATIBILITY_SAVE",
        fillable="UNKNOWN",
        field_count=None,
    )
    db.refresh(audit)
    return _serialize_audit(audit, db)


@_extension_router.post("/audits/{audit_id}/report", response_model=QualityAuditSafeOut)
def legacy_upload_report_with_safe_audit_response(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Retain the historic QMSAuditOut-shaped response while creating a draft."""

    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _create_report_draft(
        audit=audit,
        current_user=current_user,
        db=db,
        request=request,
        file=file,
    )
    db.refresh(audit)
    return _serialize_audit(audit, db)


_REPLACED = {
    ("/quality/audits/{audit_id}/checklist", "POST"),
    ("/quality/audits/{audit_id}/report", "POST"),
}
router.routes[:] = [
    route
    for route in router.routes
    if not any(
        str(getattr(route, "path", "")) == path
        and method in (getattr(route, "methods", None) or set())
        for path, method in _REPLACED
    )
]
router.routes[0:0] = list(_extension_router.routes)
