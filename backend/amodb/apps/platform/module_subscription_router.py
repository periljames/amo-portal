from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import module_renewals
from .module_commerce_router import _require_contract_authority, _tenant_id


router = APIRouter(prefix="/commerce/self-service/modules", tags=["tenant-module-subscriptions"])


@router.post("/{module_code}/cancel")
def cancel_module_at_period_end(
    module_code: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(user)
    _require_contract_authority(user)
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A cancellation reason is required.")
    try:
        return module_renewals.cancel_at_period_end(
            db,
            tenant_id=tenant_id,
            module_code=module_code,
            actor_user_id=str(user.id),
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
