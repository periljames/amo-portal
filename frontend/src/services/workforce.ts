import type {
  AttendanceSummaryRead,
  AvailabilityEventRead,
  CurrentPermissionsRead,
  EmploymentContractCreate,
  EmploymentContractRead,
  LeaveBalanceRead,
  LeaveRequestCreate,
  LeaveRequestRead,
  LeaveTypeRead,
  Page,
  PatternPreviewResponse,
  PayrollExportRow,
  PlannerPreferenceRead,
  TimesheetRead,
  WorkPatternAssignmentRead,
  WorkPatternCreate,
  WorkPatternRead,
} from "../types/workforce";
import { apiBlob, apiJson, downloadBlob, jsonBody, queryString } from "./typedApi";

const ROOT = "/workforce";

export type WorkforcePersonRead = {
  user_id: string;
  staff_code: string;
  full_name: string;
  email: string;
  role: string;
  position_title?: string | null;
  department_id?: string | null;
  department_code?: string | null;
  department_name?: string | null;
  primary_base_station_id?: string | null;
  primary_base_code?: string | null;
  employment_status?: string | null;
  contract_type?: string | null;
  standard_daily_minutes?: number | null;
  standard_weekly_minutes?: number | null;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
  licence_number?: string | null;
  licence_expires_on?: string | null;
  authorisation_count: number;
  active_authorisation_count: number;
  has_active_contract: boolean;
  is_active: boolean;
};

export type WorkforcePeopleFilters = {
  search?: string | null;
  department_id?: string | null;
  base_station_id?: string | null;
  active_only?: boolean;
  roster_eligible_only?: boolean;
  limit?: number;
};

export function getCurrentWorkforcePermissions(): Promise<CurrentPermissionsRead> {
  return apiJson(`${ROOT}/permissions/current`);
}

export function listWorkforcePeople(filters: WorkforcePeopleFilters = {}): Promise<WorkforcePersonRead[]> {
  return apiJson(`${ROOT}/people${queryString(filters)}`);
}

export function listEmploymentContracts(params: {
  page?: number;
  page_size?: number;
  user_id?: string | null;
  employment_status?: string | null;
  base_station_id?: string | null;
  search?: string | null;
} = {}): Promise<Page<EmploymentContractRead>> {
  return apiJson(`${ROOT}/employment-contracts${queryString(params)}`);
}

export function createEmploymentContract(payload: EmploymentContractCreate): Promise<EmploymentContractRead> {
  return apiJson(`${ROOT}/employment-contracts`, { method: "POST", body: jsonBody(payload) });
}

export function getEmploymentContract(contractId: string): Promise<EmploymentContractRead> {
  return apiJson(`${ROOT}/employment-contracts/${encodeURIComponent(contractId)}`);
}

export function updateEmploymentContract(contractId: string, payload: Partial<EmploymentContractCreate>): Promise<EmploymentContractRead> {
  return apiJson(`${ROOT}/employment-contracts/${encodeURIComponent(contractId)}`, { method: "PATCH", body: jsonBody(payload) });
}

export function listWorkPatterns(includeInactive = false): Promise<WorkPatternRead[]> {
  return apiJson(`${ROOT}/work-patterns${queryString({ include_inactive: includeInactive })}`);
}

export function createWorkPattern(payload: WorkPatternCreate): Promise<WorkPatternRead> {
  return apiJson(`${ROOT}/work-patterns`, { method: "POST", body: jsonBody(payload) });
}

export function updateWorkPattern(patternId: string, payload: Partial<WorkPatternCreate>): Promise<WorkPatternRead> {
  return apiJson(`${ROOT}/work-patterns/${encodeURIComponent(patternId)}`, { method: "PATCH", body: jsonBody(payload) });
}

export function listWorkPatternAssignments(params: {
  user_id?: string | null;
  pattern_id?: string | null;
} = {}): Promise<WorkPatternAssignmentRead[]> {
  return apiJson(`${ROOT}/work-pattern-assignments${queryString(params)}`);
}

