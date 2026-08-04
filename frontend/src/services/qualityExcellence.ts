import { apiRequest, qualityPath } from "./apiClient";

export type ReadinessBand = "STRONG" | "WATCH" | "AT_RISK" | "CRITICAL";
export type ControlCriticality = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ControlStatus = "DRAFT" | "ACTIVE" | "RETIRED";
export type EvidenceStatus = "LINKED" | "VERIFIED" | "EXPIRED" | "REJECTED";
export type InsightStatus = "PROPOSED" | "ACCEPTED" | "DISMISSED" | "IMPLEMENTED";
export type RiskLevel = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ExcellenceDimension = {
  id: string;
  label: string;
  score: number;
  weight: number;
};

export type ExcellencePriority = {
  id: string;
  label: string;
  count: number;
  severity: RiskLevel;
  why: string;
  path: string;
};

export type ExcellenceOverview = {
  tenant: { amo_code: string; amo_id: string };
  as_of: string;
  readiness: {
    score: number;
    band: ReadinessBand;
    dimensions: ExcellenceDimension[];
    method: string;
    disclaimer: string;
  };
  metrics: Record<string, number>;
  priority_queue: ExcellencePriority[];
  forecast: {
    commitments_due_30_days: number;
    band: "MANAGEABLE" | "ELEVATED" | "HEAVY";
    explanation: string;
  };
  capabilities: Array<{ id: string; label: string; description: string; path: string }>;
  warnings: Array<{ source: string; message: string; type: string }>;
};

export type AssuranceControl = {
  id: string;
  control_code: string;
  title: string;
  description: string | null;
  framework: string;
  clause_reference: string | null;
  process_area: string;
  owner_user_id: string | null;
  criticality: ControlCriticality;
  status: ControlStatus;
  test_frequency_days: number;
  evidence_expectation: string | null;
  last_tested_at: string | null;
  next_test_due: string | null;
  due_state: "UNSCHEDULED" | "OVERDUE" | "DUE_SOON" | "CURRENT";
  evidence_count: number;
  verified_evidence_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type AssuranceControlCreate = {
  control_code: string;
  title: string;
  description?: string | null;
  framework: string;
  clause_reference?: string | null;
  process_area: string;
  owner_user_id?: string | null;
  criticality: ControlCriticality;
  status: ControlStatus;
  test_frequency_days: number;
  evidence_expectation?: string | null;
  last_tested_at?: string | null;
  next_test_due?: string | null;
};

export type AssuranceEvidence = {
  id: string;
  control_id: string;
  source_type: string;
  source_id: string;
  relationship: string;
  label: string | null;
  evidence_status: EvidenceStatus;
  valid_until: string | null;
  notes: string | null;
  verified_at: string | null;
  created_at: string | null;
};

export type EvidenceGraph = {
  nodes: Array<{
    id: string;
    kind: "control" | "evidence";
    label: string;
    type?: string;
    framework?: string;
    process_area?: string;
    criticality?: ControlCriticality;
    status?: string;
  }>;
  edges: Array<{
    id: string;
    from: string;
    to: string;
    relationship: string;
    status: EvidenceStatus;
    valid_until: string | null;
  }>;
  summary: {
    controls: number;
    evidence_records: number;
    relationships: number;
    controls_without_evidence: number;
  };
  as_of: string;
};

export type QualityInsight = {
  id: string;
  insight_type: string;
  title: string;
  rationale: string;
  recommendation: string | null;
  payload: Record<string, unknown>;
  source_fingerprint: string;
  risk_level: RiskLevel;
  status: InsightStatus;
  created_by: "RULE_ENGINE" | "HUMAN" | string;
  human_decision_by_user_id: string | null;
  human_decision_note: string | null;
  decision_at: string | null;
  created_at: string | null;
};

type ControlListResponse = { items: AssuranceControl[]; total: number; as_of: string };
type InsightListResponse = { items: QualityInsight[]; total: number; as_of: string };

export function getQualityExcellenceOverview(amoCode: string): Promise<ExcellenceOverview> {
  return apiRequest<ExcellenceOverview>(qualityPath(amoCode, "/excellence/overview"), {
    cacheTtlMs: 10_000,
    timeoutMs: 20_000,
  });
}

export function getAssuranceControls(amoCode: string): Promise<ControlListResponse> {
  return apiRequest<ControlListResponse>(qualityPath(amoCode, "/excellence/controls"), {
    cacheTtlMs: 15_000,
    timeoutMs: 20_000,
  });
}

export function createAssuranceControl(
  amoCode: string,
  payload: AssuranceControlCreate,
): Promise<AssuranceControl> {
  return apiRequest<AssuranceControl>(qualityPath(amoCode, "/excellence/controls"), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 20_000,
  });
}

export function updateAssuranceControl(
  amoCode: string,
  controlId: string,
  payload: Partial<AssuranceControlCreate>,
): Promise<AssuranceControl> {
  return apiRequest<AssuranceControl>(qualityPath(amoCode, `/excellence/controls/${encodeURIComponent(controlId)}`), {
    method: "PATCH",
    body: JSON.stringify(payload),
    timeoutMs: 20_000,
  });
}

export function linkAssuranceEvidence(
  amoCode: string,
  controlId: string,
  payload: {
    source_type: string;
    source_id: string;
    relationship?: string;
    label?: string | null;
    evidence_status?: EvidenceStatus;
    valid_until?: string | null;
    notes?: string | null;
  },
): Promise<AssuranceEvidence> {
  return apiRequest<AssuranceEvidence>(qualityPath(amoCode, `/excellence/controls/${encodeURIComponent(controlId)}/evidence`), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 20_000,
  });
}

export function getAssuranceEvidenceGraph(amoCode: string): Promise<EvidenceGraph> {
  return apiRequest<EvidenceGraph>(qualityPath(amoCode, "/excellence/evidence-graph"), {
    cacheTtlMs: 15_000,
    timeoutMs: 20_000,
  });
}

export function getQualityInsights(amoCode: string): Promise<InsightListResponse> {
  return apiRequest<InsightListResponse>(qualityPath(amoCode, "/excellence/insights"), {
    cacheTtlMs: 10_000,
    timeoutMs: 20_000,
  });
}

export function rebuildQualityInsights(amoCode: string): Promise<{
  generated: number;
  skipped_existing: number;
  items: QualityInsight[];
}> {
  return apiRequest<{ generated: number; skipped_existing: number; items: QualityInsight[] }>(
    qualityPath(amoCode, "/excellence/insights/rebuild"),
    { method: "POST", timeoutMs: 30_000 },
  );
}

export function decideQualityInsight(
  amoCode: string,
  insightId: string,
  status: InsightStatus,
  note?: string,
): Promise<QualityInsight> {
  return apiRequest<QualityInsight>(qualityPath(amoCode, `/excellence/insights/${encodeURIComponent(insightId)}`), {
    method: "PATCH",
    body: JSON.stringify({ status, note: note || null }),
    timeoutMs: 20_000,
  });
}
