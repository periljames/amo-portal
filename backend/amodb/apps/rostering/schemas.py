# backend/amodb/apps/rostering/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..work.models import TaskAssignmentStatusEnum, TaskRoleOnTaskEnum
from . import models


class RosterSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class RosterErrorResponse(RosterSchema):
    detail: str
    error_code: str
    field_errors: dict[str, list[str] | str] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False


class ShiftTemplateBase(RosterSchema):
    code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=128)
    kind: models.ShiftTemplateKind = models.ShiftTemplateKind.DAY
    default_start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    default_end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    counts_as_duty: bool = True
    is_active: bool = True
    display_order: int = 100
    description: Optional[str] = None
    color_token: Optional[str] = Field(default=None, max_length=64)
    icon_name: Optional[str] = Field(default=None, max_length=64)


class ShiftTemplateCreate(ShiftTemplateBase):
    pass


class ShiftTemplateUpdate(RosterSchema):
    code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    label: Optional[str] = Field(default=None, min_length=1, max_length=128)
    kind: Optional[models.ShiftTemplateKind] = None
    default_start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    default_end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    counts_as_duty: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
    description: Optional[str] = None
    color_token: Optional[str] = Field(default=None, max_length=64)
    icon_name: Optional[str] = Field(default=None, max_length=64)


