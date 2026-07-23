from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from . import saas_models as models
from .tenant_saas_router import _job_payload, _tenant_scope, require_saas_admin


router = APIRouter(prefix="/tenant-saas", tags=["tenant-saas-administration"])


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str,
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user: account_models.User = Depends(require_saas_admin),
):
    scope_tenant_id = _tenant_scope(user, tenant_id)
    row = db.get(models.SaaSJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if scope_tenant_id and str(row.tenant_id or "") != scope_tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if not scope_tenant_id and not getattr(user, "is_superuser", False):
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(row)
