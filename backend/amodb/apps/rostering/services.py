# backend/amodb/apps/rostering/services.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..foundations import models as foundation_models
from ..fleet import models as fleet_models
from ..quality import models as quality_models
from ..training import compliance as training_compliance
from ..training import models as training_models
from ..work import models as work_models
from ..work import services as work_services
from . import models, schemas


DUTY_STATUSES = {
    models.RosterAssignmentStatus.DUTY,
    models.RosterAssignmentStatus.STANDBY,
    models.RosterAssignmentStatus.TRAINING,
    models.RosterAssignmentStatus.TRAVEL,
}

# Productive roster capacity excludes training and travel. Standby is shown
# separately but remains allocatable when managers explicitly assign work.
PRODUCTIVE_STATUSES = {
    models.RosterAssignmentStatus.DUTY,
    models.RosterAssignmentStatus.STANDBY,
}

OPEN_TASK_STATUSES = {
    work_models.TaskStatusEnum.PLANNED,
    work_models.TaskStatusEnum.IN_PROGRESS,
    work_models.TaskStatusEnum.PAUSED,
}

OPEN_WORK_ORDER_STATUSES = {
    work_models.WorkOrderStatusEnum.DRAFT,
    work_models.WorkOrderStatusEnum.RELEASED,
    work_models.WorkOrderStatusEnum.IN_PROGRESS,
    work_models.WorkOrderStatusEnum.INSPECTED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def effective_amo_id(user: account_models.User) -> str:
    return getattr(user, "effective_amo_id", None) or user.amo_id


def normalize_code(value: str) -> str:
    return "".join(str(value or "").strip().upper().split())


def can_view_roster(user: account_models.User) -> bool:
    return bool(user and not getattr(user, "is_system_account", False))


def can_manage_roster(user: account_models.User) -> bool:
    if getattr(user, "is_system_account", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return True
    return user.role in {
        account_models.AccountRole.PLANNING_ENGINEER,
        account_models.AccountRole.PRODUCTION_ENGINEER,
        account_models.AccountRole.QUALITY_MANAGER,
    }


def can_approve_roster(user: account_models.User) -> bool:
    if getattr(user, "is_system_account", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return True
    return user.role in {
        account_models.AccountRole.PRODUCTION_ENGINEER,
        account_models.AccountRole.QUALITY_MANAGER,
    }


def list_shift_templates(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.ShiftTemplate]:
    q = db.query(models.ShiftTemplate).filter(models.ShiftTemplate.amo_id == amo_id)
    if not include_inactive:
        q = q.filter(models.ShiftTemplate.is_active.is_(True))
    return q.order_by(models.ShiftTemplate.display_order.asc(), models.ShiftTemplate.code.asc()).all()


def create_shift_template(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.ShiftTemplateCreate) -> models.ShiftTemplate:
    row = models.ShiftTemplate(
        amo_id=amo_id,
        code=normalize_code(payload.code),
        label=payload.label.strip(),
        kind=payload.kind,
        default_start_time=payload.default_start_time,
        default_end_time=payload.default_end_time,
        duration_minutes=payload.duration_minutes,
        counts_as_duty=payload.counts_as_duty,
        is_active=payload.is_active,
        display_order=payload.display_order,
        description=payload.description,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def update_shift_template(db: Session, *, row: models.ShiftTemplate, actor_user_id: str, payload: schemas.ShiftTemplateUpdate) -> models.ShiftTemplate:
    for field in (
        "label",
        "kind",
        "default_start_time",
        "default_end_time",
        "duration_minutes",
        "counts_as_duty",
        "is_active",
        "display_order",
        "description",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) and field == "label" else value)
    if payload.code is not None:
        row.code = normalize_code(payload.code)
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    return row


def list_periods(db: Session, *, amo_id: str, status: Optional[models.RosterPeriodStatus] = None) -> list[models.RosterPeriod]:
    q = db.query(models.RosterPeriod).options(selectinload(models.RosterPeriod.versions)).filter(models.RosterPeriod.amo_id == amo_id)
    if status:
        q = q.filter(models.RosterPeriod.status == status)
    return q.order_by(models.RosterPeriod.starts_on.desc()).all()


def create_period(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.RosterPeriodCreate) -> models.RosterPeriod:
    row = models.RosterPeriod(
        amo_id=amo_id,
        period_code=normalize_code(payload.period_code).replace("/", "-"),
        name=payload.name.strip(),
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        notes=payload.notes,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    create_version(db, amo_id=amo_id, period=row, actor_user_id=actor_user_id, payload=schemas.RosterVersionCreate(title=f"{row.name} Draft v1"))
    return row


def update_period(db: Session, *, period: models.RosterPeriod, payload: schemas.RosterPeriodUpdate) -> models.RosterPeriod:
    if payload.name is not None:
        period.name = payload.name.strip()
    if payload.status is not None:
        period.status = payload.status
    if payload.notes is not None:
        period.notes = payload.notes
    db.add(period)
    db.flush()
    return period


def get_period(db: Session, *, amo_id: str, period_id: str) -> Optional[models.RosterPeriod]:
    return db.query(models.RosterPeriod).filter(models.RosterPeriod.amo_id == amo_id, models.RosterPeriod.id == period_id).first()


def get_version(db: Session, *, amo_id: str, version_id: str) -> Optional[models.RosterVersion]:
    return (
        db.query(models.RosterVersion)
        .options(selectinload(models.RosterVersion.assignments), selectinload(models.RosterVersion.validation_findings))
        .filter(models.RosterVersion.amo_id == amo_id, models.RosterVersion.id == version_id)
        .first()
    )


def next_version_no(db: Session, *, period_id: str) -> int:
    current = db.query(models.RosterVersion).filter(models.RosterVersion.period_id == period_id).order_by(models.RosterVersion.version_no.desc()).first()
    return int(current.version_no if current else 0) + 1


def create_version(db: Session, *, amo_id: str, period: models.RosterPeriod, actor_user_id: str, payload: schemas.RosterVersionCreate) -> models.RosterVersion:
    version = models.RosterVersion(
        amo_id=amo_id,
        period_id=period.id,
        version_no=next_version_no(db, period_id=period.id),
        title=payload.title,
        change_summary=payload.change_summary,
        created_by_user_id=actor_user_id,
    )
    db.add(version)
    db.flush()
    if payload.copy_from_version_id:
        source = get_version(db, amo_id=amo_id, version_id=payload.copy_from_version_id)
        if source and source.period_id == period.id:
            for item in source.assignments:
                db.add(
                    models.RosterAssignment(
                        amo_id=amo_id,
                        version_id=version.id,
                        user_id=item.user_id,
                        base_station_id=item.base_station_id,
                        shift_template_id=item.shift_template_id,
                        status=item.status,
                        starts_at=item.starts_at,
                        ends_at=item.ends_at,
                        planned_minutes=item.planned_minutes,
                        role_label=item.role_label,
                        task_note=item.task_note,
                        created_by_user_id=actor_user_id,
                        updated_by_user_id=actor_user_id,
                    )
                )
    db.flush()
    return version


def list_versions(db: Session, *, amo_id: str, period_id: str) -> list[models.RosterVersion]:
    return (
        db.query(models.RosterVersion)
        .options(selectinload(models.RosterVersion.assignments), selectinload(models.RosterVersion.validation_findings))
        .filter(models.RosterVersion.amo_id == amo_id, models.RosterVersion.period_id == period_id)
        .order_by(models.RosterVersion.version_no.desc())
        .all()
    )


def ensure_version_editable(version: models.RosterVersion) -> None:
    if version.status not in {models.RosterVersionStatus.DRAFT, models.RosterVersionStatus.SUBMITTED}:
        raise ValueError("Only draft or submitted roster versions can be edited.")


def _require_user_in_amo(db: Session, *, amo_id: str, user_id: str) -> account_models.User:
    user = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id == user_id).first()
    if not user:
        raise ValueError("User not found in AMO scope.")
    if getattr(user, "is_system_account", False):
        raise ValueError("System accounts cannot be rostered.")
    return user


def _require_base_in_amo(db: Session, *, amo_id: str, base_station_id: Optional[str]) -> None:
    if not base_station_id:
        return
    exists = db.query(foundation_models.BaseStation.id).filter(foundation_models.BaseStation.amo_id == amo_id, foundation_models.BaseStation.id == base_station_id).first()
    if not exists:
        raise ValueError("Base station not found in AMO scope.")


def _require_shift_in_amo(db: Session, *, amo_id: str, shift_template_id: Optional[str]) -> None:
    if not shift_template_id:
        return
    exists = db.query(models.ShiftTemplate.id).filter(models.ShiftTemplate.amo_id == amo_id, models.ShiftTemplate.id == shift_template_id).first()
    if not exists:
        raise ValueError("Shift template not found in AMO scope.")


def create_assignment(db: Session, *, amo_id: str, version: models.RosterVersion, actor_user_id: str, payload: schemas.RosterAssignmentCreate) -> models.RosterAssignment:
    ensure_version_editable(version)
    _require_user_in_amo(db, amo_id=amo_id, user_id=payload.user_id)
    _require_base_in_amo(db, amo_id=amo_id, base_station_id=payload.base_station_id)
    _require_shift_in_amo(db, amo_id=amo_id, shift_template_id=payload.shift_template_id)
    minutes = payload.planned_minutes
    if minutes is None:
        minutes = int((payload.ends_at - payload.starts_at).total_seconds() // 60)
    row = models.RosterAssignment(
        amo_id=amo_id,
        version_id=version.id,
        user_id=payload.user_id,
        base_station_id=payload.base_station_id,
        shift_template_id=payload.shift_template_id,
        status=payload.status,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        planned_minutes=minutes,
        role_label=payload.role_label,
        task_note=payload.task_note,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def update_assignment(db: Session, *, amo_id: str, assignment: models.RosterAssignment, actor_user_id: str, payload: schemas.RosterAssignmentUpdate) -> models.RosterAssignment:
    ensure_version_editable(assignment.version)
    if payload.base_station_id is not None:
        _require_base_in_amo(db, amo_id=amo_id, base_station_id=payload.base_station_id)
        assignment.base_station_id = payload.base_station_id
    if payload.shift_template_id is not None:
        _require_shift_in_amo(db, amo_id=amo_id, shift_template_id=payload.shift_template_id)
        assignment.shift_template_id = payload.shift_template_id
    for field in ("starts_at", "ends_at", "status", "planned_minutes", "role_label", "task_note"):
        value = getattr(payload, field)
        if value is not None:
            setattr(assignment, field, value)
    if assignment.ends_at <= assignment.starts_at:
        raise ValueError("ends_at must be after starts_at")
    if assignment.planned_minutes is None:
        assignment.planned_minutes = int((assignment.ends_at - assignment.starts_at).total_seconds() // 60)
    assignment.updated_by_user_id = actor_user_id
    db.add(assignment)
    db.flush()
    return assignment


def list_assignments_for_version(db: Session, *, amo_id: str, version_id: str) -> list[models.RosterAssignment]:
    return (
        db.query(models.RosterAssignment)
        .options(selectinload(models.RosterAssignment.user), selectinload(models.RosterAssignment.base_station), selectinload(models.RosterAssignment.shift_template))
        .filter(models.RosterAssignment.amo_id == amo_id, models.RosterAssignment.version_id == version_id)
        .order_by(models.RosterAssignment.starts_at.asc(), models.RosterAssignment.user_id.asc())
        .all()
    )


def _intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _clear_findings(db: Session, *, version_id: str) -> None:
    for row in db.query(models.RosterValidationFinding).filter(models.RosterValidationFinding.version_id == version_id).all():
        db.delete(row)
    db.flush()


def _add_finding(db: Session, *, amo_id: str, version_id: str, severity: models.RosterValidationSeverity, source: models.RosterValidationSource, code: str, message: str, assignment_id: Optional[str] = None, user_id: Optional[str] = None) -> models.RosterValidationFinding:
    row = models.RosterValidationFinding(
        amo_id=amo_id,
        version_id=version_id,
        assignment_id=assignment_id,
        user_id=user_id,
        severity=severity,
        source=source,
        code=code,
        message=message,
    )
    db.add(row)
    return row


def _date_range_for_assignment(assignment: models.RosterAssignment) -> tuple[date, date]:
    return assignment.starts_at.date(), assignment.ends_at.date()


def validate_version(db: Session, *, amo_id: str, version: models.RosterVersion) -> schemas.RosterValidationResult:
    _clear_findings(db, version_id=version.id)
    assignments = list_assignments_for_version(db, amo_id=amo_id, version_id=version.id)
    period = version.period

    if not assignments:
        _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.WARNING, source=models.RosterValidationSource.ROSTER, code="NO_ASSIGNMENTS", message="Roster version has no assignments.")

    by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for assignment in assignments:
        by_user[assignment.user_id].append(assignment)
        if assignment.starts_at.date() < period.starts_on or assignment.ends_at.date() > period.ends_on:
            _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.BLOCKER, source=models.RosterValidationSource.ROSTER, code="OUTSIDE_PERIOD", assignment_id=assignment.id, user_id=assignment.user_id, message="Assignment falls outside the roster period.")
        if assignment.status in DUTY_STATUSES and not assignment.base_station_id:
            _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.WARNING, source=models.RosterValidationSource.BASE, code="MISSING_BASE", assignment_id=assignment.id, user_id=assignment.user_id, message="Duty assignment has no base station.")

    for user_id, rows in by_user.items():
        rows.sort(key=lambda item: item.starts_at)
        for index, first in enumerate(rows):
            for second in rows[index + 1 :]:
                if second.starts_at >= first.ends_at:
                    break
                if _intervals_overlap(first.starts_at, first.ends_at, second.starts_at, second.ends_at):
                    _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.BLOCKER, source=models.RosterValidationSource.ROSTER, code="OVERLAPPING_ASSIGNMENTS", assignment_id=second.id, user_id=user_id, message="User has overlapping roster assignments in this version.")
        duty_rows = [row for row in rows if row.status in DUTY_STATUSES]
        for previous, current in zip(duty_rows, duty_rows[1:]):
            rest_hours = (current.starts_at - previous.ends_at).total_seconds() / 3600
            if rest_hours < 8:
                _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.BLOCKER, source=models.RosterValidationSource.RULE, code="REST_BELOW_8H", assignment_id=current.id, user_id=user_id, message=f"Rest before this duty is {rest_hours:.1f} hours, below the 8-hour minimum rule.")

    # Active human users without profiles remain a warning here; Phase 0 identity-health keeps the full list.
    rostered_user_ids = list(by_user.keys())
    if rostered_user_ids:
        users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id.in_(rostered_user_ids)).all()
        profiles = db.query(account_models.PersonnelProfile.user_id).filter(account_models.PersonnelProfile.amo_id == amo_id, account_models.PersonnelProfile.user_id.in_(rostered_user_ids), account_models.PersonnelProfile.status == "Active").all()
        profile_user_ids = {row[0] for row in profiles}
        for user in users:
            if getattr(user, "is_system_account", False):
                _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.BLOCKER, source=models.RosterValidationSource.IDENTITY, code="SYSTEM_ACCOUNT_ROSTERED", user_id=user.id, message="System accounts cannot be rostered.")
            elif user.id not in profile_user_ids:
                _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.WARNING, source=models.RosterValidationSource.IDENTITY, code="MISSING_PERSONNEL_PROFILE", user_id=user.id, message="Rostered user is not linked to an active PersonnelProfile record.")

    # Training events block the full day in Phase 1 because the Training module currently stores dates.
    if rostered_user_ids:
        training_rows = (
            db.query(training_models.TrainingEventParticipant, training_models.TrainingEvent)
            .join(training_models.TrainingEvent, training_models.TrainingEventParticipant.event_id == training_models.TrainingEvent.id)
            .filter(
                training_models.TrainingEventParticipant.amo_id == amo_id,
                training_models.TrainingEventParticipant.user_id.in_(rostered_user_ids),
                training_models.TrainingEvent.status.in_([training_models.TrainingEventStatus.PLANNED, training_models.TrainingEventStatus.IN_PROGRESS]),
                training_models.TrainingEvent.starts_on <= period.ends_on,
                or_(training_models.TrainingEvent.ends_on.is_(None), training_models.TrainingEvent.ends_on >= period.starts_on),
            )
            .all()
        )
        training_by_user: dict[str, list[tuple[date, date, str]]] = defaultdict(list)
        for participant, event in training_rows:
            training_by_user[participant.user_id].append((event.starts_on, event.ends_on or event.starts_on, event.title))
        for assignment in assignments:
            if assignment.status not in {models.RosterAssignmentStatus.DUTY, models.RosterAssignmentStatus.STANDBY, models.RosterAssignmentStatus.TRAVEL}:
                continue
            a_start, a_end = _date_range_for_assignment(assignment)
            for t_start, t_end, title in training_by_user.get(assignment.user_id, []):
                if a_start <= t_end and t_start <= a_end:
                    _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.WARNING, source=models.RosterValidationSource.TRAINING, code="TRAINING_CONFLICT", assignment_id=assignment.id, user_id=assignment.user_id, message=f"Assignment overlaps planned training: {title}.")
                    break

    # Shared availability service is currently backed by quality.user_availability.
    if rostered_user_ids:
        availability_rows = (
            db.query(quality_models.UserAvailability)
            .filter(
                quality_models.UserAvailability.amo_id == amo_id,
                quality_models.UserAvailability.user_id.in_(rostered_user_ids),
                quality_models.UserAvailability.effective_from <= datetime.combine(period.ends_on, time.max, tzinfo=timezone.utc),
                or_(quality_models.UserAvailability.effective_to.is_(None), quality_models.UserAvailability.effective_to >= datetime.combine(period.starts_on, time.min, tzinfo=timezone.utc)),
            )
            .all()
        )
        availability_by_user: dict[str, list[quality_models.UserAvailability]] = defaultdict(list)
        for row in availability_rows:
            availability_by_user[row.user_id].append(row)
        for assignment in assignments:
            if assignment.status not in {models.RosterAssignmentStatus.DUTY, models.RosterAssignmentStatus.STANDBY, models.RosterAssignmentStatus.TRAVEL}:
                continue
            for window in availability_by_user.get(assignment.user_id, []):
                window_end = window.effective_to or datetime.max.replace(tzinfo=timezone.utc)
                if _intervals_overlap(assignment.starts_at, assignment.ends_at, window.effective_from, window_end):
                    status_value = getattr(window.status, "value", window.status)
                    if status_value in {"AWAY", "ON_LEAVE"}:
                        _add_finding(db, amo_id=amo_id, version_id=version.id, severity=models.RosterValidationSeverity.BLOCKER, source=models.RosterValidationSource.AVAILABILITY, code=f"USER_{status_value}", assignment_id=assignment.id, user_id=assignment.user_id, message=f"Assignment overlaps a shared availability window marked {status_value}.")
                        break

    db.flush()
    findings = (
        db.query(models.RosterValidationFinding)
        .filter(models.RosterValidationFinding.version_id == version.id)
        .order_by(models.RosterValidationFinding.severity.asc(), models.RosterValidationFinding.created_at.asc())
        .all()
    )
    blocker_count = sum(1 for item in findings if item.severity == models.RosterValidationSeverity.BLOCKER)
    warning_count = sum(1 for item in findings if item.severity == models.RosterValidationSeverity.WARNING)
    info_count = sum(1 for item in findings if item.severity == models.RosterValidationSeverity.INFO)
    return schemas.RosterValidationResult(
        version_id=version.id,
        blocker_count=blocker_count,
        warning_count=warning_count,
        info_count=info_count,
        can_submit=blocker_count == 0,
        can_publish=blocker_count == 0 and version.status in {models.RosterVersionStatus.APPROVED, models.RosterVersionStatus.PUBLISHED},
        findings=[schemas.RosterValidationFindingRead.from_orm(item) for item in findings],
    )


