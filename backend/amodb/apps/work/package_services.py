from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet import models as fleet_models
from amodb.apps.fleet import services as fleet_services
from amodb.apps.maintenance_program import service as program_services

from . import models as work_models
from .package_models import WorkPackage, WorkPackageOrder, WorkPackageStatus
from .package_schemas import (
    WorkPackageAttachOrder,
    WorkPackageCreate,
    WorkPackageOrderRead,
    WorkPackageRead,
    WorkPackageReadinessRead,
    WorkPackageStatusUpdate,
    WorkPackageUpdate,
)

PACKAGE_TRANSITIONS = {
    WorkPackageStatus.DRAFT.value: {WorkPackageStatus.REVIEW.value, WorkPackageStatus.CANCELLED.value},
    WorkPackageStatus.REVIEW.value: {WorkPackageStatus.DRAFT.value, WorkPackageStatus.READY.value, WorkPackageStatus.CANCELLED.value},
    WorkPackageStatus.READY.value: {WorkPackageStatus.REVIEW.value, WorkPackageStatus.RELEASED.value, WorkPackageStatus.CANCELLED.value},
    WorkPackageStatus.RELEASED.value: {WorkPackageStatus.IN_PROGRESS.value, WorkPackageStatus.CANCELLED.value},
    WorkPackageStatus.IN_PROGRESS.value: {WorkPackageStatus.CLOSED.value},
    WorkPackageStatus.CLOSED.value: set(),
    WorkPackageStatus.CANCELLED.value: set(),
}


def _audit(db: Session, *, amo_id: str, actor_id: str | None, entity_id: str, action: str, before: dict | None, after: dict | None) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="WorkPackage",
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_id,
            before_json=before,
            after_json=after,
        ),
    )


def _get_package(db: Session, *, amo_id: str, package_id: int) -> WorkPackage:
    package = (
        db.query(WorkPackage)
        .filter(WorkPackage.amo_id == amo_id, WorkPackage.id == package_id)
        .first()
    )
    if not package:
        raise HTTPException(status_code=404, detail="Work package not found")
    return package


def _get_aircraft(db: Session, *, amo_id: str, aircraft_serial_number: str):
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(
            fleet_models.Aircraft.amo_id == amo_id,
            fleet_models.Aircraft.serial_number == aircraft_serial_number,
        )
        .first()
    )
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return aircraft


def _order_read(link: WorkPackageOrder) -> WorkPackageOrderRead:
    order = link.work_order
    tasks = list(order.tasks or [])
    completed = sum(
        1
        for task in tasks
        if task.status in {
            work_models.TaskStatusEnum.COMPLETED,
            work_models.TaskStatusEnum.INSPECTED,
            work_models.TaskStatusEnum.CLOSED,
        }
    )
    estimated = sum(float(task.estimated_manhours or 0) for task in tasks)
    return WorkPackageOrderRead(
        link_id=link.id,
        work_order_id=order.id,
        wo_number=order.wo_number,
        status=order.status.value if hasattr(order.status, "value") else str(order.status),
        description=order.description,
        due_date=order.due_date,
        sequence_no=link.sequence_no,
        source_type=link.source_type,
        source_ref=link.source_ref,
        task_count=len(tasks),
        completed_task_count=completed,
        estimated_manhours=round(estimated, 2),
    )


def package_read(package: WorkPackage) -> WorkPackageRead:
    links = sorted(package.order_links or [], key=lambda link: (link.sequence_no, link.id))
    return WorkPackageRead(
        id=package.id,
        package_ref=package.package_ref,
        aircraft_serial_number=package.aircraft_serial_number,
        title=package.title,
        description=package.description,
        check_type=package.check_type,
        status=package.status,
        due_date=package.due_date,
        planned_start=package.planned_start,
        planned_end=package.planned_end,
        source_horizon_days=package.source_horizon_days,
        baseline_generated_at=package.baseline_generated_at,
        readiness_status=package.readiness_status,
        readiness_json=package.readiness_json or {},
        created_at=package.created_at,
        updated_at=package.updated_at,
        orders=[_order_read(link) for link in links],
    )


def list_packages(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str | None = None,
    status_filter: str | None = None,
) -> list[WorkPackageRead]:
    query = db.query(WorkPackage).filter(WorkPackage.amo_id == amo_id)
    if aircraft_serial_number:
        query = query.filter(WorkPackage.aircraft_serial_number == aircraft_serial_number)
    if status_filter:
        query = query.filter(WorkPackage.status == status_filter.upper())
    rows = query.order_by(WorkPackage.updated_at.desc()).all()
    return [package_read(row) for row in rows]


