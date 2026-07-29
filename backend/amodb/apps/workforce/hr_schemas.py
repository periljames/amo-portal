"""Read models for the canonical Workforce and HR workspace."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    contract_id: str
    staff_code: str
    full_name: str
    position_title: Optional[str] = None
    department_code: Optional[str] = None
    employment_status: Optional[str] = None
    contract_type: Optional[str] = None
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
    active_leave_status: Optional[str] = None
    readiness_state: str
    readiness_reasons: list[str] = Field(default_factory=list)


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


class HrOvertimeDecisionRequest(HrSchema):
    stage: Literal["SUPERVISOR", "HR"]
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = Field(min_length=5, max_length=2000)


class HrDashboardResponse(HrSchema):
    generated_at: datetime
    can_manage_contracts: bool
    can_manage_leave_balances: bool
    can_review_leave: bool
    can_approve_leave: bool
    can_approve_timesheet_supervisor: bool
    can_approve_timesheet_hr: bool
    can_approve_overtime_supervisor: bool
    can_approve_overtime_hr: bool
    can_export_payroll: bool
    active_employee_count: int
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
    people: list[HrPersonReadiness]
