import { apiRequest, qmsPath } from "./apiClient";

export type PlannerCapabilities = {
  can_reschedule: boolean;
  can_create_audit: boolean;
  can_manage_training: boolean;
  user_id: string;
};

export type PlannerPersonOption = {
  id: string;
  full_name: string;
  email?: string | null;
  role?: string | null;
  department_name?: string | null;
};

export type PlannerScopeOption = {
  id: string;
  code: string;
  name: string;
  party_level: string;
  default_kind: string;
};

export type PlannerScheduleOptions = {
  timezone_name: string;
  frequencies: string[];
  kinds: string[];
  supported_source_types: string[];
  unsupported_source_types: Record<string, string>;
  scopes: PlannerScopeOption[];
  people: PlannerPersonOption[];
};

export type PlannerConflict = {
  subject_type: string;
  subject_id: string;
  title: string;
  start_date: string;
  end_date: string;
  start_time?: string | null;
  end_time?: string | null;
  location?: string | null;
  conflicting_user_ids: string[];
  reason: string;
};

export type PlannerAuditSchedule = {
  id: string;
  amo_id: string;
  title: string;
  domain: string;
  kind: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  frequency: string;
  next_due_date: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_days: number;
  timezone_name: string;
  location?: string | null;
  scope?: string | null;
  criteria?: string | null;
  notes?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  external_auditees: Array<Record<string, unknown>>;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  attendee_user_ids: string[];
  external_attendees: Array<Record<string, unknown>>;
  notify_auditors: boolean;
  notify_auditees: boolean;
  notify_attendees: boolean;
  reminder_interval_days: number;
  automation_active: boolean;
  lifecycle_status: string;
  version: number;
  created_at: string;
  notifications_queued: number;
  conflicts: PlannerConflict[];
};

export type CreatePlannerAuditSchedule = {
  title: string;
  domain?: string;
  kind?: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  frequency?: string;
  next_due_date: string;
  start_time?: string;
  end_time?: string | null;
  duration_days?: number;
  timezone_name?: string;
  location?: string | null;
  scope?: string | null;
  criteria?: string | null;
  notes?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  attendee_user_ids?: string[];
  external_attendees?: Array<Record<string, unknown>>;
  external_auditees?: Array<Record<string, unknown>>;
  notify_auditors?: boolean;
  notify_auditees?: boolean;
  notify_attendees?: boolean;
  reminder_interval_days?: number;
  automation_active?: boolean;
  allow_conflicts?: boolean;
  conflict_override_reason?: string | null;
};

function jsonBody(value: unknown) {
  return JSON.stringify(value);
}

export function getPlannerCapabilities(amoCode: string, signal?: AbortSignal) {
  return apiRequest<PlannerCapabilities>(
    qmsPath(amoCode, "/integrations/calendar/planner-capabilities"),
    { timeoutMs: 10_000, cacheTtlMs: 2_000, signal },
  );
}

export function getPlannerScheduleOptions(amoCode: string, signal?: AbortSignal) {
  return apiRequest<PlannerScheduleOptions>(
    qmsPath(amoCode, "/integrations/calendar/schedule-options"),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function createPlannerAuditSchedule(amoCode: string, payload: CreatePlannerAuditSchedule) {
  return apiRequest<PlannerAuditSchedule>(
    qmsPath(amoCode, "/integrations/calendar/audit-schedules"),
    { method: "POST", timeoutMs: 20_000, body: jsonBody(payload) },
  );
}

export function listPlannerAuditSchedules(
  amoCode: string,
  params: { active?: boolean; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  if (params.active !== undefined) query.set("active", String(params.active));
  query.set("limit", String(params.limit ?? 250));
  query.set("offset", String(params.offset ?? 0));
  return apiRequest<PlannerAuditSchedule[]>(
    `${qmsPath(amoCode, "/integrations/calendar/audit-schedules")}?${query.toString()}`,
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function getPlannerAuditSchedule(amoCode: string, scheduleId: string, signal?: AbortSignal) {
  return apiRequest<PlannerAuditSchedule>(
    qmsPath(amoCode, `/integrations/calendar/audit-schedules/${encodeURIComponent(scheduleId)}`),
    { timeoutMs: 15_000, cacheTtlMs: 2_000, signal },
  );
}

export function changePlannerAuditScheduleDate(
  amoCode: string,
  scheduleId: string,
  payload: {
    expected_version: number;
    new_date: string;
    reason: string;
    allow_conflicts?: boolean;
    conflict_override_reason?: string | null;
  },
) {
  return apiRequest<PlannerAuditSchedule>(
    qmsPath(amoCode, `/integrations/calendar/audit-schedules/${encodeURIComponent(scheduleId)}/date`),
    { method: "PATCH", timeoutMs: 20_000, body: jsonBody(payload) },
  );
}

export function suspendPlannerAuditSchedule(
  amoCode: string,
  scheduleId: string,
  payload: { expected_version: number; reason: string },
) {
  return apiRequest<PlannerAuditSchedule>(
    qmsPath(amoCode, `/integrations/calendar/audit-schedules/${encodeURIComponent(scheduleId)}/suspend`),
    { method: "POST", timeoutMs: 20_000, body: jsonBody(payload) },
  );
}

export function resumePlannerAuditSchedule(
  amoCode: string,
  scheduleId: string,
  payload: { expected_version: number; reason: string },
) {
  return apiRequest<PlannerAuditSchedule>(
    qmsPath(amoCode, `/integrations/calendar/audit-schedules/${encodeURIComponent(scheduleId)}/resume`),
    { method: "POST", timeoutMs: 20_000, body: jsonBody(payload) },
  );
}
