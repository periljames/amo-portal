from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import billing_auth
from amodb.database import get_read_db

from . import saas_models


router = APIRouter(prefix="/commerce/self-service", tags=["tenant-module-payment"])


@router.get("/payment-jobs/{job_id}")
def payment_job_status(
    job_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(billing_auth.require_billing_reader),
):
    tenant_id = str(getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None) or "").strip()
    if not tenant_id or getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="A tenant billing context is required.")
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
