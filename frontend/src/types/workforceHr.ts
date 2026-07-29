export type HrMetric = {
  key: string;
  label: string;
  value: number | string;
  detail?: string | null;
  tone: string;
};

export type HrActionItem = {
  id: string;
  category: string;
  severity: string;
  title: string;
  detail: string;
  user_id?: string | null;
  user_name?: string | null;
  due_on?: string | null;
  action_label?: string | null;
  action_path?: string | null;
};

export type HrPersonReadiness = {
  user_id: string;
  contract_id: string;
  staff_code: string;
  full_name: string;
  position_title?: string | null;
  department_code?: string | null;
  employment_status?: string | null;
  contract_type?: string | null;
  contract_effective_from?: string | null;
  contract_effective_to?: string | null;
  primary_base_station_id?: string | null;
  primary_base_code?: string | null;
  supervisor_name?: string | null;
  standard_weekly_minutes: number;
  standard_daily_minutes: number;
  fte_percentage: number;
  cost_centre?: string | null;
  payroll_number?: string | null;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
  work_pattern_code?: string | null;
  work_pattern_name?: string | null;
  work_pattern_effective_from?: string | null;
  active_leave_status?: string | null;
  readiness_state: string;
  readiness_reasons: string[];
};

export type HrOvertimeRequest = {
  id: string;
  amo_id: string;
  user_id: string;
  user_full_name?: string | null;
  roster_assignment_id?: string | null;
  starts_at: string;
  ends_at: string;
  requested_minutes: number;
  reason: string;
  status: "DRAFT" | "SUBMITTED" | "SUPERVISOR_APPROVED" | "HR_APPROVED" | "REJECTED" | "CANCELLED";
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type HrDashboard = {
  generated_at: string;
  can_manage_contracts: boolean;
  can_manage_leave_balances: boolean;
  can_review_leave: boolean;
  can_approve_leave: boolean;
  can_approve_timesheet_supervisor: boolean;
  can_approve_timesheet_hr: boolean;
  can_approve_overtime_supervisor: boolean;
  can_approve_overtime_hr: boolean;
  can_export_payroll: boolean;
  active_employee_count: number;
  onboarding_employee_count: number;
  suspended_employee_count: number;
  contracts_expiring_soon_count: number;
  employees_without_pattern_count: number;
  employees_without_base_count: number;
  pending_leave_count: number;
  pending_timesheet_count: number;
  pending_overtime_count: number;
  attendance_exception_count: number;
  metrics: HrMetric[];
  action_queue: HrActionItem[];
  pending_overtime: HrOvertimeRequest[];
  people: HrPersonReadiness[];
};
