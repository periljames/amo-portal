export type ContractType = "PERMANENT" | "FIXED_TERM" | "CASUAL" | "CONTRACTOR" | "INTERN" | "SECONDMENT";
export type EmploymentStatus = "ONBOARDING" | "ACTIVE" | "SUSPENDED" | "TERMINATED" | "ENDED";
export type PatternDayStatus = "DUTY" | "STANDBY" | "TRAINING" | "OFF" | "LEAVE" | "TRAVEL" | "UNAVAILABLE" | "OTHER";
export type AvailabilityType =
  | "AVAILABLE"
  | "UNAVAILABLE"
  | "ANNUAL_LEAVE"
  | "SICK_LEAVE"
  | "COMPASSIONATE_LEAVE"
  | "MATERNITY_LEAVE"
  | "PATERNITY_LEAVE"
  | "STUDY_LEAVE"
  | "UNPAID_LEAVE"
  | "TRAINING"
  | "TRAVEL"
  | "SUSPENDED"
  | "OTHER";
export type LeaveRequestStatus = "DRAFT" | "SUBMITTED" | "SUPERVISOR_APPROVED" | "HR_APPROVED" | "REJECTED" | "CANCELLED" | "RECALLED";
export type LeaveApprovalStage = "SUPERVISOR" | "HR";
export type ApprovalDecision = "APPROVED" | "REJECTED" | "REVOKED";
export type AttendanceEventType = "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END" | "MANUAL_ADJUSTMENT";
export type TimesheetStatus = "DRAFT" | "SUBMITTED" | "SUPERVISOR_APPROVED" | "HR_APPROVED" | "EXPORTED" | "REJECTED";
export type TimesheetCategory = "ORDINARY" | "OVERTIME" | "NIGHT" | "WEEKEND" | "PUBLIC_HOLIDAY" | "STANDBY" | "CALLOUT" | "TRAINING" | "TRAVEL" | "LEAVE" | "UNPAID_ABSENCE";
export type PermissionEffect = "GRANT" | "DENY";

export type WorkforceError = {
  detail: string;
  error_code: string;
  field_errors: Record<string, string | string[]>;
  conflicts: Array<Record<string, unknown>>;
  retryable: boolean;
};

export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

export type EmploymentContractRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  user_staff_code?: string | null;
  contract_type: ContractType;
  employment_status: EmploymentStatus;
  effective_from: string;
  effective_to?: string | null;
  standard_weekly_minutes: number;
  standard_daily_minutes: number;
  fte_percentage: number;
  primary_base_station_id: string;
  primary_base_code?: string | null;
  secondary_base_station_id?: string | null;
  secondary_base_code?: string | null;
  supervisor_user_id?: string | null;
  supervisor_name?: string | null;
  cost_centre?: string | null;
  payroll_number?: string | null;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type EmploymentContractCreate = Omit<EmploymentContractRead,
  "id" | "amo_id" | "user_full_name" | "user_staff_code" | "primary_base_code" |
  "secondary_base_code" | "supervisor_name" | "created_by_user_id" | "updated_by_user_id" |
  "created_at" | "updated_at"
>;

export type WorkPatternDayInput = {
  cycle_day_index: number;
  shift_template_id?: string | null;
  status: PatternDayStatus;
  start_time_local?: string | null;
  end_time_local?: string | null;
  spans_next_day: boolean;
  planned_minutes: number;
};

