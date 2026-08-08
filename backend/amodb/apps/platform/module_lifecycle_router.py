from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .module_renewals import cancel_at_period_end


router = APIRouter(prefix="/commerce/self-service", tags=["tenant-module-lifecycle"])


def _role(user: account_models.User) -> str:
    value = getattr(user, "role", None)
    return str(getattr(value, "value", value) or "").upper()


def _contract_tenant(user: account_models.User) -> str:
    if getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    if not bool(getattr(user, "is_amo_admin", False)) and _role(user) not in {"AMO_ADMIN", "FINANCE_MANAGER"}:
        raise HTTPException(status_code=403, detail="AMO administrator or Finance Manager authority is required.")
    return tenant_id


@router.post("/modules/{module_code}/cancel-at-period-end")
def cancel_module(
    module_code: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _contract_tenant(user)
    try:
        return cancel_at_period_end(
            db,
            tenant_id=tenant_id,
            module_code=module_code,
            actor_user_id=str(user.id),
            reason=str(payload.get("reason") or "").strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
