from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit import services as audit_services
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.crs import models as crs_models
from amodb.utils.identifiers import generate_uuid7

from . import models, schemas


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


WORK_ORDER_TRANSITIONS = {
    models.WorkOrderStatusEnum.DRAFT: {
        models.WorkOrderStatusEnum.RELEASED,
        models.WorkOrderStatusEnum.CANCELLED,
    },
    models.WorkOrderStatusEnum.RELEASED: {
        models.WorkOrderStatusEnum.IN_PROGRESS,
        models.WorkOrderStatusEnum.CANCELLED,
    },
    models.WorkOrderStatusEnum.IN_PROGRESS: {
        models.WorkOrderStatusEnum.INSPECTED,
        models.WorkOrderStatusEnum.CANCELLED,
    },
    models.WorkOrderStatusEnum.INSPECTED: {
        models.WorkOrderStatusEnum.CLOSED,
        models.WorkOrderStatusEnum.ARCHIVED,
    },
    models.WorkOrderStatusEnum.CLOSED: {
        models.WorkOrderStatusEnum.ARCHIVED,
    },
    models.WorkOrderStatusEnum.ARCHIVED: set(),
    models.WorkOrderStatusEnum.CANCELLED: set(),
}


TASK_TRANSITIONS = {
    models.TaskStatusEnum.PLANNED: {
        models.TaskStatusEnum.IN_PROGRESS,
        models.TaskStatusEnum.DEFERRED,
        models.TaskStatusEnum.CANCELLED,
    },
    models.TaskStatusEnum.IN_PROGRESS: {
        models.TaskStatusEnum.COMPLETED,
        models.TaskStatusEnum.PAUSED,
        models.TaskStatusEnum.CANCELLED,
    },
    models.TaskStatusEnum.COMPLETED: {
        models.TaskStatusEnum.INSPECTED,
    },
    models.TaskStatusEnum.INSPECTED: {
        models.TaskStatusEnum.CLOSED,
    },
    models.TaskStatusEnum.CLOSED: set(),
    models.TaskStatusEnum.DEFERRED: {
        models.TaskStatusEnum.PLANNED,
        models.TaskStatusEnum.CANCELLED,
    },
    models.TaskStatusEnum.PAUSED: {
        models.TaskStatusEnum.IN_PROGRESS,
        models.TaskStatusEnum.CANCELLED,
    },
    models.TaskStatusEnum.CANCELLED: set(),
}


def _record_audit(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: Optional[str],
    before: Optional[dict],
    after: Optional[dict],
    correlation_id: Optional[str] = None,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
            correlation_id=correlation_id,
        ),
    )


def _ensure_valid_work_order_transition(
    db: Session,
    *,
    work_order: models.WorkOrder,
    new_status: models.WorkOrderStatusEnum,
    actor: User,
) -> None:
    if work_order.status == new_status:
        return
    allowed = WORK_ORDER_TRANSITIONS.get(work_order.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid work order transition {work_order.status} -> {new_status}.",
        )

    if new_status == models.WorkOrderStatusEnum.INSPECTED:
        pending_tasks = (
            db.query(models.TaskCard)
            .filter(
                models.TaskCard.work_order_id == work_order.id,
                models.TaskCard.status.notin_(
                    [
                        models.TaskStatusEnum.COMPLETED,
                        models.TaskStatusEnum.INSPECTED,
                        models.TaskStatusEnum.CLOSED,
                    ]
                ),
            )
            .count()
        )
        if pending_tasks:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All task cards must be completed before inspection.",
            )

    if new_status == models.WorkOrderStatusEnum.CLOSED:
        has_inspector = (
            db.query(models.InspectorSignOff)
            .filter(
                models.InspectorSignOff.work_order_id == work_order.id,
                models.InspectorSignOff.signed_flag.is_(True),
            )
            .first()
            is not None
        )
        if not has_inspector:
            uninspected_tasks = (
                db.query(models.TaskCard)
                .filter(
                    models.TaskCard.work_order_id == work_order.id,
                    models.TaskCard.status.notin_(
                        [models.TaskStatusEnum.INSPECTED, models.TaskStatusEnum.CLOSED]
                    ),
                )
                .count()
            )
            if uninspected_tasks:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="All task cards must be inspected or a work order sign-off is required.",
                )

        crs_exists = (
            db.query(crs_models.CRS.id)
            .filter(crs_models.CRS.work_order_id == work_order.id)
            .first()
            is not None
        )
        if not crs_exists:
            if work_order.closure_reason != "NO_CRS_REQUIRED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="CRS is required to close this work order or provide NO_CRS_REQUIRED.",
                )
            if actor.role not in {AccountRole.AMO_ADMIN, AccountRole.QUALITY_MANAGER}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only AMO admin or quality manager can close without CRS.",
                )


