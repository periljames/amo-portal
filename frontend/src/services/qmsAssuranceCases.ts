import { apiRequest, qmsPath } from "./apiClient";

export type QmsAssuranceCaseStatus = "OPEN" | "INVESTIGATING" | "ACTION_PENDING" | "EFFECTIVENESS_REVIEW" | "CLOSED" | "CANCELLED";
export type QmsAssuranceCaseType = "SIGNAL" | "INVESTIGATION" | "RECURRING_FINDING" | "EFFECTIVENESS" | "SUPPLIER" | "REGULATORY" | "OTHER";
export type QmsAssuranceSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type QmsInvestigationMethod = "FIVE_WHYS" | "ISHIKAWA" | "CAUSAL_FACTOR" | "BARRIER_ANALYSIS" | "CHANGE_ANALYSIS" | "HUMAN_ORGANIZATIONAL";
export type QmsInvestigationEntryType = "FACT" | "HYPOTHESIS" | "CAUSAL_CONCLUSION";
export type QmsEffectivenessConclusion = "EFFECTIVE" | "PARTIALLY_EFFECTIVE" | "INEFFECTIVE" | "INCONCLUSIVE";

export type QmsInvestigationEntry = {
  id: string;
  method: QmsInvestigationMethod;
  entry_type: QmsInvestigationEntryType;
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

export type QmsEffectivenessPlan = {
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
  conclusion?: QmsEffectivenessConclusion | null;
  conclusion_rationale?: string | null;
  conclusion_evidence: Array<Record<string, unknown>>;
  concluded_by_user_id?: string | null;
  concluded_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type QmsAssuranceCase = {
  id: string;
  case_ref: string;
  case_type: QmsAssuranceCaseType;
  title: string;
  description?: string | null;
  severity: QmsAssuranceSeverity;
  status: QmsAssuranceCaseStatus;
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
  investigation_entries?: QmsInvestigationEntry[];
  effectiveness_plans?: QmsEffectivenessPlan[];
  events?: Array<Record<string, unknown>>;
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listQmsAssuranceCases(
  amoCode: string,
  options: { status?: QmsAssuranceCaseStatus; caseType?: QmsAssuranceCaseType; severity?: QmsAssuranceSeverity; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<{ items: QmsAssuranceCase[]; total: number; limit: number; offset: number; has_more: boolean }> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.caseType) params.set("case_type", options.caseType);
  if (options.severity) params.set("severity", options.severity);
  params.set("limit", String(options.limit ?? 100));
  params.set("offset", String(options.offset ?? 0));
  return apiRequest(qmsPath(amoCode, `/assurance-cases?${params.toString()}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function getQmsAssuranceCase(amoCode: string, caseId: string, signal?: AbortSignal): Promise<QmsAssuranceCase> {
  return apiRequest<QmsAssuranceCase>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function createQmsAssuranceCase(
  amoCode: string,
  payload: {
    case_type: QmsAssuranceCaseType;
    title: string;
    description?: string;
    severity?: QmsAssuranceSeverity;
    source_references?: Array<Record<string, unknown>>;
    regulatory_basis?: Array<Record<string, unknown> | string>;
    owner_user_id?: string;
    due_date?: string;
  },
): Promise<QmsAssuranceCase> {
  return apiRequest<QmsAssuranceCase>(qmsPath(amoCode, "/assurance-cases"), jsonOptions("POST", payload));
}

export function transitionQmsAssuranceCase(amoCode: string, caseId: string, nextStatus: QmsAssuranceCaseStatus, reason: string): Promise<QmsAssuranceCase> {
  return apiRequest<QmsAssuranceCase>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/transitions`), jsonOptions("POST", { status: nextStatus, reason }));
}

export function addQmsInvestigationEntry(
  amoCode: string,
  caseId: string,
  payload: {
    method: QmsInvestigationMethod;
    entry_type: QmsInvestigationEntryType;
    sequence_no?: number;
    category?: string;
    prompt?: string;
    statement: string;
    confidence?: number;
    evidence_references?: Array<Record<string, unknown>>;
    parent_entry_id?: string;
  },
): Promise<QmsInvestigationEntry> {
  return apiRequest<QmsInvestigationEntry>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/investigation`), jsonOptions("POST", payload));
}

export function createQmsEffectivenessPlan(
  amoCode: string,
  caseId: string,
  payload: {
    source_type?: string;
    source_id?: string;
    source_route?: string;
    expected_outcome: string;
    effectiveness_measure: string;
    verification_method: string;
    observation_window?: string;
    source_indicators?: Array<Record<string, unknown>>;
    responsible_reviewer_user_id?: string;
    planned_review_date: string;
  },
): Promise<QmsEffectivenessPlan> {
  return apiRequest<QmsEffectivenessPlan>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-plans`), jsonOptions("POST", payload));
}

export function concludeQmsEffectivenessPlan(
  amoCode: string,
  caseId: string,
  planId: string,
  payload: { conclusion: QmsEffectivenessConclusion; rationale: string; evidence_references: Array<Record<string, unknown>> },
): Promise<{ case: QmsAssuranceCase; effectiveness_plan: QmsEffectivenessPlan }> {
  return apiRequest(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-plans/${encodeURIComponent(planId)}/conclusion`), jsonOptions("POST", payload));
}
