import { apiRequest, qmsPath } from "./apiClient";

export type AssuranceCaseStatus = "OPEN" | "INVESTIGATING" | "ACTION_PENDING" | "EFFECTIVENESS_REVIEW" | "CLOSED" | "CANCELLED";
export type AssuranceCaseType = "SIGNAL" | "INVESTIGATION" | "RECURRING_FINDING" | "EFFECTIVENESS" | "SUPPLIER" | "REGULATORY" | "OTHER";
export type AssuranceSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type InvestigationMethod = "FIVE_WHYS" | "ISHIKAWA" | "CAUSAL_FACTOR" | "BARRIER_ANALYSIS" | "CHANGE_ANALYSIS" | "HUMAN_ORGANIZATIONAL";
export type InvestigationEntryType = "FACT" | "HYPOTHESIS" | "CAUSAL_CONCLUSION";
export type EffectivenessConclusion = "EFFECTIVE" | "PARTIALLY_EFFECTIVE" | "INEFFECTIVE" | "INCONCLUSIVE";

export type InvestigationEntry = {
  id: string;
  method: InvestigationMethod;
  entry_type: InvestigationEntryType;
  sequence_no: number;
  category?: string | null;
  prompt?: string | null;
  statement: string;
  confidence?: number | null;
  evidence_references: Array<Record<string, unknown>>;
  parent_entry_id?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
};

export type EffectivenessPlan = {
  id: string;
  source_type?: string | null;
  source_id?: string | null;
  source_route?: string | null;
  expected_outcome: string;
  effectiveness_measure: string;
  verification_method: string;
  observation_window?: string | null;
  source_indicators: Array<Record<string, unknown>>;
  responsible_reviewer_user_id?: string | null;
  planned_review_date: string;
  status: "PLANNED" | "OBSERVING" | "READY_FOR_REVIEW" | "CONCLUDED" | "REOPENED" | "CANCELLED";
  conclusion?: EffectivenessConclusion | null;
  conclusion_rationale?: string | null;
  conclusion_evidence: Array<Record<string, unknown>>;
  concluded_by_user_id?: string | null;
  concluded_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssuranceCaseEvent = {
  id: string;
  event_type: string;
  reason: string;
  before_snapshot?: Record<string, unknown> | null;
  after_snapshot?: Record<string, unknown> | null;
  actor_user_id?: string | null;
  created_at: string;
};

export type AssuranceCase = {
  id: string;
  case_ref: string;
  case_type: AssuranceCaseType;
  title: string;
  description?: string | null;
  severity: AssuranceSeverity;
  status: AssuranceCaseStatus;
  source_references: Array<Record<string, unknown>>;
  regulatory_basis: Array<Record<string, unknown> | string>;
  owner_user_id?: string | null;
  due_date?: string | null;
  opened_at: string;
  closed_at?: string | null;
  closed_by_user_id?: string | null;
  closure_rationale?: string | null;
  created_at: string;
  updated_at: string;
  investigation_entries?: InvestigationEntry[];
  effectiveness_plans?: EffectivenessPlan[];
  events?: AssuranceCaseEvent[];
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listAssuranceCases(amoCode: string, options: { status?: AssuranceCaseStatus; type?: AssuranceCaseType; severity?: AssuranceSeverity; limit?: number; offset?: number } = {}, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.type) params.set("case_type", options.type);
  if (options.severity) params.set("severity", options.severity);
  params.set("limit", String(options.limit ?? 100));
  params.set("offset", String(options.offset ?? 0));
  return apiRequest<{ items: AssuranceCase[]; total: number; limit: number; offset: number; has_more: boolean }>(
    qmsPath(amoCode, `/assurance-cases?${params.toString()}`),
    { timeoutMs: 15_000, cacheTtlMs: 4_000, signal },
  );
}

export function getAssuranceCase(amoCode: string, caseId: string, signal?: AbortSignal) {
  return apiRequest<AssuranceCase>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function createAssuranceCase(amoCode: string, payload: { case_type: AssuranceCaseType; title: string; description?: string; severity: AssuranceSeverity; source_references?: Array<Record<string, unknown>>; regulatory_basis?: Array<Record<string, unknown> | string>; owner_user_id?: string; due_date?: string }) {
  return apiRequest<AssuranceCase>(qmsPath(amoCode, "/assurance-cases"), jsonOptions("POST", payload));
}

export function transitionAssuranceCase(amoCode: string, caseId: string, status: AssuranceCaseStatus, reason: string) {
  return apiRequest<AssuranceCase>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/transitions`), jsonOptions("POST", { status, reason }));
}

export function addInvestigationEntry(amoCode: string, caseId: string, payload: { method: InvestigationMethod; entry_type: InvestigationEntryType; sequence_no?: number; category?: string; prompt?: string; statement: string; confidence?: number; evidence_references?: Array<Record<string, unknown>>; parent_entry_id?: string }) {
  return apiRequest<InvestigationEntry>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/investigation`), jsonOptions("POST", payload));
}

export function createEffectivenessPlan(amoCode: string, caseId: string, payload: { source_type?: string; source_id?: string; source_route?: string; expected_outcome: string; effectiveness_measure: string; verification_method: string; observation_window?: string; source_indicators?: Array<Record<string, unknown>>; responsible_reviewer_user_id?: string; planned_review_date: string }) {
  return apiRequest<EffectivenessPlan>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-plans`), jsonOptions("POST", payload));
}

export function concludeEffectiveness(amoCode: string, caseId: string, planId: string, payload: { conclusion: EffectivenessConclusion; rationale: string; evidence_references: Array<Record<string, unknown>> }) {
  return apiRequest<{ case: AssuranceCase; effectiveness_plan: EffectivenessPlan }>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-plans/${encodeURIComponent(planId)}/conclusion`), jsonOptions("POST", payload));
}
