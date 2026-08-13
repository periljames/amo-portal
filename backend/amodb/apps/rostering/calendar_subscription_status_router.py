from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import calendar_subscriptions, common

router = APIRouter(prefix="/rostering", tags=["rostering-control"])


class CalendarSubscriptionStatus(BaseModel):
    active: bool
    created_at: Optional[datetime] = None
    rotated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    refresh_interval_minutes: int = 60
    includes: list[str]


@router.get("/calendar/subscription/status", response_model=CalendarSubscriptionStatus)
def personal_calendar_subscription_status(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> CalendarSubscriptionStatus:
    """Return subscription state without creating or reactivating a bearer token."""

    workforce_permissions.require_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_VIEW_OWN,
    )
    amo_id = common.effective_amo_id(current_user)
    row = calendar_subscriptions.subscription_status(
        db,
        amo_id=amo_id,
        user_id=current_user.id,
    )
    return CalendarSubscriptionStatus(
        active=bool(row and row.revoked_at is None),
        created_at=getattr(row, "created_at", None),
        rotated_at=getattr(row, "rotated_at", None),
        revoked_at=getattr(row, "revoked_at", None),
        last_used_at=getattr(row, "last_used_at", None),
        includes=[
            "PUBLISHED_DUTY",
            "TRAINING",
            "QMS_AUDITS",
            "MAINTENANCE_TASKS",
            "AIRCRAFT_ALLOCATIONS",
        ],
    )