def attach_order(
    db: Session,
    *,
    package: WorkPackage,
    payload: WorkPackageAttachOrder,
    actor: User,
) -> WorkPackageOrder:
    order = (
        db.query(work_models.WorkOrder)
        .filter(
            work_models.WorkOrder.amo_id == package.amo_id,
            work_models.WorkOrder.id == payload.work_order_id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")
    if order.aircraft_serial_number != package.aircraft_serial_number:
        raise HTTPException(status_code=400, detail="Work order aircraft does not match the package aircraft")
    existing = (
        db.query(WorkPackageOrder)
        .filter(WorkPackageOrder.amo_id == package.amo_id, WorkPackageOrder.work_order_id == order.id)
        .first()
    )
    if existing:
        if existing.work_package_id == package.id:
            return existing
        raise HTTPException(status_code=409, detail="Work order already belongs to another work package")
    sequence = (
        db.query(WorkPackageOrder)
        .filter(WorkPackageOrder.work_package_id == package.id)
        .count()
        + 1
    )
    link = WorkPackageOrder(
        amo_id=package.amo_id,
        work_package_id=package.id,
        work_order_id=order.id,
        sequence_no=sequence,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        added_by_user_id=actor.id,
    )
    order.work_package_ref = package.package_ref
    order.updated_by_user_id = actor.id
    db.add(order)
    db.add(link)
    db.flush()
    return link


def create_package(
    db: Session,
    *,
    amo_id: str,
    payload: WorkPackageCreate,
    actor: User,
) -> WorkPackage:
    _get_aircraft(db, amo_id=amo_id, aircraft_serial_number=payload.aircraft_serial_number)
    if payload.package_ref:
        duplicate = (
            db.query(WorkPackage)
            .filter(WorkPackage.amo_id == amo_id, WorkPackage.package_ref == payload.package_ref)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Work package reference already exists")
    package = WorkPackage(
        amo_id=amo_id,
        package_ref=payload.package_ref or "PENDING",
        aircraft_serial_number=payload.aircraft_serial_number,
        title=payload.title,
        description=payload.description,
        check_type=payload.check_type,
        due_date=payload.due_date,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        source_horizon_days=payload.source_horizon_days,
        baseline_generated_at=datetime.now(UTC),
        readiness_json={},
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.add(package)
    db.flush()
    if package.package_ref == "PENDING":
        package.package_ref = f"WP-{datetime.now(UTC):%Y%m%d}-{package.id:05d}"
        db.flush()

    selected_ids = sorted(set(payload.program_item_ids))
    if selected_ids:
        assigned = program_services.list_aircraft_program_items_for_aircraft(
            db,
            amo_id=amo_id,
            aircraft_serial_number=payload.aircraft_serial_number,
        )
        available = {item.program_item_id for item in assigned}
        missing = sorted(set(selected_ids) - available)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Selected maintenance requirements are not assigned to this aircraft.",
                    "program_item_ids": missing,
                },
            )
        order = program_services.create_work_order_from_program_items(
            db,
            amo_id=amo_id,
            aircraft_serial_number=payload.aircraft_serial_number,
            program_item_ids=selected_ids,
            check_type=payload.check_type,
            wo_number=f"{package.package_ref}-01",
            created_by_user_id=actor.id,
            description=payload.description or payload.title,
        )
        order.work_package_ref = package.package_ref
        if payload.due_date:
            order.due_date = payload.due_date
        db.add(order)
        db.flush()
        attach_order(
            db,
            package=package,
            payload=WorkPackageAttachOrder(
                work_order_id=order.id,
                source_type="PROGRAM",
                source_ref=",".join(str(item_id) for item_id in selected_ids),
            ),
            actor=actor,
        )

    calculate_readiness(db, package=package)
    _audit(
        db,
        amo_id=amo_id,
        actor_id=actor.id,
        entity_id=str(package.id),
        action="create",
        before=None,
        after={"package_ref": package.package_ref, "aircraft": package.aircraft_serial_number},
    )
    return package


def update_package(
    db: Session,
    *,
    package: WorkPackage,
    payload: WorkPackageUpdate,
    actor: User,
) -> WorkPackage:
    if package.status not in {WorkPackageStatus.DRAFT.value, WorkPackageStatus.REVIEW.value}:
        raise HTTPException(status_code=409, detail="Released or completed packages cannot be edited")
    before = package_read(package).model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(package, field, value)
    if package.planned_start and package.planned_end and package.planned_end < package.planned_start:
        raise HTTPException(status_code=400, detail="planned_end must not be before planned_start")
    package.updated_by_user_id = actor.id
    db.add(package)
    calculate_readiness(db, package=package)
    _audit(
        db,
        amo_id=package.amo_id,
        actor_id=actor.id,
        entity_id=str(package.id),
        action="update",
        before=before,
        after=package_read(package).model_dump(mode="json"),
    )
    return package


def calculate_readiness(db: Session, *, package: WorkPackage) -> WorkPackageReadinessRead:
    blockers: list[str] = []
    warnings: list[str] = []
    links = list(package.order_links or [])
    orders = [link.work_order for link in links]
    tasks = [task for order in orders for task in (order.tasks or [])]

    if not orders:
        blockers.append("No work orders are attached to the package.")
    if orders and not tasks:
        blockers.append("Attached work orders contain no task cards.")
    if package.planned_start and package.planned_end and package.planned_end < package.planned_start:
        blockers.append("Planned end is before planned start.")
    if any(order.aircraft_serial_number != package.aircraft_serial_number for order in orders):
        blockers.append("One or more work orders belong to a different aircraft.")
    if any(order.status in {work_models.WorkOrderStatusEnum.CANCELLED, work_models.WorkOrderStatusEnum.CLOSED, work_models.WorkOrderStatusEnum.ARCHIVED} for order in orders):
        blockers.append("Cancelled, closed, or archived work orders cannot be released in this package.")

    document_blockers = fleet_services.get_blocking_documents(
        db,
        package.aircraft_serial_number,
        amo_id=package.amo_id,
    )
    if document_blockers:
        blockers.append(f"{len(document_blockers)} mandatory aircraft document(s) block release.")
    missing_estimates = sum(1 for task in tasks if task.estimated_manhours is None)
    if missing_estimates:
        warnings.append(f"{missing_estimates} task(s) have no estimated man-hours.")
    duplicate_inspection_tasks = sum(1 for task in tasks if task.requires_duplicate_inspection)
    if duplicate_inspection_tasks:
        warnings.append(f"{duplicate_inspection_tasks} task(s) require duplicate inspection planning.")

    readiness_status = "BLOCKED" if blockers else ("ATTENTION" if warnings else "READY")
    metrics: dict[str, Any] = {
        "work_orders": len(orders),
        "tasks": len(tasks),
        "estimated_manhours": round(sum(float(task.estimated_manhours or 0) for task in tasks), 2),
        "missing_estimates": missing_estimates,
        "duplicate_inspection_tasks": duplicate_inspection_tasks,
        "document_blockers": len(document_blockers),
    }
    generated_at = datetime.now(UTC)
    package.readiness_status = readiness_status
    package.readiness_json = {
        "blockers": blockers,
        "warnings": warnings,
        "metrics": metrics,
        "generated_at": generated_at.isoformat(),
    }
    db.add(package)
    db.flush()
    return WorkPackageReadinessRead(
        work_package_id=package.id,
        readiness_status=readiness_status,
        blockers=blockers,
        warnings=warnings,
        metrics=metrics,
        generated_at=generated_at,
    )


def change_status(
    db: Session,
    *,
    package: WorkPackage,
    payload: WorkPackageStatusUpdate,
    actor: User,
) -> WorkPackage:
    target = payload.status
    if target == package.status:
        return package
    allowed = PACKAGE_TRANSITIONS.get(package.status, set())
    if target not in allowed:
        raise HTTPException(status_code=409, detail=f"Invalid work-package transition {package.status} -> {target}")
    readiness = calculate_readiness(db, package=package)
    if target in {WorkPackageStatus.READY.value, WorkPackageStatus.RELEASED.value} and readiness.readiness_status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Work package is not ready for this transition.",
                "blockers": readiness.blockers,
                "warnings": readiness.warnings,
            },
        )
    before = {"status": package.status}
    package.status = target
    package.updated_by_user_id = actor.id
    if target == WorkPackageStatus.RELEASED.value:
        for link in package.order_links or []:
            order = link.work_order
            if order.status == work_models.WorkOrderStatusEnum.DRAFT:
                order.status = work_models.WorkOrderStatusEnum.RELEASED
                order.updated_by_user_id = actor.id
                db.add(order)
    if target == WorkPackageStatus.IN_PROGRESS.value:
        for link in package.order_links or []:
            order = link.work_order
            if order.status == work_models.WorkOrderStatusEnum.RELEASED:
                order.status = work_models.WorkOrderStatusEnum.IN_PROGRESS
                order.updated_by_user_id = actor.id
                db.add(order)
    db.add(package)
    _audit(
        db,
        amo_id=package.amo_id,
        actor_id=actor.id,
        entity_id=str(package.id),
        action="status_change",
        before=before,
        after={"status": package.status, "notes": payload.notes},
    )
    return package
