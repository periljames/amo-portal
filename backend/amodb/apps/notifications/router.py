from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import require_roles
from amodb.apps.accounts.models import AccountRole, User
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
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.QUALITY_MANAGER,
            AccountRole.SUPERUSER,
        )
    ),
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
    return qs.order_by(models.EmailLog.created_at.desc()).all()
