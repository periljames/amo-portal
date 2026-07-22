# backend/amodb/apps/rostering/planning.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..fleet import models as fleet_models
from ..foundations import models as foundation_models
from ..training import compliance as training_compliance
from ..work import models as work_models
from ..workforce import models as workforce_models
from ..workforce import services as workforce_services
from . import assignments as assignment_services
from . import catalog, common, models, schemas

UTC = timezone.utc

OPEN_TASK_STATUSES = {
    work_models.TaskStatusEnum.PLANNED,
    work_models.TaskStatusEnum.IN_PROGRESS,
    work_models.TaskStatusEnum.INSPECTED,
    work_models.TaskStatusEnum.PAUSED,
    work_models.TaskStatusEnum.DEFERRED,
}
OPEN_WORK_ORDER_STATUSES = {
    work_models.WorkOrderStatusEnum.DRAFT,
    work_models.WorkOrderStatusEnum.RELEASED,
    work_models.WorkOrderStatusEnum.IN_PROGRESS,
    work_models.WorkOrderStatusEnum.INSPECTED,
}


def _period_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    if to_date < from_date:
        raise ValueError("to date must be on or after from date")
    return (
        datetime.combine(from_date, time.min, tzinfo=UTC),
        datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC),
    )


def published_assignments(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    user_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
    department_id: Optional[str] = None,
) -> list[models.RosterAssignment]:
    start_dt, end_dt = _period_bounds(from_date, to_date)
    query = db.query(models.RosterAssignment).join(
        models.RosterVersion,
        models.RosterAssignment.version_id == models.RosterVersion.id,
    ).options(
        selectinload(models.RosterAssignment.user),
        selectinload(models.RosterAssignment.department),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.task_links).selectinload(models.RosterTaskAssignmentLink.task_assignment),
    ).filter(
        models.RosterAssignment.amo_id == amo_id,
        models.RosterAssignment.deleted_at.is_(None),
        models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
        models.RosterAssignment.starts_at < end_dt,
        models.RosterAssignment.ends_at > start_dt,
    )
    if user_id:
        query = query.filter(models.RosterAssignment.user_id == user_id)
    if base_station_id:
        query = query.filter(models.RosterAssignment.base_station_id == base_station_id)
    if department_id:
        query = query.filter(models.RosterAssignment.department_id == department_id)
    return query.order_by(models.RosterAssignment.starts_at.asc(), models.RosterAssignment.user_id.asc(), models.RosterAssignment.id.asc()).all()


def _training_due_next_month(db: Session, *, user: account_models.User, base_date: date) -> list[dict[str, Any]]:
    next_month_start = (base_date.replace(day=1) + timedelta(days=32)).replace(day=1)
    following_month_start = (next_month_start + timedelta(days=32)).replace(day=1)
    try:
        courses = training_compliance.get_courses_for_user(db, user, required_only=True)
        latest = training_compliance._latest_records_for_user(db, user, [course.id for course in courses])
    except Exception:
        return []
    due: list[dict[str, Any]] = []
    for course in courses:
        row = latest.get(course.id)
        valid_until = getattr(row, "valid_until", None) if row else None
        if valid_until and next_month_start <= valid_until < following_month_start:
            due.append({"course_id": course.course_id, "course_name": course.course_name, "valid_until": valid_until.isoformat()})
    return sorted(due, key=lambda item: (item["valid_until"], item["course_name"]))


