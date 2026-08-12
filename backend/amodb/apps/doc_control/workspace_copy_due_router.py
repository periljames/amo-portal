from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import workspace_schemas as schemas
from .workspace_copy_router import register_controlled_copy as _create_copy
from .workspace_service import require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Controlled Copy Due Dates"])


def _default_due_days(tenant) -> int:
    settings = dict(tenant.settings_json or {})
    admin = settings.get("document_control_admin")
    admin_payload = dict(admin) if isinstance(admin, dict) else {}
    policy = admin_payload.get("physical_copy_policy")
    policy_payload = dict(policy) if isinstance(policy, dict) else {}
    try:
        days = int(policy_payload.get("default_due_days", 30))
    except (TypeError, ValueError):
        days = 30
    return max(1, min(days, 3650))


@router.post(
    "/t/{tenant_slug}/controlled-copies",
    include_in_schema=False,
)
def create_controlled_copy_with_due_policy(
    tenant_slug: str,
    payload: schemas.ControlledCopyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Create a numbered copy with an authoritative return/recall due date.

    Controllers may supply an explicit due date. When they do not, the server
    derives it from the tenant's governed Document Control physical-copy policy.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    if not payload.due_back_at:
        payload = payload.model_copy(
            update={"due_back_at": utcnow() + timedelta(days=_default_due_days(tenant))}
        )
    return _create_copy(
        tenant_slug=tenant_slug,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
