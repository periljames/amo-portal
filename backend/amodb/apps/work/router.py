# backend/amodb/apps/work/router.py
"""
Work orders and task cards API.

- Work orders: creation, listing, update, delete.
- Task cards: scheduled and non-routine job cards under a work order.
- Task assignments: who is allocated to a task.
- Work logs: man-hours booked against a task.

Role model (from security / AccountRole):
- Planning / production write access:
  SUPERUSER, AMO_ADMIN, PLANNING_ENGINEER, PRODUCTION_ENGINEER
- Non-routine creation + own task updates:
  CERTIFYING_ENGINEER, CERTIFYING_TECHNICIAN, TECHNICIAN
- VIEW_ONLY and above can read.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from amodb.apps.accounts import services as account_services
from amodb.apps.accounts.models import AccountRole, User  # type: ignore
from amodb.apps.reliability import schemas as reliability_schemas
from amodb.apps.reliability import services as reliability_services
from amodb.utils.identifiers import generate_uuid7

from . import models, schemas, services
from amodb.apps.fleet import services as fleet_services

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/work-orders",
    tags=["work_orders"],
    # All endpoints require an authenticated user; role-specific checks are
    # added per-endpoint for write operations.
    dependencies=[Depends(require_module("work"))],
)

PLANNING_ROLES = {
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
}

ENGINEERING_ROLES = {
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
    AccountRole.TECHNICIAN,
}


def _ensure_aircraft_documents_clear(db: Session, aircraft_serial_number: str, amo_id: str) -> None:
    """
    Block work when mandatory aircraft documents (e.g., C of A) are due or missing evidence,
    unless Quality has an active override.
    """
    blockers = fleet_services.get_blocking_documents(db, aircraft_serial_number, amo_id=amo_id)
    if not blockers:
        return

    details = []
    for doc, evaluation in blockers:
        msg_parts = [
            doc.document_type.value.replace("_", " ").title(),
            evaluation.status.value,
        ]
        if evaluation.days_to_expiry is not None:
            msg_parts.append(f"{evaluation.days_to_expiry} days to expiry")
        if evaluation.missing_evidence:
            msg_parts.append("evidence missing")
        details.append(" - ".join(msg_parts))

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Work is blocked until required aircraft documents are renewed and uploaded. "
            f"Outstanding: {', '.join(details)}. Quality may override with a recorded reason."
        ),
    )


# ---------------------------------------------------------------------------
# Work orders
# ---------------------------------------------------------------------------


@router.get("", response_model=List[schemas.WorkOrderRead])
@router.get("/", response_model=List[schemas.WorkOrderRead], include_in_schema=False)
def list_work_orders(
    skip: int = 0,
    limit: int = 100,
    aircraft_serial_number: Optional[str] = None,
    status: Optional[models.WorkOrderStatusEnum] = None,
    wo_type: Optional[models.WorkOrderTypeEnum] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List work orders with optional filters by aircraft, status and type.
    """
    q = db.query(models.WorkOrder).filter(models.WorkOrder.amo_id == current_user.effective_amo_id)

    if aircraft_serial_number:
        q = q.filter(
            models.WorkOrder.aircraft_serial_number == aircraft_serial_number
        )

    if status:
        q = q.filter(models.WorkOrder.status == status)

    if wo_type:
        q = q.filter(models.WorkOrder.wo_type == wo_type)

    q = q.order_by(models.WorkOrder.wo_number.asc()).offset(skip).limit(limit)
    return q.all()


@router.get("/{work_order_id}", response_model=schemas.WorkOrderRead)
def get_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wo = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.id == work_order_id,
            models.WorkOrder.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.get("/by-number/{wo_number}", response_model=schemas.WorkOrderRead)
