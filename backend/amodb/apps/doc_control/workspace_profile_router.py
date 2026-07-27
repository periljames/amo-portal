from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import workspace_schemas as schemas
from .workspace_router import upsert_profile as _upsert_profile
from .workspace_service import active_tenant_users, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Profile"])


@router.put(
    "/t/{tenant_slug}/documents/{manual_id}/profile",
    include_in_schema=False,
)
def upsert_profile_with_tenant_owner_guard(
    tenant_slug: str,
    manual_id: str,
    payload: schemas.ProfileUpsert,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    if payload.owner_user_id:
        active_tenant_users(db, tenant, [payload.owner_user_id])
    return _upsert_profile(
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
