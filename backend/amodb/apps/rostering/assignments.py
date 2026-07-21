# backend/amodb/apps/rostering/assignments.py
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session, selectinload

from ..work import models as work_models
from ..workforce import calculations as workforce_calculations
from ..workforce import services as workforce_services
from . import common, models, schemas

UTC = timezone.utc


def list_assignments(db: Session, *, amo_id: str, version_id: str, include_deleted: bool = False) -> list[models.RosterAssignment]:
    query = db.query(models.RosterAssignment).options(
        selectinload(models.RosterAssignment.user),
        selectinload(models.RosterAssignment.department),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.task_links).selectinload(models.RosterTaskAssignmentLink.task_assignment),
    ).filter(models.RosterAssignment.amo_id == amo_id, models.RosterAssignment.version_id == version_id)
    if not include_deleted:
        query = query.filter(models.RosterAssignment.deleted_at.is_(None))
    return query.order_by(models.RosterAssignment.starts_at.asc(), models.RosterAssignment.user_id.asc(), models.RosterAssignment.id.asc()).all()


def _assignment_snapshot(row: models.RosterAssignment) -> dict[str, Any]:
    return {
        "user_id": row.user_id,
        "department_id": row.department_id,
        "base_station_id": row.base_station_id,
        "shift_template_id": row.shift_template_id,
        "status": common.enum_value(row.status),
        "source": common.enum_value(row.source),
        "source_reference_id": row.source_reference_id,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "planned_minutes": row.planned_minutes,
        "role_label": row.role_label,
        "team_code": row.team_code,
        "location_label": row.location_label,
        "task_note": row.task_note,
        "change_reason": row.change_reason,
        "state_revision": row.state_revision,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def _validate_assignment_payload(
    db: Session,
    *,
    version: models.RosterVersion,
    payload: schemas.RosterAssignmentCreate,
) -> tuple[Any, Optional[Any], Optional[Any], Optional[Any], int]:
    common.ensure_draft(version)
    user = common.require_user(db, amo_id=version.amo_id, user_id=payload.user_id, active_only=True)
    department_id = payload.department_id or user.department_id
    department = common.require_department(db, amo_id=version.amo_id, department_id=department_id)
    contract = workforce_services.active_contract_for_user(db, amo_id=version.amo_id, user_id=user.id, on_date=payload.starts_at.date())
    base_station_id = payload.base_station_id or getattr(contract, "primary_base_station_id", None)
    base = common.require_base(db, amo_id=version.amo_id, base_station_id=base_station_id)
    shift = common.require_shift_template(db, amo_id=version.amo_id, shift_template_id=payload.shift_template_id)
    if payload.ends_at <= payload.starts_at:
        raise ValueError("Assignment end must be after start")
    period_start = datetime.combine(version.period.starts_on, time.min, tzinfo=UTC)
    period_end = datetime.combine(version.period.ends_on + timedelta(days=1), time.min, tzinfo=UTC)
    if payload.starts_at < period_start or payload.ends_at > period_end:
        raise ValueError("Assignment must fall inside the roster period")
    planned = payload.planned_minutes
    if planned is None:
        planned = workforce_calculations.duration_minutes(payload.starts_at, payload.ends_at)
    return user, department, base, shift, int(planned)


def _create_assignment_row(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterAssignmentCreate,
    bump_parent: bool = True,
) -> models.RosterAssignment:
    user, department, base, shift, planned = _validate_assignment_payload(db, version=version, payload=payload)
    if payload.source_reference_id:
        existing = db.query(models.RosterAssignment).filter(
            models.RosterAssignment.version_id == version.id,
            models.RosterAssignment.source == payload.source,
            models.RosterAssignment.source_reference_id == payload.source_reference_id,
        ).first()
        if existing:
            if existing.deleted_at is None:
                return existing
            existing.deleted_at = None
            existing.deleted_by_user_id = None
            existing.updated_by_user_id = actor_user_id
            existing.state_revision += 1
            db.add(existing)
            if bump_parent:
                common.bump_version(version)
                db.add(version)
            db.flush()
            return existing
    row = models.RosterAssignment(
        amo_id=version.amo_id,
        version_id=version.id,
        user_id=user.id,
        department_id=getattr(department, "id", None),
        base_station_id=getattr(base, "id", None),
        shift_template_id=getattr(shift, "id", None),
        status=payload.status,
        source=payload.source,
        source_reference_id=payload.source_reference_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        planned_minutes=planned,
        role_label=payload.role_label,
        team_code=payload.team_code,
        location_label=payload.location_label,
        task_note=payload.task_note,
        change_reason=payload.change_reason,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    if bump_parent:
        common.bump_version(version)
        db.add(version)
    db.flush()
    return row


def create_assignment(db: Session, *, version: models.RosterVersion, actor_user_id: str, payload: schemas.RosterAssignmentCreate) -> models.RosterAssignment:
    row = _create_assignment_row(db, version=version, actor_user_id=actor_user_id, payload=payload)
    common.audit(db, amo_id=version.amo_id, actor_user_id=actor_user_id, entity_type="RosterAssignment", entity_id=row.id, action="create", after=_assignment_snapshot(row), metadata={"version_id": version.id})
    return row


def update_assignment(
    db: Session,
    *,
    row: models.RosterAssignment,
    actor_user_id: str,
    payload: schemas.RosterAssignmentUpdate,
) -> models.RosterAssignment:
    version = common.get_version(db, amo_id=row.amo_id, version_id=row.version_id, lock=True)
    if not version:
        raise ValueError("Roster version not found")
    common.ensure_draft(version)
    common.check_assignment_revision(row, payload.expected_state_revision)
    before = _assignment_snapshot(row)
    fields = common.model_fields_set(payload)
    for key, value in common.dump(payload, exclude_unset=True).items():
        if key == "expected_state_revision":
            continue
        setattr(row, key, value)
    if row.ends_at <= row.starts_at:
        raise ValueError("Assignment end must be after start")
    if "department_id" in fields:
        common.require_department(db, amo_id=row.amo_id, department_id=row.department_id)
    if "base_station_id" in fields:
        common.require_base(db, amo_id=row.amo_id, base_station_id=row.base_station_id)
    if "shift_template_id" in fields:
        common.require_shift_template(db, amo_id=row.amo_id, shift_template_id=row.shift_template_id)
    if "planned_minutes" not in fields:
        row.planned_minutes = workforce_calculations.duration_minutes(row.starts_at, row.ends_at)
    row.state_revision += 1
    row.updated_by_user_id = actor_user_id
    common.bump_version(version)
    db.add(row)
    db.add(version)
    db.flush()
    common.audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="RosterAssignment", entity_id=row.id, action="update", before=before, after=_assignment_snapshot(row), metadata={"version_id": version.id})
    return row


def delete_assignment(db: Session, *, row: models.RosterAssignment, actor_user_id: str, payload: schemas.RosterAssignmentDeleteRequest) -> None:
    version = common.get_version(db, amo_id=row.amo_id, version_id=row.version_id, lock=True)
    if not version:
        raise ValueError("Roster version not found")
    common.ensure_draft(version)
    common.check_assignment_revision(row, payload.expected_state_revision)
    before = _assignment_snapshot(row)
    row.deleted_at = common.utcnow()
    row.deleted_by_user_id = actor_user_id
    row.updated_by_user_id = actor_user_id
    row.change_reason = payload.reason
    row.state_revision += 1
    common.bump_version(version)
    db.add(row)
    db.add(version)
    db.flush()
    common.audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="RosterAssignment", entity_id=row.id, action="delete", before=before, after=_assignment_snapshot(row), metadata={"version_id": version.id})


