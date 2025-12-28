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

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user, require_roles
from amodb.apps.accounts.models import AccountRole, User  # type: ignore

from . import models, schemas
from amodb.apps.fleet import services as fleet_services

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/work-orders",
    tags=["work_orders"],
    # All endpoints require an authenticated user; role-specific checks are
    # added per-endpoint for write operations.
    dependencies=[Depends(get_current_active_user)],
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


def _ensure_aircraft_documents_clear(db: Session, aircraft_serial_number: str) -> None:
    """
    Block work when mandatory aircraft documents (e.g., C of A) are due or missing evidence,
    unless Quality has an active override.
    """
    blockers = fleet_services.get_blocking_documents(db, aircraft_serial_number)
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


@router.get("/", response_model=List[schemas.WorkOrderRead])
def list_work_orders(
    skip: int = 0,
    limit: int = 100,
    aircraft_serial_number: Optional[str] = None,
    status: Optional[models.WorkOrderStatusEnum] = None,
    wo_type: Optional[models.WorkOrderTypeEnum] = None,
    db: Session = Depends(get_db),
):
    """
    List work orders with optional filters by aircraft, status and type.
    """
    q = db.query(models.WorkOrder)

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
):
    wo = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id)
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.get("/by-number/{wo_number}", response_model=schemas.WorkOrderRead)
def get_work_order_by_number(
    wo_number: str,
    db: Session = Depends(get_db),
):
    wo = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.wo_number == wo_number)
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.post(
    "/",
    response_model=schemas.WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
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
        .filter(models.WorkOrder.wo_number == payload.wo_number)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Work order {payload.wo_number} already exists.",
        )

    _ensure_aircraft_documents_clear(db, payload.aircraft_serial_number)

    wo = models.WorkOrder(
        wo_number=payload.wo_number,
        aircraft_serial_number=payload.aircraft_serial_number,
        amo_code=payload.amo_code,
        originating_org=getattr(payload, "originating_org", None),
        work_package_ref=getattr(payload, "work_package_ref", None),
        description=payload.description,
        check_type=payload.check_type,
        wo_type=getattr(payload, "wo_type", models.WorkOrderTypeEnum.PERIODIC),
        status=getattr(
            payload,
            "status",
            models.WorkOrderStatusEnum.OPEN,
        ),
        is_scheduled=payload.is_scheduled,
        due_date=payload.due_date,
        open_date=payload.open_date,
        closed_date=None,
        created_by_user_id=current_user.id,
    )
    db.add(wo)
    db.flush()  # so wo.id is available

    # Optional initial task cards on create, if schema supports it
    initial_tasks = getattr(payload, "tasks", None)
    if initial_tasks:
        for t in initial_tasks:
            task = models.TaskCard(
                work_order_id=wo.id,
                aircraft_serial_number=wo.aircraft_serial_number,
                aircraft_component_id=t.aircraft_component_id,
                program_item_id=t.program_item_id,
                parent_task_id=t.parent_task_id,
                ata_chapter=t.ata_chapter,
                task_code=t.task_code,
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
                created_by_user_id=current_user.id,
            )
            db.add(task)

    db.commit()
    db.refresh(wo)
    return wo


@router.put("/{work_order_id}", response_model=schemas.WorkOrderRead)
def update_work_order(
    work_order_id: int,
    payload: schemas.WorkOrderUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(
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
    wo = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id)
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    data = payload.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status in {
        models.WorkOrderStatusEnum.OPEN,
        models.WorkOrderStatusEnum.IN_PROGRESS,
    }:
        _ensure_aircraft_documents_clear(db, wo.aircraft_serial_number)
    # updated_at optimistic concurrency could be added here later if needed
    for field, value in data.items():
        setattr(wo, field, value)

    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
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
        .filter(models.WorkOrder.id == work_order_id)
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
):
    """
    List all task cards for a given work order.
    """
    tasks = (
        db.query(models.TaskCard)
        .filter(models.TaskCard.work_order_id == work_order_id)
        .order_by(models.TaskCard.id.asc())
        .all()
    )
    return tasks


@router.get("/tasks/{task_id}", response_model=schemas.TaskCardRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = (
        db.query(models.TaskCard)
        .filter(models.TaskCard.id == task_id)
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
      category UNSCHEDULED or DEFECT under an OPEN / IN_PROGRESS work order.
    """
    wo = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id)
        .first()
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    _ensure_aircraft_documents_clear(db, wo.aircraft_serial_number)

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
            models.WorkOrderStatusEnum.OPEN,
            models.WorkOrderStatusEnum.IN_PROGRESS,
        }:
            raise HTTPException(
                status_code=400,
                detail="Non-routine tasks can only be raised on OPEN or IN_PROGRESS work orders.",
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
        work_order_id=wo.id,
        aircraft_serial_number=wo.aircraft_serial_number,
        aircraft_component_id=payload.aircraft_component_id,
        program_item_id=payload.program_item_id,
        parent_task_id=payload.parent_task_id,
        ata_chapter=payload.ata_chapter,
        task_code=payload.task_code,
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
        .filter(models.TaskCard.id == task_id)
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
        _ensure_aircraft_documents_clear(db, task.aircraft_serial_number)

    if is_planning:
        # Full update allowed
        for field, value in data.items():
            setattr(task, field, value)
    elif is_engineering:
        # Must be assigned to this task
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

        # Restrict to execution-related fields
        allowed_fields = {"status", "actual_start", "actual_end"}
        for field, value in data.items():
            if field in allowed_fields:
                setattr(task, field, value)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to update task cards",
        )

    task.updated_by_user_id = current_user.id
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
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
        .filter(models.TaskCard.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    db.delete(task)
    db.commit()
    return


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
):
    assignments = (
        db.query(models.TaskAssignment)
        .filter(models.TaskAssignment.task_id == task_id)
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
    _: User = Depends(
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
        .filter(models.TaskCard.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")

    assignment = models.TaskAssignment(
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
        .filter(models.TaskAssignment.id == assignment_id)
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
):
    logs = (
        db.query(models.WorkLogEntry)
        .filter(models.WorkLogEntry.task_id == task_id)
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
        .filter(models.TaskCard.id == task_id)
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