export function createWorkPatternAssignment(payload: {
  user_id: string;
  work_pattern_id: string;
  effective_from: string;
  effective_to?: string | null;
  cycle_anchor_date: string;
}): Promise<WorkPatternAssignmentRead> {
  return apiJson(`${ROOT}/work-pattern-assignments`, { method: "POST", body: jsonBody(payload) });
}

export function previewWorkPattern(patternId: string, payload: {
  from_date: string;
  to_date: string;
  user_ids?: string[];
  roster_version_id?: string | null;
}): Promise<PatternPreviewResponse> {
  return apiJson(`${ROOT}/work-patterns/${encodeURIComponent(patternId)}/preview`, { method: "POST", body: jsonBody(payload) });
}

export function listLeaveTypes(includeInactive = false): Promise<LeaveTypeRead[]> {
  return apiJson(`${ROOT}/leave-types${queryString({ include_inactive: includeInactive })}`);
}

export function createLeaveType(payload: Omit<LeaveTypeRead, "id" | "amo_id" | "created_by_user_id" | "updated_by_user_id" | "created_at" | "updated_at">): Promise<LeaveTypeRead> {
  return apiJson(`${ROOT}/leave-types`, { method: "POST", body: jsonBody(payload) });
}

export function updateLeaveType(leaveTypeId: string, payload: Partial<LeaveTypeRead>): Promise<LeaveTypeRead> {
  return apiJson(`${ROOT}/leave-types/${encodeURIComponent(leaveTypeId)}`, { method: "PATCH", body: jsonBody(payload) });
}

export function listLeaveBalances(params: { user_id?: string | null; leave_year?: number | null } = {}): Promise<LeaveBalanceRead[]> {
  return apiJson(`${ROOT}/leave-balances${queryString(params)}`);
}

export function updateLeaveBalance(balanceId: string, payload: {
  allocated_minutes?: number;
  carried_minutes?: number;
  adjustment_minutes?: number;
}): Promise<LeaveBalanceRead> {
  return apiJson(`${ROOT}/leave-balances/${encodeURIComponent(balanceId)}`, { method: "PATCH", body: jsonBody(payload) });
}

export function listLeaveRequests(params: {
  page?: number;
  page_size?: number;
  user_id?: string | null;
  department_id?: string | null;
  status?: string | null;
  from?: string | null;
  to?: string | null;
} = {}): Promise<Page<LeaveRequestRead>> {
  return apiJson(`${ROOT}/leave-requests${queryString(params)}`);
}

export function createLeaveRequest(payload: LeaveRequestCreate): Promise<LeaveRequestRead> {
  return apiJson(`${ROOT}/leave-requests`, { method: "POST", body: jsonBody(payload) });
}

export function updateLeaveRequest(requestId: string, payload: Partial<LeaveRequestCreate>): Promise<LeaveRequestRead> {
  return apiJson(`${ROOT}/leave-requests/${encodeURIComponent(requestId)}`, { method: "PATCH", body: jsonBody(payload) });
}

function leaveAction(requestId: string, action: string, payload: Record<string, unknown> = {}): Promise<LeaveRequestRead> {
  return apiJson(`${ROOT}/leave-requests/${encodeURIComponent(requestId)}/${action}`, { method: "POST", body: jsonBody(payload) });
}

export function submitLeaveRequest(requestId: string): Promise<LeaveRequestRead> {
  return leaveAction(requestId, "submit");
}

export function supervisorApproveLeave(requestId: string, comment?: string): Promise<LeaveRequestRead> {
  return leaveAction(requestId, "supervisor-approve", { comment });
}

export function hrApproveLeave(requestId: string, comment?: string): Promise<LeaveRequestRead> {
  return leaveAction(requestId, "hr-approve", { comment });
}

export function rejectLeaveRequest(requestId: string, reason: string): Promise<LeaveRequestRead> {
  return leaveAction(requestId, "reject", { reason });
}

export function cancelLeaveRequest(requestId: string, reason?: string): Promise<LeaveRequestRead> {
  return leaveAction(requestId, "cancel", { reason });
}