def _ensure_valid_task_transition(
    task: models.TaskCard,
    new_status: models.TaskStatusEnum,
) -> None:
    if task.status == new_status:
        return
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid task transition {task.status} -> {new_status}.",
        )


def create_work_order(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.WorkOrderCreate,
    actor: User,
) -> models.WorkOrder:
    operator_event_id = payload.operator_event_id or generate_uuid7()
    wo = models.WorkOrder(
        amo_id=amo_id,
        wo_number=payload.wo_number,
        aircraft_serial_number=payload.aircraft_serial_number,
        amo_code=payload.amo_code,
        originating_org=getattr(payload, "originating_org", None),
        work_package_ref=getattr(payload, "work_package_ref", None),
        operator_event_id=operator_event_id,
        description=payload.description,
        check_type=payload.check_type,
        wo_type=getattr(payload, "wo_type", models.WorkOrderTypeEnum.PERIODIC),
        status=getattr(payload, "status", models.WorkOrderStatusEnum.DRAFT),
        is_scheduled=payload.is_scheduled,
        due_date=payload.due_date,
        open_date=payload.open_date,
        closed_date=None,
        created_by_user_id=actor.id,
    )
    db.add(wo)
    db.flush()

    initial_tasks = getattr(payload, "tasks", None)
    if initial_tasks:
        for t in initial_tasks:
            task = models.TaskCard(
                amo_id=amo_id,
                work_order_id=wo.id,
                aircraft_serial_number=wo.aircraft_serial_number,
                aircraft_component_id=t.aircraft_component_id,
                program_item_id=t.program_item_id,
                parent_task_id=t.parent_task_id,
                ata_chapter=t.ata_chapter,
                task_code=t.task_code,
                operator_event_id=t.operator_event_id or operator_event_id,
                title=t.title,
                description=t.description,
                category=t.category,
                origin_type=t.origin_type,
                priority=t.priority,
                zone=t.zone,
                access_panel=t.access_panel,
                planned_start=t.planned_start,
                planned_end=t.planned_end,
                estimated_manhours=t.estimated_manhours,
                status=t.status,
                error_capturing_method=t.error_capturing_method,
                requires_duplicate_inspection=t.requires_duplicate_inspection,
                hf_notes=t.hf_notes,
                created_by_user_id=actor.id,
            )
            db.add(task)
            db.flush()
            for step in getattr(t, "steps", []):
                db.add(
                    models.TaskStep(
                        amo_id=amo_id,
                        task_id=task.id,
                        step_no=step.step_no,
                        instruction_text=step.instruction_text,
                        required_flag=step.required_flag,
                        measurement_type=step.measurement_type,
                        expected_range=step.expected_range,
                    )
                )

    _record_audit(
        db,
        amo_id=amo_id,
        entity_type="WorkOrder",
        entity_id=str(wo.id),
        action="create",
        actor_user_id=actor.id,
        before=None,
        after={"status": wo.status.value, "wo_number": wo.wo_number},
    )
    return wo


def update_work_order(
    db: Session,
    *,
    work_order: models.WorkOrder,
    payload: schemas.WorkOrderUpdate,
    actor: User,
) -> models.WorkOrder:
    data = payload.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status:
        _ensure_valid_work_order_transition(
            db,
            work_order=work_order,
            new_status=new_status,
            actor=actor,
        )

    before = {"status": work_order.status.value}
    for field, value in data.items():
        setattr(work_order, field, value)

    if new_status and work_order.status != new_status:
        work_order.status = new_status
    work_order.updated_by_user_id = actor.id
    db.add(work_order)

    _record_audit(
        db,
        amo_id=work_order.amo_id,
        entity_type="WorkOrder",
        entity_id=str(work_order.id),
        action="update",
        actor_user_id=actor.id,
        before=before,
        after={"status": work_order.status.value},
    )
    return work_order