def my_roster(
    db: Session,
    *,
    amo_id: str,
    user: account_models.User,
    from_date: date,
    to_date: date,
) -> schemas.MyRosterResponse:
    rows = published_assignments(db, amo_id=amo_id, from_date=from_date, to_date=to_date, user_id=user.id)
    leaves = db.query(workforce_models.LeaveRequest).options(selectinload(workforce_models.LeaveRequest.leave_type)).filter(
        workforce_models.LeaveRequest.amo_id == amo_id,
        workforce_models.LeaveRequest.user_id == user.id,
        workforce_models.LeaveRequest.status.notin_([
            workforce_models.LeaveRequestStatus.REJECTED,
            workforce_models.LeaveRequestStatus.CANCELLED,
            workforce_models.LeaveRequestStatus.RECALLED,
        ]),
        workforce_models.LeaveRequest.starts_at < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC),
        workforce_models.LeaveRequest.ends_at > datetime.combine(from_date, time.min, tzinfo=UTC),
    ).order_by(workforce_models.LeaveRequest.starts_at.asc()).all()
    published_version_ids = sorted({row.version_id for row in rows})
    acknowledged = {
        row[0]
        for row in db.query(models.RosterPublicationAcknowledgement.version_id).filter(
            models.RosterPublicationAcknowledgement.amo_id == amo_id,
            models.RosterPublicationAcknowledgement.user_id == user.id,
            models.RosterPublicationAcknowledgement.version_id.in_(published_version_ids or ["__none__"]),
        ).all()
    }
    return schemas.MyRosterResponse(
        user_id=user.id,
        from_date=from_date,
        to_date=to_date,
        assignments=[common.serialize_assignment(row) for row in rows],
        training_due_next_month=_training_due_next_month(db, user=user, base_date=from_date),
        leave_requests=[{
            "id": row.id,
            "leave_type": getattr(row.leave_type, "name", None),
            "starts_at": row.starts_at.isoformat(),
            "ends_at": row.ends_at.isoformat(),
            "status": common.enum_value(row.status),
        } for row in leaves],
        acknowledgement_required_version_ids=[version_id for version_id in published_version_ids if version_id not in acknowledged],
    )


def _base_maps(db: Session, *, amo_id: str) -> tuple[dict[str, foundation_models.BaseStation], dict[str, foundation_models.BaseStation]]:
    rows = db.query(foundation_models.BaseStation).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.is_active.is_(True),
    ).order_by(foundation_models.BaseStation.code.asc()).all()
    by_id = {row.id: row for row in rows}
    by_code: dict[str, foundation_models.BaseStation] = {}
    for row in rows:
        for value in (row.code, row.icao_code, row.iata_code):
            if value:
                by_code[str(value).strip().upper()] = row
    return by_id, by_code


def _task_cards(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    base_station_id: Optional[str],
    base_by_id: dict[str, foundation_models.BaseStation],
) -> list[work_models.TaskCard]:
    start_dt, end_dt = _period_bounds(from_date, to_date)
    query = db.query(work_models.TaskCard).join(
        work_models.WorkOrder,
        work_models.TaskCard.work_order_id == work_models.WorkOrder.id,
    ).join(
        fleet_models.Aircraft,
        work_models.WorkOrder.aircraft_serial_number == fleet_models.Aircraft.serial_number,
    ).options(
        selectinload(work_models.TaskCard.work_order).selectinload(work_models.WorkOrder.aircraft),
        selectinload(work_models.TaskCard.assignments),
    ).filter(
        work_models.TaskCard.amo_id == amo_id,
        work_models.TaskCard.status.in_(OPEN_TASK_STATUSES),
        work_models.WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES),
        or_(
            and_(work_models.TaskCard.planned_start.isnot(None), work_models.TaskCard.planned_start < end_dt, or_(work_models.TaskCard.planned_end.is_(None), work_models.TaskCard.planned_end > start_dt)),
            and_(work_models.WorkOrder.due_date.isnot(None), work_models.WorkOrder.due_date >= from_date, work_models.WorkOrder.due_date <= to_date),
        ),
    )
    if base_station_id:
        base = base_by_id.get(base_station_id)
        if not base:
            return []
        codes = [value for value in {base.code, base.icao_code, base.iata_code} if value]
        query = query.filter(fleet_models.Aircraft.home_base.in_(codes))
    return query.order_by(work_models.TaskCard.planned_start.asc().nullslast(), work_models.TaskCard.priority.asc(), work_models.TaskCard.id.asc()).all()