def submit_version(db: Session, *, version: models.RosterVersion, actor_user_id: str) -> models.RosterVersion:
    result = validate_version(db, amo_id=version.amo_id, version=version)
    if result.blocker_count > 0:
        raise ValueError("Roster version has blocker findings and cannot be submitted.")
    version.status = models.RosterVersionStatus.SUBMITTED
    version.submitted_by_user_id = actor_user_id
    version.submitted_at = _utcnow()
    db.add(version)
    db.flush()
    return version


def approve_version(db: Session, *, version: models.RosterVersion, actor_user_id: str) -> models.RosterVersion:
    result = validate_version(db, amo_id=version.amo_id, version=version)
    if result.blocker_count > 0:
        raise ValueError("Roster version has blocker findings and cannot be approved.")
    if version.status not in {models.RosterVersionStatus.SUBMITTED, models.RosterVersionStatus.DRAFT}:
        raise ValueError("Only draft or submitted versions can be approved.")
    version.status = models.RosterVersionStatus.APPROVED
    version.approved_by_user_id = actor_user_id
    version.approved_at = _utcnow()
    db.add(version)
    db.flush()
    return version


def publish_version(db: Session, *, version: models.RosterVersion, actor_user_id: str) -> models.RosterVersion:
    result = validate_version(db, amo_id=version.amo_id, version=version)
    if result.blocker_count > 0:
        raise ValueError("Roster version has blocker findings and cannot be published.")
    if version.status != models.RosterVersionStatus.APPROVED:
        raise ValueError("Only approved roster versions can be published.")
    published_siblings = db.query(models.RosterVersion).filter(models.RosterVersion.amo_id == version.amo_id, models.RosterVersion.period_id == version.period_id, models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED, models.RosterVersion.id != version.id).all()
    for sibling in published_siblings:
        sibling.status = models.RosterVersionStatus.SUPERSEDED
        db.add(sibling)
    version.status = models.RosterVersionStatus.PUBLISHED
    version.published_by_user_id = actor_user_id
    version.published_at = _utcnow()
    version.period.status = models.RosterPeriodStatus.OPEN
    for assignment in version.assignments:
        assignment.locked_after_publish = True
        db.add(assignment)
    db.add(version)
    db.add(version.period)
    db.flush()
    return version


