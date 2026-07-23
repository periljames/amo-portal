# backend/amodb/apps/rostering/commitments_router.py
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import commitments, services

router = APIRouter(prefix="/rostering", tags=["rostering"])


@router.get("/commitments", response_model=commitments.RosterCommitmentResponse)
def roster_commitments(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    user_id: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    can_view_team = workforce_permissions.any_permission(
        db,
        user=current_user,
        permissions=[
            workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
            workforce_permissions.PermissionCode.ROSTER_VIEW_ALL,
        ],
    )
    if not can_view_team:
        workforce_permissions.require_permission(
            db,
            user=current_user,
            permission=workforce_permissions.PermissionCode.ROSTER_VIEW_OWN,
        )
        user_id = [str(current_user.id)]

    try:
        return commitments.list_commitments(
            db,
            amo_id=services.effective_amo_id(current_user),
            from_date=from_date,
            to_date=to_date,
            user_ids=user_id or None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": str(exc),
                "error_code": "ROSTER_COMMITMENT_RANGE_INVALID",
                "field_errors": {},
                "conflicts": [],
                "retryable": False,
            },
        ) from exc