export type WorkPatternDayRead = WorkPatternDayInput & {
  id: string;
  amo_id: string;
  work_pattern_id: string;
  shift_code?: string | null;
  shift_label?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkPatternRead = {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  description?: string | null;
  cycle_length_days: number;
  is_active: boolean;
  timezone_name: string;
  days: WorkPatternDayRead[];
  assigned_employee_count: number;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkPatternCreate = Omit<WorkPatternRead,
  "id" | "amo_id" | "assigned_employee_count" | "created_by_user_id" | "updated_by_user_id" |
  "created_at" | "updated_at" | "days"
> & { days: WorkPatternDayInput[] };

export type WorkPatternAssignmentRead = {
  id: string;
  amo_id: string;
  user_id: string;
  work_pattern_id: string;
  effective_from: string;
  effective_to?: string | null;
  cycle_anchor_date: string;
  user_full_name?: string | null;
  pattern_code?: string | null;
  pattern_name?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type PatternPreviewRow = {
  user_id: string;
  user_full_name?: string | null;
  work_date: string;
  cycle_day_index: number;
  status: PatternDayStatus;
  starts_at?: string | null;
  ends_at?: string | null;
  planned_minutes: number;
  shift_template_id?: string | null;
  shift_code?: string | null;
  base_station_id?: string | null;
  source_reference_id: string;
  duplicate: boolean;
  conflicts: string[];
};

export type PatternPreviewResponse = {
  from_date: string;
  to_date: string;
  item_count: number;
  duplicate_count: number;
  conflict_count: number;
  items: PatternPreviewRow[];
};

export type LeaveTypeRead = {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  availability_type: AvailabilityType;
  description?: string | null;
  paid: boolean;
  deducts_balance: boolean;
  requires_attachment: boolean;
  supervisor_approval_required: boolean;
  hr_approval_required: boolean;
  allow_negative_balance: boolean;
  is_active: boolean;
  display_order: number;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type LeaveBalanceRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  leave_type_id: string;
  leave_type_code?: string | null;
  leave_type_name?: string | null;
  leave_year: number;
  allocated_minutes: number;
  carried_minutes: number;
  used_minutes: number;
  pending_minutes: number;
  adjustment_minutes: number;
  available_minutes: number;
  updated_by_user_id?: string | null;
  updated_at: string;
};

export type LeaveApprovalRead = {
  id: string;
  stage: LeaveApprovalStage;
  decision: ApprovalDecision;
  actor_user_id?: string | null;
  actor_name?: string | null;
  comment?: string | null;
  decided_at: string;
};

export type LeaveRequestRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  user_staff_code?: string | null;
  department_id?: string | null;
  leave_type_id: string;
  leave_type_code?: string | null;
  leave_type_name?: string | null;
  availability_type?: AvailabilityType | null;
  starts_at: string;
  ends_at: string;
  requested_minutes: number;
  status: LeaveRequestStatus;
  reason?: string | null;
  attachment_reference?: string | null;
  published_roster_conflicts: Array<Record<string, unknown>>;
  approvals: LeaveApprovalRead[];
  submitted_at?: string | null;
  supervisor_approved_at?: string | null;
  hr_approved_at?: string | null;
  rejected_at?: string | null;
  cancelled_at?: string | null;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type LeaveRequestCreate = {
  user_id?: string | null;
  leave_type_id: string;
  starts_at: string;
  ends_at: string;
  requested_minutes?: number | null;
  reason?: string | null;
  attachment_reference?: string | null;
};

export type AvailabilityEventRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  availability_type: AvailabilityType;
  starts_at: string;
  ends_at: string;
  blocking: boolean;
  provisional: boolean;
  source_type: string;
  source_id: string;
  reason?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type AttendanceEventRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  event_type: AttendanceEventType;
  occurred_at: string;
  source: string;
  base_station_id?: string | null;
  roster_assignment_id?: string | null;
  idempotency_key: string;
  note?: string | null;
  metadata_json?: Record<string, unknown> | null;
  recorded_by_user_id?: string | null;
  created_at: string;
};

export type AttendanceSummaryRead = {
  user_id: string;
  user_full_name?: string | null;
  from_date: string;
  to_date: string;
  presence_minutes: number;
  break_minutes: number;
  paid_minutes: number;
  incomplete: boolean;
  warnings: string[];
  events: AttendanceEventRead[];
};

export type TimesheetLineRead = {
  id: string;
  work_date: string;
  category: TimesheetCategory;
  minutes: number;
  roster_assignment_id?: string | null;
  work_log_entry_id?: number | null;
  source: string;
  description?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type TimesheetRead = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  payroll_number?: string | null;
  period_start: string;
  period_end: string;
  status: TimesheetStatus;
  planned_minutes: number;
  attendance_minutes: number;
  productive_minutes: number;
  overtime_minutes: number;
  variance_minutes: number;
  lines: TimesheetLineRead[];
  submitted_at?: string | null;
  supervisor_approved_at?: string | null;
  hr_approved_at?: string | null;
  exported_at?: string | null;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type PayrollExportRow = {
  timesheet_id: string;
  payroll_number?: string | null;
  user_id: string;
  staff_code?: string | null;
  full_name: string;
  period_start: string;
  period_end: string;
  ordinary_minutes: number;
  overtime_minutes: number;
  night_minutes: number;
  weekend_minutes: number;
  public_holiday_minutes: number;
  standby_minutes: number;
  callout_minutes: number;
  training_minutes: number;
  travel_minutes: number;
  leave_minutes: number;
  unpaid_absence_minutes: number;
  approved_at?: string | null;
};

export type CurrentPermissionsRead = {
  user_id: string;
  permissions: string[];
};

export type PlannerPreferenceRead = {
  id: string;
  amo_id: string;
  user_id: string;
  density: "compact" | "comfortable";
  group_by: string;
  zoom: string;
  default_base_station_id?: string | null;
  filters_json?: Record<string, unknown> | null;
  updated_at: string;
};
