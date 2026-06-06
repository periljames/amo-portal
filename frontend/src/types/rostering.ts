// src/types/rostering.ts
export type ShiftTemplateKind = "DAY" | "NIGHT" | "STANDBY" | "TRAINING" | "OFF" | "LEAVE" | "OTHER";
export type RosterPeriodStatus = "DRAFT" | "OPEN" | "LOCKED" | "ARCHIVED";
export type RosterVersionStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "PUBLISHED" | "SUPERSEDED" | "ARCHIVED";
export type RosterAssignmentStatus = "DUTY" | "STANDBY" | "TRAINING" | "OFF" | "LEAVE" | "TRAVEL" | "UNAVAILABLE" | "OTHER";
export type RosterValidationSeverity = "INFO" | "WARNING" | "BLOCKER";
export type RosterValidationSource = "ROSTER" | "IDENTITY" | "BASE" | "AVAILABILITY" | "TRAINING" | "AUTHORISATION" | "WORKLOAD" | "RULE";

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
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ShiftTemplateCreate = Omit<ShiftTemplateRead, "id" | "amo_id" | "created_by_user_id" | "updated_by_user_id" | "created_at" | "updated_at">;

export type RosterVersionRead = {
  id: string;
  amo_id: string;
  period_id: string;
  version_no: number;
  status: RosterVersionStatus;
  title?: string | null;
  change_summary?: string | null;
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
};

export type RosterVersionCreate = {
  title?: string | null;
  change_summary?: string | null;
  copy_from_version_id?: string | null;
};

export type RosterAssignmentRead = {
  id: string;
  amo_id: string;
  version_id: string;
  user_id: string;
  base_station_id?: string | null;
  shift_template_id?: string | null;
  status: RosterAssignmentStatus;
  starts_at: string;
  ends_at: string;
  planned_minutes?: number | null;
  role_label?: string | null;
  task_note?: string | null;
  locked_after_publish: boolean;
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  user_full_name?: string | null;
  user_role?: string | null;
  base_code?: string | null;
  base_name?: string | null;
  shift_code?: string | null;
  linked_task_count: number;
  linked_task_hours: number;
};

export type RosterAssignmentCreate = {
  user_id: string;
  starts_at: string;
  ends_at: string;
  base_station_id?: string | null;
  shift_template_id?: string | null;
  status?: RosterAssignmentStatus;
  planned_minutes?: number | null;
  role_label?: string | null;
  task_note?: string | null;
};

export type RosterValidationFindingRead = {
  id: string;
  amo_id: string;
  version_id: string;
  assignment_id?: string | null;
  user_id?: string | null;
  source: RosterValidationSource;
  severity: RosterValidationSeverity;
  code: string;
  message: string;
  resolved: boolean;
  created_at: string;
};

export type RosterValidationResult = {
  version_id: string;
  blocker_count: number;
  warning_count: number;
  info_count: number;
  can_submit: boolean;
  can_publish: boolean;
  findings: RosterValidationFindingRead[];
};

export type MyRosterResponse = {
  user_id: string;
  from_date: string;
  to_date: string;
  assignments: RosterAssignmentRead[];
  training_due_next_month: Array<Record<string, unknown>>;
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
};

export type RosterContractResponse = {
  canonical_personnel_key: string;
  route_contracts: Record<string, string>;
  source_modules: Record<string, string>;
  phase: string;
};