def acknowledge_version(db: Session, *, amo_id: str, version: models.RosterVersion, user_id: str, note: Optional[str]) -> models.RosterPublicationAcknowledgement:
    if version.status != models.RosterVersionStatus.PUBLISHED:
        raise ValueError("Only published rosters can be acknowledged.")
    existing = db.query(models.RosterPublicationAcknowledgement).filter(models.RosterPublicationAcknowledgement.version_id == version.id, models.RosterPublicationAcknowledgement.user_id == user_id).first()
    if existing:
        existing.acknowledgement_note = note or existing.acknowledgement_note
        existing.acknowledged_at = _utcnow()
        db.add(existing)
        db.flush()
        return existing
    row = models.RosterPublicationAcknowledgement(amo_id=amo_id, version_id=version.id, user_id=user_id, acknowledgement_note=note)
    db.add(row)
    db.flush()
    return row


def published_assignments_for_user(db: Session, *, amo_id: str, user_id: str, from_date: date, to_date: date) -> list[models.RosterAssignment]:
    start_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return (
        db.query(models.RosterAssignment)
        .join(models.RosterVersion, models.RosterAssignment.version_id == models.RosterVersion.id)
        .options(selectinload(models.RosterAssignment.user), selectinload(models.RosterAssignment.base_station), selectinload(models.RosterAssignment.shift_template))
        .filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.user_id == user_id,
            models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
            models.RosterAssignment.starts_at < end_dt,
            models.RosterAssignment.ends_at > start_dt,
        )
        .order_by(models.RosterAssignment.starts_at.asc())
        .all()
    )


