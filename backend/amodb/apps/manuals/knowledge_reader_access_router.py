"""Precedence routes that authorize both sides of linked-document references."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.workspace_service import get_profile, require_manual_access
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import knowledge_reader_router as reader
from . import models
from .router_legacy import _tenant_by_slug


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
    return reader.linked_resource_detail(
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        db=db,
        current_user=current_user,
    )


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
    return await reader.submit_linked_resource(
        tenant_slug=tenant_slug,
        reference_id=reference_id,
        request=request,
        artifact=artifact,
        payload_json=payload_json,
        db=db,
        current_user=current_user,
    )


__all__ = ["_enforce_reference_source_access", "router"]
