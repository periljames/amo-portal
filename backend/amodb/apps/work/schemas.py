# backend/amodb/apps/work/schemas.py
#
# Schemas for the work module:
# - WorkOrder* : work order admin layer.
# - TaskCard*  : maintenance task / work card under a work order.
# - TaskAssignment* : who is allocated to a task.
# - WorkLog*   : time booked against a task.

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from .models import (
    WorkOrderTypeEnum,
    WorkOrderStatusEnum,
    TaskCategoryEnum,
    TaskOriginTypeEnum,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskRoleOnTaskEnum,
    TaskAssignmentStatusEnum,
    ErrorCapturingMethodEnum,
)


# ---------------------------------------------------------------------------
# Task cards
# ---------------------------------------------------------------------------


class TaskCardBase(BaseModel):
    aircraft_component_id: Optional[int] = None
    program_item_id: Optional[int] = None
    parent_task_id: Optional[int] = None

    ata_chapter: Optional[str] = None
    task_code: Optional[str] = None
    title: str
    description: Optional[str] = None

    category: TaskCategoryEnum = TaskCategoryEnum.SCHEDULED
    origin_type: TaskOriginTypeEnum = TaskOriginTypeEnum.SCHEDULED
    priority: TaskPriorityEnum = TaskPriorityEnum.MEDIUM

    zone: Optional[str] = None
    access_panel: Optional[str] = None

    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    estimated_manhours: Optional[float] = None

    status: TaskStatusEnum = TaskStatusEnum.PLANNED
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    error_capturing_method: Optional[ErrorCapturingMethodEnum] = None
    requires_duplicate_inspection: bool = False
    hf_notes: Optional[str] = None


class TaskCardCreate(TaskCardBase):
    """
    Used when creating a new task card under a work order.

    The work_order_id and aircraft_serial_number come from the path / parent
    work order; they are not supplied in this payload.
    """
    pass


class TaskCardUpdate(BaseModel):
    """
    Partial update of a task card.

    last_known_updated_at is used for optimistic concurrency control.
    """

    aircraft_component_id: Optional[int] = None
    program_item_id: Optional[int] = None
    parent_task_id: Optional[int] = None

    ata_chapter: Optional[str] = None
    task_code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None

    category: Optional[TaskCategoryEnum] = None
    origin_type: Optional[TaskOriginTypeEnum] = None
    priority: Optional[TaskPriorityEnum] = None

    zone: Optional[str] = None
    access_panel: Optional[str] = None

    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    estimated_manhours: Optional[float] = None

    status: Optional[TaskStatusEnum] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    error_capturing_method: Optional[ErrorCapturingMethodEnum] = None
    requires_duplicate_inspection: Optional[bool] = None
    hf_notes: Optional[str] = None

    last_known_updated_at: datetime


class TaskCardRead(TaskCardBase):
    id: int
    work_order_id: int
    aircraft_serial_number: str

    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Work orders
# ---------------------------------------------------------------------------


class WorkOrderBase(BaseModel):
    wo_number: str
    aircraft_serial_number: str

    amo_code: Optional[str] = None
    originating_org: Optional[str] = None
    work_package_ref: Optional[str] = None

    description: Optional[str] = None
    check_type: Optional[str] = None

    wo_type: WorkOrderTypeEnum = WorkOrderTypeEnum.PERIODIC
    status: WorkOrderStatusEnum = WorkOrderStatusEnum.OPEN
    is_scheduled: bool = True

    due_date: Optional[date] = None
    open_date: Optional[date] = None
    closed_date: Optional[date] = None


class WorkOrderCreate(WorkOrderBase):
    """
    Create a work order, optionally with initial scheduled task cards.
    """
    tasks: List[TaskCardCreate] = []


class WorkOrderUpdate(BaseModel):
    """
    Partial update of a work order.
    """
    aircraft_serial_number: Optional[str] = None

    amo_code: Optional[str] = None
    originating_org: Optional[str] = None
    work_package_ref: Optional[str] = None

    description: Optional[str] = None
    check_type: Optional[str] = None

    wo_type: Optional[WorkOrderTypeEnum] = None
    status: Optional[WorkOrderStatusEnum] = None
    is_scheduled: Optional[bool] = None

    due_date: Optional[date] = None
    open_date: Optional[date] = None
    closed_date: Optional[date] = None


class WorkOrderRead(WorkOrderBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    tasks: List[TaskCardRead] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Task assignments
# ---------------------------------------------------------------------------


class TaskAssignmentBase(BaseModel):
    user_id: int
    role_on_task: TaskRoleOnTaskEnum = TaskRoleOnTaskEnum.SUPPORT
    allocated_hours: Optional[float] = None
    status: TaskAssignmentStatusEnum = TaskAssignmentStatusEnum.ASSIGNED


class TaskAssignmentCreate(TaskAssignmentBase):
    pass


class TaskAssignmentUpdate(BaseModel):
    role_on_task: Optional[TaskRoleOnTaskEnum] = None
    allocated_hours: Optional[float] = None
    status: Optional[TaskAssignmentStatusEnum] = None


class TaskAssignmentRead(TaskAssignmentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Work logs
# ---------------------------------------------------------------------------


class WorkLogBase(BaseModel):
    """
    Base fields for a work log entry.

    user_id is optional in the payload; if omitted, the current user is used.
    """
    start_time: datetime
    end_time: datetime
    actual_hours: float

    description: Optional[str] = None
    station: Optional[str] = None
    user_id: Optional[int] = None


class WorkLogCreate(WorkLogBase):
    pass


class WorkLogUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    actual_hours: Optional[float] = None

    description: Optional[str] = None
    station: Optional[str] = None


class WorkLogRead(WorkLogBase):
    id: int
    task_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
