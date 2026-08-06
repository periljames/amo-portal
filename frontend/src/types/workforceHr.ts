export type HrMetric = { key: string; label: string; value: number | string; detail?: string | null; tone: string };
export type HrActionItem = { id: string; category: string; severity: string; title: string; detail: string; user_id?: string | null; user_name?: string | null; due_on?: string | null; action_label?: string | null; action_path?: string | null };
export type HrContractState = "EFFECTIVE" | "FUTURE" | "MISSING";
export type HrPatternState = "DEFAULT" | "ASSIGNED" | "MISSING";
export type HrReadinessState = "READY" | "NEEDS_ATTENTION" | "BLOCKED";

export type HrPersonReadiness = {
  user_id: string; contract_id?: string | null; staff_code: string; full_name: string; email?: string | null;
  has_effective_contract: boolean; uses_default_day_pattern: boolean; account_role?: string | null;
  position_title?: string | null; department_id?: string | null; department_code?: string | null;
  department_name?: string | null; employment_status?: string | null; contract_type?: string | null;
  contract_state: HrContractState; contract_effective_from?: string | null; contract_effective_to?: string | null;
  primary_base_station_id?: string | null; primary_base_code?: string | null; supervisor_name?: string | null;
  standard_weekly_minutes: number; standard_daily_minutes: number; fte_percentage: number;
  cost_centre?: string | null; payroll_number?: string | null; overtime_eligible: boolean;
  night_shift_eligible: boolean; standby_eligible: boolean; work_pattern_code?: string | null;
  work_pattern_name?: string | null; work_pattern_effective_from?: string | null; pattern_state: HrPatternState;
  active_leave_status?: string | null; group_ids: string[]; group_names: string[];
  readiness_state: HrReadinessState; readiness_reasons: string[];
};

export type HrPeoplePage = { items: HrPersonReadiness[]; page: number; page_size: number; total: number; pages: number };
export type HrPeopleFilters = {
  search?: string | null; department_id?: string | null; role?: string | null; position_title?: string | null;
  contract_type?: string | null; employment_status?: string | null; base_station_id?: string | null;
  group_id?: string | null; readiness_state?: HrReadinessState | null; contract_state?: HrContractState | null;
  pattern_state?: HrPatternState | null; expires_within_days?: number | null;
  sort_by?: "name" | "staff_code" | "department" | "role" | "position_title";
  sort_dir?: "asc" | "desc";
};
export type HrFilterOption = { value: string; label: string; count: number; secondary?: string | null };
export type HrPeopleFacets = {
  departments: HrFilterOption[]; roles: HrFilterOption[]; position_titles: HrFilterOption[];
  contract_types: HrFilterOption[]; employment_statuses: HrFilterOption[]; bases: HrFilterOption[];
  groups: HrFilterOption[]; readiness_states: HrFilterOption[]; contract_states: HrFilterOption[];
  pattern_states: HrFilterOption[];
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
  generated_at: string; can_manage_contracts: boolean; can_initialize_default_day_pattern: boolean;
  can_manage_leave_balances: boolean; can_review_leave: boolean; can_approve_leave: boolean;
  can_approve_timesheet_supervisor: boolean; can_approve_timesheet_hr: boolean;
  can_approve_overtime_supervisor: boolean; can_approve_overtime_hr: boolean; can_export_payroll: boolean;
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
export type HrBulkOperationStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "COMPLETED_WITH_ERRORS" | "FAILED";
export type HrBulkOperation = {
  id: string; operation_type: "CREATE_CONTRACTS" | "ASSIGN_DEFAULT_DAY_PATTERN";
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
