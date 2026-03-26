from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import require_roles
from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db

from . import schemas, services


router = APIRouter(
    tags=["audit"],
    dependencies=[Depends(require_module("quality"))],
)

# Canonical listing endpoint. The equivalent GET /audit/ in router.py is kept
# only for POST (create). Do not add further GET routes to router.py.
@router.get("/audit-events", response_model=List[schemas.AuditEventRead])
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