def _task_links_for_assignments(db: Session, *, amo_id: str, assignment_ids: Sequence[str]) -> list[models.RosterTaskAssignmentLink]:
    if not assignment_ids:
        return []
    return db.query(models.RosterTaskAssignmentLink).options(
        selectinload(models.RosterTaskAssignmentLink.roster_assignment).selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterTaskAssignmentLink.task_assignment).selectinload(work_models.TaskAssignment.task).selectinload(work_models.TaskCard.work_order).selectinload(work_models.WorkOrder.aircraft),
    ).filter(
        models.RosterTaskAssignmentLink.amo_id == amo_id,
        models.RosterTaskAssignmentLink.roster_assignment_id.in_(assignment_ids),
    ).order_by(models.RosterTaskAssignmentLink.created_at.asc(), models.RosterTaskAssignmentLink.id.asc()).all()


def _task_summaries(
    tasks: Sequence[work_models.TaskCard],
    links: Sequence[models.RosterTaskAssignmentLink],
    *,
    base_by_code: dict[str, foundation_models.BaseStation],
) -> tuple[list[schemas.WorkloadTaskSummary], list[schemas.WorkloadWorkOrderSummary]]:
    linked_hours_by_task: dict[int, float] = defaultdict(float)
    linked_count_by_task: dict[int, int] = defaultdict(int)
    for link in links:
        task = getattr(getattr(link, "task_assignment", None), "task", None)
        if task:
            linked_hours_by_task[task.id] += common.task_link_hours(link)
            linked_count_by_task[task.id] += 1
    task_rows: list[schemas.WorkloadTaskSummary] = []
    work_order_groups: dict[int, list[schemas.WorkloadTaskSummary]] = defaultdict(list)
    work_order_objects: dict[int, work_models.WorkOrder] = {}
    for task in tasks:
        work_order = task.work_order
        aircraft = getattr(work_order, "aircraft", None)
        base = base_by_code.get(str(getattr(aircraft, "home_base", "") or "").strip().upper())
        estimate = float(task.estimated_manhours or 0.0)
        assigned_hours = sum(max(float(row.allocated_hours or 0.0), 0.0) for row in task.assignments or [])
        linked_hours = linked_hours_by_task.get(task.id, 0.0)
        remaining = max(estimate - max(assigned_hours, linked_hours), 0.0)
        row = schemas.WorkloadTaskSummary(
            task_id=task.id,
            work_order_id=work_order.id,
            wo_number=work_order.wo_number,
            aircraft_serial_number=work_order.aircraft_serial_number,
            aircraft_registration=getattr(aircraft, "registration", None),
            aircraft_model=getattr(aircraft, "model", None),
            base_station_id=getattr(base, "id", None),
            base_code=getattr(base, "code", None),
            base_name=getattr(base, "name", None),
            task_code=task.task_code,
            title=task.title,
            priority=common.enum_value(task.priority),
            status=common.enum_value(task.status),
            planned_start=task.planned_start,
            planned_end=task.planned_end,
            estimated_manhours=task.estimated_manhours,
            task_assigned_hours=round(assigned_hours, 2),
            roster_linked_hours=round(linked_hours, 2),
            remaining_manhours=round(remaining, 2),
            task_assignment_count=len(task.assignments or []),
            roster_link_count=linked_count_by_task.get(task.id, 0),
            has_estimate=task.estimated_manhours is not None,
            is_unplanned=task.planned_start is None,
            can_allocate=remaining > 0 or task.estimated_manhours is None,
        )
        task_rows.append(row)
        work_order_groups[work_order.id].append(row)
        work_order_objects[work_order.id] = work_order
    work_order_rows: list[schemas.WorkloadWorkOrderSummary] = []
    for work_order_id, grouped in sorted(work_order_groups.items(), key=lambda item: (work_order_objects[item[0]].due_date or date.max, work_order_objects[item[0]].wo_number)):
        work_order = work_order_objects[work_order_id]
        aircraft = getattr(work_order, "aircraft", None)
        base = base_by_code.get(str(getattr(aircraft, "home_base", "") or "").strip().upper())
        work_order_rows.append(schemas.WorkloadWorkOrderSummary(
            work_order_id=work_order.id,
            wo_number=work_order.wo_number,
            description=work_order.description,
            check_type=work_order.check_type,
            status=common.enum_value(work_order.status),
            due_date=work_order.due_date,
            aircraft_serial_number=work_order.aircraft_serial_number,
            aircraft_registration=getattr(aircraft, "registration", None),
            aircraft_model=getattr(aircraft, "model", None),
            base_station_id=getattr(base, "id", None),
            base_code=getattr(base, "code", None),
            base_name=getattr(base, "name", None),
            open_task_count=len(grouped),
            estimated_manhours=round(sum(float(row.estimated_manhours or 0.0) for row in grouped), 2),
            task_assigned_hours=round(sum(row.task_assigned_hours for row in grouped), 2),
            roster_linked_hours=round(sum(row.roster_linked_hours for row in grouped), 2),
            remaining_manhours=round(sum(row.remaining_manhours for row in grouped), 2),
        ))
    return task_rows, work_order_rows