def create_task_steps(
    db: Session,
    *,
    amo_id: str,
    task: models.TaskCard,
    steps: Iterable[schemas.TaskStepCreate],
    actor: User,
) -> list[models.TaskStep]:
    created: list[models.TaskStep] = []
    for step in steps:
        record = models.TaskStep(
            amo_id=amo_id,
            task_id=task.id,
            step_no=step.step_no,
            instruction_text=step.instruction_text,
            required_flag=step.required_flag,
            measurement_type=step.measurement_type,
            expected_range=step.expected_range,
        )
        db.add(record)
        created.append(record)
    _record_audit(
        db,
        amo_id=amo_id,
        entity_type="TaskCard",
        entity_id=str(task.id),
        action="steps_added",
        actor_user_id=actor.id,
        before=None,
        after={"steps_added": len(created)},
    )
    return created


def update_task(
    db: Session,
    *,
    task: models.TaskCard,
    data: dict,
    actor: User,
) -> models.TaskCard:
    new_status = data.get("status")
    if new_status:
        _ensure_valid_task_transition(task, new_status)

    before = {"status": task.status.value}
    for field, value in data.items():
        setattr(task, field, value)
    task.updated_by_user_id = actor.id
    db.add(task)

    _record_audit(
        db,
        amo_id=task.amo_id,
        entity_type="TaskCard",
        entity_id=str(task.id),
        action="update",
        actor_user_id=actor.id,
        before=before,
        after={"status": task.status.value},
    )
    return task


def execute_task_step(
    db: Session,
    *,
    amo_id: str,
    task: models.TaskCard,
    step: models.TaskStep,
    payload: schemas.TaskStepExecutionCreate,
    actor: User,
) -> models.TaskStepExecution:
    execution = models.TaskStepExecution(
        amo_id=amo_id,
        task_step_id=step.id,
        task_id=task.id,
        performed_by_user_id=actor.id,
        result_text=payload.result_text,
        measurement_value=payload.measurement_value,
        attachment_id=payload.attachment_id,
        signed_flag=payload.signed_flag,
        signature_hash=payload.signature_hash,
    )
    db.add(execution)
    _record_audit(
        db,
        amo_id=amo_id,
        entity_type="TaskStep",
        entity_id=str(step.id),
        action="execute",
        actor_user_id=actor.id,
        before=None,
        after={"task_id": task.id},
    )
    return execution


def record_task_inspection(
    db: Session,
    *,
    amo_id: str,
    task: models.TaskCard,
    payload: schemas.InspectorSignOffCreate,
    actor: User,
) -> models.InspectorSignOff:
    required_steps = (
        db.query(models.TaskStep)
        .filter(models.TaskStep.task_id == task.id, models.TaskStep.required_flag.is_(True))
        .all()
    )
    if required_steps:
        required_step_ids = {step.id for step in required_steps}
        executed_ids = {
            exec.task_step_id
            for exec in db.query(models.TaskStepExecution)
            .filter(models.TaskStepExecution.task_id == task.id)
            .all()
        }
        missing = required_step_ids - executed_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All required task steps must be executed before inspection.",
            )

    _ensure_valid_task_transition(task, models.TaskStatusEnum.INSPECTED)
    signoff = models.InspectorSignOff(
        amo_id=amo_id,
        task_card_id=task.id,
        inspector_user_id=actor.id,
        signed_at=_utcnow(),
        notes=payload.notes,
        signed_flag=payload.signed_flag,
        signature_hash=payload.signature_hash,
    )
    task.status = models.TaskStatusEnum.INSPECTED
    task.updated_by_user_id = actor.id
    db.add(task)
    db.add(signoff)
    _record_audit(
        db,
        amo_id=amo_id,
        entity_type="TaskCard",
        entity_id=str(task.id),
        action="inspect",
        actor_user_id=actor.id,
        before=None,
        after={"signed": payload.signed_flag},
    )
    return signoff


def record_work_order_inspection(
    db: Session,
    *,
    amo_id: str,
    work_order: models.WorkOrder,
    payload: schemas.InspectorSignOffCreate,
    actor: User,
) -> models.InspectorSignOff:
    signoff = models.InspectorSignOff(
        amo_id=amo_id,
        work_order_id=work_order.id,
        inspector_user_id=actor.id,
        signed_at=_utcnow(),
        notes=payload.notes,
        signed_flag=payload.signed_flag,
        signature_hash=payload.signature_hash,
    )
    db.add(signoff)
    _record_audit(
        db,
        amo_id=amo_id,
        entity_type="WorkOrder",
        entity_id=str(work_order.id),
        action="inspect",
        actor_user_id=actor.id,
        before=None,
        after={"signed": payload.signed_flag},
    )
    return signoff
