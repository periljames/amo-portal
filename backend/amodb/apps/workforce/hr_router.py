"""Canonical Workforce and HR workspace endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import (
    hr_people_directory,
    hr_schemas,
    hr_service,
    retired_pattern_guard,
    permissions,
    schemas,
    services,
)

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


def _people_filters(
    *,
    search: str | None,
    department_id: str | None,
    role: str | None,
    position_title: str | None,
    contract_type: str | None,
    employment_status: str | None,
    base_station_id: str | None,
    group_id: str | None,
    readiness_state: str | None,
    contract_state: str | None,
    pattern_state: str | None,
    expires_within_days: int | None,
    sort_by: str,
    sort_dir: str,
) -> hr_schemas.HrPeopleFilterInput:
    try:
        return hr_schemas.HrPeopleFilterInput(
            search=search,
            department_id=department_id,
            role=role,
            position_title=position_title,
            contract_type=contract_type,
            employment_status=employment_status,
            base_station_id=base_station_id,
            group_id=group_id,
            readiness_state=readiness_state,
            contract_state=contract_state,
            pattern_state=pattern_state,
            expires_within_days=expires_within_days,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValueError as exc:
        raise _error(
            "One or more Workforce directory filters are invalid.",
            code="HR_PEOPLE_FILTER_INVALID",
        ) from exc


def _require_default_pattern_permissions(db: Session, user: account_models.User) -> None:
    for permission in (
        permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
        permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,
        permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
    ):
        permissions.require_permission(db, user=user, permission=permission)


@router.get("/dashboard", response_model=hr_schemas.HrDashboardResponse)
def hr_dashboard(
    people_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    return hr_service.dashboard_v2(
        db,
        amo_id=_amo(current_user),
        current_user=current_user,
        people_limit=people_limit,
    )


@router.get("/people", response_model=hr_schemas.HrPeoplePage)
def hr_people(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    search: str | None = Query(default=None, max_length=200),
    department_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    position_title: str | None = Query(default=None, max_length=255),
    contract_type: str | None = Query(default=None),
    employment_status: str | None = Query(default=None),
    base_station_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    readiness_state: str | None = Query(default=None),
    contract_state: str | None = Query(default=None),
    pattern_state: str | None = Query(default=None),
    expires_within_days: int | None = Query(default=None, ge=1, le=365),
    sort_by: str = Query(default="name"),
    sort_dir: str = Query(default="asc"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    filters = _people_filters(
        search=search,
        department_id=department_id,
        role=role,
        position_title=position_title,
        contract_type=contract_type,
        employment_status=employment_status,
        base_station_id=base_station_id,
        group_id=group_id,
        readiness_state=readiness_state,
        contract_state=contract_state,
        pattern_state=pattern_state,
        expires_within_days=expires_within_days,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return hr_people_directory.list_people_page(
        db,
        amo_id=_amo(current_user),
        page=page,
        page_size=page_size,
        filters=filters,
    )


@router.get("/people/facets", response_model=hr_schemas.HrPeopleFacets)
def hr_people_facets(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    return hr_people_directory.list_people_facets(db, amo_id=_amo(current_user))


@router.post(
    "/people/default-day-pattern/preview",
    response_model=hr_schemas.HrDefaultDayBatchPreview,
)
def hr_preview_default_day_pattern_batch(
    selection: hr_schemas.HrPeopleSelection,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_default_pattern_permissions(db, current_user)
    raise _error(
        retired_pattern_guard.RETIRED_DEFAULT_PATTERN_MESSAGE,
        code="HR_DEFAULT_DAY_PATTERN_RETIRED",
        status_code=status.HTTP_410_GONE,
    )


@router.post(
    "/people/default-day-pattern/apply",
    response_model=hr_schemas.HrDefaultDayBatchResult,
)
def hr_apply_default_day_pattern_batch(
    payload: hr_schemas.HrDefaultDayBatchApplyRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_default_pattern_permissions(db, current_user)
    raise _error(
        retired_pattern_guard.RETIRED_DEFAULT_PATTERN_MESSAGE,
        code="HR_DEFAULT_DAY_PATTERN_RETIRED",
        status_code=status.HTTP_410_GONE,
    )


@router.post("/people/export")
def hr_export_people(
    selection: hr_schemas.HrPeopleSelection,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    try:
        content = hr_people_directory.export_people_csv(
            db,
            amo_id=_amo(current_user),
            selection=selection,
        )
    except ValueError as exc:
        raise _error(str(exc), code="HR_PEOPLE_EXPORT_INVALID") from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=workforce-people.csv",
            "Cache-Control": "no-store",
        },
    )


@router.post("/default-day-pattern", response_model=hr_schemas.HrDefaultDayBootstrapResponse)
def hr_bootstrap_default_day_pattern(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Backward-compatible tenant-wide bootstrap used by existing clients."""
    _require_default_pattern_permissions(db, current_user)
    raise _error(
        retired_pattern_guard.RETIRED_DEFAULT_PATTERN_MESSAGE,
        code="HR_DEFAULT_DAY_PATTERN_RETIRED",
        status_code=status.HTTP_410_GONE,
    )


@router.get("/work-patterns", response_model=list[schemas.WorkPatternRead])
def hr_work_patterns(
    response: Response,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
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
    permissions.require_permission(
        db,
        user=current_user,
        permission=permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
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
        raise _error(
            str(exc),
            code="HR_OVERTIME_DECISION_INVALID",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
