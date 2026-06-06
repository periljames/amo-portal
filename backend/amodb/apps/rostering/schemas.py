# backend/amodb/apps/rostering/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator

from ..work.models import TaskAssignmentStatusEnum, TaskRoleOnTaskEnum
from .models import (
    RosterAssignmentStatus,
    RosterPeriodStatus,
    RosterValidationSeverity,
    RosterValidationSource,
    RosterVersionStatus,
    ShiftTemplateKind,
)


class ShiftTemplateBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=128)
    kind: ShiftTemplateKind = ShiftTemplateKind.DAY
    default_start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    default_end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(None, ge=0)
    counts_as_duty: bool = True
    is_active: bool = True
    display_order: int = 100
    description: Optional[str] = None


class ShiftTemplateCreate(ShiftTemplateBase):
    pass


class ShiftTemplateUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=32)
    label: Optional[str] = Field(None, min_length=1, max_length=128)
    kind: Optional[ShiftTemplateKind] = None
    default_start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    default_end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(None, ge=0)
    counts_as_duty: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
    description: Optional[str] = None


class ShiftTemplateRead(ShiftTemplateBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RosterPeriodCreate(BaseModel):
    period_code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    starts_on: date
    ends_on: date
    notes: Optional[str] = None

    @validator("ends_on")
    def _ends_after_start(cls, value: date, values: dict) -> date:
        starts_on = values.get("starts_on")
        if starts_on and value < starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return value


class RosterPeriodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[RosterPeriodStatus] = None
    notes: Optional[str] = None


class RosterVersionCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    change_summary: Optional[str] = None
    copy_from_version_id: Optional[str] = None


class RosterAssignmentCreate(BaseModel):
    user_id: str
    starts_at: datetime
    ends_at: datetime
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: RosterAssignmentStatus = RosterAssignmentStatus.DUTY
    planned_minutes: Optional[int] = Field(None, ge=0)
    role_label: Optional[str] = Field(None, max_length=128)
    task_note: Optional[str] = None

    @validator("ends_at")
    def _end_after_start(cls, value: datetime, values: dict) -> datetime:
        starts_at = values.get("starts_at")
        if starts_at and value <= starts_at:
            raise ValueError("ends_at must be after starts_at")
        return value


class RosterAssignmentUpdate(BaseModel):
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: Optional[RosterAssignmentStatus] = None
    planned_minutes: Optional[int] = Field(None, ge=0)
    role_label: Optional[str] = Field(None, max_length=128)
    task_note: Optional[str] = None


class RosterAssignmentRead(BaseModel):
    id: str
    amo_id: str
    version_id: str
    user_id: str
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: RosterAssignmentStatus
    starts_at: datetime
    ends_at: datetime
    planned_minutes: Optional[int] = None
    role_label: Optional[str] = None
    task_note: Optional[str] = None
    locked_after_publish: bool
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    user_full_name: Optional[str] = None
    user_role: Optional[str] = None
    base_code: Optional[str] = None
    base_name: Optional[str] = None
    shift_code: Optional[str] = None
    linked_task_count: int = 0
    linked_task_hours: float = 0.0

    class Config:
        from_attributes = True


class RosterValidationFindingRead(BaseModel):
    id: str
    amo_id: str
    version_id: str
    assignment_id: Optional[str] = None
    user_id: Optional[str] = None
    source: RosterValidationSource
    severity: RosterValidationSeverity
    code: str
    message: str
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RosterVersionRead(BaseModel):
    id: str
    amo_id: str
    period_id: str
    version_no: int
    status: RosterVersionStatus
    title: Optional[str] = None
    change_summary: Optional[str] = None
    created_by_user_id: Optional[str] = None
    submitted_by_user_id: Optional[str] = None
    approved_by_user_id: Optional[str] = None
    published_by_user_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    assignments_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0

    class Config:
        from_attributes = True


class RosterPeriodRead(BaseModel):
    id: str
    amo_id: str
    period_code: str
    name: str
    starts_on: date
    ends_on: date
    status: RosterPeriodStatus
    notes: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: List[RosterVersionRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RosterValidationResult(BaseModel):
    version_id: str
    blocker_count: int
    warning_count: int
    info_count: int
    can_submit: bool
    can_publish: bool
    findings: List[RosterValidationFindingRead]


class RosterAcknowledgeRequest(BaseModel):
    acknowledgement_note: Optional[str] = None


class RosterAcknowledgementRead(BaseModel):
    id: str
    amo_id: str
    version_id: str
    user_id: str
    acknowledged_at: datetime
    acknowledgement_note: Optional[str] = None

    class Config:
        from_attributes = True


class MyRosterResponse(BaseModel):
    user_id: str
    from_date: date
    to_date: date
    assignments: List[RosterAssignmentRead]
    training_due_next_month: List[Dict[str, object]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 2 workload and task-allocation contracts
# ---------------------------------------------------------------------------


class RosterTaskLinkCreate(BaseModel):
    task_assignment_id: int
    allocated_start: Optional[datetime] = None
    allocated_end: Optional[datetime] = None
    allocated_hours: Optional[float] = Field(None, ge=0)

    @validator("allocated_end")
    def _allocated_end_after_start(cls, value: Optional[datetime], values: dict) -> Optional[datetime]:
        start = values.get("allocated_start")
        if value is not None and start is not None and value <= start:
            raise ValueError("allocated_end must be after allocated_start")
        return value


class RosterTaskAllocationCreate(BaseModel):
    task_id: int
    role_on_task: TaskRoleOnTaskEnum = TaskRoleOnTaskEnum.SUPPORT
    task_assignment_status: TaskAssignmentStatusEnum = TaskAssignmentStatusEnum.ASSIGNED
    allocated_start: Optional[datetime] = None
    allocated_end: Optional[datetime] = None
    allocated_hours: Optional[float] = Field(None, ge=0)

    @validator("allocated_end")
    def _allocation_end_after_start(cls, value: Optional[datetime], values: dict) -> Optional[datetime]:
        start = values.get("allocated_start")
        if value is not None and start is not None and value <= start:
            raise ValueError("allocated_end must be after allocated_start")
        return value


class RosterTaskAssignmentLinkRead(BaseModel):
    id: str
    amo_id: str
    roster_assignment_id: str
    task_assignment_id: int
    task_id: int
    user_id: str
    role_on_task: str
    task_assignment_status: str
    allocated_start: Optional[datetime] = None
    allocated_end: Optional[datetime] = None
    allocated_hours: Optional[float] = None
    task_title: Optional[str] = None
    task_code: Optional[str] = None
    work_order_id: Optional[int] = None
    wo_number: Optional[str] = None
    aircraft_serial_number: Optional[str] = None
    aircraft_registration: Optional[str] = None
    base_station_id: Optional[str] = None
    base_code: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime


class WorkloadTaskSummary(BaseModel):
    task_id: int
    work_order_id: int
    wo_number: str
    aircraft_serial_number: str
    aircraft_registration: Optional[str] = None
    aircraft_model: Optional[str] = None
    base_station_id: Optional[str] = None
    base_code: Optional[str] = None
    base_name: Optional[str] = None
    task_code: Optional[str] = None
    title: str
    priority: str
    status: str
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    estimated_manhours: Optional[float] = None
    task_assigned_hours: float = 0.0
    roster_linked_hours: float = 0.0
    remaining_manhours: float = 0.0
    task_assignment_count: int = 0
    roster_link_count: int = 0
    has_estimate: bool = False
    is_unplanned: bool = False
    can_allocate: bool = True


class WorkloadWorkOrderSummary(BaseModel):
    work_order_id: int
    wo_number: str
    description: Optional[str] = None
    check_type: Optional[str] = None
    status: str
    due_date: Optional[date] = None
    aircraft_serial_number: str
    aircraft_registration: Optional[str] = None
    aircraft_model: Optional[str] = None
    base_station_id: Optional[str] = None
    base_code: Optional[str] = None
    base_name: Optional[str] = None
    open_task_count: int = 0
    estimated_manhours: float = 0.0
    task_assigned_hours: float = 0.0
    roster_linked_hours: float = 0.0
    remaining_manhours: float = 0.0


class BaseCapacitySummary(BaseModel):
    base_station_id: Optional[str] = None
    base_code: str
    base_name: str
    assigned_people: int = 0
    certifying_people: int = 0
    technician_people: int = 0
    duty_assignment_count: int = 0
    available_hours: float = 0.0
    standby_hours: float = 0.0
    roster_linked_hours: float = 0.0
    remaining_capacity_hours: float = 0.0
    required_task_hours: float = 0.0
    task_assigned_hours: float = 0.0
    remaining_task_hours: float = 0.0
    capacity_gap_hours: float = 0.0
    capacity_variance_hours: float = 0.0
    open_task_count: int = 0
    unallocated_task_count: int = 0
    missing_estimate_count: int = 0


class PlanningBoardMetrics(BaseModel):
    assigned_people: int = 0
    roster_assignment_count: int = 0
    productive_assignment_count: int = 0
    available_duty_hours: float = 0.0
    standby_hours: float = 0.0
    roster_linked_hours: float = 0.0
    remaining_capacity_hours: float = 0.0
    required_task_hours: float = 0.0
    task_assigned_hours: float = 0.0
    remaining_task_hours: float = 0.0
    capacity_gap_hours: float = 0.0
    capacity_variance_hours: float = 0.0
    work_order_count: int = 0
    task_count: int = 0
    unallocated_task_count: int = 0
    missing_estimate_count: int = 0


class RosterPlanningBoardResponse(BaseModel):
    from_date: date
    to_date: date
    base_station_id: Optional[str] = None
    published_version_id: Optional[str] = None
    assignments: List[RosterAssignmentRead]
    findings: List[RosterValidationFindingRead]
    metrics: PlanningBoardMetrics
    base_capacity: List[BaseCapacitySummary] = Field(default_factory=list)
    work_orders: List[WorkloadWorkOrderSummary] = Field(default_factory=list)
    tasks: List[WorkloadTaskSummary] = Field(default_factory=list)
    task_links: List[RosterTaskAssignmentLinkRead] = Field(default_factory=list)


class RosterContractResponse(BaseModel):
    canonical_personnel_key: str = "users.id"
    route_contracts: Dict[str, str]
    source_modules: Dict[str, str]
    phase: str = "Phase 2 - Workload and base planning"
