import { apiRequest, qmsPath } from "./apiClient";

export type AuditProgrammeStatus = "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "ACTIVE" | "SUPERSEDED" | "CLOSED";
/** Programme methodology. Backend currently emits HYBRID; other values are reserved for display/future API support. */
export type AuditAssuranceModel = "HYBRID" | "COMPLIANCE" | "PERFORMANCE" | "RISK";
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
  mandatory_coverage_gap_count?: number;
};

export type AuditProgramme = {
  id: string;
  programme_ref: string;
  programme_series: string;
  programme_year: number;
  revision_no: number;
  title: string;
  assurance_model: AuditAssuranceModel;
  continuous_monitoring_enabled: boolean;
  optimizer_version: string;
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

export type AuditProgrammeOptimizerRecommendation = {
  universe_item_id: string;
  auditable_entity: string;
  entity_type: AuditUniverseEntityType;
  source_route?: string | null;
  algorithm: string;
  priority_score: number;
  priority_band: "ROUTINE" | "ELEVATED" | "HIGH" | "CRITICAL";
  recommended_interval_days: number;
  components: { compliance: number; risk: number; performance: number };
  drivers: Array<Record<string, unknown>>;
  signals: {
    repeat_findings: number;
    open_findings: number;
    follow_up_required: number;
    deferred_audits: number;
    failed_controls: number;
    adverse_trends: number;
    last_audit_date?: string | null;
  };
  mandatory_baseline: boolean;
  recommend_in_programme: boolean;
  recommended_in_current_programme: boolean;
  in_programme: boolean;
  programme_item_id?: string | null;
  next_recommended_due: string;
  target_start: string;
  target_end: string;
  requires_amendment: boolean;
};

export type AuditProgrammeOptimizer = {
  algorithm: string;
  weights: { compliance: number; risk: number; performance: number };
  as_of: string;
  assurance_model: AuditAssuranceModel;
  continuous_monitoring_enabled: boolean;
  recommendations: AuditProgrammeOptimizerRecommendation[];
  summary: {
    auditable_entities: number;
    recommended_current_period: number;
    mandatory_baseline_due: number;
    mandatory_coverage_gaps: number;
    adaptive_risk_performance_coverage: number;
    coverage_gaps: number;
    requires_amendment: number;
  };
  sync?: { added: number; updated: number };
  governance?: { programme_immutable: boolean; message: string };
};

export type AuditProgrammeList = { items: AuditProgramme[]; total: number; limit: number; offset: number; has_more: boolean };
export type AuditUniverseList = { items: AuditUniverseItem[]; total: number; limit: number; offset: number; has_more: boolean };

export function readinessOf(
  programme?: AuditProgramme,
  optimizer?: AuditProgrammeOptimizer,
): AuditProgrammeReadiness {
  const items = programme?.items || [];
  const server = programme?.readiness;
  const blockers = server ? [...server.blockers] : ([] as Array<{ code: string; message: string }>);
  if (!server) {
    if (!items.length) blockers.push({ code: "NO_REQUIREMENTS", message: "No governed audit coverage is defined yet." });
    if (!programme?.regulatory_basis?.length) blockers.push({ code: "NO_COMPLIANCE_BASIS", message: "Add the applicable compliance baseline before approval." });
    items.forEach((item) => {
      if (!item.target_start || !item.target_end) blockers.push({ code: "MISSING_TARGET_WINDOW", message: `${item.title}: set a target window.` });
      if (!item.criteria?.length) blockers.push({ code: "MISSING_CRITERIA", message: `${item.title}: add audit criteria.` });
    });
  }
  const mandatoryGaps = optimizer?.summary?.mandatory_coverage_gaps || 0;
  if (mandatoryGaps && !blockers.some((entry) => entry.code === "MANDATORY_COVERAGE_GAP")) {
    blockers.push({
      code: "MANDATORY_COVERAGE_GAP",
      message: `${mandatoryGaps} mandatory surveillance requirement(s) due this period are not covered.`,
    });
  }
  return {
    ready_for_approval: blockers.length === 0,
    blockers,
    requirement_count: server?.requirement_count ?? items.length,
    mandatory_requirement_count: server?.mandatory_requirement_count ?? items.filter((item) => item.mandatory_surveillance).length,
    mandatory_unscheduled_count:
      server?.mandatory_unscheduled_count ?? items.filter((item) => item.mandatory_surveillance && item.state === "PLANNED").length,
    high_risk_requirement_count:
      server?.high_risk_requirement_count ??
      items.filter((item) => ["HIGH", "CRITICAL"].includes(item.auditable_entity?.risk_classification || "")).length,
    unscheduled_requirement_count: server?.unscheduled_requirement_count ?? items.filter((item) => item.state === "PLANNED").length,
    mandatory_coverage_gap_count: server?.mandatory_coverage_gap_count ?? mandatoryGaps,
  };
}

export function listedReadinessOf(programme: AuditProgramme): AuditProgrammeReadiness | null {
  // Programme readiness is the single source of truth; list consumers must never infer it from generic audit metrics.
  return programme.readiness ? readinessOf(programme) : null;
}

export function readinessExceptionCount(readiness: AuditProgrammeReadiness): number {
  return readiness.blockers.length;
}

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
  weekend_policy?: "INCLUDE_WEEKEND" | "SKIP_WEEKEND";
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

function jsonOptions(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
}

export function listAuditProgrammes(amoCode: string, year?: number, signal?: AbortSignal): Promise<AuditProgrammeList> {
  const params = new URLSearchParams({ limit: "50", offset: "0" });
  if (year) params.set("year", String(year));
  return apiRequest(qmsPath(amoCode, `/audit-programmes?${params.toString()}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function getAuditProgramme(amoCode: string, programmeId: string, signal?: AbortSignal): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function getAuditProgrammeOptimizer(amoCode: string, programmeId: string, signal?: AbortSignal): Promise<AuditProgrammeOptimizer> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/optimizer`), { timeoutMs: 20_000, cacheTtlMs: 3_000, signal });
}

export function rebuildAuditProgrammeOptimizer(amoCode: string, programmeId: string): Promise<AuditProgrammeOptimizer> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/optimizer/rebuild`), jsonOptions("POST"));
}

export function createAuditProgramme(amoCode: string, payload: {
  programme_year: number;
  programme_kind: "INTERNAL" | "EXTERNAL" | "THIRD_PARTY";
  title?: string;
  objectives: string[];
  regulatory_basis: Array<string | Record<string, unknown>>;
  period_start: string;
  period_end: string;
}): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, "/audit-programmes"), jsonOptions("POST", payload));
}

export function updateAuditProgramme(
  amoCode: string,
  programmeId: string,
  payload: {
    title?: string;
    objectives?: string[];
    regulatory_basis?: Array<string | Record<string, unknown>>;
    period_start?: string;
    period_end?: string;
    owner_user_id?: string;
    reason: string;
  },
): Promise<AuditProgramme> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}`), jsonOptions("PATCH", payload));
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

