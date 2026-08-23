"""Access-filtered, read-only hierarchy endpoints registered first."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.core_router import _tenant_by_slug
from amodb.database import get_db
from amodb.security import get_current_active_user

from .knowledge_tree_reader import read_only_hierarchy_payload, read_only_node_connections
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
    payload = read_only_hierarchy_payload(
        db,
        manual_tenant=tenant,
        user=current_user,
    )
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


@workspace_tree_router.get("/t/{tenant_slug}/knowledge/nodes/{node_id}/connections")
def get_access_filtered_node_connections(
    tenant_slug: str,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    payload = read_only_node_connections(
        db,
        manual_tenant=tenant,
        user=current_user,
        node_id=node_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Hierarchy node not found or not visible")
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
    payload = read_only_hierarchy_payload(
        db,
        manual_tenant=tenant,
        user=current_user,
    )
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


__all__ = ["publication_tree_router", "workspace_tree_router"]