def bulk_create_assignments(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterBulkAssignmentRequest,
) -> schemas.RosterBulkAssignmentResult:
    common.ensure_draft(version)
    common.check_version_revision(version, payload.expected_version_revision)
    request_payload = common.dump(payload)
    request_hash = common.canonical_hash(request_payload)
    receipt = common.command_receipt(db, amo_id=version.amo_id, idempotency_key=payload.idempotency_key, operation="BULK_ASSIGNMENTS", request_hash=request_hash)
    if receipt:
        assignment_ids = list((receipt.response_json or {}).get("assignment_ids", []))
        rows = db.query(models.RosterAssignment).options(
            selectinload(models.RosterAssignment.user),
            selectinload(models.RosterAssignment.department),
            selectinload(models.RosterAssignment.base_station),
            selectinload(models.RosterAssignment.shift_template),
            selectinload(models.RosterAssignment.task_links),
        ).filter(models.RosterAssignment.id.in_(assignment_ids)).all()
        by_id = {row.id: row for row in rows}
        return schemas.RosterBulkAssignmentResult(
            version_id=version.id,
            created=[common.serialize_assignment(by_id[row_id]) for row_id in assignment_ids if row_id in by_id],
            skipped=list((receipt.response_json or {}).get("skipped", [])),
            conflicts=list((receipt.response_json or {}).get("conflicts", [])),
            idempotent_replay=True,
        )
    created: list[models.RosterAssignment] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    with db.begin_nested():
        for index, item in enumerate(payload.assignments):
            try:
                create_payload = schemas.RosterAssignmentCreate(**item.model_dump(exclude={"client_id"}))
                existing = None
                if create_payload.source_reference_id:
                    existing = db.query(models.RosterAssignment).filter(
                        models.RosterAssignment.version_id == version.id,
                        models.RosterAssignment.source == create_payload.source,
                        models.RosterAssignment.source_reference_id == create_payload.source_reference_id,
                        models.RosterAssignment.deleted_at.is_(None),
                    ).first()
                if existing:
                    skipped.append({"index": index, "client_id": item.client_id, "reason": "DUPLICATE_SOURCE_REFERENCE", "assignment_id": existing.id})
                    continue
                row = _create_assignment_row(db, version=version, actor_user_id=actor_user_id, payload=create_payload, bump_parent=False)
                created.append(row)
            except Exception as exc:
                conflict = {"index": index, "client_id": item.client_id, "reason": str(exc)}
                conflicts.append(conflict)
                if payload.atomic:
                    raise ValueError(f"Bulk assignment failed at item {index}: {exc}") from exc
        if created:
            common.bump_version(version)
            db.add(version)
        db.flush()
    response_json = {"version_id": version.id, "assignment_ids": [row.id for row in created], "skipped": skipped, "conflicts": conflicts}
    common.save_command_receipt(db, amo_id=version.amo_id, idempotency_key=payload.idempotency_key, operation="BULK_ASSIGNMENTS", actor_user_id=actor_user_id, request_hash=request_hash, response_json=response_json)
    common.audit(db, amo_id=version.amo_id, actor_user_id=actor_user_id, entity_type="RosterVersion", entity_id=version.id, action="bulk_assign", after={"created_count": len(created), "skipped_count": len(skipped), "conflict_count": len(conflicts), "idempotency_key": payload.idempotency_key})
    refreshed = list_assignments(db, amo_id=version.amo_id, version_id=version.id)
    by_id = {row.id: row for row in refreshed}
    return schemas.RosterBulkAssignmentResult(
        version_id=version.id,
        created=[common.serialize_assignment(by_id[row.id]) for row in created if row.id in by_id],
        skipped=skipped,
        conflicts=conflicts,
    )


