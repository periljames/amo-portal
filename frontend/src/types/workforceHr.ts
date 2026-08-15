export type HrMetric = { key: string; label: string; value: number | string; detail?: string | null; tone: string };
export type HrActionItem = { id: string; category: string; severity: string; title: string; detail: string; user_id?: string | null; user_name?: string | null; due_on?: string | null; action_label?: string | null; action_path?: string | null };
export type HrContractState = "EFFECTIVE" | "FUTURE" | "MISSING";
export type HrPatternState = "DEFAULT" | "ASSIGNED" | "MISSING";
export type HrReadinessState = "READY" | "NEEDS_ATTENTION" | "BLOCKED";
export type HrLifecycleState = "ACTIVE" | "ONBOARDING" | "SUSPENDED" | "OFFBOARDING_SCHEDULED" | "INACTIVE";
export type HrPlacementType = "PRIMARY" | "SECONDARY" | "MATRIX";

export type HrPlacement = {
  id: string; user_id: string; org_unit_id: string; org_unit_name: string; org_path_names: string[];
  position_id?: string | null; position_title?: string | null; preferred_title?: string | null;
  job_family_id?: string | null; job_family_name?: string | null; grade_id?: string | null; grade_name?: string | null;
  placement_type: HrPlacementType; base_station_id?: string | null; base_station_name?: string | null;
  supervisor_user_id?: string | null; supervisor_name?: string | null; effective_from: string; effective_to?: string | null;
};

export type HrPersonReadiness = {
  user_id: string; contract_id?: string | null; staff_code: string; full_name: string; email?: string | null;
  has_effective_contract: boolean; uses_default_day_pattern: boolean; account_role?: string | null;
  position_title?: string | null; department_id?: string | null; department_code?: string | null;
  department_name?: string | null; employment_status?: string | null; contract_type?: string | null;
  contract_state: HrContractState; hire_date?: string | null; contract_effective_from?: string | null; contract_effective_to?: string | null;
  primary_base_station_id?: string | null; primary_base_code?: string | null; supervisor_name?: string | null;
  standard_weekly_minutes: number; standard_daily_minutes: number; fte_percentage: number;
  cost_centre?: string | null; payroll_number?: string | null; overtime_eligible: boolean;
  night_shift_eligible: boolean; standby_eligible: boolean; work_pattern_code?: string | null;
  work_pattern_name?: string | null; work_pattern_effective_from?: string | null; pattern_state: HrPatternState;
  active_leave_status?: string | null; group_ids: string[]; group_names: string[];
  readiness_state: HrReadinessState; readiness_reasons: string[];
  primary_org_unit_id?: string | null; primary_org_unit_name?: string | null; primary_org_path?: string[];
  canonical_position_id?: string | null; canonical_position_title?: string | null; preferred_title?: string | null;
  job_family_id?: string | null; job_family_name?: string | null; grade_id?: string | null; grade_name?: string | null;
  supervisor_user_id?: string | null; can_have_supervisor?: boolean; secondary_org_units?: HrPlacement[]; matrix_org_units?: HrPlacement[];
  secondary_base_station_id?: string | null; secondary_base_code?: string | null;
  lifecycle_state?: HrLifecycleState; offboarding_effective_on?: string | null;
};

