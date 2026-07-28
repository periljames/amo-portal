"""API contracts for roster setup readiness and controlled automation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .automation_models import (
    RosterAutomationFrequency,
    RosterAutomationRunStatus,
    RosterAutomationTrigger,
)


class AutomationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class RosterGenerationPolicyRead(AutomationSchema):
    id: str
    amo_id: str
    enabled: bool
    frequency: RosterAutomationFrequency
    lead_periods: int
    run_day: int
    run_hour_local: int
    timezone_name: str
    period_code_pattern: str
    period_name_pattern: str
    create_initial_draft: bool
    generate_from_patterns: bool
    preserve_source_commitments: bool
    validate_after_generation: bool
    notify_planners: bool
    require_preview_confirmation: bool
    state_revision: int
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    updated_reason: Optional[str] = None
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RosterGenerationPolicyUpdate(AutomationSchema):
    enabled: Optional[bool] = None
    frequency: Optional[RosterAutomationFrequency] = None
    lead_periods: Optional[int] = Field(default=None, ge=1, le=12)
    run_day: Optional[int] = Field(default=None, ge=1, le=28)
    run_hour_local: Optional[int] = Field(default=None, ge=0, le=23)
    timezone_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    period_code_pattern: Optional[str] = Field(default=None, min_length=1, max_length=128)
    period_name_pattern: Optional[str] = Field(default=None, min_length=1, max_length=255)
    create_initial_draft: Optional[bool] = None
    generate_from_patterns: Optional[bool] = None
    preserve_source_commitments: Optional[bool] = None
    validate_after_generation: Optional[bool] = None
    notify_planners: Optional[bool] = None
    require_preview_confirmation: Optional[bool] = None
    expected_state_revision: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=2000)


class RosterAutomationPreviewRequest(AutomationSchema):
    target_from: Optional[date] = None
    target_to: Optional[date] = None
    user_ids: list[str] = Field(default_factory=list, max_length=500)
    create_missing_period: bool = True
    create_initial_draft: Optional[bool] = None
    generate_from_patterns: Optional[bool] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if bool(self.target_from) != bool(self.target_to):
            raise ValueError("target_from and target_to must be supplied together")
        if self.target_from and self.target_to and self.target_to < self.target_from:
            raise ValueError("target_to must be on or after target_from")
        return self


class RosterAutomationRunRequest(RosterAutomationPreviewRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)
    confirm_preview: bool = False


class RosterAutomationPreviewItem(AutomationSchema):
    code: str
    severity: str
    message: str
    user_id: Optional[str] = None
    reference_id: Optional[str] = None


class RosterAutomationPreviewResponse(AutomationSchema):
    target_from: date
    target_to: date
    period_code: str
    period_name: str
    period_exists: bool
    period_id: Optional[str] = None
    draft_exists: bool
    draft_version_id: Optional[str] = None
    active_pattern_assignment_count: int
    eligible_employee_count: int
    employees_without_pattern_count: int
    estimated_assignment_count: int
    blocking_issue_count: int
    warning_count: int
    items: list[RosterAutomationPreviewItem] = Field(default_factory=list)
    requires_confirmation: bool = True


class RosterGenerationRunRead(AutomationSchema):
    id: str
    amo_id: str
    policy_id: str
    trigger: RosterAutomationTrigger
    status: RosterAutomationRunStatus
    idempotency_key: str
    dry_run: bool
    period_id: Optional[str] = None
    version_id: Optional[str] = None
    target_from: str
    target_to: str
    generated_count: int
    skipped_count: int
    conflict_count: int
    validation_blocker_count: int
    validation_warning_count: int
    summary_json: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    requested_by_user_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime


class RosterSetupReadinessItem(AutomationSchema):
    key: str
    label: str
    state: str
    detail: str
    action_label: Optional[str] = None
    action_path: Optional[str] = None


class RosterSetupReadinessResponse(AutomationSchema):
    ready_count: int
    total_count: int
    can_plan: bool
    active_shift_count: int
    active_pattern_count: int
    active_rule_count: int
    active_approval_authority_count: int
    active_contract_count: int
    employees_without_pattern_count: int
    upcoming_period_count: int
    next_period_id: Optional[str] = None
    next_period_code: Optional[str] = None
    policy: RosterGenerationPolicyRead
    items: list[RosterSetupReadinessItem]
