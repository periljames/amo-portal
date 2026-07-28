"""Canonical Workforce and HR workspace endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import hr_schemas, hr_service, permissions, services

router = APIRouter(prefix="/workforce/hr", tags=["workforce-hr"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


@router.get("/dashboard", response_model=hr_schemas.HrDashboardResponse)
def hr_dashboard(
    people_limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    return hr_service.dashboard(
        db,
        amo_id=_amo(current_user),
        current_user=current_user,
        people_limit=people_limit,
    )
