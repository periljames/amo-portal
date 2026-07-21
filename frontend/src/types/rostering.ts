export type ShiftTemplateKind = "DAY" | "NIGHT" | "STANDBY" | "TRAINING" | "OFF" | "LEAVE" | "OTHER";
export type RosterPeriodStatus = "DRAFT" | "OPEN" | "LOCKED" | "ARCHIVED";
export type RosterVersionStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "PUBLISHED" | "SUPERSEDED" | "ARCHIVED";
export type RosterAssignmentStatus = "DUTY" | "STANDBY" | "TRAINING" | "OFF" | "LEAVE" | "TRAVEL" | "UNAVAILABLE" | "OTHER";
export type RosterAssignmentSource = "MANUAL" | "PATTERN" | "IMPORT" | "LEAVE" | "TRAINING" | "SYSTEM";
export type RosterValidationSeverity = "INFO" | "WARNING" | "BLOCKER";
export type RosterValidationSource = "ROSTER" | "IDENTITY" | "CONTRACT" | "BASE" | "AVAILABILITY" | "TRAINING" | "AUTHORISATION" | "WORKLOAD" | "ATTENDANCE" | "RULE";
export type RosterRuleType = "MIN_REST_HOURS" | "MAX_DUTY_HOURS_DAY" | "MAX_DUTY_HOURS_ROLLING" | "MAX_CONSECUTIVE_DAYS" | "REQUIRED_DAYS_OFF" | "MIN_COVERAGE" | "REQUIRED_CERTIFYING_COVERAGE" | "REQUIRED_AUTHORISATION" | "TRAINING_VALIDITY" | "LICENCE_VALIDITY" | "CONTRACT_ELIGIBILITY" | "AVAILABILITY_CONFLICT" | "OVERLAP" | "CUSTOM";
export type RosterRuleScope = "AMO" | "DEPARTMENT" | "BASE" | "SHIFT_TEMPLATE" | "USER";
export type RosterExceptionDecision = "ACCEPT_WARNING" | "OVERRIDE_BLOCKER" | "REVOKE";
export type RosterAmendmentType = "CORRECTION" | "LEAVE" | "SICKNESS" | "TRAINING" | "OPERATIONAL" | "COVERAGE" | "OTHER";

