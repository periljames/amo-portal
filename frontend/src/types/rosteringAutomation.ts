export type RosterAutomationFrequency = "MONTHLY" | "FORTNIGHTLY" | "WEEKLY" | "MANUAL";
export type RosterAutomationRunStatus = "PREVIEWED" | "RUNNING" | "COMPLETED" | "COMPLETED_WITH_CONFLICTS" | "FAILED" | "SKIPPED";

export type RosterGenerationPolicy = {
  id: string;
  amo_id: string;
  enabled: boolean;
  frequency: RosterAutomationFrequency;
  lead_periods: number;
  run_day: number;
  run_hour_local: number;
  timezone_name: string;
  period_code_pattern: string;
  period_name_pattern: string;
  create_initial_draft: boolean;
  generate_from_patterns: boolean;
  preserve_source_commitments: boolean;
  validate_after_generation: boolean;
  notify_planners: boolean;
  require_preview_confirmation: boolean;
  state_revision: number;
  next_run_at?: string | null;
  last_run_at?: string | null;
  updated_reason?: string | null;
  created_at: string;
  updated_at: string;
};

export type RosterGenerationPolicyUpdate = Partial<Pick<RosterGenerationPolicy,
  | "enabled"
  | "frequency"
  | "lead_periods"
  | "run_day"
  | "run_hour_local"
  | "timezone_name"
  | "period_code_pattern"
  | "period_name_pattern"
  | "create_initial_draft"
  | "generate_from_patterns"
  | "preserve_source_commitments"
  | "validate_after_generation"
  | "notify_planners"
  | "require_preview_confirmation"
>> & {
  expected_state_revision: number;
  reason: string;
};

export type RosterAutomationPreviewItem = {
  code: string;
  severity: string;
  message: string;
  user_id?: string | null;
  reference_id?: string | null;
};

export type RosterAutomationPreviewRequest = {
  target_from?: string | null;
  target_to?: string | null;
  user_ids?: string[];
  create_missing_period?: boolean;
  create_initial_draft?: boolean | null;
  generate_from_patterns?: boolean | null;
};

export type RosterAutomationPreview = {
  target_from: string;
  target_to: string;
  period_code: string;
  period_name: string;
  period_exists: boolean;
  period_id?: string | null;
  draft_exists: boolean;
  draft_version_id?: string | null;
  active_pattern_assignment_count: number;
  eligible_employee_count: number;
  employees_without_pattern_count: number;
  estimated_assignment_count: number;
  blocking_issue_count: number;
  warning_count: number;
  items: RosterAutomationPreviewItem[];
  requires_confirmation: boolean;
};

export type RosterGenerationRun = {
  id: string;
  amo_id: string;
  policy_id: string;
  trigger: string;
  status: RosterAutomationRunStatus;
  idempotency_key: string;
  dry_run: boolean;
  period_id?: string | null;
  version_id?: string | null;
  target_from: string;
  target_to: string;
  generated_count: number;
  skipped_count: number;
  conflict_count: number;
  validation_blocker_count: number;
  validation_warning_count: number;
  summary_json?: Record<string, unknown> | null;
  error_message?: string | null;
  requested_by_user_id?: string | null;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
};

export type RosterSetupReadinessItem = {
  key: string;
  label: string;
  state: "READY" | "OPTIONAL" | "NEEDS_ATTENTION" | "BLOCKED" | string;
  detail: string;
  action_label?: string | null;
  action_path?: string | null;
};

export type RosterSetupReadiness = {
  ready_count: number;
  total_count: number;
  can_plan: boolean;
  active_shift_count: number;
  active_pattern_count: number;
  active_rule_count: number;
  active_approval_authority_count: number;
  active_contract_count: number;
  employees_without_pattern_count: number;
  upcoming_period_count: number;
  next_period_id?: string | null;
  next_period_code?: string | null;
  policy: RosterGenerationPolicy;
  items: RosterSetupReadinessItem[];
};
