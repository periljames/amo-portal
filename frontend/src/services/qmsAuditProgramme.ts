import { apiRequest, qmsPath } from "./apiClient";

export type AuditProgrammeStatus = "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "ACTIVE" | "SUPERSEDED" | "CLOSED";
export type AuditProgrammeMethodology = "COMPLIANCE" | "PERFORMANCE" | "RISK";
export type AuditRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AuditUniverseEntityType = "DEPARTMENT" | "FACILITY" | "STATION" | "SUPPLIER" | "CONTRACTOR" | "PROCESS" | "CAPABILITY" | "APPROVAL_RATING" | "AIRCRAFT_TYPE" | "PERSONNEL_GROUP" | "OTHER";
export type AuditProgrammeItemState = "PLANNED" | "SCHEDULED" | "COMPLETED" | "DEFERRED" | "CANCELLED" | "FOLLOW_UP_REQUIRED";
export type AuditScheduleFrequency = "ONE_TIME" | "MONTHLY" | "QUARTERLY" | "BI_ANNUAL" | "ANNUAL";

export type AuditUniverseItem = {
  id: string;
  entity_type: AuditUniverseEntityType;
  display_label: string;
  source_owner_module: string;
  source_type: string;
  source_id: string;
  source_route?: string | null;
  risk_classification: AuditRiskLevel;
  regulatory_criticality: AuditRiskLevel;
  surveillance_interval_days?: number | null;
  mandatory_surveillance: boolean;
  active: boolean;
  notes?: string | null;
};

export type AuditProgrammeItem = {
  id: string;
  programme_id: string;
  universe_item_id: string;
  audit_type: string;
  title: string;
  purpose?: string | null;
  scope: string;
  criteria: Array<string | Record<string, unknown>>;
  mandatory_surveillance: boolean;
  recurrence: string;
  custom_interval_days?: number | null;
  target_start?: string | null;
  target_end?: string | null;
  state: AuditProgrammeItemState;
  prioritization_basis: Array<Record<string, unknown>>;
  deferral_reason?: string | null;
  cancellation_reason?: string | null;
  auditable_entity?: AuditUniverseItem | null;
};

export type AuditProgrammeReadiness = {
  ready_for_approval: boolean;
  blockers: Array<{ code: string; message: string }>;
  requirement_count: number;
  mandatory_requirement_count: number;
  mandatory_unscheduled_count: number;
  high_risk_requirement_count: number;
  unscheduled_requirement_count: number;
};

export type AuditProgramme = {
  id: string;
  programme_ref: string;
  programme_series: string;
  programme_year: number;
  revision_no: number;
  title: string;
  programme_methodology?: AuditProgrammeMethodology;
  methodology_rationale?: string | null;
  objectives: string[];
  regulatory_basis: Array<string | Record<string, unknown>>;
  status: AuditProgrammeStatus;
  period_start: string;
  period_end: string;
  owner_user_id?: string | null;
  supersedes_programme_id?: string | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  activated_at?: string | null;
  closed_at?: string | null;
  metrics: {
    planned_audit_count: number;
    completed_audit_count: number;
    deferred_audit_count: number;
    cancelled_audit_count: number;
    follow_up_audit_count: number;
    scheduled_audit_count: number;
    unscheduled_audit_count?: number;
  };
  readiness?: AuditProgrammeReadiness;
  items?: AuditProgrammeItem[];
  events?: Array<{
    id: string;
    event_type: string;
    reason: string;
    before_snapshot?: Record<string, unknown> | null;
    after_snapshot?: Record<string, unknown> | null;
    actor_user_id?: string | null;
    created_at: string;
  }>;
};

export type AuditProgrammeList = { items: AuditProgramme[]; total: number; limit: number; offset: number; has_more: boolean };
export type AuditUniverseList = { items: AuditUniverseItem[]; total: number; limit: number; offset: number; has_more: boolean };

export type AuditProgrammeSchedulingQueueItem = {
  programme_id: string;
  programme_ref: string;
  programme_status: AuditProgrammeStatus;
  programme_year: number;
  programme_revision_no: number;
  programme_item_id: string;
  universe_item_id: string;
  auditable_entity?: string | null;
  audit_type: string;
  title: string;
  recurrence: string;
  mandatory_surveillance: boolean;
  target_start?: string | null;
  target_end?: string | null;
  prioritization_basis: Array<Record<string, unknown>>;
};