def _published_findings(db: Session, *, amo_id: str, version_ids: Sequence[str]) -> list[models.RosterValidationFinding]:
    if not version_ids:
        return []
    return db.query(models.RosterValidationFinding).filter(
        models.RosterValidationFinding.amo_id == amo_id,
        models.RosterValidationFinding.version_id.in_(version_ids),
    ).order_by(models.RosterValidationFinding.sort_order.asc(), models.RosterValidationFinding.severity.asc(), models.RosterValidationFinding.code.asc(), models.RosterValidationFinding.id.asc()).all()


def planning_board(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    base_station_id: Optional[str] = None,
    department_id: Optional[str] = None,
) -> schemas.RosterPlanningBoardResponse:
    assignments = published_assignments(db, amo_id=amo_id, from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id)
    version_ids = sorted({row.version_id for row in assignments})
    findings = _published_findings(db, amo_id=amo_id, version_ids=version_ids)
    links = _task_links_for_assignments(db, amo_id=amo_id, assignment_ids=[row.id for row in assignments])
    base_by_id, base_by_code = _base_maps(db, amo_id=amo_id)
    tasks = _task_cards(db, amo_id=amo_id, from_date=from_date, to_date=to_date, base_station_id=base_station_id, base_by_id=base_by_id)
    task_rows, work_order_rows = _task_summaries(tasks, links, base_by_code=base_by_code)
    demands = catalog.list_demand_requirements(db, amo_id=amo_id, from_date=from_date, to_date=to_date, base_station_id=base_station_id, department_id=department_id)

    base_assignment_groups: dict[Optional[str], list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        base_assignment_groups[row.base_station_id].append(row)
    task_by_base: dict[Optional[str], list[schemas.WorkloadTaskSummary]] = defaultdict(list)
    for row in task_rows:
        task_by_base[row.base_station_id].append(row)
    demand_by_base: dict[Optional[str], list[models.RosterDemandRequirement]] = defaultdict(list)
    for row in demands:
        demand_by_base[row.base_station_id].append(row)
    base_ids = sorted(set(base_assignment_groups) | set(task_by_base) | set(demand_by_base), key=lambda value: (getattr(base_by_id.get(value), "code", "UNASSIGNED"), value or ""))
    base_capacity: list[schemas.BaseCapacitySummary] = []
    for base_id in base_ids:
        base = base_by_id.get(base_id)
        roster_rows = base_assignment_groups.get(base_id, [])
        task_group = task_by_base.get(base_id, [])
        demand_group = demand_by_base.get(base_id, [])
        productive = [row for row in roster_rows if row.status == models.RosterAssignmentStatus.DUTY]
        standby = [row for row in roster_rows if row.status == models.RosterAssignmentStatus.STANDBY]
        people = {row.user_id for row in roster_rows}
        certifying = {row.user_id for row in roster_rows if row.user and row.user.role in {account_models.AccountRole.CERTIFYING_ENGINEER, account_models.AccountRole.CERTIFYING_TECHNICIAN}}
        technicians = {row.user_id for row in roster_rows if row.user and row.user.role == account_models.AccountRole.TECHNICIAN}
        available_hours = sum(common.assignment_hours(row) for row in productive)
        standby_hours = sum(common.assignment_hours(row) for row in standby)
        linked_hours = sum(common.task_link_hours(link) for link in links if link.roster_assignment and link.roster_assignment.base_station_id == base_id)
        required_hours = sum(row.remaining_manhours for row in task_group)
        required_headcount = max((row.required_headcount for row in demand_group), default=0)
        base_capacity.append(schemas.BaseCapacitySummary(
            base_station_id=base_id,
            base_code=getattr(base, "code", "UNASSIGNED"),
            base_name=getattr(base, "name", "Unassigned"),
            assigned_people=len(people),
            certifying_people=len(certifying),
            technician_people=len(technicians),
            duty_assignment_count=len(productive),
            available_hours=round(available_hours, 2),
            standby_hours=round(standby_hours, 2),
            roster_linked_hours=round(linked_hours, 2),
            remaining_capacity_hours=round(max(available_hours - linked_hours, 0.0), 2),
            required_task_hours=round(required_hours, 2),
            task_assigned_hours=round(sum(row.task_assigned_hours for row in task_group), 2),
            remaining_task_hours=round(required_hours, 2),
            capacity_gap_hours=round(max(required_hours - max(available_hours - linked_hours, 0.0), 0.0), 2),
            capacity_variance_hours=round((available_hours - linked_hours) - required_hours, 2),
            open_task_count=len(task_group),
            unallocated_task_count=sum(1 for row in task_group if row.roster_link_count == 0),
            missing_estimate_count=sum(1 for row in task_group if not row.has_estimate),
            required_headcount=required_headcount,
            headcount_gap=max(required_headcount - len(people), 0),
        ))

    available_hours = sum(row.available_hours for row in base_capacity)
    linked_hours = sum(row.roster_linked_hours for row in base_capacity)
    required_hours = sum(row.required_task_hours for row in base_capacity)
    blocker_count = sum(1 for row in findings if row.severity == models.RosterValidationSeverity.BLOCKER and not row.resolved)
    warning_count = sum(1 for row in findings if row.severity == models.RosterValidationSeverity.WARNING and not row.resolved)
    leave_conflicts = sum(1 for row in findings if row.code == "BLOCKING_AVAILABILITY_CONFLICT")
    assigned_user_ids = sorted({row.user_id for row in assignments})
    acknowledgement_count = db.query(models.RosterPublicationAcknowledgement.id).filter(
        models.RosterPublicationAcknowledgement.amo_id == amo_id,
        models.RosterPublicationAcknowledgement.version_id.in_(version_ids or ["__none__"]),
        models.RosterPublicationAcknowledgement.user_id.in_(assigned_user_ids or ["__none__"]),
    ).count()
    metrics = schemas.PlanningBoardMetrics(
        assigned_people=len(assigned_user_ids),
        roster_assignment_count=len(assignments),
        productive_assignment_count=sum(1 for row in assignments if row.status == models.RosterAssignmentStatus.DUTY),
        available_duty_hours=round(available_hours, 2),
        standby_hours=round(sum(row.standby_hours for row in base_capacity), 2),
        roster_linked_hours=round(linked_hours, 2),
        remaining_capacity_hours=round(max(available_hours - linked_hours, 0.0), 2),
        required_task_hours=round(required_hours, 2),
        task_assigned_hours=round(sum(row.task_assigned_hours for row in task_rows), 2),
        remaining_task_hours=round(sum(row.remaining_manhours for row in task_rows), 2),
        capacity_gap_hours=round(max(required_hours - max(available_hours - linked_hours, 0.0), 0.0), 2),
        capacity_variance_hours=round((available_hours - linked_hours) - required_hours, 2),
        work_order_count=len(work_order_rows),
        task_count=len(task_rows),
        unallocated_task_count=sum(1 for row in task_rows if row.roster_link_count == 0),
        missing_estimate_count=sum(1 for row in task_rows if not row.has_estimate),
        blocker_count=blocker_count,
        warning_count=warning_count,
        leave_conflict_count=leave_conflicts,
        unacknowledged_count=max(len(assigned_user_ids) * max(len(version_ids), 1) - acknowledgement_count, 0),
    )
    return schemas.RosterPlanningBoardResponse(
        from_date=from_date,
        to_date=to_date,
        base_station_id=base_station_id,
        published_version_id=version_ids[-1] if len(version_ids) == 1 else None,
        assignments=[common.serialize_assignment(row) for row in assignments],
        findings=[common.serialize_finding(row) for row in findings],
        metrics=metrics,
        base_capacity=base_capacity,
        work_orders=work_order_rows,
        tasks=task_rows,
        task_links=[assignment_services.serialize_task_link(row) for row in links],
        demand_requirements=[schemas.RosterDemandRequirementRead.model_validate(row) for row in demands],
    )


def dashboard(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    current_user: Optional[account_models.User] = None,
) -> schemas.RosterDashboardResponse:
    periods = catalog.list_periods(db, amo_id=amo_id, from_date=from_date, to_date=to_date)
    versions = [version for period in periods for version in period.versions or []]
    version_ids = [row.id for row in versions]
    findings = db.query(models.RosterValidationFinding).filter(
        models.RosterValidationFinding.amo_id == amo_id,
        models.RosterValidationFinding.version_id.in_(version_ids or ["__none__"]),
        models.RosterValidationFinding.resolved.is_(False),
    ).order_by(models.RosterValidationFinding.severity.asc(), models.RosterValidationFinding.sort_order.asc(), models.RosterValidationFinding.created_at.desc()).all()
    pending_leave = db.query(workforce_models.LeaveRequest.id).filter(
        workforce_models.LeaveRequest.amo_id == amo_id,
        workforce_models.LeaveRequest.status.in_([
            workforce_models.LeaveRequestStatus.SUBMITTED,
            workforce_models.LeaveRequestStatus.SUPERVISOR_APPROVED,
        ]),
    ).count()
    published = [row for row in versions if row.status == models.RosterVersionStatus.PUBLISHED]
    published_assignments_count = sum(len({assignment.user_id for assignment in row.assignments or [] if assignment.deleted_at is None}) for row in published)
    ack_count = db.query(models.RosterPublicationAcknowledgement.id).filter(
        models.RosterPublicationAcknowledgement.amo_id == amo_id,
        models.RosterPublicationAcknowledgement.version_id.in_([row.id for row in published] or ["__none__"]),
    ).count()
    board = planning_board(db, amo_id=amo_id, from_date=from_date, to_date=to_date)
    return schemas.RosterDashboardResponse(
        from_date=from_date,
        to_date=to_date,
        active_period_count=len([row for row in periods if row.status in {models.RosterPeriodStatus.DRAFT, models.RosterPeriodStatus.OPEN}]),
        draft_version_count=sum(1 for row in versions if row.status == models.RosterVersionStatus.DRAFT),
        submitted_version_count=sum(1 for row in versions if row.status == models.RosterVersionStatus.SUBMITTED),
        published_version_count=len(published),
        blocker_count=sum(1 for row in findings if row.severity == models.RosterValidationSeverity.BLOCKER),
        warning_count=sum(1 for row in findings if row.severity == models.RosterValidationSeverity.WARNING),
        pending_leave_count=pending_leave,
        unacknowledged_publication_count=max(published_assignments_count - ack_count, 0),
        capacity_gap_hours=board.metrics.capacity_gap_hours,
        upcoming_periods=[common.serialize_period(row, current_user=current_user, db=db) for row in periods[:6]],
        top_findings=[common.serialize_finding(row) for row in findings[:12]],
    )
