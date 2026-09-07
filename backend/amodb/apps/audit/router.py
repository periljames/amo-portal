from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user
from amodb.apps.accounts.admin_profile_guard import require_active_admin_profile_or_roles
from amodb.apps.accounts.models import User
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
    action: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_admin_profile_or_roles("QUALITY_MANAGER")),
):
    limit_value = int(getattr(limit, "default", limit))
    offset_value = int(getattr(offset, "default", offset))
    return services.list_audit_events(
        db,
        amo_id=current_user.amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        start=start,
        end=end,
        limit=limit_value,
        offset=offset_value,
    )


@router.post(
    "/",
    status_code=status.HTTP_410_GONE,
    summary="Retired client-authored audit event endpoint",
)
def create_audit_event(
    payload: schemas.AuditEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Client-authored audit events are retired. Auditable events are written only by the "
            "server workflow that owns the affected record."
        ),
    )
