from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
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
    action: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
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
        action=action,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
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
    event = services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=payload.actor_user_id or current_user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        action=payload.action,
        before=payload.before,
        after=payload.after,
        correlation_id=payload.correlation_id,
        metadata=payload.metadata,
        critical=False,
    )
    if event is None:
        raise HTTPException(status_code=500, detail="Failed to record audit event")
    try:
        db.commit()
        db.refresh(event)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error persisting audit event") from exc
    return event
