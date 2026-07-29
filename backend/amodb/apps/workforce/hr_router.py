"""Canonical Workforce and HR workspace endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import hr_schemas, hr_service, permissions, schemas, services

router = APIRouter(prefix="/workforce/hr", tags=["workforce-hr"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _error(detail: str, *, code: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "error_code": code,
            "field_errors": {},
            "conflicts": [],
            "retryable": False,
        },
    )


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


@router.get("/people", response_model=hr_schemas.HrPeoplePage)
def hr_people(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    return hr_service.list_people_page(
        db,
        amo_id=_amo(current_user),
        page=page,
        page_size=page_size,
        search=search,
    )


@router.get("/work-patterns", response_model=list[schemas.WorkPatternRead])
def hr_work_patterns(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    return services.list_patterns(
        db,
        amo_id=_amo(current_user),
        include_inactive=include_inactive,
    )


@router.post(
    "/work-pattern-assignments",
    response_model=schemas.EmployeeWorkPatternAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def hr_create_work_pattern_assignment(
    payload: schemas.EmployeeWorkPatternAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    # Employee assignment is a Workforce record. Pattern template design remains
    # controlled by roster.manage_patterns; HR contract controllers can assign
    # an approved template to an employee with effective dates.
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
    )
    try:
        row = services.assign_pattern(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            payload=payload,
        )
        created_id = row.id
        db.commit()
        assignments = services.list_pattern_assignments(
            db,
            amo_id=_amo(current_user),
            user_id=row.user_id,
            pattern_id=row.work_pattern_id,
        )
        return next(item for item in assignments if item.id == created_id)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="HR_WORK_PATTERN_ASSIGNMENT_INVALID") from exc


@router.get("/overtime-requests", response_model=list[hr_schemas.HrOvertimeRequestRead])
def hr_overtime_requests(
    pending_only: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE
    )
    return hr_service.list_overtime_requests(
        db, amo_id=_amo(current_user), pending_only=pending_only, limit=limit
    )


@router.post(
    "/overtime-requests",
    response_model=hr_schemas.HrOvertimeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def hr_create_overtime_request(
    payload: schemas.OvertimeRequestCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    target_user_id = payload.user_id or current_user.id
    permission = (
        permissions.PermissionCode.OVERTIME_REQUEST
        if target_user_id == current_user.id
        else permissions.PermissionCode.OVERTIME_APPROVE
    )
    permissions.require_permission(db, user=current_user, permission=permission)
    try:
        row = hr_service.create_overtime_request(
            db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload
        )
        db.commit()
        db.refresh(row)
        return hr_service.serialize_overtime(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="HR_OVERTIME_REQUEST_INVALID") from exc


@router.post(
    "/overtime-requests/{request_id}/decision",
    response_model=hr_schemas.HrOvertimeRequestRead,
)
def hr_decide_overtime_request(
    request_id: str,
    payload: hr_schemas.HrOvertimeDecisionRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db, user=current_user, permission=permissions.PermissionCode.OVERTIME_APPROVE
    )
    if payload.stage == "HR":
        permissions.require_permission(
            db, user=current_user, permission=permissions.PermissionCode.ATTENDANCE_APPROVE
        )
    try:
        row = hr_service.decide_overtime(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            request_id=request_id,
            payload=payload,
        )
        db.commit()
        return hr_service.serialize_overtime(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="HR_OVERTIME_DECISION_INVALID", status_code=status.HTTP_409_CONFLICT) from exc
