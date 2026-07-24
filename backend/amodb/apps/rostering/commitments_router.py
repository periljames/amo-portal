# backend/amodb/apps/rostering/commitments_router.py
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import models as workforce_models
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
    can_view_all = workforce_permissions.has_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_VIEW_ALL,
    )
    can_view_department = workforce_permissions.has_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
    )
    if not can_view_all and not can_view_department:
        workforce_permissions.require_permission(
            db,
            user=current_user,
            permission=workforce_permissions.PermissionCode.ROSTER_VIEW_OWN,
        )
        user_id = [str(current_user.id)]

    amo_id = services.effective_amo_id(current_user)
    eligible_query = db.query(workforce_models.EmploymentContract.user_id).join(
        account_models.User,
        account_models.User.id == workforce_models.EmploymentContract.user_id,
    ).filter(
        workforce_models.EmploymentContract.amo_id == amo_id,
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
        workforce_models.EmploymentContract.employment_status
        == workforce_models.EmploymentStatus.ACTIVE,
        workforce_models.EmploymentContract.effective_from <= to_date,
        or_(
            workforce_models.EmploymentContract.effective_to.is_(None),
            workforce_models.EmploymentContract.effective_to >= from_date,
        ),
    )

    if not can_view_all and can_view_department:
        department_id = getattr(current_user, "department_id", None)
        if department_id:
            eligible_query = eligible_query.filter(
                account_models.User.department_id == department_id,
            )
        else:
            eligible_query = eligible_query.filter(
                account_models.User.id == current_user.id,
            )

    if user_id:
        eligible_query = eligible_query.filter(
            workforce_models.EmploymentContract.user_id.in_(user_id),
        )
    eligible_user_ids = sorted({str(row[0]) for row in eligible_query.all()})

    try:
        return commitments.list_commitments(
            db,
            amo_id=amo_id,
            from_date=from_date,
            to_date=to_date,
            user_ids=eligible_user_ids or ["__none__"],
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
