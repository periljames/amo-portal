# backend/amodb/apps/workforce/router.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models, permissions, schemas, services

router = APIRouter(prefix="/workforce", tags=["workforce"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _error(
    detail: str,
    *,
    error_code: str = "WORKFORCE_VALIDATION_ERROR",
    status_code: int = status.HTTP_400_BAD_REQUEST,
    conflicts: Optional[list[dict]] = None,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "error_code": error_code,
            "field_errors": {},
            "conflicts": conflicts or [],
            "retryable": retryable,
        },
    )


def _commit(db: Session, row=None):
    try:
        db.commit()
        if row is not None:
            db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise _error("A workforce record with the same identity already exists.", error_code="WORKFORCE_CONFLICT", status_code=409) from exc


def _permission(db: Session, user: account_models.User, code: permissions.PermissionCode, *, department_id: Optional[str] = None, base_station_id: Optional[str] = None) -> None:
    permissions.require_permission(db, user=user, permission=code, department_id=department_id, base_station_id=base_station_id)


@router.get("/permissions/current", response_model=schemas.CurrentPermissionsRead)
def current_permissions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return schemas.CurrentPermissionsRead(user_id=current_user.id, permissions=permissions.permissions_for_user(db, user=current_user))


@router.get("/permission-grants", response_model=list[schemas.PermissionGrantRead])
def permission_grants(
    user_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    return services.list_permission_grants(db, amo_id=_amo(current_user), user_id=user_id)


@router.post("/permission-grants", response_model=schemas.PermissionGrantRead, status_code=status.HTTP_201_CREATED)
def create_permission_grant(
    payload: schemas.PermissionGrantCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    try:
        row = services.create_permission_grant(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        return _commit(db, row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="WORKFORCE_PERMISSION_GRANT_INVALID") from exc


@router.delete("/permission-grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission_grant(
    grant_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    row = db.query(models.WorkforcePermissionGrant).filter(models.WorkforcePermissionGrant.amo_id == _amo(current_user), models.WorkforcePermissionGrant.id == grant_id).first()
    if not row:
        raise _error("Permission grant not found", error_code="WORKFORCE_PERMISSION_GRANT_NOT_FOUND", status_code=404)
    services.delete_permission_grant(db, row=row, actor_user_id=current_user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Employment contracts
# ---------------------------------------------------------------------------


@router.get("/employment-contracts", response_model=schemas.Page[schemas.EmploymentContractRead])
def list_employment_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    employment_status: Optional[models.EmploymentStatus] = Query(default=None),
    base_station_id: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not permissions.has_permission(db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE):
        user_id = current_user.id
    return services.list_contracts(
        db,
        amo_id=_amo(current_user),
        page_number=page,
        page_size=page_size,
        user_id=user_id,
        employment_status=employment_status,
        base_station_id=base_station_id,
        search=search,
    )


@router.post("/employment-contracts", response_model=schemas.EmploymentContractRead, status_code=status.HTTP_201_CREATED)
def create_employment_contract(
    payload: schemas.EmploymentContractCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    try:
        row = services.create_contract(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_contract(services.get_contract(db, amo_id=_amo(current_user), contract_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="EMPLOYMENT_CONTRACT_INVALID", conflicts=[{"user_id": payload.user_id}]) from exc


@router.get("/employment-contracts/{contract_id}", response_model=schemas.EmploymentContractRead)
def get_employment_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_contract(db, amo_id=_amo(current_user), contract_id=contract_id)
    if not row:
        raise _error("Employment contract not found", error_code="EMPLOYMENT_CONTRACT_NOT_FOUND", status_code=404)
    if row.user_id != current_user.id:
        _permission(db, current_user, permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE)
    return services.serialize_contract(row)


@router.patch("/employment-contracts/{contract_id}", response_model=schemas.EmploymentContractRead)
def patch_employment_contract(
    contract_id: str,
    payload: schemas.EmploymentContractUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    row = services.get_contract(db, amo_id=_amo(current_user), contract_id=contract_id)
    if not row:
        raise _error("Employment contract not found", error_code="EMPLOYMENT_CONTRACT_NOT_FOUND", status_code=404)
    try:
        services.update_contract(db, row=row, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_contract(services.get_contract(db, amo_id=_amo(current_user), contract_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="EMPLOYMENT_CONTRACT_INVALID", conflicts=[{"contract_id": contract_id}]) from exc


# ---------------------------------------------------------------------------
# Work patterns
# ---------------------------------------------------------------------------


@router.get("/work-patterns", response_model=list[schemas.WorkPatternRead])
def list_work_patterns(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    return services.list_patterns(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.post("/work-patterns", response_model=schemas.WorkPatternRead, status_code=status.HTTP_201_CREATED)
def create_work_pattern(
    payload: schemas.WorkPatternCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    try:
        row = services.create_pattern(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_pattern(services.get_pattern(db, amo_id=_amo(current_user), pattern_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="WORK_PATTERN_INVALID") from exc


@router.get("/work-patterns/{pattern_id}", response_model=schemas.WorkPatternRead)
def get_work_pattern(
    pattern_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    row = services.get_pattern(db, amo_id=_amo(current_user), pattern_id=pattern_id)
    if not row:
        raise _error("Work pattern not found", error_code="WORK_PATTERN_NOT_FOUND", status_code=404)
    return services.serialize_pattern(row)


@router.patch("/work-patterns/{pattern_id}", response_model=schemas.WorkPatternRead)
def patch_work_pattern(
    pattern_id: str,
    payload: schemas.WorkPatternUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    row = services.get_pattern(db, amo_id=_amo(current_user), pattern_id=pattern_id)
    if not row:
        raise _error("Work pattern not found", error_code="WORK_PATTERN_NOT_FOUND", status_code=404)
    try:
        services.update_pattern(db, row=row, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_pattern(services.get_pattern(db, amo_id=_amo(current_user), pattern_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="WORK_PATTERN_INVALID") from exc


@router.get("/work-pattern-assignments", response_model=list[schemas.EmployeeWorkPatternAssignmentRead])
def list_work_pattern_assignments(
    user_id: Optional[str] = Query(default=None),
    pattern_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    return services.list_pattern_assignments(db, amo_id=_amo(current_user), user_id=user_id, pattern_id=pattern_id)


@router.post("/work-pattern-assignments", response_model=schemas.EmployeeWorkPatternAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_work_pattern_assignment(
    payload: schemas.EmployeeWorkPatternAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    try:
        row = services.assign_pattern(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.list_pattern_assignments(db, amo_id=_amo(current_user), user_id=row.user_id, pattern_id=row.work_pattern_id)[0]
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="WORK_PATTERN_ASSIGNMENT_INVALID") from exc


@router.post("/work-patterns/{pattern_id}/preview", response_model=schemas.PatternPreviewResponse)
def preview_work_pattern(
    pattern_id: str,
    payload: schemas.PatternPreviewRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    try:
        return services.preview_patterns(db, amo_id=_amo(current_user), payload=payload, pattern_id=pattern_id)
    except ValueError as exc:
        raise _error(str(exc), error_code="WORK_PATTERN_PREVIEW_INVALID") from exc


# ---------------------------------------------------------------------------
# Leave and availability
# ---------------------------------------------------------------------------


@router.get("/leave-types", response_model=list[schemas.LeaveTypeRead])
def list_leave_types(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    rows = services.list_leave_types(db, amo_id=_amo(current_user), include_inactive=include_inactive)
    db.commit()
    return rows


@router.post("/leave-types", response_model=schemas.LeaveTypeRead, status_code=status.HTTP_201_CREATED)
def create_leave_type(
    payload: schemas.LeaveTypeCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_MANAGE_BALANCES)
    try:
        return _commit(db, services.create_leave_type(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_TYPE_INVALID") from exc


@router.patch("/leave-types/{leave_type_id}", response_model=schemas.LeaveTypeRead)
def patch_leave_type(
    leave_type_id: str,
    payload: schemas.LeaveTypeUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_MANAGE_BALANCES)
    row = db.query(models.LeaveType).filter(models.LeaveType.amo_id == _amo(current_user), models.LeaveType.id == leave_type_id).first()
    if not row:
        raise _error("Leave type not found", error_code="LEAVE_TYPE_NOT_FOUND", status_code=404)
    services.update_leave_type(db, row=row, actor_user_id=current_user.id, payload=payload)
    return _commit(db, row)


@router.get("/leave-balances", response_model=list[schemas.LeaveBalanceRead])
def list_leave_balances(
    user_id: Optional[str] = Query(default=None),
    leave_year: Optional[int] = Query(default=None, ge=2000, le=2200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not permissions.has_permission(db, user=current_user, permission=permissions.PermissionCode.LEAVE_MANAGE_BALANCES):
        user_id = current_user.id
    return services.list_balances(db, amo_id=_amo(current_user), user_id=user_id, leave_year=leave_year)


@router.patch("/leave-balances/{balance_id}", response_model=schemas.LeaveBalanceRead)
def patch_leave_balance(
    balance_id: str,
    payload: schemas.LeaveBalanceUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_MANAGE_BALANCES)
    row = db.query(models.EmployeeLeaveBalance).options(
        selectinload(models.EmployeeLeaveBalance.user),
        selectinload(models.EmployeeLeaveBalance.leave_type),
    ).filter(models.EmployeeLeaveBalance.amo_id == _amo(current_user), models.EmployeeLeaveBalance.id == balance_id).first()
    if not row:
        raise _error("Leave balance not found", error_code="LEAVE_BALANCE_NOT_FOUND", status_code=404)
    services.update_balance(db, row=row, actor_user_id=current_user.id, payload=payload)
    _commit(db, row)
    return services.serialize_balance(row)


@router.get("/leave-requests", response_model=schemas.Page[schemas.LeaveRequestRead])
def list_leave_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    request_status: Optional[models.LeaveRequestStatus] = Query(default=None, alias="status"),
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not permissions.any_permission(db, user=current_user, permissions=[permissions.PermissionCode.LEAVE_REVIEW, permissions.PermissionCode.LEAVE_APPROVE]):
        user_id = current_user.id
        department_id = None
    return services.list_leave_requests(db, amo_id=_amo(current_user), page_number=page, page_size=page_size, user_id=user_id, department_id=department_id, request_status=request_status, from_date=from_date, to_date=to_date)


@router.post("/leave-requests", response_model=schemas.LeaveRequestRead, status_code=status.HTTP_201_CREATED)
def create_leave_request(
    payload: schemas.LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_REQUEST)
    try:
        row = services.create_leave_request(db, amo_id=_amo(current_user), actor=current_user, payload=payload)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_REQUEST_INVALID") from exc


@router.get("/leave-requests/{request_id}", response_model=schemas.LeaveRequestRead)
def get_leave_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    if row.user_id != current_user.id:
        _permission(db, current_user, permissions.PermissionCode.LEAVE_REVIEW, department_id=getattr(row.user, "department_id", None))
    return services.serialize_leave_request(db, row)


@router.patch("/leave-requests/{request_id}", response_model=schemas.LeaveRequestRead)
def patch_leave_request(
    request_id: str,
    payload: schemas.LeaveRequestUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.update_leave_request(db, row=row, actor=current_user, payload=payload)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_REQUEST_INVALID") from exc


@router.post("/leave-requests/{request_id}/submit", response_model=schemas.LeaveRequestRead)
def submit_leave_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.submit_leave_request(db, row=row, actor=current_user)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_SUBMIT_FAILED") from exc


@router.post("/leave-requests/{request_id}/supervisor-approve", response_model=schemas.LeaveRequestRead)
def supervisor_approve_leave(
    request_id: str,
    payload: schemas.WorkflowDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_REVIEW)
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.supervisor_approve_leave(db, row=row, actor=current_user, comment=payload.comment)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_SUPERVISOR_APPROVAL_FAILED") from exc


@router.post("/leave-requests/{request_id}/hr-approve", response_model=schemas.LeaveRequestRead)
def hr_approve_leave(
    request_id: str,
    payload: schemas.WorkflowDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_APPROVE)
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.hr_approve_leave(db, row=row, actor=current_user, comment=payload.comment)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_HR_APPROVAL_FAILED") from exc


@router.post("/leave-requests/{request_id}/reject", response_model=schemas.LeaveRequestRead)
def reject_leave(
    request_id: str,
    payload: schemas.WorkflowDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.LEAVE_REVIEW)
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.reject_leave(db, row=row, actor=current_user, reason=payload.reason or payload.comment)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_REJECTION_FAILED") from exc


@router.post("/leave-requests/{request_id}/cancel", response_model=schemas.LeaveRequestRead)
def cancel_leave(
    request_id: str,
    payload: schemas.WorkflowDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_leave_request(db, amo_id=_amo(current_user), request_id=request_id)
    if not row:
        raise _error("Leave request not found", error_code="LEAVE_REQUEST_NOT_FOUND", status_code=404)
    try:
        services.cancel_leave(db, row=row, actor=current_user, reason=payload.reason or payload.comment)
        _commit(db, row)
        return services.serialize_leave_request(db, services.get_leave_request(db, amo_id=_amo(current_user), request_id=row.id))
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="LEAVE_CANCELLATION_FAILED") from exc


@router.get("/availability-events", response_model=list[schemas.AvailabilityEventRead])
def list_availability_events(
    from_dt: datetime = Query(..., alias="from"),
    to_dt: datetime = Query(..., alias="to"),
    user_id: Optional[str] = Query(default=None),
    blocking: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if user_id and user_id != current_user.id:
        _permission(db, current_user, permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    elif not user_id and not permissions.has_permission(db, user=current_user, permission=permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT):
        user_id = current_user.id
    return services.list_availability(db, amo_id=_amo(current_user), from_dt=from_dt, to_dt=to_dt, user_id=user_id, blocking=blocking)


@router.post("/availability-events", response_model=schemas.AvailabilityEventRead, status_code=status.HTTP_201_CREATED)
def create_availability_event(
    payload: schemas.AvailabilityEventCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_MANAGE)
    try:
        row = services.create_availability(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        row = db.query(models.EmployeeAvailabilityEvent).options(selectinload(models.EmployeeAvailabilityEvent.user)).filter(models.EmployeeAvailabilityEvent.id == row.id).first()
        return services.serialize_availability(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="AVAILABILITY_EVENT_INVALID") from exc


@router.patch("/availability-events/{event_id}", response_model=schemas.AvailabilityEventRead)
def patch_availability_event(
    event_id: str,
    payload: schemas.AvailabilityEventUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_MANAGE)
    row = db.query(models.EmployeeAvailabilityEvent).options(selectinload(models.EmployeeAvailabilityEvent.user)).filter(models.EmployeeAvailabilityEvent.amo_id == _amo(current_user), models.EmployeeAvailabilityEvent.id == event_id).first()
    if not row:
        raise _error("Availability event not found", error_code="AVAILABILITY_EVENT_NOT_FOUND", status_code=404)
    try:
        services.update_availability(db, row=row, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_availability(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="AVAILABILITY_EVENT_INVALID") from exc


@router.delete("/availability-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_MANAGE)
    row = db.query(models.EmployeeAvailabilityEvent).filter(models.EmployeeAvailabilityEvent.amo_id == _amo(current_user), models.EmployeeAvailabilityEvent.id == event_id).first()
    if not row:
        raise _error("Availability event not found", error_code="AVAILABILITY_EVENT_NOT_FOUND", status_code=404)
    try:
        services.delete_availability(db, row=row, actor_user_id=current_user.id)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="AVAILABILITY_EVENT_DELETE_FAILED") from exc


# ---------------------------------------------------------------------------
# Public holidays, attendance, timesheets and payroll
# ---------------------------------------------------------------------------


@router.get("/public-holidays", response_model=list[schemas.PublicHolidayRead])
def list_public_holidays(
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_public_holidays(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date)


@router.post("/public-holiday-calendars", status_code=status.HTTP_201_CREATED)
def create_public_holiday_calendar(
    payload: schemas.PublicHolidayCalendarCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    try:
        row = services.create_holiday_calendar(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return {"id": row.id, "code": row.code, "name": row.name}
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="PUBLIC_HOLIDAY_CALENDAR_INVALID") from exc


@router.post("/public-holidays", response_model=schemas.PublicHolidayRead, status_code=status.HTTP_201_CREATED)
def create_public_holiday(
    payload: schemas.PublicHolidayCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    try:
        row = services.create_public_holiday(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.list_public_holidays(db, amo_id=_amo(current_user), from_date=row.holiday_date, to_date=row.holiday_date)[0]
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="PUBLIC_HOLIDAY_INVALID") from exc


@router.get("/attendance-events", response_model=schemas.AttendanceSummaryRead)
def get_attendance_events(
    user_id: Optional[str] = Query(default=None),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    target_user_id = user_id or current_user.id
    if target_user_id != current_user.id:
        _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_MANAGE)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == _amo(current_user)).first()
    return services.attendance_summary(db, amo_id=_amo(current_user), user_id=target_user_id, from_date=from_date, to_date=to_date, timezone_name=getattr(amo, "time_zone", None) or "UTC")


@router.post("/attendance-events", response_model=schemas.AttendanceEventRead, status_code=status.HTTP_201_CREATED)
def create_attendance_event(
    payload: schemas.AttendanceEventCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_VIEW_OWN)
    try:
        row = services.create_attendance_event(db, amo_id=_amo(current_user), actor=current_user, payload=payload)
        _commit(db, row)
        row = db.query(models.AttendanceEvent).options(selectinload(models.AttendanceEvent.user)).filter(models.AttendanceEvent.id == row.id).first()
        return services.serialize_attendance(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="ATTENDANCE_EVENT_INVALID") from exc


@router.get("/timesheets", response_model=schemas.Page[schemas.TimesheetRead])
def list_timesheets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    sheet_status: Optional[models.TimesheetStatus] = Query(default=None, alias="status"),
    period_start: Optional[date] = Query(default=None, alias="from"),
    period_end: Optional[date] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not permissions.has_permission(db, user=current_user, permission=permissions.PermissionCode.TIMESHEET_APPROVE):
        user_id = current_user.id
    return services.list_timesheets(db, amo_id=_amo(current_user), page_number=page, page_size=page_size, user_id=user_id, sheet_status=sheet_status, period_start=period_start, period_end=period_end)


@router.post("/timesheets/generate", response_model=list[schemas.TimesheetRead])
def generate_timesheets(
    payload: schemas.TimesheetGenerateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_MANAGE)
    try:
        rows = services.generate_timesheets(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        db.commit()
        ids = [row.id for row in rows]
        refreshed = db.query(models.Timesheet).options(selectinload(models.Timesheet.user), selectinload(models.Timesheet.lines)).filter(models.Timesheet.id.in_(ids)).order_by(models.Timesheet.user_id.asc()).all()
        for row in refreshed:
            row._active_contract = services.active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.period_end)
        return [services.serialize_timesheet(row) for row in refreshed]
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="TIMESHEET_GENERATION_FAILED") from exc


@router.post("/timesheets/{timesheet_id}/submit", response_model=schemas.TimesheetRead)
def submit_timesheet(
    timesheet_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = db.query(models.Timesheet).options(selectinload(models.Timesheet.user), selectinload(models.Timesheet.lines)).filter(models.Timesheet.amo_id == _amo(current_user), models.Timesheet.id == timesheet_id).first()
    if not row:
        raise _error("Timesheet not found", error_code="TIMESHEET_NOT_FOUND", status_code=404)
    try:
        services.submit_timesheet(db, row=row, actor=current_user)
        _commit(db, row)
        row._active_contract = services.active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.period_end)
        return services.serialize_timesheet(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="TIMESHEET_SUBMIT_FAILED") from exc


@router.post("/timesheets/{timesheet_id}/approve", response_model=schemas.TimesheetRead)
def approve_timesheet(
    timesheet_id: str,
    payload: schemas.TimesheetApprovalRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.TIMESHEET_APPROVE)
    if payload.stage == models.LeaveApprovalStage.HR:
        _permission(db, current_user, permissions.PermissionCode.ATTENDANCE_APPROVE)
    row = db.query(models.Timesheet).options(selectinload(models.Timesheet.user), selectinload(models.Timesheet.lines)).filter(models.Timesheet.amo_id == _amo(current_user), models.Timesheet.id == timesheet_id).first()
    if not row:
        raise _error("Timesheet not found", error_code="TIMESHEET_NOT_FOUND", status_code=404)
    try:
        services.approve_timesheet(db, row=row, actor=current_user, payload=payload)
        _commit(db, row)
        row._active_contract = services.active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.period_end)
        return services.serialize_timesheet(row)
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), error_code="TIMESHEET_APPROVAL_FAILED") from exc


@router.get("/payroll-export", response_model=list[schemas.PayrollExportRow])
def payroll_export(
    period_start: Optional[date] = Query(default=None, alias="from"),
    period_end: Optional[date] = Query(default=None, alias="to"),
    format: str = Query(default="json", pattern=r"^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _permission(db, current_user, permissions.PermissionCode.PAYROLL_EXPORT)
    rows = services.payroll_export_rows(db, amo_id=_amo(current_user), period_start=period_start, period_end=period_end)
    if format == "csv":
        for row in db.query(models.Timesheet).filter(models.Timesheet.amo_id == _amo(current_user), models.Timesheet.id.in_([item.timesheet_id for item in rows])).all():
            row.status = models.TimesheetStatus.EXPORTED
            row.exported_at = services._utcnow()
            row.updated_by_user_id = current_user.id
            db.add(row)
            services._audit(db, amo_id=row.amo_id, actor_user_id=current_user.id, entity_type="Timesheet", entity_id=row.id, action="payroll_export", after={"status": "EXPORTED"}, critical=True)
        db.commit()
        return PlainTextResponse(
            services.payroll_export_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=workforce-payroll-export.csv"},
        )
    return rows


@router.get("/planner-preferences", response_model=schemas.PlannerPreferenceRead)
def get_planner_preferences(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_or_create_planner_preference(db, amo_id=_amo(current_user), user_id=current_user.id)
    db.commit()
    return services.serialize_planner_preference(row)


@router.patch("/planner-preferences", response_model=schemas.PlannerPreferenceRead)
def patch_planner_preferences(
    payload: schemas.PlannerPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = services.get_or_create_planner_preference(db, amo_id=_amo(current_user), user_id=current_user.id)
    if payload.default_base_station_id:
        try:
            services._require_base(db, amo_id=_amo(current_user), base_station_id=payload.default_base_station_id)
        except ValueError as exc:
            raise _error(str(exc), error_code="PLANNER_PREFERENCE_INVALID") from exc
    services.update_planner_preference(db, row=row, payload=payload)
    _commit(db, row)
    return services.serialize_planner_preference(row)
