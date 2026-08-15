"""API contracts for governed Workforce structure and personnel mutations."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import hr_schemas


class GovernanceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class GovernedPeopleFilterInput(hr_schemas.HrPeopleFilterInput):
    org_unit_id: str | None = None
    include_descendants: bool = True
    placement_type: Literal["PRIMARY", "SECONDARY", "MATRIX"] | None = None
    position_id: str | None = None
    job_family_id: str | None = None
    grade_id: str | None = None
    supervisor_user_id: str | None = None
    secondary_base_station_id: str | None = None
    contract_effective_from_on_or_after: date | None = None
    contract_effective_from_on_or_before: date | None = None
    contract_effective_to_on_or_after: date | None = None
    contract_effective_to_on_or_before: date | None = None
    lifecycle_state: Literal[
        "ACTIVE",
        "ONBOARDING",
        "SUSPENDED",
        "OFFBOARDING_SCHEDULED",
        "INACTIVE",
    ] | None = None
    sort_by: Literal[
        "name",
        "staff_code",
        "department",
        "role",
        "position_title",
        "org_unit",
        "position",
        "job_family",
        "grade",
        "supervisor",
        "contract_start",
        "contract_end",
        "primary_base",
        "secondary_base",
        "employment_status",
    ] = "name"

    @model_validator(mode="after")
    def validate_contract_ranges(self):
        if (
            self.contract_effective_from_on_or_after
            and self.contract_effective_from_on_or_before
            and self.contract_effective_from_on_or_after
            > self.contract_effective_from_on_or_before
        ):
            raise ValueError("Contract start-date range is reversed")
        if (
            self.contract_effective_to_on_or_after
            and self.contract_effective_to_on_or_before
            and self.contract_effective_to_on_or_after
            > self.contract_effective_to_on_or_before
        ):
            raise ValueError("Contract end-date range is reversed")
        return self


class GovernedPeopleSelection(GovernanceSchema):
    mode: Literal["EXPLICIT", "FILTERED"]
    user_ids: list[str] = Field(default_factory=list, max_length=10000)
    exclude_user_ids: list[str] = Field(default_factory=list, max_length=10000)
    filters: GovernedPeopleFilterInput = Field(default_factory=GovernedPeopleFilterInput)

    @model_validator(mode="after")
    def validate_selection(self):
        if self.mode == "EXPLICIT" and not self.user_ids:
            raise ValueError("At least one user must be selected")
        if self.mode == "FILTERED" and self.user_ids:
            raise ValueError("Filtered selections must not include explicit user IDs")
        return self


class OrgUnitRead(GovernanceSchema):
    id: str
    parent_id: str | None = None
    legacy_department_id: str | None = None
    code: str
    name: str
    unit_type: str
    description: str | None = None
    is_active: bool
    sort_order: int
    depth: int = 0
    path_ids: list[str] = Field(default_factory=list)
    path_names: list[str] = Field(default_factory=list)


class OrgUnitWrite(GovernanceSchema):
    parent_id: str | None = None
    legacy_department_id: str | None = None
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_type: Literal["DEPARTMENT", "SECTION", "TEAM", "MATRIX", "OTHER"] = "TEAM"
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=100000)


class JobFamilyRead(GovernanceSchema):
    id: str
    code: str
    name: str
    description: str | None = None
    is_active: bool


class JobFamilyWrite(GovernanceSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class GradeRead(GovernanceSchema):
    id: str
    code: str
    name: str
    rank_order: int
    description: str | None = None
    is_active: bool


class GradeWrite(GovernanceSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    rank_order: int = Field(default=100, ge=0, le=100000)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class PositionRead(GovernanceSchema):
    id: str
    code: str
    canonical_title: str
    job_family_id: str | None = None
    job_family_name: str | None = None
    grade_id: str | None = None
    grade_name: str | None = None
    description: str | None = None
    role_source: Literal["TENANT", "KCAR_2025"] = "TENANT"
    role_key: str | None = None
    management_level: Literal["STAFF", "SUPERVISOR", "MANAGER", "EXECUTIVE"] = "STAFF"
    can_have_supervisor: bool = True
    is_locked: bool = False
    is_supervisory: bool
    is_active: bool


class PositionWrite(GovernanceSchema):
    code: str = Field(min_length=1, max_length=64)
    canonical_title: str = Field(min_length=1, max_length=255)
    job_family_id: str | None = None
    grade_id: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    management_level: Literal["STAFF", "SUPERVISOR", "MANAGER", "EXECUTIVE"] = "STAFF"
    tenant_function: Literal["HUMAN_RESOURCES", "INFORMATION_TECHNOLOGY", "FINANCE"] | None = None
    is_supervisory: bool = False
    is_active: bool = True


class HierarchyRoleStatus(GovernanceSchema):
    key: str
    code: str
    title: str
    management_level: Literal["MANAGER", "EXECUTIVE"]
    description: str
    status: Literal["READY", "MATCH_AVAILABLE", "MISSING"]
    position_id: str | None = None
    can_have_supervisor: bool = False


class TenantFunctionStatus(GovernanceSchema):
    key: Literal["HUMAN_RESOURCES", "INFORMATION_TECHNOLOGY", "FINANCE"]
    label: str
    suggested_code: str
    suggested_title: str
    status: Literal["READY", "PENDING_TENANT_SETUP"]
    position_id: str | None = None


class HierarchyBlueprintRead(GovernanceSchema):
    source_title: str
    source_reference: str
    source_url: str
    regulatory_roles: list[HierarchyRoleStatus] = Field(default_factory=list)
    tenant_functions: list[TenantFunctionStatus] = Field(default_factory=list)
    required_role_count: int = 0
    ready_role_count: int = 0
    missing_role_count: int = 0
    created_count: int = 0
    adopted_count: int = 0
    updated_count: int = 0
    supervisor_links_cleared: int = 0
    accounts_synced: int = 0


class PlacementRead(GovernanceSchema):
    id: str
    user_id: str
    org_unit_id: str
    org_unit_name: str
    org_path_names: list[str] = Field(default_factory=list)
    position_id: str | None = None
    position_title: str | None = None
    preferred_title: str | None = None
    job_family_id: str | None = None
    job_family_name: str | None = None
    grade_id: str | None = None
    grade_name: str | None = None
    placement_type: str
    base_station_id: str | None = None
    base_station_name: str | None = None
    supervisor_user_id: str | None = None
    supervisor_name: str | None = None
    effective_from: date
    effective_to: date | None = None


class GovernedPersonReadiness(hr_schemas.HrPersonReadiness):
    primary_org_unit_id: str | None = None
    primary_org_unit_name: str | None = None
    primary_org_path: list[str] = Field(default_factory=list)
    canonical_position_id: str | None = None
    canonical_position_title: str | None = None
    preferred_title: str | None = None
    job_family_id: str | None = None
    job_family_name: str | None = None
    grade_id: str | None = None
    grade_name: str | None = None
    supervisor_user_id: str | None = None
    can_have_supervisor: bool = True
    secondary_org_units: list[PlacementRead] = Field(default_factory=list)
    matrix_org_units: list[PlacementRead] = Field(default_factory=list)
    secondary_base_station_id: str | None = None
    secondary_base_code: str | None = None
    lifecycle_state: str = "ACTIVE"
    offboarding_effective_on: date | None = None


class GovernedPeoplePage(GovernanceSchema):
    items: list[GovernedPersonReadiness]
    page: int
    page_size: int
    total: int
    pages: int


class GovernedPeopleFacets(hr_schemas.HrPeopleFacets):
    org_units: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    positions: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    job_families: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    grades: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    supervisors: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    secondary_bases: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    placement_types: list[hr_schemas.HrFilterOption] = Field(default_factory=list)
    lifecycle_states: list[hr_schemas.HrFilterOption] = Field(default_factory=list)


class SupervisorOption(GovernanceSchema):
    user_id: str
    staff_code: str
    full_name: str
    position_title: str | None = None
    org_unit_name: str | None = None
    is_supervisory_position: bool = False


class SupervisorOptionsPage(GovernanceSchema):
    items: list[SupervisorOption]
    page: int
    page_size: int
    total: int
    pages: int


MutationType = Literal[
    "ASSIGN_ORGANIZATION",
    "ASSIGN_POSITION",
    "ASSIGN_BASES",
    "ASSIGN_SUPERVISOR",
    "UPDATE_GROUPS",
    "UPDATE_CONTRACT_SETTINGS",
    "SCHEDULE_OFFBOARDING",
]


class ContractSettingsMutation(GovernanceSchema):
    contract_type: str | None = None
    employment_status: str | None = None
    effective_to: date | None = None
    standard_weekly_minutes: int | None = Field(default=None, ge=0, le=10080)
    standard_daily_minutes: int | None = Field(default=None, ge=0, le=1440)
    fte_percentage: float | None = Field(default=None, gt=0, le=100)
    cost_centre: str | None = Field(default=None, max_length=64)
    overtime_eligible: bool | None = None
    night_shift_eligible: bool | None = None
    standby_eligible: bool | None = None


class PersonnelMutationRequest(GovernanceSchema):
    selection: GovernedPeopleSelection
    expected_match_count: int = Field(ge=1, le=10000)
    expected_selection_token: str = Field(min_length=16, max_length=128)
    mutation_type: MutationType
    effective_on: date
    org_unit_id: str | None = None
    placement_type: Literal["PRIMARY", "SECONDARY", "MATRIX"] | None = None
    position_id: str | None = None
    preferred_title: str | None = Field(default=None, max_length=255)
    primary_base_station_id: str | None = None
    secondary_base_station_id: str | None = None
    supervisor_user_id: str | None = None
    group_ids: list[str] = Field(default_factory=list, max_length=500)
    group_mode: Literal["ADD", "REMOVE", "REPLACE"] | None = None
    contract_settings: ContractSettingsMutation | None = None
    offboarding_reason: str | None = Field(default=None, max_length=2000)
    revoke_access: bool = True
    end_contracts: bool = True
    remove_groups: bool = True

    @model_validator(mode="after")
    def validate_mutation(self):
        if self.mutation_type == "ASSIGN_ORGANIZATION" and not self.org_unit_id:
            raise ValueError("org_unit_id is required")
        if self.mutation_type == "ASSIGN_POSITION" and not self.position_id:
            raise ValueError("position_id is required")
        if self.mutation_type == "ASSIGN_BASES" and not self.primary_base_station_id:
            raise ValueError("primary_base_station_id is required")
        if self.mutation_type == "ASSIGN_SUPERVISOR" and not self.supervisor_user_id:
            raise ValueError("supervisor_user_id is required")
        if self.mutation_type == "UPDATE_GROUPS" and (not self.group_mode or not self.group_ids):
            raise ValueError("group_mode and at least one group_id are required")
        if self.mutation_type == "UPDATE_CONTRACT_SETTINGS" and self.contract_settings is None:
            raise ValueError("contract_settings is required")
        if self.mutation_type == "SCHEDULE_OFFBOARDING" and not (self.offboarding_reason or "").strip():
            raise ValueError("offboarding_reason is required")
        return self


class OffboardingPlanRead(GovernanceSchema):
    id: str
    user_id: str
    effective_on: date
    reason: str
    status: str
    revoke_access: bool
    end_contracts: bool
    remove_groups: bool
    completed_at: datetime | None = None