def training_due_next_month(db: Session, *, user: account_models.User, base_date: date) -> list[dict[str, object]]:
    next_month_start = (base_date.replace(day=1) + timedelta(days=32)).replace(day=1)
    following_month_start = (next_month_start + timedelta(days=32)).replace(day=1)
    courses = training_compliance.get_courses_for_user(db, user, required_only=True)
    latest = training_compliance._latest_records_for_user(db, user, [course.id for course in courses])  # intentional reuse of existing module logic
    due: list[dict[str, object]] = []
    for course in courses:
        row = latest.get(course.id)
        valid_until = getattr(row, "valid_until", None) if row else None
        if valid_until and next_month_start <= valid_until < following_month_start:
            due.append({"course_id": course.course_id, "course_name": course.course_name, "valid_until": valid_until.isoformat()})
    return due


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _link_hours(link: models.RosterTaskAssignmentLink) -> float:
    if link.allocated_hours is not None:
        return max(float(link.allocated_hours), 0.0)
    if link.allocated_start is not None and link.allocated_end is not None:
        return max((link.allocated_end - link.allocated_start).total_seconds() / 3600.0, 0.0)
    task_assignment = getattr(link, "task_assignment", None)
    if task_assignment is not None and getattr(task_assignment, "allocated_hours", None) is not None:
        return max(float(task_assignment.allocated_hours), 0.0)
    return 0.0


def _assignment_hours(item: models.RosterAssignment) -> float:
    if item.planned_minutes is not None:
        return max(float(item.planned_minutes) / 60.0, 0.0)
    return max((item.ends_at - item.starts_at).total_seconds() / 3600.0, 0.0)


