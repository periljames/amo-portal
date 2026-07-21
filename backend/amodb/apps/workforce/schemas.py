# backend/amodb/apps/workforce/schemas.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import models

T = TypeVar("T")


class WorkforceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class ErrorResponse(WorkforceSchema):
    detail: str
    error_code: str
    field_errors: dict[str, list[str] | str] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False


class Page(WorkforceSchema, Generic[T]):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)


class EmploymentContractBase(WorkforceSchema):
    user_id: str
    contract_type: models.ContractType = models.ContractType.PERMANENT
    employment_status: models.EmploymentStatus = models.EmploymentStatus.ACTIVE
    effective_from: date
    effective_to: Optional[date] = None
    standard_weekly_minutes: int = Field(default=2400, ge=0)
    standard_daily_minutes: int = Field(default=480, ge=0)
    fte_percentage: float = Field(default=100.0, gt=0, le=100)
    primary_base_station_id: str
    secondary_base_station_id: Optional[str] = None
    supervisor_user_id: Optional[str] = None
    cost_centre: Optional[str] = Field(default=None, max_length=64)
    payroll_number: Optional[str] = Field(default=None, max_length=64)
    overtime_eligible: bool = True
    night_shift_eligible: bool = True
    standby_eligible: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class EmploymentContractCreate(EmploymentContractBase):
    pass


class EmploymentContractUpdate(WorkforceSchema):
    contract_type: Optional[models.ContractType] = None
    employment_status: Optional[models.EmploymentStatus] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    standard_weekly_minutes: Optional[int] = Field(default=None, ge=0)
    standard_daily_minutes: Optional[int] = Field(default=None, ge=0)
    fte_percentage: Optional[float] = Field(default=None, gt=0, le=100)
    primary_base_station_id: Optional[str] = None
    secondary_base_station_id: Optional[str] = None
    supervisor_user_id: Optional[str] = None
    cost_centre: Optional[str] = Field(default=None, max_length=64)
    payroll_number: Optional[str] = Field(default=None, max_length=64)
    overtime_eligible: Optional[bool] = None
    night_shift_eligible: Optional[bool] = None
    standby_eligible: Optional[bool] = None


class EmploymentContractRead(EmploymentContractBase):
    id: str
    amo_id: str
    user_full_name: Optional[str] = None
    user_staff_code: Optional[str] = None
    primary_base_code: Optional[str] = None
    secondary_base_code: Optional[str] = None
    supervisor_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkPatternDayInput(WorkforceSchema):
    cycle_day_index: int = Field(ge=0)
    shift_template_id: Optional[str] = None
    status: models.PatternDayStatus = models.PatternDayStatus.DUTY
    start_time_local: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time_local: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    spans_next_day: bool = False
    planned_minutes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_times(self):
        if bool(self.start_time_local) != bool(self.end_time_local):
            if not (self.start_time_local and self.planned_minutes > 0):
                raise ValueError("Supply both start/end times, or start time with planned_minutes")
        return self


