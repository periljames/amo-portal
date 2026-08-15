"""Canonical HR dashboard assembled from Workforce-owned records.

This service intentionally does not duplicate identity, contract, leave,
attendance, timesheet, overtime, base or work-pattern data. It presents those
source records as one actionable HR workspace.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..accounts import models as account_models
from ..audit import schemas as audit_schemas
from ..audit import services as audit_services
from . import hr_schemas, models, permissions, schemas, services


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _value(value) -> str:
    return str(getattr(value, "value", value))


def _display_name(user: Optional[account_models.User]) -> Optional[str]:
    if not user:
        return None
    full_name = str(getattr(user, "full_name", "") or "").strip()
    if full_name:
        return full_name
    return " ".join(
        part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part
    ).strip() or getattr(user, "email", None)


def _amo_zone(db: Session, *, amo_id: str) -> ZoneInfo:
    zone_name = (
        db.query(account_models.AMO.time_zone)
        .filter(account_models.AMO.id == amo_id)
        .scalar()
        or "UTC"
    )
    try:
        return ZoneInfo(str(zone_name))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _amo_work_date(db: Session, *, amo_id: str, instant: datetime) -> date:
    normalized = instant if instant.tzinfo is not None else instant.replace(tzinfo=timezone.utc)
    return normalized.astimezone(_amo_zone(db, amo_id=amo_id)).date()


def _validated_roster_assignment(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    assignment_id: str,
    starts_at: datetime,
    ends_at: datetime,
):
    from ..rostering import models as roster_models

    assignment = db.query(roster_models.RosterAssignment).filter(
        roster_models.RosterAssignment.id == assignment_id,
        roster_models.RosterAssignment.amo_id == amo_id,
    ).first()
    if assignment is None:
        raise ValueError("Roster assignment was not found in this AMO")
    if str(assignment.user_id) != str(user_id):
        raise ValueError("Roster assignment does not belong to the overtime employee")
    if assignment.deleted_at is not None:
        raise ValueError("Deleted roster assignments cannot support overtime claims")
    if assignment.starts_at >= ends_at or assignment.ends_at <= starts_at:
        raise ValueError("Roster assignment does not overlap the overtime window")
    return assignment


def _department_code(user: Optional[account_models.User]) -> Optional[str]:
    department = getattr(user, "department", None) if user else None
    return getattr(department, "code", None)


def _active_contracts(db: Session, *, amo_id: str, on_date: date) -> list[models.EmploymentContract]:
    return db.query(models.EmploymentContract).options(
        joinedload(models.EmploymentContract.user),
        joinedload(models.EmploymentContract.supervisor),
        joinedload(models.EmploymentContract.primary_base),
    ).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from <= on_date,
        or_(
            models.EmploymentContract.effective_to.is_(None),
            models.EmploymentContract.effective_to >= on_date,
        ),
    ).order_by(models.EmploymentContract.user_id.asc(), models.EmploymentContract.effective_from.desc()).all()


def _effective_patterns(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
    on_date: date,
) -> dict[str, models.EmployeeWorkPatternAssignment]:
    if not user_ids:
        return {}
    rows = db.query(models.EmployeeWorkPatternAssignment).options(
        joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_(user_ids),
        models.EmployeeWorkPatternAssignment.effective_from <= on_date,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= on_date,
        ),
    ).order_by(
        models.EmployeeWorkPatternAssignment.user_id.asc(),
        models.EmployeeWorkPatternAssignment.effective_from.desc(),
    ).all()
    result: dict[str, models.EmployeeWorkPatternAssignment] = {}
    for row in rows:
        result.setdefault(row.user_id, row)
    return result


def _active_leave(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
    now: datetime,
) -> dict[str, models.LeaveRequest]:
    if not user_ids:
        return {}
    rows = db.query(models.LeaveRequest).options(
        joinedload(models.LeaveRequest.leave_type),
    ).filter(
        models.LeaveRequest.amo_id == amo_id,
        models.LeaveRequest.user_id.in_(user_ids),
        models.LeaveRequest.status.in_([
            models.LeaveRequestStatus.SUBMITTED,
            models.LeaveRequestStatus.SUPERVISOR_APPROVED,
            models.LeaveRequestStatus.HR_APPROVED,
        ]),
        models.LeaveRequest.starts_at <= now,
        models.LeaveRequest.ends_at > now,
    ).order_by(models.LeaveRequest.starts_at.asc()).all()
    result: dict[str, models.LeaveRequest] = {}
    for row in rows:
        result.setdefault(row.user_id, row)
    return result


def serialize_overtime(row: models.OvertimeRequest) -> hr_schemas.HrOvertimeRequestRead:
    return hr_schemas.HrOvertimeRequestRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=_display_name(row.user),
        roster_assignment_id=row.roster_assignment_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        requested_minutes=row.requested_minutes,
        reason=row.reason,
        status=_value(row.status),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def serialize_attendance_exception(
    row: models.RosterActualVariance,
    *,
    user: Optional[account_models.User] = None,
) -> hr_schemas.HrAttendanceExceptionRead:
    return hr_schemas.HrAttendanceExceptionRead(
        id=row.id,
        amo_id=row.amo_id,
        roster_assignment_id=row.roster_assignment_id,
        user_id=row.user_id,
        user_full_name=_display_name(user),
        planned_minutes=row.planned_minutes,
        attendance_minutes=row.attendance_minutes,
        productive_minutes=row.productive_minutes,
        variance_minutes=row.variance_minutes,
        classification=row.classification,
        metadata_json=row.metadata_json if isinstance(row.metadata_json, dict) else None,
        calculated_at=row.calculated_at,
    )


def list_overtime_requests(
    db: Session,
    *,
    amo_id: str,
    pending_only: bool = True,
    limit: int = 200,
) -> list[hr_schemas.HrOvertimeRequestRead]:
    query = db.query(models.OvertimeRequest).options(
        joinedload(models.OvertimeRequest.user),
    ).filter(models.OvertimeRequest.amo_id == amo_id)
    if pending_only:
        query = query.filter(models.OvertimeRequest.status.in_([
            models.OvertimeRequestStatus.SUBMITTED,
            models.OvertimeRequestStatus.SUPERVISOR_APPROVED,
        ]))
    rows = query.order_by(models.OvertimeRequest.starts_at.asc(), models.OvertimeRequest.id.asc()).limit(limit).all()
    return [serialize_overtime(row) for row in rows]


def create_overtime_request(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.OvertimeRequestCreate,
) -> models.OvertimeRequest:
    user_id = payload.user_id or actor_user_id
    services._require_user(db, amo_id=amo_id, user_id=user_id, active_only=True)
    on_date = _amo_work_date(db, amo_id=amo_id, instant=payload.starts_at)
    contract = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= on_date,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= on_date),
    ).order_by(models.EmploymentContract.effective_from.desc()).first()
    if contract is None:
        raise ValueError("An active employment contract is required for overtime")
    if not contract.overtime_eligible:
        raise ValueError("The employee is not eligible for overtime under the active contract")
    actual_minutes = int((payload.ends_at - payload.starts_at).total_seconds() // 60)
    requested_minutes = payload.requested_minutes or actual_minutes
    if requested_minutes < 1 or requested_minutes > actual_minutes:
        raise ValueError("requested_minutes must be within the requested overtime window")
    if payload.roster_assignment_id:
        _validated_roster_assignment(
            db,
            amo_id=amo_id,
            user_id=user_id,
            assignment_id=payload.roster_assignment_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
    duplicate = db.query(models.OvertimeRequest.id).filter(
        models.OvertimeRequest.amo_id == amo_id,
        models.OvertimeRequest.user_id == user_id,
        models.OvertimeRequest.starts_at == payload.starts_at,
        models.OvertimeRequest.ends_at == payload.ends_at,
        models.OvertimeRequest.status.notin_([
            models.OvertimeRequestStatus.REJECTED,
            models.OvertimeRequestStatus.CANCELLED,
        ]),
    ).first()
    if duplicate:
        raise ValueError("An active overtime request already exists for this window")
    row = models.OvertimeRequest(
        amo_id=amo_id,
        user_id=user_id,
        roster_assignment_id=payload.roster_assignment_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        requested_minutes=requested_minutes,
        reason=payload.reason.strip(),
        status=models.OvertimeRequestStatus.SUBMITTED,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def decide_overtime(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    request_id: str,
    payload: hr_schemas.HrOvertimeDecisionRequest,
) -> models.OvertimeRequest:
    row = db.query(models.OvertimeRequest).options(
        joinedload(models.OvertimeRequest.user),
    ).filter(
        models.OvertimeRequest.amo_id == amo_id,
        models.OvertimeRequest.id == request_id,
    ).with_for_update().first()
    if row is None:
        raise ValueError("Overtime request not found")
    if str(actor_user_id) == str(row.user_id):
        raise ValueError("Overtime requesters cannot approve their own claims")
    stage = models.LeaveApprovalStage(payload.stage)
    decision = models.ApprovalDecision(payload.decision)
    if stage == models.LeaveApprovalStage.SUPERVISOR:
        work_date = _amo_work_date(db, amo_id=amo_id, instant=row.starts_at)
        contract = db.query(models.EmploymentContract).filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id == row.user_id,
            models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
            models.EmploymentContract.effective_from <= work_date,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= work_date,
            ),
        ).order_by(models.EmploymentContract.effective_from.desc()).first()
        if contract is None or str(contract.supervisor_user_id or "") != str(actor_user_id):
            raise ValueError("Only the assigned supervisor may decide the supervisor overtime stage")
    expected = (
        models.OvertimeRequestStatus.SUBMITTED
        if stage == models.LeaveApprovalStage.SUPERVISOR
        else models.OvertimeRequestStatus.SUPERVISOR_APPROVED
    )
    if row.status != expected:
        raise ValueError(f"Overtime request is not awaiting {stage.value.lower()} review")
    existing = db.query(models.OvertimeApproval.id).filter(
        models.OvertimeApproval.amo_id == amo_id,
        models.OvertimeApproval.overtime_request_id == row.id,
        models.OvertimeApproval.stage == stage,
    ).first()
    if existing:
        raise ValueError(f"The {stage.value.lower()} overtime decision is already recorded")
    db.add(models.OvertimeApproval(
        amo_id=amo_id,
        overtime_request_id=row.id,
        stage=stage,
        decision=decision,
        actor_user_id=actor_user_id,
        comment=payload.comment.strip(),
    ))
    if decision == models.ApprovalDecision.REJECTED:
        row.status = models.OvertimeRequestStatus.REJECTED
    elif stage == models.LeaveApprovalStage.SUPERVISOR:
        row.status = models.OvertimeRequestStatus.SUPERVISOR_APPROVED
    else:
        row.status = models.OvertimeRequestStatus.HR_APPROVED
    db.add(row)
    db.flush()
    return row


def _person_readiness(
    contract: models.EmploymentContract,
    *,
    pattern: Optional[models.EmployeeWorkPatternAssignment],
    leave: Optional[models.LeaveRequest],
) -> hr_schemas.HrPersonReadiness:
    reasons: list[str] = []
    status_value = _value(contract.employment_status)
    if status_value != models.EmploymentStatus.ACTIVE.value:
        reasons.append(f"Employment status is {status_value.replace('_', ' ').lower()}.")
    if not contract.primary_base_station_id:
        reasons.append("No primary base is assigned.")
    if not pattern or not pattern.work_pattern or not pattern.work_pattern.is_active:
        reasons.append("No active work pattern is assigned.")
    if leave and _value(leave.status) == models.LeaveRequestStatus.HR_APPROVED.value:
        reasons.append("Employee is currently on approved leave.")

    if status_value == models.EmploymentStatus.SUSPENDED.value:
        state = "BLOCKED"
    elif reasons:
        state = "NEEDS_ATTENTION"
    else:
        state = "READY"

    user = contract.user
    work_pattern = pattern.work_pattern if pattern else None
    return hr_schemas.HrPersonReadiness(
        user_id=contract.user_id,
        contract_id=contract.id,
        staff_code=str(getattr(user, "staff_code", "") or ""),
        full_name=_display_name(user) or contract.user_id,
        position_title=getattr(user, "position_title", None),
        department_code=_department_code(user),
        employment_status=status_value,
        contract_type=_value(contract.contract_type),
        contract_effective_from=contract.effective_from,
        contract_effective_to=contract.effective_to,
        primary_base_station_id=contract.primary_base_station_id,
        primary_base_code=getattr(contract.primary_base, "code", None),
        supervisor_name=_display_name(contract.supervisor),
        standard_weekly_minutes=contract.standard_weekly_minutes,
        standard_daily_minutes=contract.standard_daily_minutes,
        fte_percentage=float(contract.fte_percentage),
        cost_centre=contract.cost_centre,
        payroll_number=contract.payroll_number,
        overtime_eligible=contract.overtime_eligible,
        night_shift_eligible=contract.night_shift_eligible,
        standby_eligible=contract.standby_eligible,
        work_pattern_code=getattr(work_pattern, "code", None),
        work_pattern_name=getattr(work_pattern, "name", None),
        work_pattern_effective_from=pattern.effective_from if pattern else None,
        active_leave_status=_value(leave.status) if leave else None,
        readiness_state=state,
        readiness_reasons=reasons,
    )



def _pending_queue_counts(db: Session, *, amo_id: str) -> dict[str, int]:
    """Return uncapped queue totals independently from dashboard samples."""

    pending_leave = int(db.query(func.count(models.LeaveRequest.id)).filter(
        models.LeaveRequest.amo_id == amo_id,
        models.LeaveRequest.status.in_([
            models.LeaveRequestStatus.SUBMITTED,
            models.LeaveRequestStatus.SUPERVISOR_APPROVED,
        ]),
    ).scalar() or 0)
    pending_timesheet = int(db.query(func.count(models.Timesheet.id)).filter(
        models.Timesheet.amo_id == amo_id,
        models.Timesheet.status.in_([
            models.TimesheetStatus.SUBMITTED,
            models.TimesheetStatus.SUPERVISOR_APPROVED,
        ]),
    ).scalar() or 0)
    pending_overtime = int(db.query(func.count(models.OvertimeRequest.id)).filter(
        models.OvertimeRequest.amo_id == amo_id,
        models.OvertimeRequest.status.in_([
            models.OvertimeRequestStatus.SUBMITTED,
            models.OvertimeRequestStatus.SUPERVISOR_APPROVED,
        ]),
    ).scalar() or 0)
    attendance_exception = int(db.query(func.count(models.RosterActualVariance.id)).filter(
        models.RosterActualVariance.amo_id == amo_id,
        or_(
            models.RosterActualVariance.classification != "MATCHED",
            func.abs(models.RosterActualVariance.variance_minutes) >= 30,
        ),
    ).scalar() or 0)
    attendance_event_review = int(db.query(func.count(models.AttendanceEvent.id)).filter(
        models.AttendanceEvent.amo_id == amo_id,
        models.AttendanceEvent.metadata_json.isnot(None),
        models.AttendanceEvent.metadata_json["requires_review"].as_boolean().is_(True),
    ).scalar() or 0)
    return {
        "leave": pending_leave,
        "timesheet": pending_timesheet,
        "overtime": pending_overtime,
        "attendance_exception": attendance_exception + attendance_event_review,
    }


def list_people_page(
    db: Session,
    *,
    amo_id: str,
    page: int = 1,
    page_size: int = 100,
    search: Optional[str] = None,
) -> hr_schemas.HrPeoplePage:
    today = date.today()
    now = _utcnow()
    contracts = _active_contracts(db, amo_id=amo_id, on_date=today)
    current_contracts: dict[str, models.EmploymentContract] = {}
    for row in contracts:
        current_contracts.setdefault(str(row.user_id), row)
    selected_contracts = list(current_contracts.values())
    user_ids = list(current_contracts)
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)
    items = [
        _person_readiness(
            row,
            pattern=patterns.get(str(row.user_id)),
            leave=leave_by_user.get(str(row.user_id)),
        )
        for row in selected_contracts
    ]
    needle = str(search or "").strip().lower()
    if needle:
        items = [
            item for item in items
            if any(
                needle in str(value or "").lower()
                for value in (
                    item.full_name,
                    item.staff_code,
                    item.position_title,
                    item.department_code,
                    item.primary_base_code,
                    item.payroll_number,
                )
            )
        ]
    items.sort(key=lambda item: (item.readiness_state == "READY", item.full_name.lower(), item.user_id))
    total = len(items)
    safe_page_size = max(1, min(int(page_size), 200))
    pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    safe_page = max(1, int(page))
    start = (safe_page - 1) * safe_page_size
    return hr_schemas.HrPeoplePage(
        items=items[start:start + safe_page_size],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
        pages=pages,
    )


def dashboard(
    db: Session,
    *,
    amo_id: str,
    current_user: account_models.User,
    people_limit: int = 200,
) -> hr_schemas.HrDashboardResponse:
    today = date.today()
    now = _utcnow()
    expiry_cutoff = today + timedelta(days=60)
    contracts = _active_contracts(db, amo_id=amo_id, on_date=today)

    # One effective contract per user. Overlap prevention belongs to Workforce
    # services, but this presentation remains deterministic if historic data is
    # imperfect.
    current_contracts: dict[str, models.EmploymentContract] = {}
    for row in contracts:
        current_contracts.setdefault(row.user_id, row)
    selected_contracts = list(current_contracts.values())
    user_ids = list(current_contracts)
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)

    active_count = sum(1 for row in selected_contracts if _value(row.employment_status) == "ACTIVE")
    onboarding_count = sum(1 for row in selected_contracts if _value(row.employment_status) == "ONBOARDING")
    suspended_count = sum(1 for row in selected_contracts if _value(row.employment_status) == "SUSPENDED")
    expiring_rows = [
        row for row in selected_contracts
        if row.effective_to is not None and today <= row.effective_to <= expiry_cutoff
    ]
    without_pattern = [row for row in selected_contracts if row.user_id not in patterns]
    without_base = [row for row in selected_contracts if not row.primary_base_station_id]
    pending_counts = _pending_queue_counts(db, amo_id=amo_id)

    pending_leave_rows = db.query(models.LeaveRequest).options(
        joinedload(models.LeaveRequest.user),
        joinedload(models.LeaveRequest.leave_type),
    ).filter(
        models.LeaveRequest.amo_id == amo_id,
        models.LeaveRequest.status.in_([
            models.LeaveRequestStatus.SUBMITTED,
            models.LeaveRequestStatus.SUPERVISOR_APPROVED,
        ]),
    ).order_by(models.LeaveRequest.submitted_at.asc(), models.LeaveRequest.created_at.asc()).limit(50).all()

    pending_timesheet_rows = db.query(models.Timesheet).options(
        joinedload(models.Timesheet.user),
    ).filter(
        models.Timesheet.amo_id == amo_id,
        models.Timesheet.status.in_([
            models.TimesheetStatus.SUBMITTED,
            models.TimesheetStatus.SUPERVISOR_APPROVED,
        ]),
    ).order_by(models.Timesheet.period_end.asc()).limit(50).all()

    pending_overtime_rows = db.query(models.OvertimeRequest).options(
        joinedload(models.OvertimeRequest.user),
    ).filter(
        models.OvertimeRequest.amo_id == amo_id,
        models.OvertimeRequest.status.in_([
            models.OvertimeRequestStatus.SUBMITTED,
            models.OvertimeRequestStatus.SUPERVISOR_APPROVED,
        ]),
    ).order_by(models.OvertimeRequest.starts_at.asc()).limit(50).all()

    attendance_exception_rows = db.query(models.RosterActualVariance).filter(
        models.RosterActualVariance.amo_id == amo_id,
        or_(
            models.RosterActualVariance.classification != "MATCHED",
            func.abs(models.RosterActualVariance.variance_minutes) >= 30,
        ),
    ).order_by(models.RosterActualVariance.calculated_at.desc()).limit(50).all()

    attendance_review_events = db.query(models.AttendanceEvent).options(
        joinedload(models.AttendanceEvent.user),
    ).filter(
        models.AttendanceEvent.amo_id == amo_id,
        models.AttendanceEvent.metadata_json.isnot(None),
        models.AttendanceEvent.metadata_json["requires_review"].as_boolean().is_(True),
    ).order_by(models.AttendanceEvent.occurred_at.desc()).limit(50).all()

    attendance_user_ids = sorted(
        {row.user_id for row in attendance_exception_rows}
        | {row.user_id for row in attendance_review_events}
    )
    attendance_users = (
        db.query(account_models.User).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(attendance_user_ids),
        ).all()
        if attendance_user_ids
        else []
    )
    attendance_users_by_id = {str(user.id): user for user in attendance_users}

    actions: list[hr_schemas.HrActionItem] = []
    for row in expiring_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"contract:{row.id}",
            category="CONTRACT",
            severity="WARNING",
            title="Contract expires soon",
            detail=f"Contract ends on {row.effective_to.isoformat()}.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            due_on=row.effective_to,
            action_label="Open contract",
            action_path=f"contracts/{row.id}",
        ))
    for row in without_pattern[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"pattern:{row.user_id}",
            category="WORK_PATTERN",
            severity="WARNING",
            title="No work pattern assigned",
            detail="Automatic rotation cannot create duty for this employee until an effective work pattern is assigned.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            action_label="Assign pattern",
            action_path=f"people/{row.user_id}?section=work-pattern",
        ))
    for row in without_base[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"base:{row.user_id}",
            category="BASE",
            severity="BLOCKER",
            title="Primary base missing",
            detail="The active employment contract has no primary base.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            action_label="Open employment record",
            action_path=f"people/{row.user_id}?section=contract",
        ))
    for row in pending_leave_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"leave:{row.id}",
            category="LEAVE",
            severity="ACTION",
            title="Leave approval required",
            detail=f"{getattr(row.leave_type, 'name', 'Leave')} from {row.starts_at.date()} to {row.ends_at.date()}.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            due_on=row.starts_at.date(),
            action_label="Review leave",
            action_path=f"leave/{row.id}",
        ))
    for row in pending_timesheet_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"timesheet:{row.id}",
            category="TIMESHEET",
            severity="ACTION",
            title="Timesheet approval required",
            detail=f"Pay period {row.period_start} to {row.period_end}.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            due_on=row.period_end,
            action_label="Review timesheet",
            action_path=f"time/timesheets/{row.id}",
        ))
    for row in pending_overtime_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"overtime:{row.id}",
            category="OVERTIME",
            severity="ACTION",
            title="Overtime approval required",
            detail=f"{row.requested_minutes} minutes from {row.starts_at.isoformat()}.",
            user_id=row.user_id,
            user_name=_display_name(row.user),
            due_on=row.starts_at.date(),
            action_label="Review overtime",
            action_path=f"time/overtime/{row.id}",
        ))
    for row in attendance_exception_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"attendance:{row.id}",
            category="ATTENDANCE",
            severity="ACTION",
            title="Attendance variance requires review",
            detail=(
                f"{row.classification}: {row.variance_minutes:+d} minutes variance; "
                f"{row.attendance_minutes} attendance minutes against {row.planned_minutes} planned."
            ),
            user_id=row.user_id,
            user_name=_display_name(attendance_users_by_id.get(str(row.user_id))),
            due_on=row.calculated_at.date(),
            action_label="Inspect variance",
            action_path=f"time/attendance/{row.id}",
        ))
    for row in attendance_review_events[:20]:
        metadata = row.metadata_json or {}
        actions.append(hr_schemas.HrActionItem(
            id=f"attendance-event:{row.id}",
            category="ATTENDANCE",
            severity="ACTION",
            title="Attendance event needs confirmation",
            detail=str(metadata.get("review_reason") or "Location, timing or automatic closure evidence requires review."),
            user_id=row.user_id,
            user_name=_display_name(row.user),
            due_on=row.occurred_at.date(),
            action_label="Review attendance",
            action_path=f"time/attendance?event={row.id}",
        ))
    actions.sort(key=lambda item: (
        0 if item.severity == "BLOCKER" else 1 if item.severity == "ACTION" else 2,
        item.due_on or date.max,
        item.id,
    ))

    metrics = [
        hr_schemas.HrMetric(key="active", label="Active employees", value=active_count, detail="Effective active contracts", tone="good"),
        hr_schemas.HrMetric(key="onboarding", label="Onboarding", value=onboarding_count, detail="Not yet fully active", tone="info"),
        hr_schemas.HrMetric(key="leave", label="Leave approvals", value=pending_counts["leave"], detail="Supervisor or HR action", tone="warning" if pending_counts["leave"] else "neutral"),
        hr_schemas.HrMetric(key="time", label="Time approvals", value=pending_counts["timesheet"], detail="Submitted timesheets", tone="warning" if pending_counts["timesheet"] else "neutral"),
        hr_schemas.HrMetric(key="attendance", label="Attendance review", value=pending_counts["attendance_exception"], detail="Location, timing or variance checks", tone="warning" if pending_counts["attendance_exception"] else "good"),
        hr_schemas.HrMetric(key="patterns", label="Pattern gaps", value=len(without_pattern), detail="Cannot be auto-rotated", tone="danger" if without_pattern else "good"),
        hr_schemas.HrMetric(key="contracts", label="Expiring contracts", value=len(expiring_rows), detail="Within 60 days", tone="warning" if expiring_rows else "neutral"),
    ]

    can_manage_contracts = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS
    )
    can_manage_patterns = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.ROSTER_MANAGE_PATTERNS
    )
    can_assign_patterns = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS
    )
    can_manage_leave_balances = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.LEAVE_MANAGE_BALANCES
    )
    can_review_leave = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.LEAVE_REVIEW
    )
    can_approve_leave = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.LEAVE_APPROVE
    )
    can_approve_timesheet_supervisor = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.TIMESHEET_APPROVE
    )
    can_approve_timesheet_hr = can_approve_timesheet_supervisor and permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.ATTENDANCE_APPROVE
    )
    can_approve_overtime_supervisor = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.OVERTIME_APPROVE
    )
    can_approve_overtime_hr = can_approve_overtime_supervisor and permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.ATTENDANCE_APPROVE
    )
    can_manage_attendance = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.ATTENDANCE_MANAGE
    )
    can_export_payroll = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.PAYROLL_EXPORT
    )

    people = [
        _person_readiness(
            row,
            pattern=patterns.get(row.user_id),
            leave=leave_by_user.get(row.user_id),
        )
        for row in selected_contracts[:people_limit]
    ]
    people.sort(key=lambda row: (row.readiness_state == "READY", row.full_name.lower(), row.user_id))

    return hr_schemas.HrDashboardResponse(
        generated_at=now,
        can_manage_contracts=can_manage_contracts,
        can_manage_patterns=can_manage_patterns,
        can_assign_patterns=can_assign_patterns,
        can_manage_leave_balances=can_manage_leave_balances,
        can_review_leave=can_review_leave,
        can_approve_leave=can_approve_leave,
        can_approve_timesheet_supervisor=can_approve_timesheet_supervisor,
        can_approve_timesheet_hr=can_approve_timesheet_hr,
        can_approve_overtime_supervisor=can_approve_overtime_supervisor,
        can_approve_overtime_hr=can_approve_overtime_hr,
        can_manage_attendance=can_manage_attendance,
        can_export_payroll=can_export_payroll,
        active_employee_count=active_count,
        onboarding_employee_count=onboarding_count,
        suspended_employee_count=suspended_count,
        contracts_expiring_soon_count=len(expiring_rows),
        employees_without_pattern_count=len(without_pattern),
        employees_without_base_count=len(without_base),
        pending_leave_count=pending_counts["leave"],
        pending_timesheet_count=pending_counts["timesheet"],
        pending_overtime_count=pending_counts["overtime"],
        attendance_exception_count=pending_counts["attendance_exception"],
        metrics=metrics,
        action_queue=actions[:100],
        pending_overtime=[serialize_overtime(row) for row in pending_overtime_rows],
        attendance_exceptions=[
            serialize_attendance_exception(
                row,
                user=attendance_users_by_id.get(str(row.user_id)),
            )
            for row in attendance_exception_rows
        ],
        people=people,
    )

def _active_tenant_users(db: Session, *, amo_id: str) -> list[account_models.User]:
    """Return every active human tenant account, regardless of HR completeness."""
    return db.query(account_models.User).options(
        joinedload(account_models.User.department),
    ).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(
        account_models.User.full_name.asc(),
        account_models.User.staff_code.asc(),
        account_models.User.id.asc(),
    ).all()


def _current_contracts_by_user(
    db: Session,
    *,
    amo_id: str,
    on_date: date,
) -> dict[str, models.EmploymentContract]:
    result: dict[str, models.EmploymentContract] = {}
    for row in _active_contracts(db, amo_id=amo_id, on_date=on_date):
        result.setdefault(str(row.user_id), row)
    return result


def _readiness_contracts_by_user(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
    on_date: date,
) -> dict[str, models.EmploymentContract]:
    """Return the effective contract or, when absent, the next future contract."""
    result = _current_contracts_by_user(db, amo_id=amo_id, on_date=on_date)
    missing_user_ids = [user_id for user_id in user_ids if user_id not in result]
    if not missing_user_ids:
        return result
    future_rows = db.query(models.EmploymentContract).options(
        joinedload(models.EmploymentContract.user),
        joinedload(models.EmploymentContract.supervisor),
        joinedload(models.EmploymentContract.primary_base),
    ).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id.in_(missing_user_ids),
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from > on_date,
    ).order_by(
        models.EmploymentContract.user_id.asc(),
        models.EmploymentContract.effective_from.asc(),
        models.EmploymentContract.id.asc(),
    ).all()
    for row in future_rows:
        result.setdefault(str(row.user_id), row)
    return result


def _person_readiness_for_user(
    user: account_models.User,
    *,
    amo_id: str,
    contract: Optional[models.EmploymentContract],
    pattern: Optional[models.EmployeeWorkPatternAssignment],
    leave: Optional[models.LeaveRequest],
    on_date: date,
    hire_date: Optional[date] = None,
) -> hr_schemas.HrPersonReadiness:
    reasons: list[str] = []
    status_value = _value(contract.employment_status) if contract else None
    contract_is_effective = bool(
        contract
        and contract.effective_from <= on_date
        and (contract.effective_to is None or contract.effective_to >= on_date)
    )
    if contract is None:
        reasons.append("No effective or future employment contract exists.")
    elif not contract_is_effective:
        reasons.append(f"Employment contract starts on {contract.effective_from.isoformat()}.")
        if not contract.primary_base_station_id:
            reasons.append("The future contract has no primary base assigned.")
    else:
        if status_value != models.EmploymentStatus.ACTIVE.value:
            reasons.append(f"Employment status is {status_value.replace('_', ' ').lower()}.")
        if not contract.primary_base_station_id:
            reasons.append("No primary base is assigned.")
    work_pattern = pattern.work_pattern if pattern else None
    if not work_pattern or not work_pattern.is_active:
        reasons.append("No active work pattern is assigned.")
    if leave and _value(leave.status) == models.LeaveRequestStatus.HR_APPROVED.value:
        reasons.append("Employee is currently on approved leave.")

    if status_value == models.EmploymentStatus.SUSPENDED.value:
        state = "BLOCKED"
    elif reasons:
        state = "NEEDS_ATTENTION"
    else:
        state = "READY"

    managed_default_pattern_id = _default_day_system_id(
        amo_id=amo_id,
        system_key=_DEFAULT_DAY_PATTERN_KEY,
    )
    uses_managed_default = bool(
        pattern and str(pattern.work_pattern_id) == managed_default_pattern_id
    )
    contract_state = (
        "EFFECTIVE"
        if contract_is_effective
        else "FUTURE"
        if contract is not None
        else "MISSING"
    )
    pattern_state = "DEFAULT" if uses_managed_default else "ASSIGNED" if work_pattern else "MISSING"

    return hr_schemas.HrPersonReadiness(
        user_id=str(user.id),
        contract_id=contract.id if contract else None,
        staff_code=str(getattr(user, "staff_code", "") or ""),
        full_name=_display_name(user) or str(user.id),
        email=getattr(user, "email", None),
        has_effective_contract=contract_is_effective,
        uses_default_day_pattern=uses_managed_default,
        position_title=getattr(user, "position_title", None),
        department_code=_department_code(user),
        employment_status=status_value,
        contract_type=_value(contract.contract_type) if contract else None,
        contract_state=contract_state,
        hire_date=hire_date,
        contract_effective_from=contract.effective_from if contract else None,
        contract_effective_to=contract.effective_to if contract else None,
        primary_base_station_id=contract.primary_base_station_id if contract else None,
        primary_base_code=getattr(contract.primary_base, "code", None) if contract else None,
        supervisor_name=_display_name(contract.supervisor) if contract else None,
        standard_weekly_minutes=contract.standard_weekly_minutes if contract else 2400,
        standard_daily_minutes=contract.standard_daily_minutes if contract else 480,
        fte_percentage=float(contract.fte_percentage) if contract else 100.0,
        cost_centre=contract.cost_centre if contract else None,
        payroll_number=contract.payroll_number if contract else None,
        overtime_eligible=contract.overtime_eligible if contract else True,
        night_shift_eligible=contract.night_shift_eligible if contract else True,
        standby_eligible=contract.standby_eligible if contract else True,
        work_pattern_code=getattr(work_pattern, "code", None),
        work_pattern_name=getattr(work_pattern, "name", None),
        work_pattern_effective_from=pattern.effective_from if pattern else None,
        pattern_state=pattern_state,
        active_leave_status=_value(leave.status) if leave else None,
        readiness_state=state,
        readiness_reasons=reasons,
    )


def _apply_automatic_pattern_readiness(
    db: Session,
    *,
    amo_id: str,
    on_date: date,
    items: list[hr_schemas.HrPersonReadiness],
) -> set[str]:
    """Annotate people resolved by a scoped rule when no explicit override exists."""
    candidates = [item.user_id for item in items if item.pattern_state == "MISSING"]
    if not candidates:
        return set()
    preview = services.preview_patterns(
        db,
        amo_id=amo_id,
        payload=schemas.PatternPreviewRequest(
            from_date=on_date,
            to_date=on_date,
            user_ids=candidates,
        ),
    )
    rule_rows = {
        str(row.user_id): row
        for row in preview.items
        if row.resolution_source == "RULE" and row.pattern_id
    }
    if not rule_rows:
        return set()
    names = {
        str(pattern.id): pattern.name
        for pattern in db.query(models.WorkPattern).filter(
            models.WorkPattern.amo_id == amo_id,
            models.WorkPattern.id.in_({str(row.pattern_id) for row in rule_rows.values()}),
        ).all()
    }
    resolved: set[str] = set()
    for item in items:
        row = rule_rows.get(item.user_id)
        if row is None:
            continue
        item.work_pattern_code = row.pattern_code
        item.work_pattern_name = names.get(str(row.pattern_id), row.pattern_code)
        item.pattern_state = "ASSIGNED"
        item.readiness_reasons = [
            reason for reason in item.readiness_reasons
            if reason != "No active work pattern is assigned."
        ]
        if "AMBIGUOUS_PATTERN_RULE" in row.conflicts:
            item.readiness_reasons.append("Multiple automatic work-pattern rules match this employee.")
        if item.employment_status == models.EmploymentStatus.SUSPENDED.value:
            item.readiness_state = "BLOCKED"
        else:
            item.readiness_state = "NEEDS_ATTENTION" if item.readiness_reasons else "READY"
        resolved.add(item.user_id)
    return resolved


def list_people_page_v2(
    db: Session,
    *,
    amo_id: str,
    page: int = 1,
    page_size: int = 100,
    search: Optional[str] = None,
) -> hr_schemas.HrPeoplePage:
    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()
    now = _utcnow()
    users = _active_tenant_users(db, amo_id=amo_id)
    user_ids = [str(user.id) for user in users]
    contracts = _readiness_contracts_by_user(
        db, amo_id=amo_id, user_ids=user_ids, on_date=today
    )
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)
    hire_dates = services.hire_dates_by_user(db, amo_id=amo_id, user_ids=user_ids)
    items = [
        _person_readiness_for_user(
            user,
            amo_id=amo_id,
            contract=contracts.get(str(user.id)),
            pattern=patterns.get(str(user.id)),
            leave=leave_by_user.get(str(user.id)),
            on_date=today,
            hire_date=hire_dates.get(str(user.id)),
        )
        for user in users
    ]
    _apply_automatic_pattern_readiness(
        db,
        amo_id=amo_id,
        on_date=today,
        items=items,
    )
    needle = str(search or "").strip().lower()
    if needle:
        items = [
            item for item in items
            if any(
                needle in str(value or "").lower()
                for value in (
                    item.full_name,
                    item.email,
                    item.staff_code,
                    item.position_title,
                    item.department_code,
                    item.primary_base_code,
                    item.payroll_number,
                )
            )
        ]
    items.sort(key=lambda item: (
        item.has_effective_contract,
        item.readiness_state == "READY",
        item.full_name.lower(),
        item.user_id,
    ))
    total = len(items)
    safe_page_size = max(1, min(int(page_size), 200))
    pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    safe_page = max(1, int(page))
    start = (safe_page - 1) * safe_page_size
    return hr_schemas.HrPeoplePage(
        items=items[start:start + safe_page_size],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
        pages=pages,
    )


def dashboard_v2(
    db: Session,
    *,
    amo_id: str,
    current_user: account_models.User,
    people_limit: int = 200,
) -> hr_schemas.HrDashboardResponse:
    response = dashboard(
        db,
        amo_id=amo_id,
        current_user=current_user,
        people_limit=people_limit,
    )
    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()
    now = _utcnow()
    users = _active_tenant_users(db, amo_id=amo_id)
    user_ids = [str(user.id) for user in users]
    current_contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    contracts = _readiness_contracts_by_user(
        db, amo_id=amo_id, user_ids=user_ids, on_date=today
    )
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)
    hire_dates = services.hire_dates_by_user(db, amo_id=amo_id, user_ids=user_ids)
    people = [
        _person_readiness_for_user(
            user,
            amo_id=amo_id,
            contract=contracts.get(str(user.id)),
            pattern=patterns.get(str(user.id)),
            leave=leave_by_user.get(str(user.id)),
            on_date=today,
            hire_date=hire_dates.get(str(user.id)),
        )
        for user in users
    ]
    automatically_patterned = _apply_automatic_pattern_readiness(
        db,
        amo_id=amo_id,
        on_date=today,
        items=people,
    )
    people.sort(key=lambda item: (
        item.has_effective_contract,
        item.readiness_state == "READY",
        item.full_name.lower(),
        item.user_id,
    ))
    without_effective_contract = [
        user for user in users if str(user.id) not in current_contracts
    ]
    without_any_contract = [
        user for user in users if str(user.id) not in contracts
    ]
    future_contract_users = [
        user for user in without_effective_contract
        if str(user.id) in contracts
    ]
    without_pattern = [
        user for user in users
        if str(user.id) not in automatically_patterned
        and (not (assignment := patterns.get(str(user.id)))
        or not assignment.work_pattern
        or not assignment.work_pattern.is_active)
    ]
    without_base = [
        user for user in users
        if (contract := contracts.get(str(user.id))) is not None and not contract.primary_base_station_id
    ]

    response.active_employee_count = len(users)
    response.employees_without_contract_count = len(without_effective_contract)
    response.onboarding_employee_count = sum(
        1 for contract in current_contracts.values()
        if _value(contract.employment_status) == models.EmploymentStatus.ONBOARDING.value
    )
    response.suspended_employee_count = sum(
        1 for contract in current_contracts.values()
        if _value(contract.employment_status) == models.EmploymentStatus.SUSPENDED.value
    )
    response.employees_without_pattern_count = len(without_pattern)
    response.employees_without_base_count = len(without_base)
    response.people = people[:people_limit]
    # The former tenant-wide DAY bootstrap is retired. Automatic assignment is
    # now enabled only on an explicitly scoped work-pattern rule.
    response.can_initialize_default_day_pattern = False

    metric_by_key = {metric.key: metric for metric in response.metrics}
    if "active" in metric_by_key:
        metric_by_key["active"].value = len(users)
        metric_by_key["active"].detail = "Active tenant user accounts"
    if "patterns" in metric_by_key:
        metric_by_key["patterns"].value = len(without_pattern)
        metric_by_key["patterns"].detail = "Active users without a current pattern"
        metric_by_key["patterns"].tone = "danger" if without_pattern else "good"
    response.metrics.insert(1, hr_schemas.HrMetric(
        key="contract_gaps",
        label="Contract gaps",
        value=len(without_effective_contract),
        detail="Active users without a currently effective contract",
        tone="danger" if without_effective_contract else "good",
    ))

    missing_contract_actions = [
        hr_schemas.HrActionItem(
            id=f"contract-missing:{user.id}",
            category="CONTRACT",
            severity="BLOCKER",
            title="Employment contract missing",
            detail="This active tenant user cannot be rostered until an effective Workforce contract is created.",
            user_id=str(user.id),
            user_name=_display_name(user),
            action_label="Create contract",
            action_path=f"people/{user.id}?section=contract",
        )
        for user in without_any_contract[:50]
    ]
    future_contract_actions = [
        hr_schemas.HrActionItem(
            id=f"contract-future:{user.id}",
            category="CONTRACT",
            severity="WARNING",
            title="Employment contract not yet effective",
            detail=(
                "This active tenant user remains in the effective-contract gap until "
                f"{contracts[str(user.id)].effective_from.isoformat()}."
            ),
            user_id=str(user.id),
            user_name=_display_name(user),
            action_label="Edit future contract",
            action_path=f"people/{user.id}?section=contract",
        )
        for user in future_contract_users[:50]
    ]
    response.action_queue = (
        missing_contract_actions
        + future_contract_actions
        + list(response.action_queue)
    )[:100]
    return response


_DEFAULT_DAY_SHIFT_CODE = "DEFAULT-DAY"
_DEFAULT_DAY_PATTERN_CODE = "DEFAULT-DAY-5X2"
_DEFAULT_DAY_SHIFT_KEY = "workforce.default-day.shift.v1"
_DEFAULT_DAY_PATTERN_KEY = "workforce.default-day.pattern.v1"


def _default_day_system_id(*, amo_id: str, system_key: str) -> str:
    """Return the immutable tenant-scoped identity for a portal-owned baseline."""
    return str(uuid5(NAMESPACE_URL, f"amo-portal:{amo_id}:{system_key}"))


def _resolve_existing_day_shift(db: Session, *, amo_id: str):
    """Reuse tenant configuration; never manufacture a hidden DEFAULT-DAY shift."""
    from ..rostering import models as roster_models

    system_id = _default_day_system_id(amo_id=amo_id, system_key=_DEFAULT_DAY_SHIFT_KEY)
    rows = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.kind == roster_models.ShiftTemplateKind.DAY,
        roster_models.ShiftTemplate.counts_as_duty.is_(True),
        roster_models.ShiftTemplate.is_active.is_(True),
    ).with_for_update().all()
    if not rows:
        raise ValueError(
            "Create or activate a day-duty shift in Roster setup before assigning a default work pattern"
        )
    legacy = next((row for row in rows if str(row.id) == system_id), None)
    if legacy is not None:
        return legacy
    legacy = next((row for row in rows if str(row.code or "").strip().upper() == _DEFAULT_DAY_SHIFT_CODE), None)
    if legacy is not None:
        return legacy
    return sorted(
        rows,
        key=lambda row: (
            0 if str(row.code or "").strip().upper() == "D" else 1,
            0 if len(str(row.code or "").strip()) <= 2 else 1,
            0 if str(row.default_start_time or "")[:5] == "08:00" and str(row.default_end_time or "")[:5] == "17:00" else 1,
            int(row.display_order or 0),
            str(row.code or ""),
        ),
    )[0]


def _work_pattern_snapshot(db: Session, row: models.WorkPattern) -> dict:
    days = db.query(models.WorkPatternDay).filter(
        models.WorkPatternDay.amo_id == row.amo_id,
        models.WorkPatternDay.work_pattern_id == row.id,
    ).order_by(models.WorkPatternDay.cycle_day_index.asc(), models.WorkPatternDay.id.asc()).all()
    return {
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "cycle_length_days": row.cycle_length_days,
        "is_active": bool(row.is_active),
        "timezone_name": row.timezone_name,
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "days": [
            {
                "cycle_day_index": day.cycle_day_index,
                "shift_template_id": day.shift_template_id,
                "status": _value(day.status),
                "start_time_local": day.start_time_local,
                "end_time_local": day.end_time_local,
                "spans_next_day": bool(day.spans_next_day),
                "planned_minutes": day.planned_minutes,
            }
            for day in days
        ],
    }


def _pattern_assignment_snapshot(row: models.EmployeeWorkPatternAssignment) -> dict:
    return {
        "user_id": str(row.user_id),
        "work_pattern_id": str(row.work_pattern_id),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
    }


def _bootstrap_audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    operation_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Write required bootstrap evidence in the same authoritative transaction."""
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            correlation_id=operation_id,
            metadata={
                "module": "workforce",
                "operation": "DEFAULT_DAY_BOOTSTRAP",
                "system_owned": True,
                **(metadata or {}),
            },
        ),
    )