def serialize_assignment(item: models.RosterAssignment) -> schemas.RosterAssignmentRead:
    task_links = list(item.task_links or [])
    return schemas.RosterAssignmentRead(
        id=item.id,
        amo_id=item.amo_id,
        version_id=item.version_id,
        user_id=item.user_id,
        base_station_id=item.base_station_id,
        shift_template_id=item.shift_template_id,
        status=item.status,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        planned_minutes=item.planned_minutes,
        role_label=item.role_label,
        task_note=item.task_note,
        locked_after_publish=item.locked_after_publish,
        created_by_user_id=item.created_by_user_id,
        updated_by_user_id=item.updated_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        user_full_name=getattr(item.user, "full_name", None),
        user_role=_enum_value(getattr(item.user, "role", "")) if item.user else None,
        base_code=getattr(item.base_station, "code", None) if item.base_station else None,
        base_name=getattr(item.base_station, "name", None) if item.base_station else None,
        shift_code=getattr(item.shift_template, "code", None) if item.shift_template else None,
        linked_task_count=len(task_links),
        linked_task_hours=round(sum(_link_hours(link) for link in task_links), 2),
    )


def summarize_version(version: models.RosterVersion) -> schemas.RosterVersionRead:
    findings = list(version.validation_findings or [])
    return schemas.RosterVersionRead(
        id=version.id,
        amo_id=version.amo_id,
        period_id=version.period_id,
        version_no=version.version_no,
        status=version.status,
        title=version.title,
        change_summary=version.change_summary,
        created_by_user_id=version.created_by_user_id,
        submitted_by_user_id=version.submitted_by_user_id,
        approved_by_user_id=version.approved_by_user_id,
        published_by_user_id=version.published_by_user_id,
        submitted_at=version.submitted_at,
        approved_at=version.approved_at,
        published_at=version.published_at,
        created_at=version.created_at,
        updated_at=version.updated_at,
        assignments_count=len(version.assignments or []),
        blocker_count=sum(1 for f in findings if f.severity == models.RosterValidationSeverity.BLOCKER),
        warning_count=sum(1 for f in findings if f.severity == models.RosterValidationSeverity.WARNING),
    )


def _base_label(base: foundation_models.BaseStation | None, fallback_code: str | None = None) -> tuple[Optional[str], str, str]:
    if base:
        return base.id, base.code, base.name
    code = fallback_code or "UNASSIGNED"
    return None, code, code


def _base_maps(db: Session, *, amo_id: str) -> tuple[dict[str, foundation_models.BaseStation], dict[str, foundation_models.BaseStation]]:
    rows = db.query(foundation_models.BaseStation).filter(foundation_models.BaseStation.amo_id == amo_id, foundation_models.BaseStation.is_active.is_(True)).all()
    by_id = {row.id: row for row in rows}
    by_code: dict[str, foundation_models.BaseStation] = {}
    for row in rows:
        for value in (row.code, row.icao_code, row.iata_code):
            if value:
                by_code[normalize_code(value)] = row
    return by_id, by_code


def _aircraft_base(aircraft: fleet_models.Aircraft | None, by_code: dict[str, foundation_models.BaseStation]) -> foundation_models.BaseStation | None:
    if not aircraft:
        return None
    home_base = getattr(aircraft, "home_base", None)
    return by_code.get(normalize_code(home_base)) if home_base else None


def _serialize_task_link(link: models.RosterTaskAssignmentLink) -> schemas.RosterTaskAssignmentLinkRead:
    task_assignment = link.task_assignment
    task = task_assignment.task if task_assignment else None
    work_order = task.work_order if task else None
    aircraft = work_order.aircraft if work_order else None
    roster_assignment = link.roster_assignment
    base_station = roster_assignment.base_station if roster_assignment else None
    return schemas.RosterTaskAssignmentLinkRead(
        id=link.id,
        amo_id=link.amo_id,
        roster_assignment_id=link.roster_assignment_id,
        task_assignment_id=link.task_assignment_id,
        task_id=task.id if task else 0,
        user_id=task_assignment.user_id if task_assignment else "",
        role_on_task=_enum_value(task_assignment.role_on_task) if task_assignment else "",
        task_assignment_status=_enum_value(task_assignment.status) if task_assignment else "",
        allocated_start=link.allocated_start,
        allocated_end=link.allocated_end,
        allocated_hours=link.allocated_hours,
        task_title=getattr(task, "title", None),
        task_code=getattr(task, "task_code", None),
        work_order_id=getattr(work_order, "id", None),
        wo_number=getattr(work_order, "wo_number", None),
        aircraft_serial_number=getattr(work_order, "aircraft_serial_number", None),
        aircraft_registration=getattr(aircraft, "registration", None),
        base_station_id=getattr(base_station, "id", None),
        base_code=getattr(base_station, "code", None),
        created_by_user_id=link.created_by_user_id,
        created_at=link.created_at,
    )


def _query_published_assignments(
    db: Session,
    *,
    amo_id: str,
    start_dt: datetime,
    end_dt: datetime,
    base_station_id: Optional[str],
) -> list[models.RosterAssignment]:
    q = (
        db.query(models.RosterAssignment)
        .join(models.RosterVersion, models.RosterAssignment.version_id == models.RosterVersion.id)
        .options(
            selectinload(models.RosterAssignment.user),
            selectinload(models.RosterAssignment.base_station),
            selectinload(models.RosterAssignment.shift_template),
            selectinload(models.RosterAssignment.task_links)
            .selectinload(models.RosterTaskAssignmentLink.task_assignment)
            .selectinload(work_models.TaskAssignment.task)
            .selectinload(work_models.TaskCard.work_order)
            .selectinload(work_models.WorkOrder.aircraft),
        )
        .filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
            models.RosterAssignment.starts_at < end_dt,
            models.RosterAssignment.ends_at > start_dt,
        )
    )
    if base_station_id:
        q = q.filter(models.RosterAssignment.base_station_id == base_station_id)
    return q.order_by(models.RosterAssignment.starts_at.asc()).all()