export type AuditProgrammeSchedulingQueue = {
  items: AuditProgrammeSchedulingQueueItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type AuditProgrammeScheduleLink = {
  programme_item_id: string;
  state: AuditProgrammeItemState;
  schedule_id?: string | null;
  scheduled_by_user_id?: string | null;
  scheduled_at?: string | null;
  schedule_title?: string | null;
  next_due_date?: string | null;
  frequency?: AuditScheduleFrequency | null;
  lifecycle_status?: string | null;
  version?: number | null;
};

export type PlannerScheduleOption = { id: string; code: string; name: string; party_level: string; default_kind: string };
export type PlannerPersonOption = { id: string; full_name: string; email?: string | null; role?: string | null; department_name?: string | null };
export type PlannerScheduleOptions = {
  timezone_name: string;
  frequencies: AuditScheduleFrequency[];
  kinds: string[];
  supported_source_types: string[];
  unsupported_source_types: Record<string, string>;
  scopes: PlannerScheduleOption[];
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

export type ProgrammeScheduleCreate = {
  title: string;
  domain?: string;
  kind?: string;
  audit_scope_id?: string;
  audit_scope_code?: string;
  frequency: AuditScheduleFrequency;
  next_due_date: string;
  start_time?: string;
  end_time?: string;
  duration_days?: number;
  timezone_name?: string;
  location?: string;
  scope?: string;
  criteria?: string;
  notes?: string;
  auditee?: string;
  auditee_email?: string;
  auditee_user_id?: string;
  lead_auditor_user_id?: string;
  observer_auditor_user_id?: string;
  assistant_auditor_user_id?: string;
  attendee_user_ids?: string[];
  notify_auditors?: boolean;
  notify_auditees?: boolean;
  notify_attendees?: boolean;
  reminder_interval_days?: number;
  automation_active?: boolean;
  allow_conflicts?: boolean;
  conflict_override_reason?: string;
};

export type PlannerAuditSchedule = {
  id: string;
  amo_id: string;
  title: string;
  domain: string;
  kind: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  frequency: AuditScheduleFrequency;
  next_due_date: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_days: number;
  timezone_name: string;
  location?: string | null;
  lifecycle_status: string;
  version: number;
  conflicts: PlannerConflict[];
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listAuditProgrammes(amoCode: string, year?: number, signal?: AbortSignal): Promise<AuditProgrammeList> {
  const params = new URLSearchParams({ limit: "50", offset: "0" });
  if (year) params.set("year", String(year));
  return apiRequest(qmsPath(amoCode, `/audit-programmes?${params.toString()}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function getAuditProgramme(amoCode: string, programmeId: string, signal?: AbortSignal): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function createAuditProgramme(amoCode: string, payload: {
  programme_year: number;
  title: string;
  programme_methodology?: AuditProgrammeMethodology;
  methodology_rationale?: string;
  objectives: string[];
  regulatory_basis: Array<string | Record<string, unknown>>;
  period_start: string;
  period_end: string;
}): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, "/audit-programmes"), jsonOptions("POST", payload));
}

export function transitionAuditProgramme(amoCode: string, programmeId: string, targetStatus: AuditProgrammeStatus, reason: string): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/transitions`), jsonOptions("POST", { target_status: targetStatus, reason }));
}

export function createAuditProgrammeAmendment(amoCode: string, programmeId: string, reason: string): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/amendments`), jsonOptions("POST", { reason }));
}

export function listAuditUniverse(amoCode: string, signal?: AbortSignal): Promise<AuditUniverseList> {
  return apiRequest(qmsPath(amoCode, "/audit-programmes/universe/items?limit=200&offset=0"), { timeoutMs: 15_000, cacheTtlMs: 10_000, signal });
}

export function createAuditUniverseItem(amoCode: string, payload: {
  entity_type: AuditUniverseEntityType; display_label: string; source_owner_module: string; source_type: string; source_id: string;
  source_route?: string; risk_classification: AuditRiskLevel; regulatory_criticality: AuditRiskLevel;
  surveillance_interval_days?: number; mandatory_surveillance: boolean; notes?: string;
}): Promise<AuditUniverseItem> {
  return apiRequest(qmsPath(amoCode, "/audit-programmes/universe/items"), jsonOptions("POST", payload));
}

export function addAuditProgrammeItem(amoCode: string, programmeId: string, payload: {
  universe_item_id: string; audit_type: string; title: string; purpose?: string; scope: string;
  criteria: string[]; mandatory_surveillance: boolean; recurrence: string; target_start?: string; target_end?: string;
  prioritization_basis: Array<Record<string, unknown>>;
}): Promise<AuditProgrammeItem> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/items`), jsonOptions("POST", payload));
}

export function listAuditProgrammeSchedulingQueue(amoCode: string, signal?: AbortSignal): Promise<AuditProgrammeSchedulingQueue> {
  return apiRequest(qmsPath(amoCode, "/audit-programmes/planner/queue?limit=50&offset=0"), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function listAuditProgrammeScheduleLinks(amoCode: string, programmeId: string, signal?: AbortSignal): Promise<{ items: AuditProgrammeScheduleLink[] }> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/schedule-links`), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getPlannerScheduleOptions(amoCode: string, signal?: AbortSignal): Promise<PlannerScheduleOptions> {
  return apiRequest(qmsPath(amoCode, "/integrations/calendar/schedule-options"), { timeoutMs: 15_000, cacheTtlMs: 10_000, signal });
}

export function scheduleAuditProgrammeItem(
  amoCode: string,
  programmeId: string,
  itemId: string,
  payload: ProgrammeScheduleCreate,
): Promise<PlannerAuditSchedule> {
  return apiRequest(
    qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/items/${encodeURIComponent(itemId)}/schedule`),
    jsonOptions("POST", payload),
  );
}
