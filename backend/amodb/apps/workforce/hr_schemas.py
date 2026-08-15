"""Read models for the canonical Workforce and HR workspace."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HrSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class HrMetric(HrSchema):
    key: str
    label: str
    value: int | float | str
    detail: Optional[str] = None
    tone: str = "neutral"


class HrActionItem(HrSchema):
    id: str
    category: str
    severity: str
    title: str
    detail: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    due_on: Optional[date] = None
    action_label: Optional[str] = None
    action_path: Optional[str] = None


class HrPersonReadiness(HrSchema):
    user_id: str
    contract_id: Optional[str] = None
    staff_code: str
    full_name: str
    email: Optional[str] = None
    has_effective_contract: bool = False
    uses_default_day_pattern: bool = False
    account_role: Optional[str] = None
    position_title: Optional[str] = None
    department_id: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    employment_status: Optional[str] = None
    contract_type: Optional[str] = None
    contract_state: Literal["EFFECTIVE", "FUTURE", "MISSING"] = "MISSING"
    hire_date: Optional[date] = None
    contract_effective_from: Optional[date] = None
    contract_effective_to: Optional[date] = None
    primary_base_station_id: Optional[str] = None
    primary_base_code: Optional[str] = None
    supervisor_name: Optional[str] = None
    standard_weekly_minutes: int = 0
    standard_daily_minutes: int = 0
    fte_percentage: float = 100.0
    cost_centre: Optional[str] = None
    payroll_number: Optional[str] = None
    overtime_eligible: bool = True
    night_shift_eligible: bool = True
    standby_eligible: bool = True
    work_pattern_code: Optional[str] = None
    work_pattern_name: Optional[str] = None
    work_pattern_effective_from: Optional[date] = None
    pattern_state: Literal["DEFAULT", "ASSIGNED", "MISSING"] = "MISSING"
    active_leave_status: Optional[str] = None
    group_ids: list[str] = Field(default_factory=list)
    group_names: list[str] = Field(default_factory=list)
    readiness_state: str
    readiness_reasons: list[str] = Field(default_factory=list)


class HrPeoplePage(HrSchema):
    items: list[HrPersonReadiness]
    page: int
    page_size: int
    total: int
    pages: int


class HrPeopleFilterInput(HrSchema):
    search: Optional[str] = Field(default=None, max_length=200)
    department_id: Optional[str] = None
    role: Optional[str] = None
    position_title: Optional[str] = Field(default=None, max_length=255)
    contract_type: Optional[str] = None
    employment_status: Optional[str] = None
    base_station_id: Optional[str] = None
    group_id: Optional[str] = None
    readiness_state: Optional[Literal["READY", "NEEDS_ATTENTION", "BLOCKED"]] = None
    contract_state: Optional[Literal["EFFECTIVE", "FUTURE", "MISSING"]] = None
    pattern_state: Optional[Literal["DEFAULT", "ASSIGNED", "MISSING"]] = None
    expires_within_days: Optional[int] = Field(default=None, ge=1, le=365)
    sort_by: Literal["name", "staff_code", "department", "role", "position_title"] = "name"
    sort_dir: Literal["asc", "desc"] = "asc"


class HrFilterOption(HrSchema):
    value: str
    label: str
    count: int
    secondary: Optional[str] = None


class HrPeopleFacets(HrSchema):
    departments: list[HrFilterOption] = Field(default_factory=list)
    roles: list[HrFilterOption] = Field(default_factory=list)
    position_titles: list[HrFilterOption] = Field(default_factory=list)
    contract_types: list[HrFilterOption] = Field(default_factory=list)
    employment_statuses: list[HrFilterOption] = Field(default_factory=list)
    bases: list[HrFilterOption] = Field(default_factory=list)
    groups: list[HrFilterOption] = Field(default_factory=list)
    readiness_states: list[HrFilterOption] = Field(default_factory=list)
    contract_states: list[HrFilterOption] = Field(default_factory=list)
    pattern_states: list[HrFilterOption] = Field(default_factory=list)


class HrPeopleSelection(HrSchema):
    mode: Literal["EXPLICIT", "FILTERED"]
    user_ids: list[str] = Field(default_factory=list, max_length=10000)
    exclude_user_ids: list[str] = Field(default_factory=list, max_length=10000)
    filters: HrPeopleFilterInput = Field(default_factory=HrPeopleFilterInput)

    @model_validator(mode="after")
    def validate_selection(self):
        if self.mode == "EXPLICIT" and not self.user_ids:
            raise ValueError("At least one user must be selected")
        if self.mode == "FILTERED" and self.user_ids:
            raise ValueError("Filtered selections must not include explicit user IDs")
        return self


class HrDefaultDayBatchPreview(HrSchema):
    matched_count: int
    eligible_count: int
    assignable_count: int
    already_assigned_count: int
    ineligible_count: int
    selection_token: str = ""
    capped: bool = False


class HrDefaultDayBatchApplyRequest(HrSchema):
    selection: HrPeopleSelection
    expected_match_count: int = Field(ge=0, le=10000)
    expected_selection_token: str = Field(min_length=64, max_length=64)


class HrDefaultDayBatchResult(HrSchema):
    shift_template_id: str
    work_pattern_id: str
    matched_count: int
    eligible_count: int
    assigned_count: int
    already_assigned_count: int
    ineligible_count: int
    skipped_conflict_count: int


class HrOvertimeRequestRead(HrSchema):
    id: str
    amo_id: str
    user_id: str
    user_full_name: Optional[str] = None
    roster_assignment_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    requested_minutes: int
    reason: str
    status: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class HrAttendanceExceptionRead(HrSchema):
    id: str
    amo_id: str
    roster_assignment_id: str
    user_id: str
    user_full_name: Optional[str] = None
    planned_minutes: int
    attendance_minutes: int
    productive_minutes: int
    variance_minutes: int
    classification: str
    metadata_json: Optional[dict[str, Any]] = None
    calculated_at: datetime


class HrOvertimeDecisionRequest(HrSchema):
    stage: Literal["SUPERVISOR", "HR"]
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = Field(min_length=5, max_length=2000)


class HrDashboardResponse(HrSchema):
    generated_at: datetime
    can_manage_contracts: bool
    can_manage_patterns: bool = False
    can_assign_patterns: bool = False
    can_initialize_default_day_pattern: bool = False
    can_manage_leave_balances: bool
    can_review_leave: bool
    can_approve_leave: bool
    can_approve_timesheet_supervisor: bool
    can_approve_timesheet_hr: bool
    can_approve_overtime_supervisor: bool
    can_approve_overtime_hr: bool
    can_manage_attendance: bool
    can_export_payroll: bool
    active_employee_count: int
    employees_without_contract_count: int = 0
    onboarding_employee_count: int
    suspended_employee_count: int
    contracts_expiring_soon_count: int
    employees_without_pattern_count: int
    employees_without_base_count: int
    pending_leave_count: int
    pending_timesheet_count: int
    pending_overtime_count: int
    attendance_exception_count: int
    metrics: list[HrMetric]
    action_queue: list[HrActionItem]
    pending_overtime: list[HrOvertimeRequestRead]
    attendance_exceptions: list[HrAttendanceExceptionRead] = Field(default_factory=list)
    people: list[HrPersonReadiness]


class HrDefaultDayBootstrapResponse(HrSchema):
    shift_template_id: str
    work_pattern_id: str
    eligible_user_count: int
    assigned_user_count: int
    already_assigned_count: int
    skipped_conflict_count: int