def _query_workload_tasks(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    base_station_id: Optional[str],
    base_by_id: dict[str, foundation_models.BaseStation],
    base_by_code: dict[str, foundation_models.BaseStation],
) -> list[work_models.TaskCard]:
    start_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    q = (
        db.query(work_models.TaskCard)
        .join(work_models.WorkOrder, work_models.TaskCard.work_order_id == work_models.WorkOrder.id)
        .join(fleet_models.Aircraft, work_models.WorkOrder.aircraft_serial_number == fleet_models.Aircraft.serial_number)
        .options(
            selectinload(work_models.TaskCard.work_order).selectinload(work_models.WorkOrder.aircraft),
            selectinload(work_models.TaskCard.assignments),
        )
        .filter(
            work_models.TaskCard.amo_id == amo_id,
            work_models.TaskCard.status.in_(OPEN_TASK_STATUSES),
            work_models.WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES),
        )
        .filter(
            or_(
                and_(work_models.TaskCard.planned_start.isnot(None), work_models.TaskCard.planned_start < end_dt, work_models.TaskCard.planned_end.isnot(None), work_models.TaskCard.planned_end > start_dt),
                and_(work_models.TaskCard.planned_start.isnot(None), work_models.TaskCard.planned_start >= start_dt, work_models.TaskCard.planned_start < end_dt),
                and_(work_models.WorkOrder.due_date.isnot(None), work_models.WorkOrder.due_date >= from_date, work_models.WorkOrder.due_date <= to_date),
            )
        )
    )
    if base_station_id:
        selected_base = base_by_id.get(base_station_id)
        accepted_codes = [normalize_code(x) for x in (getattr(selected_base, "code", None), getattr(selected_base, "icao_code", None), getattr(selected_base, "iata_code", None)) if x]
        if accepted_codes:
            q = q.filter(fleet_models.Aircraft.home_base.in_(accepted_codes))
        else:
            return []
    return q.order_by(work_models.TaskCard.planned_start.asc().nullslast(), work_models.TaskCard.priority.asc()).all()


def _task_link_hours_by_assignment(db: Session, *, amo_id: str, task_assignment_ids: list[int]) -> dict[int, float]:
    if not task_assignment_ids:
        return {}
    rows = (
        db.query(models.RosterTaskAssignmentLink)
        .filter(models.RosterTaskAssignmentLink.amo_id == amo_id, models.RosterTaskAssignmentLink.task_assignment_id.in_(task_assignment_ids))
        .all()
    )
    totals: dict[int, float] = defaultdict(float)
    for row in rows:
        totals[row.task_assignment_id] += _link_hours(row)
    return totals


def _build_workload_summaries(
    db: Session,
    *,
    amo_id: str,
    tasks: list[work_models.TaskCard],
    base_by_code: dict[str, foundation_models.BaseStation],
) -> tuple[list[schemas.WorkloadWorkOrderSummary], list[schemas.WorkloadTaskSummary]]:
    task_assignment_ids = [assignment.id for task in tasks for assignment in (task.assignments or [])]
    link_hours = _task_link_hours_by_assignment(db, amo_id=amo_id, task_assignment_ids=task_assignment_ids)
    task_summaries: list[schemas.WorkloadTaskSummary] = []
    by_work_order: dict[int, dict[str, object]] = {}

    for task in tasks:
        work_order = task.work_order
        aircraft = work_order.aircraft if work_order else None
        base = _aircraft_base(aircraft, base_by_code)
        base_id, base_code, base_name = _base_label(base, getattr(aircraft, "home_base", None))
        assigned_hours = round(sum(max(float(getattr(a, "allocated_hours", None) or 0.0), 0.0) for a in (task.assignments or [])), 2)
        roster_linked_hours = round(sum(link_hours.get(a.id, 0.0) for a in (task.assignments or [])), 2)
        estimated = float(task.estimated_manhours or 0.0)
        remaining = max(estimated - roster_linked_hours, 0.0) if task.estimated_manhours is not None else 0.0
        summary = schemas.WorkloadTaskSummary(
            task_id=task.id,
            work_order_id=task.work_order_id,
            wo_number=getattr(work_order, "wo_number", ""),
            aircraft_serial_number=task.aircraft_serial_number,
            aircraft_registration=getattr(aircraft, "registration", None),
            aircraft_model=getattr(aircraft, "aircraft_model_code", None) or getattr(aircraft, "template", None),
            base_station_id=base_id,
            base_code=base_code,
            base_name=base_name,
            task_code=task.task_code,
            title=task.title,
            priority=_enum_value(task.priority),
            status=_enum_value(task.status),
            planned_start=task.planned_start,
            planned_end=task.planned_end,
            estimated_manhours=task.estimated_manhours,
            task_assigned_hours=assigned_hours,
            roster_linked_hours=roster_linked_hours,
            remaining_manhours=round(remaining, 2),
            task_assignment_count=len(task.assignments or []),
            roster_link_count=sum(1 for a in (task.assignments or []) if link_hours.get(a.id, 0.0) > 0),
            has_estimate=task.estimated_manhours is not None,
            is_unplanned=task.planned_start is None,
            can_allocate=True,
        )
        task_summaries.append(summary)
        if work_order:
            bucket = by_work_order.setdefault(
                work_order.id,
                {
                    "work_order": work_order,
                    "aircraft": aircraft,
                    "base_id": base_id,
                    "base_code": base_code,
                    "base_name": base_name,
                    "open_task_count": 0,
                    "estimated_manhours": 0.0,
                    "task_assigned_hours": 0.0,
                    "roster_linked_hours": 0.0,
                    "missing_estimates": 0,
                },
            )
            bucket["open_task_count"] = int(bucket["open_task_count"]) + 1
            bucket["estimated_manhours"] = float(bucket["estimated_manhours"]) + estimated
            bucket["task_assigned_hours"] = float(bucket["task_assigned_hours"]) + assigned_hours
            bucket["roster_linked_hours"] = float(bucket["roster_linked_hours"]) + roster_linked_hours
            if task.estimated_manhours is None:
                bucket["missing_estimates"] = int(bucket["missing_estimates"]) + 1

    work_orders: list[schemas.WorkloadWorkOrderSummary] = []
    for bucket in by_work_order.values():
        wo = bucket["work_order"]
        aircraft = bucket["aircraft"]
        estimated = round(float(bucket["estimated_manhours"]), 2)
        linked = round(float(bucket["roster_linked_hours"]), 2)
        work_orders.append(
            schemas.WorkloadWorkOrderSummary(
                work_order_id=wo.id,
                wo_number=wo.wo_number,
                description=wo.description,
                check_type=wo.check_type,
                status=_enum_value(wo.status),
                due_date=wo.due_date,
                aircraft_serial_number=wo.aircraft_serial_number,
                aircraft_registration=getattr(aircraft, "registration", None),
                aircraft_model=getattr(aircraft, "aircraft_model_code", None) or getattr(aircraft, "template", None),
                base_station_id=bucket["base_id"],
                base_code=str(bucket["base_code"]),
                base_name=str(bucket["base_name"]),
                open_task_count=int(bucket["open_task_count"]),
                estimated_manhours=estimated,
                task_assigned_hours=round(float(bucket["task_assigned_hours"]), 2),
                roster_linked_hours=linked,
                remaining_manhours=round(max(estimated - linked, 0.0), 2),
            )
        )
    work_orders.sort(key=lambda item: (item.due_date or date.max, item.wo_number))
    return work_orders, task_summaries


def _build_capacity_summaries(
    *,
    assignments: list[models.RosterAssignment],
    task_summaries: list[schemas.WorkloadTaskSummary],
) -> list[schemas.BaseCapacitySummary]:
    buckets: dict[str, schemas.BaseCapacitySummary] = {}
    people_by_base: dict[str, set[str]] = defaultdict(set)
    certifying_by_base: dict[str, set[str]] = defaultdict(set)
    technician_by_base: dict[str, set[str]] = defaultdict(set)

    for assignment in assignments:
        base_id, base_code, base_name = _base_label(assignment.base_station)
        key = base_id or f"code:{base_code}"
        bucket = buckets.setdefault(key, schemas.BaseCapacitySummary(base_station_id=base_id, base_code=base_code, base_name=base_name))
        hours = _assignment_hours(assignment)
        if assignment.status in PRODUCTIVE_STATUSES:
            bucket.available_hours += hours
            bucket.duty_assignment_count += 1
            people_by_base[key].add(assignment.user_id)
            role_value = _enum_value(getattr(assignment.user, "role", "")) if assignment.user else ""
            if role_value in {"CERTIFYING_ENGINEER", "CERTIFYING_TECHNICIAN"}:
                certifying_by_base[key].add(assignment.user_id)
            if role_value == "TECHNICIAN":
                technician_by_base[key].add(assignment.user_id)
        if assignment.status == models.RosterAssignmentStatus.STANDBY:
            bucket.standby_hours += hours
        bucket.roster_linked_hours += sum(_link_hours(link) for link in assignment.task_links or [])

    for task in task_summaries:
        key = task.base_station_id or f"code:{task.base_code}"
        bucket = buckets.setdefault(key, schemas.BaseCapacitySummary(base_station_id=task.base_station_id, base_code=task.base_code, base_name=task.base_name or task.base_code))
        bucket.required_task_hours += float(task.estimated_manhours or 0.0)
        bucket.task_assigned_hours += task.task_assigned_hours
        bucket.remaining_task_hours += task.remaining_manhours
        bucket.open_task_count += 1
        if task.remaining_manhours > 0:
            bucket.unallocated_task_count += 1
        if not task.has_estimate:
            bucket.missing_estimate_count += 1

    for key, bucket in buckets.items():
        bucket.assigned_people = len(people_by_base.get(key, set()))
        bucket.certifying_people = len(certifying_by_base.get(key, set()))
        bucket.technician_people = len(technician_by_base.get(key, set()))
        bucket.available_hours = round(bucket.available_hours, 2)
        bucket.standby_hours = round(bucket.standby_hours, 2)
        bucket.roster_linked_hours = round(bucket.roster_linked_hours, 2)
        bucket.required_task_hours = round(bucket.required_task_hours, 2)
        bucket.task_assigned_hours = round(bucket.task_assigned_hours, 2)
        bucket.remaining_task_hours = round(bucket.remaining_task_hours, 2)
        bucket.remaining_capacity_hours = round(max(bucket.available_hours - bucket.roster_linked_hours, 0.0), 2)
        bucket.capacity_gap_hours = round(max(bucket.remaining_task_hours - bucket.remaining_capacity_hours, 0.0), 2)
        bucket.capacity_variance_hours = round(bucket.remaining_capacity_hours - bucket.remaining_task_hours, 2)
    return sorted(buckets.values(), key=lambda row: row.base_code)


def list_task_links_for_assignment(db: Session, *, amo_id: str, assignment_id: str) -> list[schemas.RosterTaskAssignmentLinkRead]:
    rows = (
        db.query(models.RosterTaskAssignmentLink)
        .options(
            selectinload(models.RosterTaskAssignmentLink.roster_assignment).selectinload(models.RosterAssignment.base_station),
            selectinload(models.RosterTaskAssignmentLink.task_assignment)
            .selectinload(work_models.TaskAssignment.task)
            .selectinload(work_models.TaskCard.work_order)
            .selectinload(work_models.WorkOrder.aircraft),
        )
        .filter(models.RosterTaskAssignmentLink.amo_id == amo_id, models.RosterTaskAssignmentLink.roster_assignment_id == assignment_id)
        .order_by(models.RosterTaskAssignmentLink.created_at.asc())
        .all()
    )
    return [_serialize_task_link(row) for row in rows]