export type HrPeoplePage = { items: HrPersonReadiness[]; page: number; page_size: number; total: number; pages: number };
export type HrPeopleFilters = {
  search?: string | null; department_id?: string | null; role?: string | null; position_title?: string | null;
  contract_type?: string | null; employment_status?: string | null; base_station_id?: string | null;
  group_id?: string | null; readiness_state?: HrReadinessState | null; contract_state?: HrContractState | null;
  pattern_state?: HrPatternState | null; expires_within_days?: number | null;
  org_unit_id?: string | null; include_descendants?: boolean; placement_type?: HrPlacementType | null;
  position_id?: string | null; job_family_id?: string | null; grade_id?: string | null;
  supervisor_user_id?: string | null; secondary_base_station_id?: string | null;
  contract_effective_from_on_or_after?: string | null; contract_effective_from_on_or_before?: string | null;
  contract_effective_to_on_or_after?: string | null; contract_effective_to_on_or_before?: string | null;
  lifecycle_state?: HrLifecycleState | null;
  sort_by?: "name" | "staff_code" | "department" | "role" | "position_title" | "org_unit" | "position" |
    "job_family" | "grade" | "supervisor" | "contract_start" | "contract_end" | "primary_base" |
    "secondary_base" | "employment_status";
  sort_dir?: "asc" | "desc";
};
export type HrFilterOption = { value: string; label: string; count: number; secondary?: string | null };
export type HrPeopleFacets = {
  departments: HrFilterOption[]; roles: HrFilterOption[]; position_titles: HrFilterOption[];
  contract_types: HrFilterOption[]; employment_statuses: HrFilterOption[]; bases: HrFilterOption[];
  groups: HrFilterOption[]; readiness_states: HrFilterOption[]; contract_states: HrFilterOption[];
  pattern_states: HrFilterOption[]; org_units?: HrFilterOption[]; positions?: HrFilterOption[];
  job_families?: HrFilterOption[]; grades?: HrFilterOption[]; supervisors?: HrFilterOption[];
  secondary_bases?: HrFilterOption[]; placement_types?: HrFilterOption[]; lifecycle_states?: HrFilterOption[];
};
export type HrPeopleSelection =
  | { mode: "EXPLICIT"; user_ids: string[]; exclude_user_ids?: string[]; filters?: HrPeopleFilters }
  | { mode: "FILTERED"; user_ids?: string[]; exclude_user_ids: string[]; filters: HrPeopleFilters };

export type HrDefaultDayBatchPreview = {
  matched_count: number; eligible_count: number; assignable_count: number; already_assigned_count: number;
  ineligible_count: number; selection_token: string; capped: boolean;
};
export type HrDefaultDayBatchResult = {
  shift_template_id: string; work_pattern_id: string; matched_count: number; eligible_count: number;
  assigned_count: number; already_assigned_count: number; ineligible_count: number; skipped_conflict_count: number;
};
export type HrOvertimeRequest = {
  id: string; amo_id: string; user_id: string; user_full_name?: string | null; roster_assignment_id?: string | null;
  starts_at: string; ends_at: string; requested_minutes: number; reason: string;
  status: "DRAFT" | "SUBMITTED" | "SUPERVISOR_APPROVED" | "HR_APPROVED" | "REJECTED" | "CANCELLED";
  created_by_user_id?: string | null; created_at: string; updated_at: string;
};
export type HrAttendanceException = {
  id: string; amo_id: string; roster_assignment_id: string; user_id: string; user_full_name?: string | null;
  planned_minutes: number; attendance_minutes: number; productive_minutes: number; variance_minutes: number;
  classification: string; metadata_json?: Record<string, unknown> | null; calculated_at: string;
};
export type HrDashboard = {
  generated_at: string; can_manage_contracts: boolean; can_manage_patterns: boolean; can_assign_patterns: boolean; can_initialize_default_day_pattern: boolean;
  can_manage_leave_balances: boolean; can_review_leave: boolean; can_approve_leave: boolean;
  can_approve_timesheet_supervisor: boolean; can_approve_timesheet_hr: boolean;
  can_approve_overtime_supervisor: boolean; can_approve_overtime_hr: boolean; can_manage_attendance: boolean; can_export_payroll: boolean;
  active_employee_count: number; employees_without_contract_count: number; onboarding_employee_count: number;
  suspended_employee_count: number; contracts_expiring_soon_count: number; employees_without_pattern_count: number;
  employees_without_base_count: number; pending_leave_count: number; pending_timesheet_count: number;
  pending_overtime_count: number; attendance_exception_count: number; metrics: HrMetric[]; action_queue: HrActionItem[];
  pending_overtime: HrOvertimeRequest[]; attendance_exceptions: HrAttendanceException[]; people: HrPersonReadiness[];
};
export type HrDefaultDayBootstrap = {
  shift_template_id: string; work_pattern_id: string; eligible_user_count: number; assigned_user_count: number;
  already_assigned_count: number; skipped_conflict_count: number;
};

