from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db
from amodb.security import get_current_active_user

from . import saas_models


router = APIRouter(prefix="/commerce/self-service", tags=["tenant-module-payment"])


def _role(user: account_models.User) -> str:
    value = getattr(user, "role", None)
    return str(getattr(value, "value", value) or "").upper()


def _tenant_payment_user(user: account_models.User) -> str:
    if getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    if not bool(getattr(user, "is_amo_admin", False)) and _role(user) not in {"AMO_ADMIN", "FINANCE_MANAGER", "ACCOUNTS_OFFICER"}:
        raise HTTPException(status_code=403, detail="Authorised tenant finance role required.")
    return tenant_id


@router.get("/payment-jobs/{job_id}")
def payment_job_status(
    job_id: str,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_payment_user(user)
    row = db.get(saas_models.SaaSJob, job_id)
    if row is None or str(row.tenant_id or "") != tenant_id:
        raise HTTPException(status_code=404, detail="Payment job not found.")
    if str(row.job_type or "") not in {"PAYSTACK_INITIATE_PAYMENT", "MPESA_STK_PUSH", "PAYSTACK_WEBHOOK", "MPESA_CALLBACK"}:
        raise HTTPException(status_code=404, detail="Payment job not found.")
    return {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "result": row.result_json,
        "last_error": row.last_error,
        "attempt_count": row.attempt_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }
