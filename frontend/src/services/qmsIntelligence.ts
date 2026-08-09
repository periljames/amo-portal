import { apiRequest, qmsPath } from "./apiClient";

export type QmsIntelligenceOverview = {
  as_of: string;
  programme: {
    states: Record<string, number>;
    completion: { numerator: number; denominator: number; value: number | null };
    deferral_rate: { numerator: number; denominator: number; value: number | null };
    calculation: string;
  };
  assurance: { open_cases: number; overdue_cases: number; ineffective_or_inconclusive_reviews: number };
  people: { active_privileges: number; expiring_within_60_days: number };
  controls: { overdue_control_tests: number; failed_or_partial_test_records: number; stale_or_expired_evidence_links: number; proposed_human_reviews: number };
  targeted_surveillance: Array<{
    universe_item_id: string;
    label: string;
    entity_type: string;
    source_owner_module: string;
    source_type: string;
    source_id: string;
    source_route?: string | null;
    mandatory_surveillance: boolean;
    risk_classification: string;
    regulatory_criticality: string;
    surveillance_interval_days?: number | null;
    programme_states: string[];
    priority_order: number;
    factors: Array<{ code: string; label: string; value: unknown; hard_requirement: boolean; source: string; rule: string }>;
    explanation: string;
  }>;
  method: { type: string; statement: string };
};

export type QmsRiskPlanningFactor = {
  code: string;
  label: string;
  value: unknown;
  source: string;
  hard_requirement: boolean;
  rationale: string;
};

export type QmsRiskPlanningContext = {
  as_of: string;
  items: Array<{
    universe_item_id: string;
    label: string;
    entity_type: string;
    source_owner_module: string;
    source_type: string;
    source_id: string;
    source_route?: string | null;
    mandatory_surveillance: boolean;
    risk_classification: string;
    regulatory_criticality: string;
    programme_states: string[];
    planning_order: number;
    factors: QmsRiskPlanningFactor[];
    method: string;
  }>;
  global_factors: QmsRiskPlanningFactor[];
  authoritative_metrics: Record<string, number>;
  reliability: Record<string, number>;
  source_warnings: Array<{ source: string; message: string; type: string }>;
  method: { type: string; statement: string };
};

export type QmsSignalRule = {
  id: string;
  rule_code: string;
  title: string;
  metric: string;
  operator: string;
  threshold: number;
  severity: "INFO" | "WATCH" | "WARNING" | "CRITICAL";
  explanation: string;
  source_contract: Record<string, unknown>;
  is_active: boolean;
};

export type QmsSignalObservation = {
  id: string;
  rule_id?: string;
  rule_code?: string;
  metric: string;
  observed_value?: number;
  value?: number;
  threshold: number;
  operator: string;
  triggered: boolean;
  severity: string;
  explanation: string;
  source_snapshot: Record<string, unknown>;
  source_references?: Array<Record<string, unknown>>;
  as_of: string;
  state?: string;
};

export type QmsRequirementNode = {
  id: string;
  node_type: string;
  title: string;
  source_owner_module: string;
  source_type: string;
  source_id: string;
  source_route?: string | null;
  support_state: "SUPPORTED" | "UNSUPPORTED" | "STALE" | "UNRESOLVED" | "BLOCKED";
  state_reason: string;
  source_snapshot?: Record<string, unknown> | null;
  evidence_as_of?: string | null;
  updated_at: string;
};

export type QmsApprovalTwin = {
  as_of: string;
  assurance_state: "SUPPORTED" | "UNSUPPORTED" | "STALE" | "UNRESOLVED" | "BLOCKED";
  is_compliance_declaration: false;
  state_counts: Record<string, number>;
  blockers: Array<{ id: string; node_type: string; title: string; support_state: string; state_reason: string; source_route?: string | null }>;
  explanation: string;
};

function jsonOptions(method: string, body?: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) };
}

export function getQmsIntelligenceOverview(amoCode: string, signal?: AbortSignal): Promise<QmsIntelligenceOverview> {
  return apiRequest<QmsIntelligenceOverview>(qmsPath(amoCode, "/intelligence/overview"), { timeoutMs: 20_000, cacheTtlMs: 5_000, signal });
}

export function getQmsAuditRiskPlanningContext(amoCode: string, signal?: AbortSignal): Promise<QmsRiskPlanningContext> {
  return apiRequest<QmsRiskPlanningContext>(qmsPath(amoCode, "/audit-programmes/risk-context?limit=100"), { timeoutMs: 20_000, cacheTtlMs: 5_000, signal });
}

export function listQmsSignalRules(amoCode: string, signal?: AbortSignal): Promise<{ items: QmsSignalRule[] }> {
  return apiRequest(qmsPath(amoCode, "/intelligence/signal-rules"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function configureQmsSignalDefaults(amoCode: string): Promise<{ created: number; configured: number }> {
  return apiRequest(qmsPath(amoCode, "/intelligence/signal-rules/defaults"), jsonOptions("POST"));
}

export function evaluateQmsSignals(amoCode: string): Promise<{ as_of: string; evaluated: number; triggered: number; observations: QmsSignalObservation[] }> {
  return apiRequest(qmsPath(amoCode, "/intelligence/signals/evaluate"), jsonOptions("POST"));
}

export function listQmsSignals(amoCode: string, signal?: AbortSignal): Promise<{ items: QmsSignalObservation[] }> {
  return apiRequest(qmsPath(amoCode, "/intelligence/signals?triggered_only=true&limit=100"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getQmsApprovalTwin(amoCode: string, signal?: AbortSignal): Promise<QmsApprovalTwin> {
  return apiRequest(qmsPath(amoCode, "/intelligence/approval-digital-twin"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getQmsApprovalGraph(amoCode: string, signal?: AbortSignal): Promise<{ nodes: QmsRequirementNode[]; links: Array<Record<string, unknown>> }> {
  return apiRequest(qmsPath(amoCode, "/intelligence/approval-graph"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function createQmsRequirementNode(
  amoCode: string,
  payload: {
    node_type: string;
    title: string;
    source_owner_module: string;
    source_type: string;
    source_id: string;
    source_route?: string;
    support_state: QmsRequirementNode["support_state"];
    state_reason: string;
    source_snapshot?: Record<string, unknown>;
    evidence_as_of?: string;
  },
): Promise<QmsRequirementNode> {
  return apiRequest(qmsPath(amoCode, "/intelligence/approval-graph/nodes"), jsonOptions("POST", payload));
}