export type ShiftTemplateRead = {
  id: string;
  amo_id: string;
  code: string;
  label: string;
  kind: ShiftTemplateKind;
  default_start_time?: string | null;
  default_end_time?: string | null;
  duration_minutes?: number | null;
  counts_as_duty: boolean;
  is_active: boolean;
  display_order: number;
  description?: string | null;
  color_token?: string | null;
  icon_name?: string | null;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ShiftTemplateCreate = Omit<ShiftTemplateRead, "id" | "amo_id" | "created_by_user_id" | "updated_by_user_id" | "created_at" | "updated_at">;

export type RosterValidationFindingRead = {
  id: string;
  amo_id: string;
  version_id: string;
  assignment_id?: string | null;
  user_id?: string | null;
  rule_id?: string | null;
  source: RosterValidationSource;
  severity: RosterValidationSeverity;
  code: string;
  message: string;
  details_json?: Record<string, unknown> | null;
  overridable: boolean;
  resolved: boolean;
  overridden_at?: string | null;
  overridden_by_user_id?: string | null;
  override_reason?: string | null;
  sort_order: number;
  created_at: string;
};

export type RosterVersionRead = {
  id: string;
  amo_id: string;
  period_id: string;
  source_version_id?: string | null;
  version_no: number;
  status: RosterVersionStatus;
  title?: string | null;
  change_summary?: string | null;
  amendment_type?: RosterAmendmentType | null;
  amendment_reason?: string | null;
  effective_from?: string | null;
  idempotency_key?: string | null;
  state_revision: number;
  last_validated_at?: string | null;
  validation_fingerprint?: string | null;
  created_by_user_id?: string | null;
  submitted_by_user_id?: string | null;
  approved_by_user_id?: string | null;
  published_by_user_id?: string | null;
  submitted_at?: string | null;
  approved_at?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
  assignments_count: number;
  blocker_count: number;
  warning_count: number;
  overridden_count: number;
  acknowledgement_count: number;
  can_edit: boolean;
  can_submit: boolean;
  can_approve: boolean;
  can_publish: boolean;
};

export type RosterPeriodRead = {
  id: string;
  amo_id: string;
  period_code: string;
  name: string;
  starts_on: string;
  ends_on: string;
  status: RosterPeriodStatus;
  notes?: string | null;
  timezone_name: string;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  versions: RosterVersionRead[];
};

export type RosterPeriodCreate = {
  period_code: string;
  name: string;
  starts_on: string;
  ends_on: string;
  notes?: string | null;
  timezone_name?: string | null;
};

export type RosterVersionCreate = {
  title?: string | null;
  change_summary?: string | null;
  copy_from_version_id?: string | null;
  source_version_id?: string | null;
  amendment_type?: RosterAmendmentType | null;
  amendment_reason?: string | null;
  effective_from?: string | null;
  idempotency_key?: string | null;
};

export type RosterAssignmentRead = {
  id: string;
  amo_id: string;
  version_id: string;
  user_id: string;
  department_id?: string | null;
  base_station_id?: string | null;
  shift_template_id?: string | null;
  status: RosterAssignmentStatus;
  source: RosterAssignmentSource;
  source_reference_id?: string | null;
  starts_at: string;
  ends_at: string;
  planned_minutes?: number | null;
  role_label?: string | null;
  team_code?: string | null;
  location_label?: string | null;
  task_note?: string | null;
  change_reason?: string | null;
  locked_after_publish: boolean;
  state_revision: number;
  deleted_at?: string | null;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  user_full_name?: string | null;
  user_staff_code?: string | null;
  user_role?: string | null;
  department_code?: string | null;
  department_name?: string | null;
  base_code?: string | null;
  base_name?: string | null;
  shift_code?: string | null;
  shift_label?: string | null;
  shift_kind?: string | null;
  linked_task_count: number;
  linked_task_hours: number;
  contract_status?: string | null;
  availability_state?: string | null;
  training_state?: string | null;
  authorisation_state?: string | null;
};

export type RosterAssignmentCreate = {
  user_id: string;
  starts_at: string;
  ends_at: string;
  department_id?: string | null;
  base_station_id?: string | null;
  shift_template_id?: string | null;
  status?: RosterAssignmentStatus;
  source?: RosterAssignmentSource;
  source_reference_id?: string | null;
  planned_minutes?: number | null;
  role_label?: string | null;
  team_code?: string | null;
  location_label?: string | null;
  task_note?: string | null;
  change_reason?: string | null;
};

export type RosterAssignmentUpdate = Partial<Omit<RosterAssignmentCreate, "user_id" | "source" | "source_reference_id">> & {
  expected_state_revision?: number | null;
};

export type RosterValidationResult = {
  version_id: string;
  validation_fingerprint?: string | null;
  blocker_count: number;
  warning_count: number;
  info_count: number;
  overridden_count: number;
  can_submit: boolean;
  can_publish: boolean;
  findings: RosterValidationFindingRead[];
};

export type RosterRuleRead = {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  description?: string | null;
  rule_type: RosterRuleType;
  scope: RosterRuleScope;
  severity: RosterValidationSeverity;
  parameters_json: Record<string, unknown>;
  department_id?: string | null;
  base_station_id?: string | null;
  shift_template_id?: string | null;
  user_id?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  allow_override: boolean;
  is_active: boolean;
  display_order: number;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type RosterRuleCreate = Omit<RosterRuleRead, "id" | "amo_id" | "created_by_user_id" | "updated_by_user_id" | "created_at" | "updated_at">;

export type RosterRuleExceptionRead = {
  id: string;
  amo_id: string;
  version_id: string;
  finding_id?: string | null;
  rule_id?: string | null;
  assignment_id?: string | null;
  user_id?: string | null;
  decision: RosterExceptionDecision;
  reason: string;
  approved_by_user_id: string;
  expires_at?: string | null;
  created_at: string;
};

export type RosterBulkAssignmentResult = {
  version_id: string;
  created: RosterAssignmentRead[];
  skipped: Array<Record<string, unknown>>;
  conflicts: Array<Record<string, unknown>>;
  idempotent_replay: boolean;
};

export type MyRosterResponse = {
  user_id: string;
  from_date: string;
  to_date: string;
  assignments: RosterAssignmentRead[];
  training_due_next_month: Array<Record<string, unknown>>;
  leave_requests: Array<Record<string, unknown>>;
  acknowledgement_required_version_ids: string[];
};

export type RosterTaskAssignmentLinkRead = {
  id: string;
  amo_id: string;
  roster_assignment_id: string;
  task_assignment_id: number;
  task_id: number;
  user_id: string;
  role_on_task: string;
  task_assignment_status: string;
  allocated_start?: string | null;
  allocated_end?: string | null;
  allocated_hours?: number | null;
  task_title?: string | null;
  task_code?: string | null;
  work_order_id?: number | null;
  wo_number?: string | null;
  aircraft_serial_number?: string | null;
  aircraft_registration?: string | null;
  base_station_id?: string | null;
  base_code?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
};

export type WorkloadTaskSummary = {
  task_id: number;
  work_order_id: number;
  wo_number: string;
  aircraft_serial_number: string;
  aircraft_registration?: string | null;
  aircraft_model?: string | null;
  base_station_id?: string | null;
  base_code?: string | null;
  base_name?: string | null;
  task_code?: string | null;
  title: string;
  priority: string;
  status: string;
  planned_start?: string | null;
  planned_end?: string | null;
  estimated_manhours?: number | null;
  task_assigned_hours: number;
  roster_linked_hours: number;
  remaining_manhours: number;
  task_assignment_count: number;
  roster_link_count: number;
  has_estimate: boolean;
  is_unplanned: boolean;
  can_allocate: boolean;
};

export type WorkloadWorkOrderSummary = {
  work_order_id: number;
  wo_number: string;
  description?: string | null;
  check_type?: string | null;
  status: string;
  due_date?: string | null;
  aircraft_serial_number: string;
  aircraft_registration?: string | null;
  aircraft_model?: string | null;
  base_station_id?: string | null;
  base_code?: string | null;
  base_name?: string | null;
  open_task_count: number;
  estimated_manhours: number;
  task_assigned_hours: number;
  roster_linked_hours: number;
  remaining_manhours: number;
};

export type RosterDemandRequirementRead = {
  id: string;
  amo_id: string;
  base_station_id?: string | null;
  department_id?: string | null;
  starts_at: string;
  ends_at: string;
  requirement_code: string;
  label: string;
  required_headcount: number;
  required_minutes: number;
  role_label?: string | null;
  authorisation_type_id?: string | null;
  source_type: string;
  source_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  is_active: boolean;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type BaseCapacitySummary = {
  base_station_id?: string | null;
  base_code: string;
  base_name: string;
  assigned_people: number;
  certifying_people: number;
  technician_people: number;
  duty_assignment_count: number;
  available_hours: number;
  standby_hours: number;
  roster_linked_hours: number;
  remaining_capacity_hours: number;
  required_task_hours: number;
  task_assigned_hours: number;
  remaining_task_hours: number;
  capacity_gap_hours: number;
  capacity_variance_hours: number;
  open_task_count: number;
  unallocated_task_count: number;
  missing_estimate_count: number;
  required_headcount: number;
  headcount_gap: number;
};

export type PlanningBoardMetrics = {
  assigned_people: number;
  roster_assignment_count: number;
  productive_assignment_count: number;
  available_duty_hours: number;
  standby_hours: number;
  roster_linked_hours: number;
  remaining_capacity_hours: number;
  required_task_hours: number;
  task_assigned_hours: number;
  remaining_task_hours: number;
  capacity_gap_hours: number;
  capacity_variance_hours: number;
  work_order_count: number;
  task_count: number;
  unallocated_task_count: number;
  missing_estimate_count: number;
  blocker_count: number;
  warning_count: number;
  leave_conflict_count: number;
  unacknowledged_count: number;
};

export type RosterPlanningBoardResponse = {
  from_date: string;
  to_date: string;
  base_station_id?: string | null;
  published_version_id?: string | null;
  assignments: RosterAssignmentRead[];
  findings: RosterValidationFindingRead[];
  metrics: PlanningBoardMetrics;
  base_capacity: BaseCapacitySummary[];
  work_orders: WorkloadWorkOrderSummary[];
  tasks: WorkloadTaskSummary[];
  task_links: RosterTaskAssignmentLinkRead[];
  demand_requirements: RosterDemandRequirementRead[];
};

export type RosterDashboardResponse = {
  from_date: string;
  to_date: string;
  active_period_count: number;
  draft_version_count: number;
  submitted_version_count: number;
  published_version_count: number;
  blocker_count: number;
  warning_count: number;
  pending_leave_count: number;
  unacknowledged_publication_count: number;
  capacity_gap_hours: number;
  upcoming_periods: RosterPeriodRead[];
  top_findings: RosterValidationFindingRead[];
};

export type RosterReportSummary = {
  from_date: string;
  to_date: string;
  planned_minutes: number;
  attendance_minutes: number;
  productive_minutes: number;
  overtime_minutes: number;
  assignment_count: number;
  assigned_people: number;
  leave_minutes: number;
  training_minutes: number;
  standby_minutes: number;
  acknowledgement_rate: number;
  blocker_count: number;
  warning_count: number;
  by_base: Array<Record<string, unknown>>;
  by_department: Array<Record<string, unknown>>;
  by_user: Array<Record<string, unknown>>;
};

export type RosterContractResponse = {
  canonical_personnel_key: string;
  route_contracts: Record<string, string>;
  source_modules: Record<string, string>;
  phase: string;
  permissions: string[];
  capabilities: Record<string, boolean>;
};