export function updateAuditUniverseItem(amoCode: string, universeItemId: string, payload: {
  display_label?: string;
  source_route?: string | null;
  risk_classification?: AuditRiskLevel;
  regulatory_criticality?: AuditRiskLevel;
  surveillance_interval_days?: number | null;
  mandatory_surveillance?: boolean;
  active?: boolean;
  notes?: string | null;
}): Promise<AuditUniverseItem> {
  return apiRequest(
    qmsPath(amoCode, `/audit-programmes/universe/items/${encodeURIComponent(universeItemId)}`),
    jsonOptions("PATCH", payload),
  );
}

export function addAuditProgrammeItem(amoCode: string, programmeId: string, payload: {
  universe_item_id: string; audit_type: string; title: string; purpose?: string; scope: string;
  criteria: string[]; mandatory_surveillance: boolean; recurrence: string; target_start?: string; target_end?: string;
  prioritization_basis: Array<Record<string, unknown>>;
}): Promise<AuditProgrammeItem> {
  return apiRequest(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/items`), jsonOptions("POST", payload));
}

export function updateAuditProgrammeItem(
  amoCode: string,
  programmeId: string,
  itemId: string,
  payload: {
    title?: string;
    purpose?: string | null;
    scope?: string;
    criteria?: Array<string | Record<string, unknown>>;
    mandatory_surveillance?: boolean;
    recurrence?: string;
    custom_interval_days?: number | null;
    target_start?: string | null;
    target_end?: string | null;
    prioritization_basis?: Array<Record<string, unknown>>;
    state?: AuditProgrammeItemState;
    deferral_reason?: string | null;
    cancellation_reason?: string | null;
    reason: string;
  },
): Promise<AuditProgrammeItem> {
  return apiRequest(
    qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/items/${encodeURIComponent(itemId)}`),
    jsonOptions("PATCH", payload),
  );
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