def get_work_order_by_number(
    wo_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wo = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.wo_number == wo_number,
            models.WorkOrder.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.post(
    "",
    response_model=schemas.WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    response_model=schemas.WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_work_order(
    payload: schemas.WorkOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    """
    Create a new work order.

    Only planning / production / AMO admin (and SUPERUSER via require_roles)
    are allowed to create work orders.
    """
    existing = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.wo_number == payload.wo_number,
            models.WorkOrder.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Work order {payload.wo_number} already exists.",
        )

    _ensure_aircraft_documents_clear(db, payload.aircraft_serial_number, current_user.effective_amo_id)

    wo = services.create_work_order(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )

    if payload.is_scheduled:
        account_services.record_usage(
            db,
            amo_id=current_user.effective_amo_id,
            meter_key=account_services.METER_KEY_SCHEDULED_JOBS,
            quantity=1,
            commit=False,
        )

    db.commit()
    db.refresh(wo)
    return wo


@router.put("/{work_order_id}", response_model=schemas.WorkOrderRead)
def update_work_order(
    work_order_id: int,
    payload: schemas.WorkOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    """
    Update a work order (planning / status / description).

    Restricted to planning / production / AMO admin.
    """
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    if wo.amo_id != current_user.amo_id:
        raise HTTPException(status_code=404, detail="Work order not found")

    data = payload.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status in {
        models.WorkOrderStatusEnum.RELEASED,
        models.WorkOrderStatusEnum.IN_PROGRESS,
    }:
        _ensure_aircraft_documents_clear(db, wo.aircraft_serial_number, current_user.amo_id)

    services.update_work_order(db, work_order=wo, payload=payload, actor=current_user)
    db.commit()
    db.refresh(wo)
    return wo


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    """
    Delete a work order.

    For now this performs a hard delete. Later we can change this to a
    soft cancel (status=CANCELLED) if needed.
    """
    wo = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.id == work_order_id,
            models.WorkOrder.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    db.delete(wo)
    db.commit()
    return


# ---------------------------------------------------------------------------
# Task cards
# ---------------------------------------------------------------------------


@router.get(
    "/{work_order_id}/tasks",
    response_model=List[schemas.TaskCardRead],
)
def list_tasks_for_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all task cards for a given work order.
    """
    tasks = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.work_order_id == work_order_id,
            models.TaskCard.amo_id == current_user.effective_amo_id,
        )
        .order_by(models.TaskCard.id.asc())
        .all()
    )
    return tasks


@router.get("/tasks/{task_id}", response_model=schemas.TaskCardRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")
    return task


@router.post(
    "/{work_order_id}/tasks",
    response_model=schemas.TaskCardRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    work_order_id: int,
    payload: schemas.TaskCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create a task card under a work order.

    Rules:
    - Planning / production / AMO admin can create scheduled and non-routine.
    - Certifying staff / technicians can only create NON_ROUTINE tasks with
      category UNSCHEDULED or DEFECT under a RELEASED / IN_PROGRESS work order.
    """
    wo = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.id == work_order_id,
            models.WorkOrder.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    _ensure_aircraft_documents_clear(db, wo.aircraft_serial_number, current_user.effective_amo_id)

    is_planning = (
        current_user.is_superuser
        or current_user.role in PLANNING_ROLES
    )
    is_engineering = current_user.role in ENGINEERING_ROLES

    if not (is_planning or is_engineering):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to create task cards",
        )

    category = payload.category
    origin_type = payload.origin_type

    # Engineers / technicians – enforce NON_ROUTINE / UNSCHEDULED / DEFECT only
    if is_engineering and not is_planning:
        if wo.status not in {
            models.WorkOrderStatusEnum.RELEASED,
            models.WorkOrderStatusEnum.IN_PROGRESS,
        }:
            raise HTTPException(
                status_code=400,
                detail="Non-routine tasks can only be raised on RELEASED or IN_PROGRESS work orders.",
            )

        # Force NON_ROUTINE origin
        origin_type = models.TaskOriginTypeEnum.NON_ROUTINE

        # Restrict category
        if category not in {
            models.TaskCategoryEnum.UNSCHEDULED,
            models.TaskCategoryEnum.DEFECT,
        }:
            category = models.TaskCategoryEnum.UNSCHEDULED

    task = models.TaskCard(
        amo_id=current_user.effective_amo_id,
        work_order_id=wo.id,
        aircraft_serial_number=wo.aircraft_serial_number,
        aircraft_component_id=payload.aircraft_component_id,
        program_item_id=payload.program_item_id,
        parent_task_id=payload.parent_task_id,
        ata_chapter=payload.ata_chapter,
        task_code=payload.task_code,
        operator_event_id=payload.operator_event_id or wo.operator_event_id,
        title=payload.title,
        description=payload.description,
        category=category,
        origin_type=origin_type,
        priority=payload.priority,
        zone=payload.zone,
        access_panel=payload.access_panel,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        estimated_manhours=payload.estimated_manhours,
        status=payload.status,
        error_capturing_method=payload.error_capturing_method,
        requires_duplicate_inspection=payload.requires_duplicate_inspection,
        hf_notes=payload.hf_notes,
        created_by_user_id=current_user.id,
    )
    db.add(task)
    db.flush()

    steps = getattr(payload, "steps", None)
    if steps:
        services.create_task_steps(
            db,
            amo_id=current_user.effective_amo_id,
            task=task,
            steps=steps,
            actor=current_user,
        )
    db.commit()
    db.refresh(task)
    return task


@router.put("/tasks/{task_id}", response_model=schemas.TaskCardRead)
def update_task(
    task_id: int,
    payload: schemas.TaskCardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update a task card.

    - Planning / production / AMO admin: can update any field.
    - Engineers / technicians: can only update tasks assigned to them, and
      only limited execution fields (status, actual_start, actual_end).
    """
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.effective_amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    is_planning = (
        current_user.is_superuser
        or current_user.role in PLANNING_ROLES
    )
    is_engineering = current_user.role in ENGINEERING_ROLES

    data = payload.model_dump(exclude_unset=True)
    part_movement_event_type = data.pop("part_movement_event_type", None)
    part_movement_event_date = data.pop("part_movement_event_date", None)
    part_movement_component_instance_id = data.pop("part_movement_component_instance_id", None)
    part_movement_notes = data.pop("part_movement_notes", None)
    part_movement_idempotency_key = data.pop("part_movement_idempotency_key", None)
    removal_reason = data.pop("removal_reason", None)
    hours_at_removal = data.pop("hours_at_removal", None)
    cycles_at_removal = data.pop("cycles_at_removal", None)
    part_movement_reason_code = data.pop("part_movement_reason_code", None)

    # Optional optimistic concurrency: if client sent last_known_updated_at,
    # check it against DB value.
    expected_updated_at = data.pop("last_known_updated_at", None)
    if expected_updated_at is not None and task.updated_at != expected_updated_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task card has been modified by another user.",
        )

    incoming_status = data.get("status")
    if incoming_status == models.TaskStatusEnum.IN_PROGRESS:
        _ensure_aircraft_documents_clear(db, task.aircraft_serial_number, current_user.amo_id)

    if is_planning:
        allowed_data = data
    elif is_engineering:
        assignment = (
            db.query(models.TaskAssignment)
            .filter(
                models.TaskAssignment.task_id == task.id,
                models.TaskAssignment.user_id == current_user.id,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this task.",
            )

        allowed_fields = {"status", "actual_start", "actual_end"}
        allowed_data = {k: v for k, v in data.items() if k in allowed_fields}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to update task cards",
        )

    services.update_task(db, task=task, data=allowed_data, actor=current_user)

    if part_movement_event_type:
        component_id = data.get("aircraft_component_id") or task.aircraft_component_id
        if component_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="aircraft_component_id is required to record a part movement.",
            )
        removal_tracking_id = None
        if part_movement_event_type in {
            reliability_schemas.PartMovementTypeEnum.REMOVE,
            reliability_schemas.PartMovementTypeEnum.SWAP,
        }:
            removal_tracking_id = generate_uuid7()
        movement_payload = reliability_schemas.PartMovementLedgerCreate(
            aircraft_serial_number=task.aircraft_serial_number,
            component_id=component_id,
            component_instance_id=part_movement_component_instance_id,
            work_order_id=task.work_order_id,
            task_card_id=task.id,
            event_type=part_movement_event_type,
            event_date=part_movement_event_date or date.today(),
            notes=part_movement_notes,
            reason_code=part_movement_reason_code or removal_reason,
            idempotency_key=part_movement_idempotency_key,
        )
        if part_movement_event_type in {
            reliability_schemas.PartMovementTypeEnum.REMOVE,
            reliability_schemas.PartMovementTypeEnum.SWAP,
        }:
            reliability_services.record_part_movement_with_removal(
                db,
                amo_id=current_user.amo_id,
                data=movement_payload,
                removal_tracking_id=removal_tracking_id,
                removal_reason=removal_reason,
                hours_at_removal=hours_at_removal,
                cycles_at_removal=cycles_at_removal,
                actor_user_id=current_user.id,
                commit=False,
            )
        else:
            reliability_services.create_part_movement(
                db,
                amo_id=current_user.amo_id,
                data=movement_payload,
                removal_tracking_id=removal_tracking_id,
                actor_user_id=current_user.id,
                commit=False,
            )

    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    """
    Delete a task card (hard delete for now).
    """
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    db.delete(task)
    db.commit()
    return


# ---------------------------------------------------------------------------
# Task steps + execution + inspection
# ---------------------------------------------------------------------------


@router.post(
    "/tasks/{task_id}/steps",
    response_model=List[schemas.TaskStepRead],
    status_code=status.HTTP_201_CREATED,
)
def create_task_steps(
    task_id: int,
    payload: List[schemas.TaskStepCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")
    steps = services.create_task_steps(
        db,
        amo_id=current_user.amo_id,
        task=task,
        steps=payload,
        actor=current_user,
    )
    db.commit()
    for step in steps:
        db.refresh(step)
    return steps


@router.post(
    "/tasks/{task_id}/steps/{step_id}/execute",
    response_model=schemas.TaskStepExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
def execute_task_step(
    task_id: int,
    step_id: int,
    payload: schemas.TaskStepExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    assignment = (
        db.query(models.TaskAssignment)
        .filter(
            models.TaskAssignment.task_id == task.id,
            models.TaskAssignment.user_id == current_user.id,
        )
        .first()
    )
    is_planning = current_user.is_superuser or current_user.role in PLANNING_ROLES
    if not (assignment or is_planning):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this task.",
        )

    step = (
        db.query(models.TaskStep)
        .filter(
            models.TaskStep.id == step_id,
            models.TaskStep.task_id == task.id,
        )
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Task step not found")

    execution = services.execute_task_step(
        db,
        amo_id=current_user.amo_id,
        task=task,
        step=step,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(execution)
    return execution


@router.post(
    "/tasks/{task_id}/inspect",
    response_model=schemas.InspectorSignOffRead,
    status_code=status.HTTP_201_CREATED,
)
def inspect_task(
    task_id: int,
    payload: schemas.InspectorSignOffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.CERTIFYING_ENGINEER,
            AccountRole.CERTIFYING_TECHNICIAN,
        )
    ),
):
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")
    signoff = services.record_task_inspection(
        db,
        amo_id=current_user.amo_id,
        task=task,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(signoff)
    return signoff


@router.post(
    "/{work_order_id}/inspect",
    response_model=schemas.InspectorSignOffRead,
    status_code=status.HTTP_201_CREATED,
)
def inspect_work_order(
    work_order_id: int,
    payload: schemas.InspectorSignOffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.CERTIFYING_ENGINEER,
            AccountRole.CERTIFYING_TECHNICIAN,
        )
    ),
):
    work_order = (
        db.query(models.WorkOrder)
        .filter(
            models.WorkOrder.id == work_order_id,
            models.WorkOrder.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    signoff = services.record_work_order_inspection(
        db,
        amo_id=current_user.amo_id,
        work_order=work_order,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(signoff)
    return signoff


# ---------------------------------------------------------------------------
# Task assignments
# ---------------------------------------------------------------------------


@router.get(
    "/tasks/{task_id}/assignments",
    response_model=List[schemas.TaskAssignmentRead],
)
def list_assignments_for_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    assignments = (
        db.query(models.TaskAssignment)
        .filter(
            models.TaskAssignment.task_id == task_id,
            models.TaskAssignment.amo_id == current_user.amo_id,
        )
        .order_by(models.TaskAssignment.id.asc())
        .all()
    )
    return assignments


@router.post(
    "/tasks/{task_id}/assignments",
    response_model=schemas.TaskAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    task_id: int,
    payload: schemas.TaskAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AccountRole.AMO_ADMIN,
            AccountRole.PLANNING_ENGINEER,
            AccountRole.PRODUCTION_ENGINEER,
        )
    ),
):
    """
    Create a task assignment (planning / production / AMO admin only).
    """
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    assignment = models.TaskAssignment(
        amo_id=current_user.amo_id,
        task_id=task.id,
        user_id=payload.user_id,
        role_on_task=payload.role_on_task,
        allocated_hours=payload.allocated_hours,
        status=payload.status,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.put(
    "/assignments/{assignment_id}",
    response_model=schemas.TaskAssignmentRead,
)
def update_assignment(
    assignment_id: int,
    payload: schemas.TaskAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update a task assignment.

    Planning / production / AMO admin can update anything.
    Assignees may update their own assignment status (e.g. ACCEPTED/REJECTED).
    """
    assignment = (
        db.query(models.TaskAssignment)
        .filter(
            models.TaskAssignment.id == assignment_id,
            models.TaskAssignment.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    is_planning = (
        current_user.is_superuser
        or current_user.role in PLANNING_ROLES
    )

    data = payload.model_dump(exclude_unset=True)

    if is_planning:
        for field, value in data.items():
            setattr(assignment, field, value)
    else:
        # Only allow assignee to change their own status
        if assignment.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only update your own assignment.",
            )
        allowed_fields = {"status"}
        for field, value in data.items():
            if field in allowed_fields:
                setattr(assignment, field, value)

    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


# ---------------------------------------------------------------------------
# Work logs
# ---------------------------------------------------------------------------


@router.get(
    "/tasks/{task_id}/work-logs",
    response_model=List[schemas.WorkLogRead],
)
def list_work_logs_for_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    logs = (
        db.query(models.WorkLogEntry)
        .filter(
            models.WorkLogEntry.task_id == task_id,
            models.WorkLogEntry.amo_id == current_user.amo_id,
        )
        .order_by(models.WorkLogEntry.start_time.asc())
        .all()
    )
    return logs


@router.post(
    "/tasks/{task_id}/work-logs",
    response_model=schemas.WorkLogRead,
    status_code=status.HTTP_201_CREATED,
)
def create_work_log(
    task_id: int,
    payload: schemas.WorkLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create a work log entry.

    Allowed for:
    - Users assigned to the task.
    - Planning / production / AMO admin (and SUPERUSER).
    """
    task = (
        db.query(models.TaskCard)
        .filter(
            models.TaskCard.id == task_id,
            models.TaskCard.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    is_planning = (
        current_user.is_superuser
        or current_user.role in PLANNING_ROLES
    )

    is_assigned = (
        db.query(models.TaskAssignment)
        .filter(
            models.TaskAssignment.task_id == task.id,
            models.TaskAssignment.user_id == current_user.id,
        )
        .first()
        is not None
    )

    if not (is_planning or is_assigned):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to book time on this task.",
        )

    # If schema does not include user_id, default to current user
    user_id = getattr(payload, "user_id", None) or current_user.id

    log = models.WorkLogEntry(
        amo_id=current_user.amo_id,
        task_id=task.id,
        user_id=user_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        actual_hours=payload.actual_hours,
        description=payload.description,
        station=payload.station,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
