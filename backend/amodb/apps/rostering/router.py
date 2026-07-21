# backend/amodb/apps/rostering/router.py
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import exports, models, schemas, services

router = APIRouter(prefix="/rostering", tags=["rostering"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _error(
    detail: str,
    *,
    error_code: str = "ROSTER_VALIDATION_ERROR",
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


def _translate(exc: Exception, *, default_code: str) -> HTTPException:
    message = str(exc)
    if isinstance(exc, RuntimeError) and message.startswith("ROSTER_VERSION_REVISION_CONFLICT:"):
        current = int(message.rsplit(":", 1)[-1])
        return _error(
            "Roster version changed since it was loaded. Refresh before retrying.",
            error_code="ROSTER_VERSION_REVISION_CONFLICT",
            status_code=409,
            conflicts=[{"current_state_revision": current}],
            retryable=True,
        )
    if isinstance(exc, RuntimeError) and message.startswith("ROSTER_ASSIGNMENT_REVISION_CONFLICT:"):
        current = int(message.rsplit(":", 1)[-1])
        return _error(
            "Roster assignment changed since it was loaded. Refresh before retrying.",
            error_code="ROSTER_ASSIGNMENT_REVISION_CONFLICT",
            status_code=409,
            conflicts=[{"current_state_revision": current}],
            retryable=True,
        )
    return _error(message, error_code=default_code)


def _commit(db: Session, row=None):
    try:
        db.commit()
        if row is not None:
            db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            "A roster record conflicts with an existing record.",
            error_code="ROSTER_DATABASE_CONFLICT",
            status_code=409,
        ) from exc


def _require(
    db: Session,
    user: account_models.User,
    permission: workforce_permissions.PermissionCode,
    *,
    department_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=permission,
        department_id=department_id,
        base_station_id=base_station_id,
    )


def _version_or_404(db: Session, *, amo_id: str, version_id: str, lock: bool = False) -> models.RosterVersion:
    row = services.get_version(db, amo_id=amo_id, version_id=version_id, lock=lock)
    if not row:
        raise _error("Roster version not found", error_code="ROSTER_VERSION_NOT_FOUND", status_code=404)
    return row


def _assignment_or_404(db: Session, *, amo_id: str, assignment_id: str, include_deleted: bool = False, lock: bool = False) -> models.RosterAssignment:
    row = services.get_assignment(db, amo_id=amo_id, assignment_id=assignment_id, include_deleted=include_deleted, lock=lock)
    if not row:
        raise _error("Roster assignment not found", error_code="ROSTER_ASSIGNMENT_NOT_FOUND", status_code=404)
    return row


@router.get("/contracts", response_model=schemas.RosterContractResponse)
def roster_contracts(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.roster_contracts(db, current_user=current_user)


# ---------------------------------------------------------------------------
# Dashboard and read models
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=schemas.RosterDashboardResponse)
def roster_dashboard(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    try:
        return services.dashboard(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, current_user=current_user)
    except ValueError as exc:
        raise _translate(exc, default_code="ROSTER_DASHBOARD_INVALID") from exc


@router.get("/planning-board", response_model=schemas.RosterPlanningBoardResponse)
def roster_planning_board(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    base_station_id: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT, department_id=department_id, base_station_id=base_station_id)
    try:
        return services.planning_board(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id)
    except ValueError as exc:
        raise _translate(exc, default_code="ROSTER_PLANNING_BOARD_INVALID") from exc


@router.get("/my-roster", response_model=schemas.MyRosterResponse)
def my_roster(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    try:
        return services.my_roster(db, amo_id=_amo(current_user), user=current_user, from_date=from_date, to_date=to_date)
    except ValueError as exc:
        raise _translate(exc, default_code="MY_ROSTER_INVALID") from exc


@router.get("/my-roster.ics")
def my_roster_calendar(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    rows = services.assignment_export_rows(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, user_id=current_user.id)
    return PlainTextResponse(
        exports.assignment_ics(rows, calendar_name="My AMO Duty Roster"),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=my-duty-roster.ics"},
    )


# ---------------------------------------------------------------------------
# Shift templates, periods and versions
# ---------------------------------------------------------------------------


@router.get("/shift-templates", response_model=list[schemas.ShiftTemplateRead])
def list_shift_templates(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    rows = services.list_shift_templates(db, amo_id=_amo(current_user), include_inactive=include_inactive)
    db.commit()
    return rows


@router.post("/shift-templates", response_model=schemas.ShiftTemplateRead, status_code=status.HTTP_201_CREATED)
def create_shift_template(
    payload: schemas.ShiftTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES)
    try:
        return _commit(db, services.create_shift_template(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload))
    except ValueError as exc:
        db.rollback()
        raise _translate(exc, default_code="SHIFT_TEMPLATE_INVALID") from exc


@router.patch("/shift-templates/{template_id}", response_model=schemas.ShiftTemplateRead)
@router.put("/shift-templates/{template_id}", response_model=schemas.ShiftTemplateRead, include_in_schema=False)
def patch_shift_template(
    template_id: str,
    payload: schemas.ShiftTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES)
    row = services.get_shift_template(db, amo_id=_amo(current_user), template_id=template_id)
    if not row:
        raise _error("Shift template not found", error_code="SHIFT_TEMPLATE_NOT_FOUND", status_code=404)
    try:
        services.update_shift_template(db, row=row, actor_user_id=current_user.id, payload=payload)
        return _commit(db, row)
    except ValueError as exc:
        db.rollback()
        raise _translate(exc, default_code="SHIFT_TEMPLATE_INVALID") from exc


@router.get("/periods", response_model=list[schemas.RosterPeriodRead])
def list_roster_periods(
    period_status: Optional[models.RosterPeriodStatus] = Query(default=None, alias="status"),
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    rows = services.list_periods(db, amo_id=_amo(current_user), period_status=period_status, from_date=from_date, to_date=to_date)
    return [services.serialize_period(row, current_user=current_user, db=db) for row in rows]


@router.post("/periods", response_model=schemas.RosterPeriodRead, status_code=status.HTTP_201_CREATED)
def create_roster_period(
    payload: schemas.RosterPeriodCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_CREATE)
    try:
        row = services.create_period(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_period(services.get_period(db, amo_id=_amo(current_user), period_id=row.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_PERIOD_INVALID") from exc


@router.get("/periods/{period_id}", response_model=schemas.RosterPeriodRead)
def get_roster_period(
    period_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    row = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not row:
        raise _error("Roster period not found", error_code="ROSTER_PERIOD_NOT_FOUND", status_code=404)
    return services.serialize_period(row, current_user=current_user, db=db)


@router.patch("/periods/{period_id}", response_model=schemas.RosterPeriodRead)
@router.put("/periods/{period_id}", response_model=schemas.RosterPeriodRead, include_in_schema=False)
def patch_roster_period(
    period_id: str,
    payload: schemas.RosterPeriodUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_EDIT)
    row = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not row:
        raise _error("Roster period not found", error_code="ROSTER_PERIOD_NOT_FOUND", status_code=404)
    try:
        services.update_period(db, row=row, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_period(services.get_period(db, amo_id=_amo(current_user), period_id=period_id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_PERIOD_INVALID") from exc


@router.get("/periods/{period_id}/versions", response_model=list[schemas.RosterVersionRead])
def list_roster_versions(
    period_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    period = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not period:
        raise _error("Roster period not found", error_code="ROSTER_PERIOD_NOT_FOUND", status_code=404)
    return [services.serialize_version(row, current_user=current_user, db=db) for row in services.list_versions(db, amo_id=_amo(current_user), period_id=period_id)]


@router.post("/periods/{period_id}/versions", response_model=schemas.RosterVersionRead, status_code=status.HTTP_201_CREATED)
def create_roster_version(
    period_id: str,
    payload: schemas.RosterVersionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_CREATE)
    period = services.get_period(db, amo_id=_amo(current_user), period_id=period_id)
    if not period:
        raise _error("Roster period not found", error_code="ROSTER_PERIOD_NOT_FOUND", status_code=404)
    if payload.source_version_id or payload.copy_from_version_id:
        source_id = payload.source_version_id or payload.copy_from_version_id
        source = services.get_version(db, amo_id=_amo(current_user), version_id=source_id)
        if source and source.status == models.RosterVersionStatus.PUBLISHED:
            _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_AMEND_PUBLISHED)
    try:
        row = services.create_version(db, period=period, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=row.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_VERSION_INVALID") from exc


@router.post("/versions/{version_id}/amend", response_model=schemas.RosterVersionRead, status_code=status.HTTP_201_CREATED)
def amend_published_roster(
    version_id: str,
    payload: schemas.RosterVersionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_AMEND_PUBLISHED)
    source = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    if source.status != models.RosterVersionStatus.PUBLISHED:
        raise _error("Only a published roster can be amended", error_code="ROSTER_AMENDMENT_SOURCE_INVALID")
    amended_payload = schemas.RosterVersionCreate(
        title=payload.title,
        change_summary=payload.change_summary,
        source_version_id=source.id,
        amendment_type=payload.amendment_type or models.RosterAmendmentType.OTHER,
        amendment_reason=payload.amendment_reason,
        effective_from=payload.effective_from,
        idempotency_key=payload.idempotency_key,
    )
    try:
        row = services.create_version(db, period=source.period, actor_user_id=current_user.id, payload=amended_payload)
        _commit(db, row)
        return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=row.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_AMENDMENT_INVALID") from exc


@router.get("/versions/{version_id}", response_model=schemas.RosterVersionRead)
def get_roster_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=version_id), current_user=current_user, db=db)


# ---------------------------------------------------------------------------
# Assignments, bulk operations and pattern generation
# ---------------------------------------------------------------------------


@router.get("/versions/{version_id}/assignments", response_model=list[schemas.RosterAssignmentRead])
def list_roster_assignments(
    version_id: str,
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    return [services.serialize_assignment(row) for row in services.list_assignments(db, amo_id=_amo(current_user), version_id=version_id, include_deleted=include_deleted)]


@router.post("/versions/{version_id}/assignments", response_model=schemas.RosterAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_roster_assignment(
    version_id: str,
    payload: schemas.RosterAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_EDIT, department_id=payload.department_id, base_station_id=payload.base_station_id)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        row = services.create_assignment(db, version=version, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_assignment(_assignment_or_404(db, amo_id=_amo(current_user), assignment_id=row.id))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_ASSIGNMENT_INVALID") from exc


@router.patch("/assignments/{assignment_id}", response_model=schemas.RosterAssignmentRead)
@router.put("/assignments/{assignment_id}", response_model=schemas.RosterAssignmentRead, include_in_schema=False)
def patch_roster_assignment(
    assignment_id: str,
    payload: schemas.RosterAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = _assignment_or_404(db, amo_id=_amo(current_user), assignment_id=assignment_id, lock=True)
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_EDIT, department_id=row.department_id, base_station_id=row.base_station_id)
    try:
        services.update_assignment(db, row=row, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        return services.serialize_assignment(_assignment_or_404(db, amo_id=_amo(current_user), assignment_id=row.id))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_ASSIGNMENT_INVALID") from exc


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_roster_assignment(
    assignment_id: str,
    payload: schemas.RosterAssignmentDeleteRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    row = _assignment_or_404(db, amo_id=_amo(current_user), assignment_id=assignment_id, lock=True)
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_DELETE_DRAFT_ASSIGNMENT, department_id=row.department_id, base_station_id=row.base_station_id)
    try:
        services.delete_assignment(db, row=row, actor_user_id=current_user.id, payload=payload)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_ASSIGNMENT_DELETE_FAILED") from exc


@router.post("/versions/{version_id}/assignments/bulk", response_model=schemas.RosterBulkAssignmentResult)
def bulk_create_roster_assignments(
    version_id: str,
    payload: schemas.RosterBulkAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_EDIT)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        result = services.bulk_create_assignments(db, version=version, actor_user_id=current_user.id, payload=payload)
        db.commit()
        return result
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_BULK_ASSIGNMENT_FAILED") from exc


@router.post("/versions/{version_id}/generate-from-pattern", response_model=schemas.RosterBulkAssignmentResult)
def generate_roster_from_pattern(
    version_id: str,
    payload: schemas.PatternGenerationRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        result = services.generate_from_patterns(db, version=version, actor_user_id=current_user.id, payload=payload)
        db.commit()
        return result
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_PATTERN_GENERATION_FAILED") from exc


# ---------------------------------------------------------------------------
# Validation, approval, publication and acknowledgement
# ---------------------------------------------------------------------------


@router.get("/versions/{version_id}/findings", response_model=list[schemas.RosterValidationFindingRead])
def list_validation_findings(
    version_id: str,
    include_resolved: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    query = db.query(models.RosterValidationFinding).filter(models.RosterValidationFinding.amo_id == _amo(current_user), models.RosterValidationFinding.version_id == version_id)
    if not include_resolved:
        query = query.filter(models.RosterValidationFinding.resolved.is_(False))
    rows = query.order_by(models.RosterValidationFinding.sort_order.asc(), models.RosterValidationFinding.severity.asc(), models.RosterValidationFinding.code.asc(), models.RosterValidationFinding.id.asc()).all()
    return [services.serialize_finding(row) for row in rows]


@router.post("/versions/{version_id}/validate", response_model=schemas.RosterValidationResult)
def validate_roster_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VALIDATE)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        result = services.validate_version(db, version=version, actor_user_id=current_user.id)
        db.commit()
        return result
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_VALIDATION_FAILED") from exc


@router.post("/versions/{version_id}/submit", response_model=schemas.RosterVersionRead)
def submit_roster_version(
    version_id: str,
    payload: schemas.RosterLifecycleRequest = schemas.RosterLifecycleRequest(),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_SUBMIT)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        services.submit_version(db, version=version, actor_user_id=current_user.id, payload=payload)
        _commit(db, version)
        return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=version.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_SUBMIT_FAILED") from exc


@router.post("/versions/{version_id}/approve", response_model=schemas.RosterVersionRead)
def approve_roster_version(
    version_id: str,
    payload: schemas.RosterLifecycleRequest = schemas.RosterLifecycleRequest(),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_APPROVE)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        services.approve_version(db, version=version, actor_user_id=current_user.id, payload=payload)
        _commit(db, version)
        return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=version.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_APPROVAL_FAILED") from exc


@router.post("/versions/{version_id}/publish", response_model=schemas.RosterVersionRead)
def publish_roster_version(
    version_id: str,
    payload: schemas.RosterLifecycleRequest = schemas.RosterLifecycleRequest(),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_PUBLISH)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id, lock=True)
    try:
        services.publish_version(db, version=version, actor_user_id=current_user.id, payload=payload)
        _commit(db, version)
        return services.serialize_version(_version_or_404(db, amo_id=_amo(current_user), version_id=version.id), current_user=current_user, db=db)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_PUBLICATION_FAILED") from exc


@router.post("/versions/{version_id}/acknowledge", response_model=schemas.RosterAcknowledgementRead)
def acknowledge_roster_version(
    version_id: str,
    payload: schemas.RosterAcknowledgeRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    try:
        row = services.acknowledge_version(db, version=version, user_id=current_user.id, payload=payload)
        return _commit(db, row)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_ACKNOWLEDGEMENT_FAILED") from exc


@router.post("/findings/{finding_id}/override", response_model=schemas.RosterRuleExceptionRead)
def override_validation_finding(
    finding_id: str,
    payload: schemas.RosterRuleOverrideRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = services.get_finding(db, amo_id=_amo(current_user), finding_id=finding_id)
    if not finding:
        raise _error("Validation finding not found", error_code="ROSTER_FINDING_NOT_FOUND", status_code=404)
    permission = workforce_permissions.PermissionCode.ROSTER_OVERRIDE_BLOCKER if finding.severity == models.RosterValidationSeverity.BLOCKER else workforce_permissions.PermissionCode.ROSTER_OVERRIDE_WARNING
    _require(db, current_user, permission)
    try:
        row = services.override_finding(db, finding=finding, actor_user_id=current_user.id, payload=payload)
        return _commit(db, row)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_OVERRIDE_FAILED") from exc


@router.get("/rule-exceptions", response_model=list[schemas.RosterRuleExceptionRead])
def list_rule_exceptions(
    version_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VALIDATE)
    return services.list_exceptions(db, amo_id=_amo(current_user), version_id=version_id)


@router.post("/rule-exceptions/{exception_id}/revoke", response_model=schemas.RosterRuleExceptionRead)
def revoke_rule_exception(
    exception_id: str,
    payload: schemas.RosterRuleOverrideRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_OVERRIDE_BLOCKER)
    row = services.get_exception(db, amo_id=_amo(current_user), exception_id=exception_id)
    if not row:
        raise _error("Rule exception not found", error_code="ROSTER_EXCEPTION_NOT_FOUND", status_code=404)
    try:
        services.revoke_exception(db, exception=row, actor_user_id=current_user.id, reason=payload.reason)
        return _commit(db, row)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_EXCEPTION_REVOKE_FAILED") from exc


# ---------------------------------------------------------------------------
# Rules and demand
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=list[schemas.RosterRuleRead])
def list_roster_rules(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VALIDATE)
    rows = services.list_rules(db, amo_id=_amo(current_user), include_inactive=include_inactive)
    db.commit()
    return rows


@router.post("/rules", response_model=schemas.RosterRuleRead, status_code=status.HTTP_201_CREATED)
def create_roster_rule(
    payload: schemas.RosterRuleCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_RULES)
    try:
        return _commit(db, services.create_rule(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_RULE_INVALID") from exc


@router.patch("/rules/{rule_id}", response_model=schemas.RosterRuleRead)
def patch_roster_rule(
    rule_id: str,
    payload: schemas.RosterRuleUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_RULES)
    row = services.get_rule(db, amo_id=_amo(current_user), rule_id=rule_id)
    if not row:
        raise _error("Roster rule not found", error_code="ROSTER_RULE_NOT_FOUND", status_code=404)
    try:
        services.update_rule(db, row=row, actor_user_id=current_user.id, payload=payload)
        return _commit(db, row)
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_RULE_INVALID") from exc


@router.get("/demand-requirements", response_model=list[schemas.RosterDemandRequirementRead])
def list_demand_requirements(
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    base_station_id: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT, department_id=department_id, base_station_id=base_station_id)
    return services.list_demand_requirements(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id, include_inactive=include_inactive)


@router.post("/demand-requirements", response_model=schemas.RosterDemandRequirementRead, status_code=status.HTTP_201_CREATED)
def create_demand_requirement(
    payload: schemas.RosterDemandRequirementCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_ALLOCATE_WORK, department_id=payload.department_id, base_station_id=payload.base_station_id)
    try:
        return _commit(db, services.create_demand_requirement(db, amo_id=_amo(current_user), actor_user_id=current_user.id, payload=payload))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_DEMAND_INVALID") from exc


# ---------------------------------------------------------------------------
# Maintenance-task allocation
# ---------------------------------------------------------------------------


@router.get("/assignments/{assignment_id}/task-links", response_model=list[schemas.RosterTaskAssignmentLinkRead])
def list_assignment_task_links(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise _error("Roster access denied", error_code="ROSTER_ACCESS_DENIED", status_code=403)
    _assignment_or_404(db, amo_id=_amo(current_user), assignment_id=assignment_id)
    return [services.serialize_task_link(row) for row in services.list_task_links(db, amo_id=_amo(current_user), assignment_id=assignment_id)]


@router.post("/assignments/{assignment_id}/task-links", response_model=schemas.RosterTaskAssignmentLinkRead, status_code=status.HTTP_201_CREATED)
def link_assignment_to_task_assignment(
    assignment_id: str,
    payload: schemas.RosterTaskLinkCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_ALLOCATE_WORK)
    assignment = _assignment_or_404(db, amo_id=_amo(current_user), assignment_id=assignment_id)
    try:
        row = services.link_task_assignment(db, assignment=assignment, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        links = services.list_task_links(db, amo_id=_amo(current_user), assignment_id=assignment_id)
        return services.serialize_task_link(next(item for item in links if item.id == row.id))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_TASK_LINK_FAILED") from exc


@router.post("/assignments/{assignment_id}/task-allocations", response_model=schemas.RosterTaskAssignmentLinkRead, status_code=status.HTTP_201_CREATED)
def allocate_assignment_to_task(
    assignment_id: str,
    payload: schemas.RosterTaskAllocationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_ALLOCATE_WORK)
    assignment = _assignment_or_404(db, amo_id=_amo(current_user), assignment_id=assignment_id)
    try:
        row = services.allocate_to_task(db, assignment=assignment, actor_user_id=current_user.id, payload=payload)
        _commit(db, row)
        links = services.list_task_links(db, amo_id=_amo(current_user), assignment_id=assignment_id)
        return services.serialize_task_link(next(item for item in links if item.id == row.id))
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise _translate(exc, default_code="ROSTER_TASK_ALLOCATION_FAILED") from exc


# ---------------------------------------------------------------------------
# Reports and exports
# ---------------------------------------------------------------------------


@router.get("/reports/summary", response_model=schemas.RosterReportSummary)
def roster_report_summary(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    base_station_id: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT, department_id=department_id, base_station_id=base_station_id)
    try:
        return services.report_summary(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id)
    except ValueError as exc:
        raise _translate(exc, default_code="ROSTER_REPORT_INVALID") from exc


@router.get("/reports/export")
def export_roster_report(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    format: str = Query(default="csv", pattern=r"^(csv|xlsx|pdf|ics)$"),
    base_station_id: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT, department_id=department_id, base_station_id=base_station_id)
    rows = services.assignment_export_rows(db, amo_id=_amo(current_user), from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id, user_id=user_id)
    base_name = f"duty-roster-{from_date.isoformat()}-{to_date.isoformat()}"
    if format == "csv":
        return PlainTextResponse(exports.assignment_csv(rows), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={base_name}.csv"})
    if format == "ics":
        return PlainTextResponse(exports.assignment_ics(rows), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename={base_name}.ics"})
    if format == "xlsx":
        payload = exports.assignment_xlsx(rows)
        return StreamingResponse(BytesIO(payload), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={base_name}.xlsx"})
    payload = exports.assignment_pdf(rows, title="Published Duty Roster", subtitle=f"{from_date.isoformat()} to {to_date.isoformat()}")
    return StreamingResponse(BytesIO(payload), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={base_name}.pdf"})
