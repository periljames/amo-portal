import { apiRequest, qmsPath } from "./apiClient";

export type AuditProgrammeStatus = "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "ACTIVE" | "SUPERSEDED" | "CLOSED";
export type AuditRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AuditUniverseEntityType = "DEPARTMENT" | "FACILITY" | "STATION" | "SUPPLIER" | "CONTRACTOR" | "PROCESS" | "CAPABILITY" | "APPROVAL_RATING" | "AIRCRAFT_TYPE" | "PERSONNEL_GROUP" | "OTHER";
export type AuditProgrammeItemState = "PLANNED" | "SCHEDULED" | "COMPLETED" | "DEFERRED" | "CANCELLED" | "FOLLOW_UP_REQUIRED";

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

export type AuditProgramme = {
  id: string;
  programme_ref: string;
  programme_series: string;
  programme_year: number;
  revision_no: number;
  title: string;
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
  };
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
  programme_year: number; title: string; objectives: string[]; regulatory_basis: string[];
  period_start: string; period_end: string;
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
