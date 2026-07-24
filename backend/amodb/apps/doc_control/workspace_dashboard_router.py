from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .workspace_router import dashboard as _get_full_dashboard
from .workspace_service import is_control_user


router = APIRouter(prefix="/workspace", tags=["Document Control Dashboard"])


@router.get("/t/{tenant_slug}/dashboard", include_in_schema=False)
def get_role_appropriate_dashboard(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return operational metrics only to Document Control personnel."""
    payload = _get_full_dashboard(
        tenant_slug=tenant_slug,
        db=db,
        current_user=current_user,
    )
    if is_control_user(current_user):
        return payload

    source_metrics = dict(payload.get("metrics") or {})
    public_metrics = {
        key: 0
        for key in source_metrics
    }
    public_metrics["document_records"] = int(source_metrics.get("document_records", 0))
    public_metrics["revision_records"] = int(source_metrics.get("revision_records", 0))
    public_metrics["effective_publications"] = int(
        source_metrics.get("effective_publications", 0)
    )
    return {
        "default_workspace": "LIBRARY",
        "capabilities": {"read": True, "control": False, "approve": False},
        "metrics": public_metrics,
        "recent_activity": [],
    }