class ShiftTemplateRead(ShiftTemplateBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RosterPeriodCreate(RosterSchema):
    period_code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    starts_on: date
    ends_on: date
    notes: Optional[str] = None
    timezone_name: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class RosterPeriodUpdate(RosterSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[models.RosterPeriodStatus] = None
    notes: Optional[str] = None
    timezone_name: Optional[str] = Field(default=None, max_length=64)


class RosterVersionCreate(RosterSchema):
    title: Optional[str] = Field(default=None, max_length=255)
    change_summary: Optional[str] = None
    copy_from_version_id: Optional[str] = None
    source_version_id: Optional[str] = None
    amendment_type: Optional[models.RosterAmendmentType] = None
    amendment_reason: Optional[str] = None
    effective_from: Optional[datetime] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)


class RosterAssignmentCreate(RosterSchema):
    user_id: str
    starts_at: datetime
    ends_at: datetime
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: models.RosterAssignmentStatus = models.RosterAssignmentStatus.DUTY
    source: models.RosterAssignmentSource = models.RosterAssignmentSource.MANUAL
    source_reference_id: Optional[str] = Field(default=None, max_length=128)
    planned_minutes: Optional[int] = Field(default=None, ge=0)
    role_label: Optional[str] = Field(default=None, max_length=128)
    team_code: Optional[str] = Field(default=None, max_length=64)
    location_label: Optional[str] = Field(default=None, max_length=128)
    task_note: Optional[str] = None
    change_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class RosterAssignmentUpdate(RosterSchema):
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: Optional[models.RosterAssignmentStatus] = None
    planned_minutes: Optional[int] = Field(default=None, ge=0)
    role_label: Optional[str] = Field(default=None, max_length=128)
    team_code: Optional[str] = Field(default=None, max_length=64)
    location_label: Optional[str] = Field(default=None, max_length=128)
    task_note: Optional[str] = None
    change_reason: Optional[str] = None
    expected_state_revision: Optional[int] = Field(default=None, ge=1)


class RosterAssignmentDeleteRequest(RosterSchema):
    reason: str = Field(min_length=1)
    expected_state_revision: Optional[int] = Field(default=None, ge=1)


class RosterAssignmentRead(RosterSchema):
    id: str
    amo_id: str
    version_id: str
    user_id: str
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    status: models.RosterAssignmentStatus
    source: models.RosterAssignmentSource = models.RosterAssignmentSource.MANUAL
    source_reference_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    planned_minutes: Optional[int] = None
    role_label: Optional[str] = None
    team_code: Optional[str] = None
    location_label: Optional[str] = None
    task_note: Optional[str] = None
    change_reason: Optional[str] = None
    locked_after_publish: bool
    state_revision: int = 1
    deleted_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    user_full_name: Optional[str] = None
    user_staff_code: Optional[str] = None
    user_role: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    base_code: Optional[str] = None
    base_name: Optional[str] = None
    shift_code: Optional[str] = None
    shift_label: Optional[str] = None
    shift_kind: Optional[str] = None
    linked_task_count: int = 0
    linked_task_hours: float = 0.0
    contract_status: Optional[str] = None
    availability_state: Optional[str] = None
    training_state: Optional[str] = None
    authorisation_state: Optional[str] = None




class RosterRuleSetBase(RosterSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version_label: Optional[str] = Field(default=None, max_length=128)
    regulatory_basis: Optional[str] = None
    manual_reference: Optional[str] = None
    description: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    priority: int = 100
    is_active: bool = True


class RosterRuleSetCreate(RosterRuleSetBase):
    pass


class RosterRuleSetUpdate(RosterSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    version_label: Optional[str] = Field(default=None, max_length=128)
    regulatory_basis: Optional[str] = None
    manual_reference: Optional[str] = None
    description: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class RosterRuleSetRead(RosterRuleSetBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RosterApprovalAuthorityBase(RosterSchema):
    user_id: str
    authority_level: models.RosterApprovalAuthorityLevel
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    can_approve: bool = True
    can_publish: bool = False
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool = True


class RosterApprovalAuthorityCreate(RosterApprovalAuthorityBase):
    pass


class RosterApprovalAuthorityUpdate(RosterSchema):
    can_approve: Optional[bool] = None
    can_publish: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=2000)
    is_active: Optional[bool] = None


class RosterApprovalAuthorityRead(RosterApprovalAuthorityBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RosterDepartmentApprovalRead(RosterSchema):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amo_id: str
    version_id: str
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    assigned_approver_user_id: Optional[str] = None
    status: models.RosterDepartmentApprovalStatus
    decided_by_user_id: Optional[str] = None
    decision_comment: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RosterApprovalMatrixResponse(RosterSchema):
    version_id: Optional[str] = None
    required_count: int = 0
    approved_count: int = 0
    pending_count: int = 0
    changes_requested_count: int = 0
    items: list[RosterDepartmentApprovalRead] = Field(default_factory=list)


class RosterCalendarSubscriptionRead(RosterSchema):
    https_url: str
    webcal_url: str
    feed_path: str
    refresh_interval_minutes: int = 60
    includes: list[str] = Field(default_factory=list)


class RosterRuleBase(RosterSchema):
    rule_set_id: Optional[str] = None
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    rule_type: models.RosterRuleType
    scope: models.RosterRuleScope = models.RosterRuleScope.AMO
    severity: models.RosterValidationSeverity = models.RosterValidationSeverity.BLOCKER
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    shift_template_id: Optional[str] = None
    user_id: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    allow_override: bool = False
    is_active: bool = True
    display_order: int = 100

    @model_validator(mode="after")
    def validate_scope_and_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        required = {
            models.RosterRuleScope.DEPARTMENT: self.department_id,
            models.RosterRuleScope.BASE: self.base_station_id,
            models.RosterRuleScope.SHIFT_TEMPLATE: self.shift_template_id,
            models.RosterRuleScope.USER: self.user_id,
        }
        if self.scope in required and not required[self.scope]:
            raise ValueError(f"{self.scope.value.lower()} scope requires its scope identifier")
        return self


class RosterRuleCreate(RosterRuleBase):
    pass


class RosterRuleUpdate(RosterSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    severity: Optional[models.RosterValidationSeverity] = None
    parameters_json: Optional[dict[str, Any]] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    allow_override: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class RosterRuleRead(RosterRuleBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RosterValidationFindingRead(RosterSchema):
    id: str
    amo_id: str
    version_id: str
    assignment_id: Optional[str] = None
    user_id: Optional[str] = None
    rule_id: Optional[str] = None
    source: models.RosterValidationSource
    severity: models.RosterValidationSeverity
    code: str
    message: str
    details_json: Optional[dict[str, Any]] = None
    overridable: bool = False
    resolved: bool
    overridden_at: Optional[datetime] = None
    overridden_by_user_id: Optional[str] = None
    override_reason: Optional[str] = None
    sort_order: int = 100
    created_at: datetime


class RosterVersionRead(RosterSchema):
    id: str
    amo_id: str
    period_id: str
    source_version_id: Optional[str] = None
    version_no: int
    status: models.RosterVersionStatus
    title: Optional[str] = None
    change_summary: Optional[str] = None
    amendment_type: Optional[models.RosterAmendmentType] = None
    amendment_reason: Optional[str] = None
    effective_from: Optional[datetime] = None
    idempotency_key: Optional[str] = None
    state_revision: int = 1
    last_validated_at: Optional[datetime] = None
    validation_fingerprint: Optional[str] = None
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
    overridden_count: int = 0
    acknowledgement_count: int = 0
    approval_required_count: int = 0
    approval_approved_count: int = 0
    approval_pending_count: int = 0
    can_edit: bool = False
    can_submit: bool = False
    can_approve: bool = False
    can_publish: bool = False


class RosterPeriodRead(RosterSchema):
    id: str
    amo_id: str
    period_code: str
    name: str
    starts_on: date
    ends_on: date
    status: models.RosterPeriodStatus
    notes: Optional[str] = None
    timezone_name: str = "UTC"
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: list[RosterVersionRead] = Field(default_factory=list)


class RosterValidationResult(RosterSchema):
    version_id: str
    validation_fingerprint: Optional[str] = None
    blocker_count: int
    warning_count: int
    info_count: int
    overridden_count: int = 0
    can_submit: bool
    can_publish: bool
    findings: list[RosterValidationFindingRead]


class RosterRuleOverrideRequest(RosterSchema):
    decision: models.RosterExceptionDecision
    reason: str = Field(min_length=8)
    expires_at: Optional[datetime] = None


class RosterRuleExceptionRead(RosterSchema):
    id: str
    amo_id: str
    version_id: str
    finding_id: Optional[str] = None
    rule_id: Optional[str] = None
    assignment_id: Optional[str] = None
    user_id: Optional[str] = None
    decision: models.RosterExceptionDecision
    reason: str
    approved_by_user_id: str
    expires_at: Optional[datetime] = None
    created_at: datetime


class RosterLifecycleRequest(RosterSchema):
    expected_state_revision: Optional[int] = Field(default=None, ge=1)
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)
    comment: Optional[str] = None
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None


class RosterAcknowledgeRequest(RosterSchema):
    acknowledgement_note: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)


class RosterAcknowledgementRead(RosterSchema):
    id: str
    amo_id: str
    version_id: str
    user_id: str
    idempotency_key: Optional[str] = None
    delivery_status: str = "PENDING"
    viewed_at: Optional[datetime] = None
    acknowledged_at: datetime
    acknowledgement_note: Optional[str] = None


class RosterBulkAssignmentItem(RosterAssignmentCreate):
    client_id: Optional[str] = Field(default=None, max_length=128)


class RosterBulkAssignmentRequest(RosterSchema):
    assignments: list[RosterBulkAssignmentItem] = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_version_revision: Optional[int] = Field(default=None, ge=1)
    atomic: bool = True


class RosterBulkAssignmentResult(RosterSchema):
    version_id: str
    created: list[RosterAssignmentRead] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    idempotent_replay: bool = False


class PatternGenerationRequest(RosterSchema):
    from_date: date
    to_date: date
    user_ids: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=128)
    skip_duplicates: bool = True
    expected_version_revision: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class RosterDemandRequirementCreate(RosterSchema):
    base_station_id: Optional[str] = None
    department_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    requirement_code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    required_headcount: int = Field(default=0, ge=0)
    required_minutes: int = Field(default=0, ge=0)
    role_label: Optional[str] = Field(default=None, max_length=128)
    authorisation_type_id: Optional[str] = None
    source_type: str = Field(default="MANUAL", max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    metadata_json: Optional[dict[str, Any]] = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.required_headcount <= 0 and self.required_minutes <= 0:
            raise ValueError("Specify required_headcount or required_minutes")
        return self


class RosterDemandRequirementRead(RosterDemandRequirementCreate):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MyRosterResponse(RosterSchema):
    user_id: str
    from_date: date
    to_date: date
    assignments: list[RosterAssignmentRead]
    training_due_next_month: list[dict[str, Any]] = Field(default_factory=list)
    leave_requests: list[dict[str, Any]] = Field(default_factory=list)
    acknowledgement_required_version_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Workload and task-allocation contracts
# ---------------------------------------------------------------------------


class RosterTaskLinkCreate(RosterSchema):
    task_assignment_id: int
    allocated_start: Optional[datetime] = None
    allocated_end: Optional[datetime] = None
    allocated_hours: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_window(self):
        if self.allocated_start and self.allocated_end and self.allocated_end <= self.allocated_start:
            raise ValueError("allocated_end must be after allocated_start")
        return self


class RosterTaskAllocationCreate(RosterSchema):
    task_id: int
    role_on_task: TaskRoleOnTaskEnum = TaskRoleOnTaskEnum.SUPPORT
    task_assignment_status: TaskAssignmentStatusEnum = TaskAssignmentStatusEnum.ASSIGNED
    allocated_start: Optional[datetime] = None
    allocated_end: Optional[datetime] = None
    allocated_hours: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_window(self):
        if self.allocated_start and self.allocated_end and self.allocated_end <= self.allocated_start:
            raise ValueError("allocated_end must be after allocated_start")
        return self


class RosterTaskAssignmentLinkRead(RosterSchema):
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


class WorkloadTaskSummary(RosterSchema):
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


class WorkloadWorkOrderSummary(RosterSchema):
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


class BaseCapacitySummary(RosterSchema):
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
    required_headcount: int = 0
    headcount_gap: int = 0


class PlanningBoardMetrics(RosterSchema):
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
    blocker_count: int = 0
    warning_count: int = 0
    leave_conflict_count: int = 0
    unacknowledged_count: int = 0


class RosterPlanningBoardResponse(RosterSchema):
    from_date: date
    to_date: date
    base_station_id: Optional[str] = None
    published_version_id: Optional[str] = None
    assignments: list[RosterAssignmentRead]
    findings: list[RosterValidationFindingRead]
    metrics: PlanningBoardMetrics
    base_capacity: list[BaseCapacitySummary]
    work_orders: list[WorkloadWorkOrderSummary]
    tasks: list[WorkloadTaskSummary]
    task_links: list[RosterTaskAssignmentLinkRead]
    demand_requirements: list[RosterDemandRequirementRead] = Field(default_factory=list)


class RosterDashboardResponse(RosterSchema):
    from_date: date
    to_date: date
    active_period_count: int
    draft_version_count: int
    submitted_version_count: int
    published_version_count: int
    blocker_count: int
    warning_count: int
    pending_leave_count: int
    unacknowledged_publication_count: int
    capacity_gap_hours: float
    upcoming_periods: list[RosterPeriodRead] = Field(default_factory=list)
    top_findings: list[RosterValidationFindingRead] = Field(default_factory=list)


class RosterReportSummary(RosterSchema):
    from_date: date
    to_date: date
    planned_minutes: int
    attendance_minutes: int
    productive_minutes: int
    overtime_minutes: int
    assignment_count: int
    assigned_people: int
    leave_minutes: int
    training_minutes: int
    standby_minutes: int
    acknowledgement_rate: float
    blocker_count: int
    warning_count: int
    by_base: list[dict[str, Any]] = Field(default_factory=list)
    by_department: list[dict[str, Any]] = Field(default_factory=list)
    by_user: list[dict[str, Any]] = Field(default_factory=list)


class RosterContractResponse(RosterSchema):
    canonical_personnel_key: str
    route_contracts: dict[str, str]
    source_modules: dict[str, str]
    phase: str
    permissions: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