def bootstrap_default_day_pattern(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> hr_schemas.HrDefaultDayBootstrapResponse:
    """Build the managed pattern from an existing tenant day shift and assign it safely."""

    amo = db.query(account_models.AMO).filter(
        account_models.AMO.id == amo_id,
    ).with_for_update().one()
    timezone_name = str(amo.time_zone or "UTC")
    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()
    week_monday = today - timedelta(days=today.weekday())
    operation_id = str(uuid4())

    shift = _resolve_existing_day_shift(db, amo_id=amo_id)

    pattern_id = _default_day_system_id(amo_id=amo_id, system_key=_DEFAULT_DAY_PATTERN_KEY)
    pattern_by_code = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.code == _DEFAULT_DAY_PATTERN_CODE,
    ).with_for_update().first()
    pattern = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.id == pattern_id,
    ).with_for_update().first()
    if pattern_by_code is not None and str(pattern_by_code.id) != pattern_id:
        raise ValueError(
            "Reserved work-pattern code DEFAULT-DAY-5X2 is already owned by tenant configuration; "
            "rename that pattern before applying the managed default-day baseline."
        )
    if pattern is not None and pattern_by_code is not None and str(pattern.id) != str(pattern_by_code.id):
        raise ValueError("Managed default-day pattern identity conflicts with the reserved code")

    pattern_before = _work_pattern_snapshot(db, pattern) if pattern is not None else None
    if pattern is None:
        pattern = models.WorkPattern(
            id=pattern_id,
            amo_id=amo_id,
            code=_DEFAULT_DAY_PATTERN_CODE,
            name="Default day shift · Monday to Friday",
            description=(
                "Portal-managed five-day baseline followed by two days off. "
                "This is visible draft input, not a published roster."
            ),
            cycle_length_days=7,
            is_active=True,
            timezone_name=timezone_name,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(pattern)
        db.flush()
    else:
        pattern.code = _DEFAULT_DAY_PATTERN_CODE
        pattern.name = "Default day shift · Monday to Friday"
        pattern.description = (
            "Portal-managed five-day baseline followed by two days off. "
            "This is visible draft input, not a published roster."
        )
        pattern.cycle_length_days = 7
        pattern.is_active = True
        pattern.timezone_name = timezone_name
        pattern.updated_by_user_id = actor_user_id
        db.add(pattern)
        db.flush()

    existing_days = db.query(models.WorkPatternDay).filter(
        models.WorkPatternDay.amo_id == amo_id,
        models.WorkPatternDay.work_pattern_id == pattern.id,
    ).order_by(models.WorkPatternDay.cycle_day_index.asc(), models.WorkPatternDay.id.asc()).all()
    days_by_index = {int(row.cycle_day_index): row for row in existing_days if 0 <= int(row.cycle_day_index) < 7}
    for extra_day in existing_days:
        if int(extra_day.cycle_day_index) not in range(7):
            db.delete(extra_day)
    for day_index in range(7):
        duty = day_index < 5
        day = days_by_index.get(day_index)
        if day is None:
            day = models.WorkPatternDay(
                amo_id=amo_id,
                work_pattern_id=pattern.id,
                cycle_day_index=day_index,
            )
        day.shift_template_id = shift.id if duty else None
        day.status = models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF
        day.start_time_local = "08:00" if duty else None
        day.end_time_local = "17:00" if duty else None
        day.spans_next_day = False
        day.planned_minutes = 480 if duty else 0
        db.add(day)
    db.flush()
    pattern_after = _work_pattern_snapshot(db, pattern)
    if pattern_before != pattern_after:
        _bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="WorkPattern",
            entity_id=str(pattern.id),
            action="bootstrap_create" if pattern_before is None else "bootstrap_update",
            before=pattern_before,
            after=pattern_after,
            metadata={"system_key": _DEFAULT_DAY_PATTERN_KEY},
        )

    users = _active_tenant_users(db, amo_id=amo_id)
    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    eligible_users = [
        user for user in users
        if (contract := contracts.get(str(user.id))) is not None
        and _value(contract.employment_status) in {
            models.EmploymentStatus.ACTIVE.value,
            models.EmploymentStatus.ONBOARDING.value,
        }
    ]
    current_rows = db.query(models.EmployeeWorkPatternAssignment).options(
        joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_([str(user.id) for user in eligible_users] or ["__none__"]),
        models.EmployeeWorkPatternAssignment.effective_from <= today,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= today,
        ),
    ).with_for_update(of=models.EmployeeWorkPatternAssignment).all()
    occupied = {str(row.user_id): row for row in current_rows}

    assigned = 0
    already_assigned = 0
    skipped_conflict = 0
    for user in eligible_users:
        current = occupied.get(str(user.id))
        current_has_active_pattern = bool(
            current and current.work_pattern and current.work_pattern.is_active
        )
        current_is_reserved_default = bool(
            current_has_active_pattern and str(current.work_pattern_id) == str(pattern.id)
        )
        current_default_anchor_is_monday = bool(
            current_is_reserved_default
            and current.cycle_anchor_date
            and current.cycle_anchor_date.weekday() == 0
        )
        if current_has_active_pattern and (
            not current_is_reserved_default or current_default_anchor_is_monday
        ):
            already_assigned += 1
            continue

        future = db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            models.EmployeeWorkPatternAssignment.user_id == user.id,
            models.EmployeeWorkPatternAssignment.effective_from > today,
        ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).with_for_update().first()
        effective_to = future.effective_from - timedelta(days=1) if future else None
        if effective_to is not None and effective_to < today:
            skipped_conflict += 1
            continue

        if current is not None:
            current_before = _pattern_assignment_snapshot(current)
            if current.effective_from < today:
                current.effective_to = today - timedelta(days=1)
                db.add(current)
                db.flush()
                _bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=str(current.id),
                    action="bootstrap_close",
                    before=current_before,
                    after=_pattern_assignment_snapshot(current),
                    metadata={"user_id": str(user.id), "replacement_pattern_id": str(pattern.id)},
                )
            else:
                current_id = str(current.id)
                db.delete(current)
                db.flush()
                _bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=current_id,
                    action="bootstrap_delete",
                    before=current_before,
                    after=None,
                    metadata={"user_id": str(user.id), "replacement_pattern_id": str(pattern.id)},
                )

        created = models.EmployeeWorkPatternAssignment(
            amo_id=amo_id,
            user_id=user.id,
            work_pattern_id=pattern.id,
            effective_from=today,
            effective_to=effective_to,
            cycle_anchor_date=week_monday,
            created_by_user_id=actor_user_id,
        )
        db.add(created)
        db.flush()
        _bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="EmployeeWorkPatternAssignment",
            entity_id=str(created.id),
            action="bootstrap_assign",
            after=_pattern_assignment_snapshot(created),
            metadata={"user_id": str(user.id), "system_key": _DEFAULT_DAY_PATTERN_KEY},
        )
        assigned += 1

    db.flush()
    return hr_schemas.HrDefaultDayBootstrapResponse(
        shift_template_id=shift.id,
        work_pattern_id=pattern.id,
        eligible_user_count=len(eligible_users),
        assigned_user_count=assigned,
        already_assigned_count=already_assigned,
        skipped_conflict_count=skipped_conflict,
    )