export type HrContractDefaults = {
  contract_type: string; employment_status: string; effective_from: string; effective_to?: string | null;
  standard_weekly_minutes: number; standard_daily_minutes: number; fte_percentage: number;
  primary_base_station_id?: string | null; secondary_base_station_id?: string | null;
  supervisor_user_id?: string | null; cost_centre?: string | null; overtime_eligible: boolean;
  night_shift_eligible: boolean; standby_eligible: boolean;
};
export type HrContractOverride = {
  user_id: string; effective_from?: string | null; effective_to?: string | null;
  primary_base_station_id?: string | null; secondary_base_station_id?: string | null;
  supervisor_user_id?: string | null; payroll_number?: string | null; cost_centre?: string | null;
  standard_weekly_minutes?: number | null; standard_daily_minutes?: number | null;
  fte_percentage?: number | null; overtime_eligible?: boolean | null;
  night_shift_eligible?: boolean | null; standby_eligible?: boolean | null;
};
export type HrContractPreviewRow = {
  user_id: string; staff_code?: string | null; full_name: string; department_name?: string | null;
  position_title?: string | null; primary_base_station_id?: string | null; supervisor_user_id?: string | null;
  effective_from: string; effective_to?: string | null; eligible: boolean; reasons: string[];
};
export type HrContractBatchPreview = {
  selection_token: string; matched_count: number; eligible_count: number; blocked_count: number;
  already_contracted_count: number; rows: HrContractPreviewRow[]; rows_truncated: boolean;
};

export type HrWorkPatternBatchOptions = {
  work_pattern_id: string; effective_from: string; effective_to?: string | null;
  cycle_anchor_date?: string | null; conflict_strategy: "REPLACE_OVERLAPS" | "SKIP_ASSIGNED"; reason: string;
};
export type HrWorkPatternPreviewRow = {
  user_id: string; staff_code?: string | null; full_name: string; department_name?: string | null;
  current_pattern_code?: string | null; current_pattern_name?: string | null;
  target_pattern_code: string; target_pattern_name: string;
  action: "ASSIGN" | "REPLACE" | "UNCHANGED" | "SKIP" | "BLOCKED"; eligible: boolean; reasons: string[];
};
export type HrWorkPatternBatchPreview = {
  selection_token: string; matched_count: number; eligible_count: number; blocked_count: number;
  assign_count: number; replace_count: number; unchanged_count: number; skipped_count: number;
  target_pattern_id: string; target_pattern_code: string; target_pattern_name: string;
  rows: HrWorkPatternPreviewRow[]; rows_truncated: boolean;
};

export type HrBulkOperationType = "CREATE_CONTRACTS" | "ASSIGN_DEFAULT_DAY_PATTERN" | "ASSIGN_WORK_PATTERN" | "ASSIGN_ORGANIZATION" |
  "ASSIGN_POSITION" | "ASSIGN_BASES" | "ASSIGN_SUPERVISOR" | "UPDATE_GROUPS" |
  "UPDATE_CONTRACT_SETTINGS" | "SCHEDULE_OFFBOARDING";
export type HrBulkOperationStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "COMPLETED_WITH_ERRORS" | "FAILED";
export type HrBulkOperation = {
  id: string; operation_type: HrBulkOperationType;
  status: HrBulkOperationStatus; idempotency_key: string; selection_token: string; total_count: number;
  processed_count: number; succeeded_count: number; skipped_count: number; failed_count: number;
  progress_percent: number; retry_of_operation_id?: string | null; last_error?: string | null;
  started_at?: string | null; completed_at?: string | null; heartbeat_at?: string | null;
  created_at: string; updated_at: string;
};
export type HrBulkOperationItem = {
  id: string; user_id: string; staff_code?: string | null; full_name?: string | null;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "SKIPPED" | "FAILED"; attempt_count: number;
  outcome_code?: string | null; outcome_message?: string | null; result?: Record<string, unknown> | null;
  started_at?: string | null; completed_at?: string | null;
};
export type HrBulkOperationItemsPage = { items: HrBulkOperationItem[]; page: number; page_size: number; total: number; pages: number };
export type HrBulkOperationsPage = { items: HrBulkOperation[]; page: number; page_size: number; total: number; pages: number };

