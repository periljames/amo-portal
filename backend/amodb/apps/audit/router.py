from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db

from . import schemas, services


router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_module("quality"))],
)


@router.get("/", response_model=List[schemas.AuditEventRead])
def list_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.QUALITY_MANAGER,
            AccountRole.SUPERUSER,
        )
    ),
):
    return services.list_audit_events(
        db,
        amo_id=current_user.amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        start=start,
        end=end,
    )


@router.post(
    "/",
    response_model=schemas.AuditEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_audit_event(
    payload: schemas.AuditEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    event = services.create_audit_event(db, amo_id=current_user.amo_id, data=payload)
    db.commit()
    db.refresh(event)
    return event
