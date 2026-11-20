from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.apps.accounts.admin_profile_guard import require_active_admin_profile_or_roles
from amodb.apps.accounts.models import User
from amodb.database import get_db

from . import models, schemas


router = APIRouter(
    tags=["notifications"],
    dependencies=[Depends(require_module("quality"))],
)


@router.get("/email-logs", response_model=List[schemas.EmailLogRead])
def list_email_logs(
    status: Optional[models.EmailStatus] = None,
    template_key: Optional[str] = None,
    recipient: Optional[str] = None,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(51, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_admin_profile_or_roles("QUALITY_MANAGER")),
):
    qs = db.query(models.EmailLog).filter(models.EmailLog.amo_id == current_user.amo_id)
    if status:
        qs = qs.filter(models.EmailLog.status == status)
    if template_key:
        qs = qs.filter(models.EmailLog.template_key == template_key)
    if recipient:
        qs = qs.filter(models.EmailLog.recipient.ilike(f"%{recipient}%"))
    if start:
        qs = qs.filter(models.EmailLog.created_at >= start)
    if end:
        qs = qs.filter(models.EmailLog.created_at <= end)
    # Bound the admin ledger without weakening its tenant/role controls.
    # Stable ordering makes pagination deterministic when timestamps tie.
    return qs.order_by(models.EmailLog.created_at.desc(), models.EmailLog.id.desc()).offset(offset).limit(limit).all()
