"""API contracts for controlled Workforce bulk changes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import governance_schemas, models


OperationType = Literal[
    "CREATE_CONTRACTS",
    "ASSIGN_DEFAULT_DAY_PATTERN",
    "ASSIGN_WORK_PATTERN",
    "ASSIGN_ORGANIZATION",
    "ASSIGN_POSITION",
    "ASSIGN_BASES",
    "ASSIGN_SUPERVISOR",
    "UPDATE_GROUPS",
    "UPDATE_CONTRACT_SETTINGS",
    "SCHEDULE_OFFBOARDING",
]
OperationStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]
ItemStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "SKIPPED", "FAILED"]


class BulkSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ContractDefaults(BulkSchema):
    contract_type: models.ContractType = models.ContractType.PERMANENT
    employment_status: models.EmploymentStatus = models.EmploymentStatus.ACTIVE
    effective_from: date
    effective_to: date | None = None
    standard_weekly_minutes: int = Field(default=2400, ge=0, le=10080)
    standard_daily_minutes: int = Field(default=480, ge=0, le=1440)
    fte_percentage: float = Field(default=100.0, gt=0, le=100)
    primary_base_station_id: str | None = None
    secondary_base_station_id: str | None = None
    supervisor_user_id: str | None = None
    cost_centre: str | None = Field(default=None, max_length=64)
    overtime_eligible: bool = True
    night_shift_eligible: bool = True
    standby_eligible: bool = True

    @model_validator(mode="after")
    def validate_contract_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if self.contract_type in {
            models.ContractType.FIXED_TERM,
            models.ContractType.TEMPORARY,
            models.ContractType.CONTRACTOR,
            models.ContractType.INTERN,
        } and self.effective_to is None:
            raise ValueError("An end date is required for contingent contracts")
        return self


class ContractOverride(BulkSchema):
    user_id: str
    effective_from: date | None = None
    effective_to: date | None = None
    primary_base_station_id: str | None = None
    secondary_base_station_id: str | None = None
    supervisor_user_id: str | None = None
    payroll_number: str | None = Field(default=None, max_length=64)
    cost_centre: str | None = Field(default=None, max_length=64)
    standard_weekly_minutes: int | None = Field(default=None, ge=0, le=10080)
    standard_daily_minutes: int | None = Field(default=None, ge=0, le=1440)
    fte_percentage: float | None = Field(default=None, gt=0, le=100)
    overtime_eligible: bool | None = None
    night_shift_eligible: bool | None = None
    standby_eligible: bool | None = None


class ContractBatchPreviewRequest(BulkSchema):
    selection: governance_schemas.GovernedPeopleSelection
    defaults: ContractDefaults
    overrides: list[ContractOverride] = Field(default_factory=list, max_length=10000)
    preview_limit: int = Field(default=250, ge=1, le=1000)

    @model_validator(mode="after")
    def unique_overrides(self):
        ids = [row.user_id for row in self.overrides]
        if len(ids) != len(set(ids)):
            raise ValueError("Only one contract override is allowed per user")
        return self


class ContractPreviewRow(BulkSchema):
    user_id: str
    staff_code: str | None = None
    full_name: str
    department_name: str | None = None
    position_title: str | None = None
    primary_base_station_id: str | None = None
    supervisor_user_id: str | None = None
    effective_from: date
    effective_to: date | None = None
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class ContractBatchPreview(BulkSchema):
    selection_token: str
    matched_count: int
    eligible_count: int
    blocked_count: int
    already_contracted_count: int
    rows: list[ContractPreviewRow]
    rows_truncated: bool = False


class ContractBatchSubmitRequest(ContractBatchPreviewRequest):
    expected_match_count: int = Field(ge=1, le=10000)
    expected_selection_token: str = Field(min_length=16, max_length=128)


class DefaultPatternBatchSubmitRequest(BulkSchema):
    selection: governance_schemas.GovernedPeopleSelection
    expected_match_count: int = Field(ge=1, le=10000)
    expected_selection_token: str = Field(min_length=16, max_length=128)


class WorkPatternBatchOptions(BulkSchema):
    work_pattern_id: str = Field(min_length=1, max_length=36)
    effective_from: date
    effective_to: date | None = None
    cycle_anchor_date: date | None = None
    conflict_strategy: Literal["REPLACE_OVERLAPS", "SKIP_ASSIGNED"] = "REPLACE_OVERLAPS"
    reason: str = Field(default="Batch work-pattern change", min_length=5, max_length=500)

    @model_validator(mode="after")
    def validate_pattern_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if self.cycle_anchor_date is None:
            self.cycle_anchor_date = self.effective_from
        return self


class WorkPatternBatchPreviewRequest(BulkSchema):
    selection: governance_schemas.GovernedPeopleSelection
    options: WorkPatternBatchOptions
    preview_limit: int = Field(default=250, ge=1, le=1000)


class WorkPatternPreviewRow(BulkSchema):
    user_id: str
    staff_code: str | None = None
    full_name: str
    department_name: str | None = None
    current_pattern_code: str | None = None
    current_pattern_name: str | None = None
    target_pattern_code: str
    target_pattern_name: str
    action: Literal["ASSIGN", "REPLACE", "UNCHANGED", "SKIP", "BLOCKED"]
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class WorkPatternBatchPreview(BulkSchema):
    selection_token: str
    matched_count: int
    eligible_count: int
    blocked_count: int
    assign_count: int
    replace_count: int
    unchanged_count: int
    skipped_count: int
    target_pattern_id: str
    target_pattern_code: str
    target_pattern_name: str
    rows: list[WorkPatternPreviewRow]
    rows_truncated: bool = False


class WorkPatternBatchSubmitRequest(WorkPatternBatchPreviewRequest):
    expected_match_count: int = Field(ge=1, le=10000)
    expected_selection_token: str = Field(min_length=16, max_length=128)


PersonnelMutationRequest = governance_schemas.PersonnelMutationRequest


class BulkOperationRead(BulkSchema):
    id: str
    operation_type: OperationType
    status: OperationStatus
    idempotency_key: str
    selection_token: str
    total_count: int
    processed_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    progress_percent: float
    retry_of_operation_id: str | None = None
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BulkOperationItemRead(BulkSchema):
    id: str
    user_id: str
    staff_code: str | None = None
    full_name: str | None = None
    status: ItemStatus
    attempt_count: int
    outcome_code: str | None = None
    outcome_message: str | None = None
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BulkOperationItemsPage(BulkSchema):
    items: list[BulkOperationItemRead]
    page: int
    page_size: int
    total: int
    pages: int


class BulkOperationsPage(BulkSchema):
    items: list[BulkOperationRead]
    page: int
    page_size: int
    total: int
    pages: int


class BulkOperationRetryRequest(BulkSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