export function listAvailabilityEvents(params: {
  from: string;
  to: string;
  user_id?: string | null;
  blocking?: boolean | null;
}): Promise<AvailabilityEventRead[]> {
  return apiJson(`${ROOT}/availability-events${queryString(params)}`);
}

export function createAvailabilityEvent(payload: {
  user_id: string;
  availability_type: string;
  starts_at: string;
  ends_at: string;
  blocking?: boolean;
  provisional?: boolean;
  source_type?: string;
  source_id?: string | null;
  reason?: string | null;
  metadata_json?: Record<string, unknown> | null;
}): Promise<AvailabilityEventRead> {
  return apiJson(`${ROOT}/availability-events`, { method: "POST", body: jsonBody(payload) });
}

export function updateAvailabilityEvent(eventId: string, payload: Partial<AvailabilityEventRead>): Promise<AvailabilityEventRead> {
  return apiJson(`${ROOT}/availability-events/${encodeURIComponent(eventId)}`, { method: "PATCH", body: jsonBody(payload) });
}

export function deleteAvailabilityEvent(eventId: string): Promise<void> {
  return apiJson(`${ROOT}/availability-events/${encodeURIComponent(eventId)}`, { method: "DELETE" });
}

export function getAttendanceSummary(params: { user_id?: string | null; from: string; to: string }): Promise<AttendanceSummaryRead> {
  return apiJson(`${ROOT}/attendance-events${queryString(params)}`);
}

export function createAttendanceEvent(payload: {
  user_id?: string | null;
  event_type: string;
  occurred_at: string;
  source?: string;
  base_station_id?: string | null;
  roster_assignment_id?: string | null;
  idempotency_key: string;
  note?: string | null;
  metadata_json?: Record<string, unknown> | null;
}) {
  return apiJson(`${ROOT}/attendance-events`, { method: "POST", body: jsonBody(payload) });
}

export function listTimesheets(params: {
  page?: number;
  page_size?: number;
  user_id?: string | null;
  status?: string | null;
  from?: string | null;
  to?: string | null;
} = {}): Promise<Page<TimesheetRead>> {
  return apiJson(`${ROOT}/timesheets${queryString(params)}`);
}

export function generateTimesheets(payload: {
  period_start: string;
  period_end: string;
  user_ids?: string[];
  replace_draft?: boolean;
}): Promise<TimesheetRead[]> {
  return apiJson(`${ROOT}/timesheets/generate`, { method: "POST", body: jsonBody(payload) });
}

export function submitTimesheet(timesheetId: string): Promise<TimesheetRead> {
  return apiJson(`${ROOT}/timesheets/${encodeURIComponent(timesheetId)}/submit`, { method: "POST" });
}

export function approveTimesheet(timesheetId: string, stage: "SUPERVISOR" | "HR", comment?: string): Promise<TimesheetRead> {
  return apiJson(`${ROOT}/timesheets/${encodeURIComponent(timesheetId)}/approve`, { method: "POST", body: jsonBody({ stage, comment }) });
}

export function getPayrollExport(params: { from?: string | null; to?: string | null }): Promise<PayrollExportRow[]> {
  return apiJson(`${ROOT}/payroll-export${queryString({ ...params, format: "json" })}`);
}

export async function downloadPayrollExport(params: { from?: string | null; to?: string | null }): Promise<void> {
  const result = await apiBlob(`${ROOT}/payroll-export${queryString({ ...params, format: "csv" })}`);
  downloadBlob(result.blob, result.filename || "workforce-payroll-export.csv");
}

export function getPlannerPreferences(): Promise<PlannerPreferenceRead> {
  return apiJson(`${ROOT}/planner-preferences`);
}

export function updatePlannerPreferences(payload: Partial<PlannerPreferenceRead>): Promise<PlannerPreferenceRead> {
  return apiJson(`${ROOT}/planner-preferences`, { method: "PATCH", body: jsonBody(payload) });
}