export type HrOrgUnit = { id: string; parent_id?: string | null; legacy_department_id?: string | null; code: string; name: string; unit_type: string; description?: string | null; is_active: boolean; sort_order: number; depth: number; path_ids: string[]; path_names: string[] };
export type HrOrgUnitWrite = Omit<HrOrgUnit, "id" | "depth" | "path_ids" | "path_names">;
export type HrJobFamily = { id: string; code: string; name: string; description?: string | null; is_active: boolean };
export type HrJobFamilyWrite = Omit<HrJobFamily, "id">;
export type HrGrade = { id: string; code: string; name: string; rank_order: number; description?: string | null; is_active: boolean };
export type HrGradeWrite = Omit<HrGrade, "id">;
export type HrManagementLevel = "STAFF" | "SUPERVISOR" | "MANAGER" | "EXECUTIVE";
export type HrTenantFunction = "HUMAN_RESOURCES" | "INFORMATION_TECHNOLOGY" | "FINANCE";
export type HrPosition = {
  id: string; code: string; canonical_title: string; job_family_id?: string | null; job_family_name?: string | null;
  grade_id?: string | null; grade_name?: string | null; description?: string | null;
  role_source: "TENANT" | "KCAR_2025"; role_key?: string | null; management_level: HrManagementLevel;
  can_have_supervisor: boolean; is_locked: boolean; is_supervisory: boolean; is_active: boolean;
};
export type HrPositionWrite = {
  code: string; canonical_title: string; job_family_id?: string | null; grade_id?: string | null;
  description?: string | null; management_level: HrManagementLevel; tenant_function?: HrTenantFunction | null;
  is_supervisory: boolean; is_active: boolean;
};
export type HrHierarchyRoleStatus = {
  key: string; code: string; title: string; management_level: "MANAGER" | "EXECUTIVE";
  description: string; status: "READY" | "MATCH_AVAILABLE" | "MISSING";
  position_id?: string | null; can_have_supervisor: false;
};
export type HrTenantFunctionStatus = {
  key: HrTenantFunction; label: string; suggested_code: string; suggested_title: string;
  status: "READY" | "PENDING_TENANT_SETUP"; position_id?: string | null;
};
export type HrHierarchyBlueprint = {
  source_title: string; source_reference: string; source_url: string;
  regulatory_roles: HrHierarchyRoleStatus[]; tenant_functions: HrTenantFunctionStatus[];
  required_role_count: number; ready_role_count: number; missing_role_count: number;
  created_count: number; adopted_count: number; updated_count: number; supervisor_links_cleared: number; accounts_synced: number;
};
export type HrSupervisorOption = { user_id: string; staff_code: string; full_name: string; position_title?: string | null; org_unit_name?: string | null; is_supervisory_position: boolean };
export type HrSupervisorOptionsPage = { items: HrSupervisorOption[]; page: number; page_size: number; total: number; pages: number };

export type HrPersonnelMutationType = Exclude<HrBulkOperationType, "CREATE_CONTRACTS" | "ASSIGN_DEFAULT_DAY_PATTERN" | "ASSIGN_WORK_PATTERN">;
export type HrContractSettingsMutation = {
  contract_type?: string | null; employment_status?: string | null; effective_to?: string | null;
  standard_weekly_minutes?: number | null; standard_daily_minutes?: number | null; fte_percentage?: number | null;
  cost_centre?: string | null; overtime_eligible?: boolean | null; night_shift_eligible?: boolean | null;
  standby_eligible?: boolean | null;
};
export type HrPersonnelMutationPayload = {
  selection: HrPeopleSelection; expected_match_count: number; expected_selection_token: string;
  mutation_type: HrPersonnelMutationType; effective_on: string; org_unit_id?: string | null;
  placement_type?: HrPlacementType | null; position_id?: string | null; preferred_title?: string | null;
  primary_base_station_id?: string | null; secondary_base_station_id?: string | null;
  supervisor_user_id?: string | null; group_ids?: string[]; group_mode?: "ADD" | "REMOVE" | "REPLACE" | null;
  contract_settings?: HrContractSettingsMutation | null; offboarding_reason?: string | null;
  revoke_access?: boolean; end_contracts?: boolean; remove_groups?: boolean;
};