def generate_from_patterns(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.PatternGenerationRequest,
) -> schemas.RosterBulkAssignmentResult:
    common.ensure_draft(version)
    common.check_version_revision(version, payload.expected_version_revision)
    request_hash = common.canonical_hash(common.dump(payload))
    receipt = common.command_receipt(db, amo_id=version.amo_id, idempotency_key=payload.idempotency_key, operation="GENERATE_PATTERN", request_hash=request_hash)
    if receipt:
        assignment_ids = list((receipt.response_json or {}).get("assignment_ids", []))
        rows = list_assignments(db, amo_id=version.amo_id, version_id=version.id)
        by_id = {row.id: row for row in rows}
        return schemas.RosterBulkAssignmentResult(
            version_id=version.id,
            created=[common.serialize_assignment(by_id[row_id]) for row_id in assignment_ids if row_id in by_id],
            skipped=list((receipt.response_json or {}).get("skipped", [])),
            conflicts=list((receipt.response_json or {}).get("conflicts", [])),
            idempotent_replay=True,
        )
    preview = workforce_services.preview_patterns(
        db,
        amo_id=version.amo_id,
        payload=__import__("amodb.apps.workforce.schemas", fromlist=["PatternPreviewRequest"]).PatternPreviewRequest(
            from_date=payload.from_date,
            to_date=payload.to_date,
            user_ids=payload.user_ids,
            roster_version_id=version.id,
        ),
    )
    zone = workforce_calculations.get_zone(version.period.timezone_name or "UTC")
    items: list[schemas.RosterBulkAssignmentItem] = []
    skipped: list[dict[str, Any]] = []
    for row in preview.items:
        if row.duplicate and payload.skip_duplicates:
            skipped.append({"source_reference_id": row.source_reference_id, "reason": "DUPLICATE_SOURCE_REFERENCE"})
            continue
        if row.conflicts:
            skipped.append({"source_reference_id": row.source_reference_id, "reason": "PATTERN_PREVIEW_CONFLICT", "conflicts": row.conflicts})
            continue
        starts_at = row.starts_at
        ends_at = row.ends_at
        if starts_at is None or ends_at is None:
            starts_at = datetime.combine(row.work_date, time.min, tzinfo=zone).astimezone(UTC)
            ends_at = datetime.combine(row.work_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        items.append(schemas.RosterBulkAssignmentItem(
            user_id=row.user_id,
            starts_at=starts_at,
            ends_at=ends_at,
            base_station_id=row.base_station_id,
            shift_template_id=row.shift_template_id,
            status=models.RosterAssignmentStatus(row.status.value),
            source=models.RosterAssignmentSource.PATTERN,
            source_reference_id=row.source_reference_id,
            planned_minutes=row.planned_minutes,
            change_reason="Generated from assigned work pattern",
            client_id=row.source_reference_id,
        ))
    if not items:
        common.save_command_receipt(db, amo_id=version.amo_id, idempotency_key=payload.idempotency_key, operation="GENERATE_PATTERN", actor_user_id=actor_user_id, request_hash=request_hash, response_json={"version_id": version.id, "assignment_ids": [], "skipped": skipped, "conflicts": []})
        return schemas.RosterBulkAssignmentResult(version_id=version.id, skipped=skipped)
    bulk = bulk_create_assignments(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=schemas.RosterBulkAssignmentRequest(
            assignments=items,
            idempotency_key=f"{payload.idempotency_key}:bulk",
            expected_version_revision=version.state_revision,
            atomic=True,
        ),
    )
    response_json = {"version_id": version.id, "assignment_ids": [row.id for row in bulk.created], "skipped": skipped + bulk.skipped, "conflicts": bulk.conflicts}
    common.save_command_receipt(db, amo_id=version.amo_id, idempotency_key=payload.idempotency_key, operation="GENERATE_PATTERN", actor_user_id=actor_user_id, request_hash=request_hash, response_json=response_json)
    common.audit(db, amo_id=version.amo_id, actor_user_id=actor_user_id, entity_type="RosterVersion", entity_id=version.id, action="generate_pattern", after={"created_count": len(bulk.created), "skipped_count": len(skipped) + len(bulk.skipped), "idempotency_key": payload.idempotency_key})
    bulk.skipped = skipped + bulk.skipped
    return bulk


def _validate_allocation_window(assignment: models.RosterAssignment, *, start: Optional[datetime], end: Optional[datetime], hours: Optional[float]) -> None:
    if start and start < assignment.starts_at:
        raise ValueError("Task allocation starts before the roster assignment")
    if end and end > assignment.ends_at:
        raise ValueError("Task allocation ends after the roster assignment")
    if start and end and end <= start:
        raise ValueError("Task allocation end must be after start")
    if hours is not None and hours > common.assignment_hours(assignment) + 0.001:
        raise ValueError("Task allocation exceeds available roster hours")


def list_task_links(db: Session, *, amo_id: str, assignment_id: str) -> list[models.RosterTaskAssignmentLink]:
    return db.query(models.RosterTaskAssignmentLink).options(
        selectinload(models.RosterTaskAssignmentLink.roster_assignment).selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterTaskAssignmentLink.task_assignment).selectinload(work_models.TaskAssignment.task).selectinload(work_models.TaskCard.work_order).selectinload(work_models.WorkOrder.aircraft),
    ).filter(models.RosterTaskAssignmentLink.amo_id == amo_id, models.RosterTaskAssignmentLink.roster_assignment_id == assignment_id).order_by(models.RosterTaskAssignmentLink.created_at.asc(), models.RosterTaskAssignmentLink.id.asc()).all()