def link_existing_task_assignment(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    roster_assignment_id: str,
    payload: schemas.RosterTaskLinkCreate,
) -> models.RosterTaskAssignmentLink:
    roster_assignment = db.query(models.RosterAssignment).filter(models.RosterAssignment.amo_id == amo_id, models.RosterAssignment.id == roster_assignment_id).first()
    if not roster_assignment:
        raise ValueError("Roster assignment not found.")
    task_assignment = db.query(work_models.TaskAssignment).filter(work_models.TaskAssignment.amo_id == amo_id, work_models.TaskAssignment.id == payload.task_assignment_id).first()
    if not task_assignment:
        raise ValueError("Task assignment not found.")
    if task_assignment.user_id != roster_assignment.user_id:
        raise ValueError("Task assignment user must match the roster assignment user.")
    row = models.RosterTaskAssignmentLink(
        amo_id=amo_id,
        roster_assignment_id=roster_assignment.id,
        task_assignment_id=task_assignment.id,
        allocated_start=payload.allocated_start,
        allocated_end=payload.allocated_end,
        allocated_hours=payload.allocated_hours,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def create_task_allocation_from_roster(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    roster_assignment_id: str,
    payload: schemas.RosterTaskAllocationCreate,
) -> models.RosterTaskAssignmentLink:
    roster_assignment = db.query(models.RosterAssignment).filter(models.RosterAssignment.amo_id == amo_id, models.RosterAssignment.id == roster_assignment_id).first()
    if not roster_assignment:
        raise ValueError("Roster assignment not found.")
    task = db.query(work_models.TaskCard).filter(work_models.TaskCard.amo_id == amo_id, work_models.TaskCard.id == payload.task_id).first()
    if not task:
        raise ValueError("Task card not found.")
    task_assignment = work_models.TaskAssignment(
        amo_id=amo_id,
        task_id=task.id,
        user_id=roster_assignment.user_id,
        role_on_task=payload.role_on_task,
        allocated_hours=payload.allocated_hours,
        status=payload.task_assignment_status,
    )
    db.add(task_assignment)
    db.flush()
    link_payload = schemas.RosterTaskLinkCreate(
        task_assignment_id=task_assignment.id,
        allocated_start=payload.allocated_start or roster_assignment.starts_at,
        allocated_end=payload.allocated_end or roster_assignment.ends_at,
        allocated_hours=payload.allocated_hours,
    )
    return link_existing_task_assignment(db, amo_id=amo_id, actor_user_id=actor_user_id, roster_assignment_id=roster_assignment_id, payload=link_payload)


def planning_board(db: Session, *, amo_id: str, from_date: date, to_date: date, base_station_id: Optional[str]) -> schemas.RosterPlanningBoardResponse:
    start_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    base_by_id, base_by_code = _base_maps(db, amo_id=amo_id)
    assignments = _query_published_assignments(db, amo_id=amo_id, start_dt=start_dt, end_dt=end_dt, base_station_id=base_station_id)
    version_ids = sorted({a.version_id for a in assignments})
    findings: list[models.RosterValidationFinding] = []
    if version_ids:
        findings = db.query(models.RosterValidationFinding).filter(models.RosterValidationFinding.version_id.in_(version_ids)).all()
    tasks = _query_workload_tasks(db, amo_id=amo_id, from_date=from_date, to_date=to_date, base_station_id=base_station_id, base_by_id=base_by_id, base_by_code=base_by_code)
    work_orders, task_summaries = _build_workload_summaries(db, amo_id=amo_id, tasks=tasks, base_by_code=base_by_code)
    base_capacity = _build_capacity_summaries(assignments=assignments, task_summaries=task_summaries)
    all_links = [link for assignment in assignments for link in (assignment.task_links or [])]
    available_hours = round(sum(_assignment_hours(a) for a in assignments if a.status in PRODUCTIVE_STATUSES), 2)
    standby_hours = round(sum(_assignment_hours(a) for a in assignments if a.status == models.RosterAssignmentStatus.STANDBY), 2)
    roster_linked_hours = round(sum(_link_hours(link) for link in all_links), 2)
    required_task_hours = round(sum(float(task.estimated_manhours or 0.0) for task in task_summaries), 2)
    remaining_task_hours = round(sum(task.remaining_manhours for task in task_summaries), 2)
    remaining_capacity_hours = round(max(available_hours - roster_linked_hours, 0.0), 2)
    metrics = schemas.PlanningBoardMetrics(
        assigned_people=len({a.user_id for a in assignments if a.status in PRODUCTIVE_STATUSES}),
        roster_assignment_count=len(assignments),
        productive_assignment_count=sum(1 for a in assignments if a.status in PRODUCTIVE_STATUSES),
        available_duty_hours=available_hours,
        standby_hours=standby_hours,
        roster_linked_hours=roster_linked_hours,
        remaining_capacity_hours=remaining_capacity_hours,
        required_task_hours=required_task_hours,
        task_assigned_hours=round(sum(task.task_assigned_hours for task in task_summaries), 2),
        remaining_task_hours=remaining_task_hours,
        capacity_gap_hours=round(max(remaining_task_hours - remaining_capacity_hours, 0.0), 2),
        capacity_variance_hours=round(remaining_capacity_hours - remaining_task_hours, 2),
        work_order_count=len(work_orders),
        task_count=len(task_summaries),
        unallocated_task_count=sum(1 for task in task_summaries if task.remaining_manhours > 0),
        missing_estimate_count=sum(1 for task in task_summaries if not task.has_estimate),
    )
    return schemas.RosterPlanningBoardResponse(
        from_date=from_date,
        to_date=to_date,
        base_station_id=base_station_id,
        published_version_id=version_ids[-1] if len(version_ids) == 1 else None,
        assignments=[serialize_assignment(item) for item in assignments],
        findings=[schemas.RosterValidationFindingRead.from_orm(item) for item in findings],
        metrics=metrics,
        base_capacity=base_capacity,
        work_orders=work_orders,
        tasks=task_summaries,
        task_links=[_serialize_task_link(link) for link in all_links],
    )


def roster_contracts() -> schemas.RosterContractResponse:
    return schemas.RosterContractResponse(
        route_contracts={
            "rostering_root": "/maintenance/:amoCode/rostering",
            "rostering_dashboard": "/maintenance/:amoCode/rostering/dashboard",
            "rostering_calendar": "/maintenance/:amoCode/rostering/calendar",
            "rostering_planning_board": "/maintenance/:amoCode/rostering/planning-board",
            "rostering_my_roster": "/maintenance/:amoCode/rostering/my-roster",
            "rostering_training_impact": "/maintenance/:amoCode/rostering/training-impact",
            "rostering_reports": "/maintenance/:amoCode/rostering/reports",
            "rostering_settings": "/maintenance/:amoCode/rostering/settings",
            "training_person": "/maintenance/:amoCode/qms/training-competence/people/:userId",
            "admin_user_detail": "/maintenance/:amoCode/admin/users/:userId",
            "planning_work_orders": "/maintenance/:amoCode/planning/work-orders",
            "planning_work_packages": "/maintenance/:amoCode/planning/work-packages",
            "production_control_board": "/maintenance/:amoCode/production/control-board",
            "maintenance_work_order_detail": "/maintenance/:amoCode/maintenance/work-orders/:woId",
        },
        source_modules={
            "personnel_identity": "accounts.users.id",
            "personnel_profile": "accounts.personnel_profiles linked by user_id",
            "base_station": "foundations.base_stations",
            "availability": "foundations availability service backed by quality.user_availability",
            "training_due": "training compliance service",
            "fleet_aircraft": "fleet.aircraft home_base mapped to foundations.base_stations",
            "workload": "work_orders and task_cards",
            "task_allocation": "work.task_assignments linked through roster_task_assignment_links",
            "work_logs": "work.work_log_entries retained as actual task man-hour source",
        },
    )
