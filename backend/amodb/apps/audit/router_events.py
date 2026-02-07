from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
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


@router.get("/audit-events", response_model=List[schemas.AuditEventRead])
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