def serialize_task_link(link: models.RosterTaskAssignmentLink) -> schemas.RosterTaskAssignmentLinkRead:
    task_assignment = link.task_assignment
    task = task_assignment.task if task_assignment else None
    work_order = task.work_order if task else None
    aircraft = work_order.aircraft if work_order else None
    roster_assignment = link.roster_assignment
    base = roster_assignment.base_station if roster_assignment else None
    return schemas.RosterTaskAssignmentLinkRead(
        id=link.id,
        amo_id=link.amo_id,
        roster_assignment_id=link.roster_assignment_id,
        task_assignment_id=link.task_assignment_id,
        task_id=getattr(task, "id", 0),
        user_id=getattr(task_assignment, "user_id", ""),
        role_on_task=common.enum_value(getattr(task_assignment, "role_on_task", "")),
        task_assignment_status=common.enum_value(getattr(task_assignment, "status", "")),
        allocated_start=link.allocated_start,
        allocated_end=link.allocated_end,
        allocated_hours=link.allocated_hours,
        task_title=getattr(task, "title", None),
        task_code=getattr(task, "task_code", None),
        work_order_id=getattr(work_order, "id", None),
        wo_number=getattr(work_order, "wo_number", None),
        aircraft_serial_number=getattr(work_order, "aircraft_serial_number", None),
        aircraft_registration=getattr(aircraft, "registration", None),
        base_station_id=getattr(base, "id", None),
        base_code=getattr(base, "code", None),
        created_by_user_id=link.created_by_user_id,
        created_at=link.created_at,
    )


