"""Access-filtered hierarchy endpoints registered ahead of compatibility routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.router_legacy import _tenant_by_slug
from amodb.database import get_db
from amodb.security import get_current_active_user

from .knowledge_service import hierarchy_payload
from .workspace_service import is_control_user, resolve_tenant


workspace_tree_router = APIRouter(prefix="/workspace", tags=["Document Control Knowledge Graph"])
publication_tree_router = APIRouter(prefix="/manuals", tags=["Publications Knowledge Graph"])


@workspace_tree_router.get("/t/{tenant_slug}/knowledge/tree")
def get_access_filtered_knowledge_tree(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    payload = hierarchy_payload(
        db,
        manual_tenant=tenant,
        actor_id=current_user.id if is_control_user(current_user) else None,
        user=current_user,
    )
    db.commit()
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


@publication_tree_router.get("/t/{tenant_slug}/knowledge-tree")
def get_access_filtered_publication_tree(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant: manual_models.Tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The requested hierarchy is outside the active AMO")
    payload = hierarchy_payload(
        db,
        manual_tenant=tenant,
        actor_id=current_user.id if is_control_user(current_user) else None,
        user=current_user,
    )
    db.commit()
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


__all__ = ["publication_tree_router", "workspace_tree_router"]
