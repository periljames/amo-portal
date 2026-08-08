from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import billing_auth
from amodb.database import get_db

from . import module_renewals


router = APIRouter(prefix="/commerce/self-service/modules", tags=["tenant-module-subscriptions"])


@router.post("/{module_code}/cancel")
def cancel_module_at_period_end(
    module_code: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(billing_auth.require_contract_manager),
):
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id or getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="A tenant billing context is required.")
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