def link_task_assignment(
    db: Session,
    *,
    assignment: models.RosterAssignment,
    actor_user_id: str,
    payload: schemas.RosterTaskLinkCreate,
) -> models.RosterTaskAssignmentLink:
    if assignment.deleted_at is not None:
        raise ValueError("Deleted roster assignments cannot receive task allocations")
    task_assignment = db.query(work_models.TaskAssignment).options(selectinload(work_models.TaskAssignment.task)).filter(
        work_models.TaskAssignment.amo_id == assignment.amo_id,
        work_models.TaskAssignment.id == payload.task_assignment_id,
    ).first()
    if not task_assignment:
        raise ValueError("Task assignment not found in AMO scope")
    if task_assignment.user_id != assignment.user_id:
        raise ValueError("Task assignment and roster assignment must belong to the same person")
    _validate_allocation_window(assignment, start=payload.allocated_start, end=payload.allocated_end, hours=payload.allocated_hours)
    existing = db.query(models.RosterTaskAssignmentLink).filter(
        models.RosterTaskAssignmentLink.roster_assignment_id == assignment.id,
        models.RosterTaskAssignmentLink.task_assignment_id == task_assignment.id,
    ).first()
    if existing:
        return existing
    row = models.RosterTaskAssignmentLink(
        amo_id=assignment.amo_id,
        roster_assignment_id=assignment.id,
        task_assignment_id=task_assignment.id,
        allocated_start=payload.allocated_start,
        allocated_end=payload.allocated_end,
        allocated_hours=payload.allocated_hours,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(db, amo_id=assignment.amo_id, actor_user_id=actor_user_id, entity_type="RosterTaskAssignmentLink", entity_id=row.id, action="create", after={"roster_assignment_id": assignment.id, "task_assignment_id": task_assignment.id, "allocated_hours": payload.allocated_hours})
    return row


def allocate_to_task(
    db: Session,
    *,
    assignment: models.RosterAssignment,
    actor_user_id: str,
    payload: schemas.RosterTaskAllocationCreate,
) -> models.RosterTaskAssignmentLink:
    task = db.query(work_models.TaskCard).filter(work_models.TaskCard.amo_id == assignment.amo_id, work_models.TaskCard.id == payload.task_id).first()
    if not task:
        raise ValueError("Task card not found in AMO scope")
    task_assignment = db.query(work_models.TaskAssignment).filter(
        work_models.TaskAssignment.amo_id == assignment.amo_id,
        work_models.TaskAssignment.task_id == task.id,
        work_models.TaskAssignment.user_id == assignment.user_id,
        work_models.TaskAssignment.role_on_task == payload.role_on_task,
    ).first()
    if not task_assignment:
        task_assignment = work_models.TaskAssignment(
            amo_id=assignment.amo_id,
            task_id=task.id,
            user_id=assignment.user_id,
            role_on_task=payload.role_on_task,
            allocated_hours=payload.allocated_hours,
            status=payload.task_assignment_status,
        )
        db.add(task_assignment)
        db.flush()
    return link_task_assignment(
        db,
        assignment=assignment,
        actor_user_id=actor_user_id,
        payload=schemas.RosterTaskLinkCreate(
            task_assignment_id=task_assignment.id,
            allocated_start=payload.allocated_start,
            allocated_end=payload.allocated_end,
            allocated_hours=payload.allocated_hours,
        ),
    )
