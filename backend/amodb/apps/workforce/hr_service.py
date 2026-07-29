"""Canonical HR dashboard assembled from Workforce-owned records.

This service intentionally does not duplicate identity, contract, leave,
attendance, timesheet, overtime, base or work-pattern data. It presents those
source records as one actionable HR workspace.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..accounts import models as account_models
from . import hr_schemas, models, permissions


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
    actions.sort(key=lambda item: (
        0 if item.severity == "BLOCKER" else 1 if item.severity == "ACTION" else 2,
        item.due_on or date.max,
        item.id,
    ))

    metrics = [
        hr_schemas.HrMetric(key="active", label="Active employees", value=active_count, detail="Effective active contracts", tone="good"),
        hr_schemas.HrMetric(key="onboarding", label="Onboarding", value=onboarding_count, detail="Not yet fully active", tone="info"),
        hr_schemas.HrMetric(key="leave", label="Leave approvals", value=len(pending_leave_rows), detail="Supervisor or HR action", tone="warning" if pending_leave_rows else "neutral"),
        hr_schemas.HrMetric(key="time", label="Time approvals", value=len(pending_timesheet_rows), detail="Submitted timesheets", tone="warning" if pending_timesheet_rows else "neutral"),
        hr_schemas.HrMetric(key="patterns", label="Pattern gaps", value=len(without_pattern), detail="Cannot be auto-rotated", tone="danger" if without_pattern else "good"),
        hr_schemas.HrMetric(key="contracts", label="Expiring contracts", value=len(expiring_rows), detail="Within 60 days", tone="warning" if expiring_rows else "neutral"),
    ]

    can_manage_contracts = permissions.has_permission(
        db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS
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
        can_manage_leave_balances=can_manage_leave_balances,
        can_review_leave=can_review_leave,
        can_approve_leave=can_approve_leave,
        can_approve_timesheet_supervisor=can_approve_timesheet_supervisor,
        can_approve_timesheet_hr=can_approve_timesheet_hr,
        can_export_payroll=can_export_payroll,
        active_employee_count=active_count,
        onboarding_employee_count=onboarding_count,
        suspended_employee_count=suspended_count,
        contracts_expiring_soon_count=len(expiring_rows),
        employees_without_pattern_count=len(without_pattern),
        employees_without_base_count=len(without_base),
        pending_leave_count=len(pending_leave_rows),
        pending_timesheet_count=len(pending_timesheet_rows),
        pending_overtime_count=len(pending_overtime_rows),
        attendance_exception_count=len(attendance_exception_rows),
        metrics=metrics,
        action_queue=actions[:100],
        people=people,
    )
