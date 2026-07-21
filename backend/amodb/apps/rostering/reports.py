# backend/amodb/apps/rostering/reports.py
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..workforce import models as workforce_models
from . import common, models, planning, schemas


def report_summary(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    base_station_id: Optional[str] = None,
    department_id: Optional[str] = None,
) -> schemas.RosterReportSummary:
    assignments = planning.published_assignments(
        db,
        amo_id=amo_id,
        from_date=from_date,
        to_date=to_date,
        base_station_id=base_station_id,
        department_id=department_id,
    )
    version_ids = sorted({row.version_id for row in assignments})
    findings = db.query(models.RosterValidationFinding).filter(
        models.RosterValidationFinding.amo_id == amo_id,
        models.RosterValidationFinding.version_id.in_(version_ids or ["__none__"]),
        models.RosterValidationFinding.resolved.is_(False),
    ).all()
    user_ids = sorted({row.user_id for row in assignments})
    sheets = db.query(workforce_models.Timesheet).filter(
        workforce_models.Timesheet.amo_id == amo_id,
        workforce_models.Timesheet.user_id.in_(user_ids or ["__none__"]),
        workforce_models.Timesheet.period_end >= from_date,
        workforce_models.Timesheet.period_start <= to_date,
    ).all()
    planned_minutes = sum(int(row.planned_minutes or common.assignment_hours(row) * 60) for row in assignments)
    attendance_minutes = sum(int(row.attendance_minutes or 0) for row in sheets)
    productive_minutes = sum(int(row.productive_minutes or 0) for row in sheets)
    overtime_minutes = sum(int(row.overtime_minutes or 0) for row in sheets)
    leave_minutes = sum(int(row.planned_minutes or common.assignment_hours(row) * 60) for row in assignments if row.status == models.RosterAssignmentStatus.LEAVE)
    training_minutes = sum(int(row.planned_minutes or common.assignment_hours(row) * 60) for row in assignments if row.status == models.RosterAssignmentStatus.TRAINING)
    standby_minutes = sum(int(row.planned_minutes or common.assignment_hours(row) * 60) for row in assignments if row.status == models.RosterAssignmentStatus.STANDBY)

    acknowledgement_required = len({(row.version_id, row.user_id) for row in assignments})
    acknowledgement_count = db.query(models.RosterPublicationAcknowledgement.id).filter(
        models.RosterPublicationAcknowledgement.amo_id == amo_id,
        models.RosterPublicationAcknowledgement.version_id.in_(version_ids or ["__none__"]),
        models.RosterPublicationAcknowledgement.user_id.in_(user_ids or ["__none__"]),
    ).count()
    acknowledgement_rate = round((acknowledgement_count / acknowledgement_required) * 100, 2) if acknowledgement_required else 100.0

    by_base: dict[str, dict[str, Any]] = defaultdict(lambda: {"assignment_count": 0, "planned_minutes": 0, "people": set()})
    by_department: dict[str, dict[str, Any]] = defaultdict(lambda: {"assignment_count": 0, "planned_minutes": 0, "people": set()})
    by_user: dict[str, dict[str, Any]] = defaultdict(lambda: {"assignment_count": 0, "planned_minutes": 0, "standby_minutes": 0, "training_minutes": 0, "leave_minutes": 0})
    for row in assignments:
        minutes = int(row.planned_minutes or common.assignment_hours(row) * 60)
        base_key = getattr(row.base_station, "code", None) or "UNASSIGNED"
        department_key = getattr(row.department, "code", None) or "UNASSIGNED"
        user_key = row.user_id
        by_base[base_key]["assignment_count"] += 1
        by_base[base_key]["planned_minutes"] += minutes
        by_base[base_key]["people"].add(row.user_id)
        by_department[department_key]["assignment_count"] += 1
        by_department[department_key]["planned_minutes"] += minutes
        by_department[department_key]["people"].add(row.user_id)
        by_user[user_key]["user_id"] = row.user_id
        by_user[user_key]["full_name"] = getattr(row.user, "full_name", row.user_id)
        by_user[user_key]["staff_code"] = getattr(row.user, "staff_code", None)
        by_user[user_key]["assignment_count"] += 1
        by_user[user_key]["planned_minutes"] += minutes
        if row.status == models.RosterAssignmentStatus.STANDBY:
            by_user[user_key]["standby_minutes"] += minutes
        elif row.status == models.RosterAssignmentStatus.TRAINING:
            by_user[user_key]["training_minutes"] += minutes
        elif row.status == models.RosterAssignmentStatus.LEAVE:
            by_user[user_key]["leave_minutes"] += minutes
    sheet_by_user = {row.user_id: row for row in sheets}
    for user_id, values in by_user.items():
        sheet = sheet_by_user.get(user_id)
        values["attendance_minutes"] = int(getattr(sheet, "attendance_minutes", 0) or 0)
        values["productive_minutes"] = int(getattr(sheet, "productive_minutes", 0) or 0)
        values["overtime_minutes"] = int(getattr(sheet, "overtime_minutes", 0) or 0)
        values["variance_minutes"] = int(getattr(sheet, "variance_minutes", 0) or 0)

    return schemas.RosterReportSummary(
        from_date=from_date,
        to_date=to_date,
        planned_minutes=planned_minutes,
        attendance_minutes=attendance_minutes,
        productive_minutes=productive_minutes,
        overtime_minutes=overtime_minutes,
        assignment_count=len(assignments),
        assigned_people=len(user_ids),
        leave_minutes=leave_minutes,
        training_minutes=training_minutes,
        standby_minutes=standby_minutes,
        acknowledgement_rate=acknowledgement_rate,
        blocker_count=sum(1 for row in findings if row.severity == models.RosterValidationSeverity.BLOCKER),
        warning_count=sum(1 for row in findings if row.severity == models.RosterValidationSeverity.WARNING),
        by_base=[{"base_code": key, "assigned_people": len(value.pop("people")), **value} for key, value in sorted(by_base.items())],
        by_department=[{"department_code": key, "assigned_people": len(value.pop("people")), **value} for key, value in sorted(by_department.items())],
        by_user=[value for _, value in sorted(by_user.items(), key=lambda item: (item[1].get("full_name") or "", item[0]))],
    )


def assignment_export_rows(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    base_station_id: Optional[str] = None,
    department_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = planning.published_assignments(
        db,
        amo_id=amo_id,
        from_date=from_date,
        to_date=to_date,
        user_id=user_id,
        base_station_id=base_station_id,
        department_id=department_id,
    )
    return [{
        "assignment_id": row.id,
        "version_id": row.version_id,
        "user_id": row.user_id,
        "staff_code": getattr(row.user, "staff_code", None),
        "full_name": getattr(row.user, "full_name", None),
        "department_code": getattr(row.department, "code", None),
        "base_code": getattr(row.base_station, "code", None),
        "shift_code": getattr(row.shift_template, "code", None),
        "status": common.enum_value(row.status),
        "source": common.enum_value(row.source),
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "planned_minutes": int(row.planned_minutes or common.assignment_hours(row) * 60),
        "role_label": row.role_label,
        "team_code": row.team_code,
        "location_label": row.location_label,
        "linked_task_count": len(row.task_links or []),
        "linked_task_hours": round(sum(common.task_link_hours(link) for link in row.task_links or []), 2),
        "change_reason": row.change_reason,
    } for row in rows]