class WorkPatternCreate(WorkforceSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    cycle_length_days: int = Field(ge=1, le=366)
    is_active: bool = True
    timezone_name: str = Field(default="UTC", min_length=1, max_length=64)
    days: list[WorkPatternDayInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_days(self):
        indexes = [row.cycle_day_index for row in self.days]
        if len(indexes) != len(set(indexes)):
            raise ValueError("cycle_day_index values must be unique")
        if any(index >= self.cycle_length_days for index in indexes):
            raise ValueError("cycle_day_index must be below cycle_length_days")
        return self


class WorkPatternUpdate(WorkforceSchema):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    cycle_length_days: Optional[int] = Field(default=None, ge=1, le=366)
    is_active: Optional[bool] = None
    timezone_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    days: Optional[list[WorkPatternDayInput]] = None


class WorkPatternDayRead(WorkPatternDayInput):
    id: str
    amo_id: str
    work_pattern_id: str
    shift_code: Optional[str] = None
    shift_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkPatternRead(WorkforceSchema):
    id: str
    amo_id: str
    code: str
    name: str
    description: Optional[str] = None
    cycle_length_days: int
    is_active: bool
    timezone_name: str
    days: list[WorkPatternDayRead] = Field(default_factory=list)
    assigned_employee_count: int = 0
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EmployeeWorkPatternAssignmentCreate(WorkforceSchema):
    user_id: str
    work_pattern_id: str
    effective_from: date
    effective_to: Optional[date] = None
    cycle_anchor_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class EmployeeWorkPatternAssignmentRead(EmployeeWorkPatternAssignmentCreate):
    id: str
    amo_id: str
    user_full_name: Optional[str] = None
    pattern_code: Optional[str] = None
    pattern_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PatternPreviewRequest(WorkforceSchema):
    from_date: date
    to_date: date
    user_ids: list[str] = Field(default_factory=list)
    roster_version_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class PatternPreviewRow(WorkforceSchema):
    user_id: str
    user_full_name: Optional[str] = None
    work_date: date
    cycle_day_index: int
    status: models.PatternDayStatus
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    planned_minutes: int
    shift_template_id: Optional[str] = None
    shift_code: Optional[str] = None
    base_station_id: Optional[str] = None
    source_reference_id: str
    duplicate: bool = False
    conflicts: list[str] = Field(default_factory=list)


class PatternPreviewResponse(WorkforceSchema):
    from_date: date
    to_date: date
    item_count: int
    duplicate_count: int
    conflict_count: int
    items: list[PatternPreviewRow]


class LeaveTypeCreate(WorkforceSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    availability_type: models.AvailabilityType
    description: Optional[str] = None
    paid: bool = True
    deducts_balance: bool = True
    requires_attachment: bool = False
    supervisor_approval_required: bool = True
    hr_approval_required: bool = True
    allow_negative_balance: bool = False
    is_active: bool = True
    display_order: int = 100


class LeaveTypeUpdate(WorkforceSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    availability_type: Optional[models.AvailabilityType] = None
    description: Optional[str] = None
    paid: Optional[bool] = None
    deducts_balance: Optional[bool] = None
    requires_attachment: Optional[bool] = None
    supervisor_approval_required: Optional[bool] = None
    hr_approval_required: Optional[bool] = None
    allow_negative_balance: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class LeaveTypeRead(LeaveTypeCreate):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LeaveBalanceUpdate(WorkforceSchema):
    allocated_minutes: Optional[int] = Field(default=None, ge=0)
    carried_minutes: Optional[int] = None
    adjustment_minutes: Optional[int] = None


class LeaveBalanceRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    leave_type_id: str
    leave_type_code: Optional[str] = None
    leave_type_name: Optional[str] = None
    leave_year: int
    allocated_minutes: int
    carried_minutes: int
    used_minutes: int
    pending_minutes: int
    adjustment_minutes: int
    available_minutes: int
    updated_by_user_id: Optional[str] = None
    updated_at: datetime


class LeaveRequestCreate(WorkforceSchema):
    user_id: Optional[str] = None
    leave_type_id: str
    starts_at: datetime
    ends_at: datetime
    requested_minutes: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = None
    attachment_reference: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class LeaveRequestUpdate(WorkforceSchema):
    leave_type_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    requested_minutes: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = None
    attachment_reference: Optional[str] = Field(default=None, max_length=255)


class WorkflowDecision(WorkforceSchema):
    comment: Optional[str] = None
    reason: Optional[str] = None


class LeaveApprovalRead(WorkforceSchema):
    id: str
    stage: models.LeaveApprovalStage
    decision: models.ApprovalDecision
    actor_user_id: Optional[str] = None
    actor_name: Optional[str] = None
    comment: Optional[str] = None
    decided_at: datetime


class LeaveRequestRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    user_staff_code: Optional[str] = None
    department_id: Optional[str] = None
    leave_type_id: str
    leave_type_code: Optional[str] = None
    leave_type_name: Optional[str] = None
    availability_type: Optional[models.AvailabilityType] = None
    starts_at: datetime
    ends_at: datetime
    requested_minutes: int
    status: models.LeaveRequestStatus
    reason: Optional[str] = None
    attachment_reference: Optional[str] = None
    published_roster_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[LeaveApprovalRead] = Field(default_factory=list)
    submitted_at: Optional[datetime] = None
    supervisor_approved_at: Optional[datetime] = None
    hr_approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AvailabilityEventCreate(WorkforceSchema):
    user_id: str
    availability_type: models.AvailabilityType
    starts_at: datetime
    ends_at: datetime
    blocking: bool = True
    provisional: bool = False
    source_type: str = Field(default="MANUAL", max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=64)
    reason: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class AvailabilityEventUpdate(WorkforceSchema):
    availability_type: Optional[models.AvailabilityType] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    blocking: Optional[bool] = None
    provisional: Optional[bool] = None
    reason: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class AvailabilityEventRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    availability_type: models.AvailabilityType
    starts_at: datetime
    ends_at: datetime
    blocking: bool
    provisional: bool
    source_type: str
    source_id: str
    reason: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PublicHolidayCalendarCreate(WorkforceSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    country_code: Optional[str] = Field(default=None, max_length=8)
    timezone_name: str = Field(default="UTC", max_length=64)
    is_active: bool = True


class PublicHolidayCreate(WorkforceSchema):
    calendar_id: str
    holiday_date: date
    name: str = Field(min_length=1, max_length=255)
    paid: bool = True
    metadata_json: Optional[dict[str, Any]] = None


class PublicHolidayRead(PublicHolidayCreate):
    id: str
    amo_id: str
    calendar_code: Optional[str] = None
    calendar_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime


class AttendanceEventCreate(WorkforceSchema):
    user_id: Optional[str] = None
    event_type: models.AttendanceEventType
    occurred_at: datetime
    source: str = Field(default="MANUAL", max_length=64)
    base_station_id: Optional[str] = None
    roster_assignment_id: Optional[str] = None
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class AttendanceEventRead(AttendanceEventCreate):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    recorded_by_user_id: Optional[str] = None
    created_at: datetime


class AttendanceSummaryRead(WorkforceSchema):
    user_id: str
    user_full_name: Optional[str] = None
    from_date: date
    to_date: date
    presence_minutes: int
    break_minutes: int
    paid_minutes: int
    incomplete: bool
    warnings: list[str] = Field(default_factory=list)
    events: list[AttendanceEventRead] = Field(default_factory=list)


class TimesheetGenerateRequest(WorkforceSchema):
    period_start: date
    period_end: date
    user_ids: list[str] = Field(default_factory=list)
    replace_draft: bool = True

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class TimesheetLineRead(WorkforceSchema):
    id: str
    work_date: date
    category: models.TimesheetCategory
    minutes: int
    roster_assignment_id: Optional[str] = None
    work_log_entry_id: Optional[int] = None
    source: str
    description: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class TimesheetRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    payroll_number: Optional[str] = None
    period_start: date
    period_end: date
    status: models.TimesheetStatus
    planned_minutes: int
    attendance_minutes: int
    productive_minutes: int
    overtime_minutes: int
    variance_minutes: int
    lines: list[TimesheetLineRead] = Field(default_factory=list)
    submitted_at: Optional[datetime] = None
    supervisor_approved_at: Optional[datetime] = None
    hr_approved_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TimesheetApprovalRequest(WorkforceSchema):
    stage: models.LeaveApprovalStage = models.LeaveApprovalStage.SUPERVISOR
    comment: Optional[str] = None


class OvertimeRequestCreate(WorkforceSchema):
    user_id: Optional[str] = None
    roster_assignment_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    requested_minutes: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class OvertimeRequestRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    roster_assignment_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    requested_minutes: int
    reason: str
    status: models.OvertimeRequestStatus
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PayrollExportRow(WorkforceSchema):
    timesheet_id: str
    payroll_number: Optional[str] = None
    user_id: str
    staff_code: Optional[str] = None
    full_name: str
    period_start: date
    period_end: date
    ordinary_minutes: int
    overtime_minutes: int
    night_minutes: int
    weekend_minutes: int
    public_holiday_minutes: int
    standby_minutes: int
    callout_minutes: int
    training_minutes: int
    travel_minutes: int
    leave_minutes: int
    unpaid_absence_minutes: int
    approved_at: Optional[datetime] = None


class PermissionGrantCreate(WorkforceSchema):
    user_id: str
    permission_code: str = Field(min_length=1, max_length=128)
    effect: models.PermissionEffect = models.PermissionEffect.GRANT
    department_id: Optional[str] = None
    base_station_id: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class PermissionGrantRead(PermissionGrantCreate):
    id: str
    amo_id: str
    granted_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CurrentPermissionsRead(WorkforceSchema):
    user_id: str
    permissions: list[str]


class PlannerPreferenceUpdate(WorkforceSchema):
    density: Optional[str] = Field(default=None, pattern=r"^(compact|comfortable)$")
    group_by: Optional[str] = Field(default=None, max_length=32)
    zoom: Optional[str] = Field(default=None, max_length=32)
    default_base_station_id: Optional[str] = None
    filters_json: Optional[dict[str, Any]] = None


class PlannerPreferenceRead(WorkforceSchema):
    id: str
    amo_id: str
    user_id: str
    density: str
    group_by: str
    zoom: str
    default_base_station_id: Optional[str] = None
    filters_json: Optional[dict[str, Any]] = None
    updated_at: datetime
