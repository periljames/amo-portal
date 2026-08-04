import { apiRequest, qualityPath } from "./apiClient";

export type ReadinessBand = "STRONG" | "WATCH" | "AT_RISK" | "CRITICAL";
export type ControlCriticality = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ControlStatus = "DRAFT" | "ACTIVE" | "RETIRED";
export type ControlApprovalStatus = "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "RETIRED";
export type ControlTestResult = "PASS" | "FAIL" | "PARTIAL" | "NOT_TESTED";
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
  source_coverage?: { available: number; warnings: number };
  warnings: Array<{ source: string; message: string; type: string }>;
};

export type AssuranceControl = {
  id: string;
  control_code: string;
  title: string;
  description: string | null;
  control_objective: string | null;
  test_method: string | null;
  framework: string;
  clause_reference: string | null;
  process_area: string;
  owner_user_id: string | null;
  criticality: ControlCriticality;
  status: ControlStatus;
  approval_status: ControlApprovalStatus;
  version_no: number;
  test_frequency_days: number;
  evidence_expectation: string | null;
  last_tested_at: string | null;
  next_test_due: string | null;
  due_state: "UNSCHEDULED" | "OVERDUE" | "DUE_SOON" | "CURRENT";
  evidence_count: number;
  verified_evidence_count: number;
  latest_test_result: ControlTestResult | null;
  latest_tested_at: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AssuranceControlCreate = {
  control_code: string;
  title: string;
  description?: string | null;
  control_objective?: string | null;
  test_method?: string | null;
  framework: string;
  clause_reference?: string | null;
  process_area: string;
  owner_user_id?: string | null;
  criticality: ControlCriticality;
  status: ControlStatus;
  approval_status?: ControlApprovalStatus;
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
  source_table: string | null;
  source_route: string | null;
  source_label: string | null;
  source_snapshot: Record<string, unknown>;
  relationship: string;
  label: string | null;
  evidence_status: EvidenceStatus;
  valid_until: string | null;
  notes: string | null;
  verified_at: string | null;
  source_verified_at: string | null;
  last_synced_at: string | null;
  invalidated_at: string | null;
  invalidation_reason: string | null;
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
    approval_status?: ControlApprovalStatus;
    version_no?: number;
    route?: string | null;
    last_synced_at?: string | null;
    invalidation_reason?: string | null;
  }>;
  edges: Array<{
    id: string;
    from: string;
    to: string;
    relationship: string;
    status: EvidenceStatus;
    valid_until: string | null;
    source_route?: string | null;
    last_synced_at?: string | null;
    invalidation_reason?: string | null;
  }>;
  summary: {
    controls: number;
    evidence_records: number;
    relationships: number;
    controls_without_evidence: number;
    invalid_relationships?: number;
    verified_relationships?: number;
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

export type SourceCatalogItem = {
  source_type: string;
  label: string;
  table: string;
  available: boolean;
  description: string;
};

export type SourceSearchItem = {
  id: string;
  label: string;
  status: string | null;
  valid_until: string | null;
  route: string;
  snapshot: Record<string, unknown>;
};

export type ControlTest = {
  id: string;
  control_id: string;
  result: ControlTestResult;
  tested_at: string | null;
  tested_by_user_id: string | null;
  method: string | null;
  notes: string | null;
  evidence_summary: Record<string, unknown>;
  next_test_due: string | null;
  created_at: string | null;
};

export type AssuranceEvent = {
  id: string;
  source_table: string;
  source_type: string;
  source_id: string;
  event_type: "INSERT" | "UPDATE" | "DELETE";
  changed_fields: string[];
  processing_status: "PENDING" | "PROCESSED" | "ERROR";
  processing_error: string | null;
  actor_user_id: string | null;
  occurred_at: string | null;
  processed_at: string | null;
};

export type ManagementReviewPack = {
  generated_at: string;
  tenant: { amo_code: string; amo_id: string };
  readiness: ExcellenceOverview["readiness"];
  executive_summary: string[];
  decisions_required: Array<{
    title: string;
    reason: string;
    severity: RiskLevel;
    count: number;
    path: string;
  }>;
  metrics: Record<string, number>;
  evidence_gaps: {
    invalid_evidence: number;
    controls_due: number;
    pending_events: number;
  };
  source_warnings: Array<{ source: string; message: string; type: string }>;
};

type ControlListResponse = { items: AssuranceControl[]; total: number; as_of: string };
type InsightListResponse = { items: QualityInsight[]; total: number; as_of: string };

export function getQualityExcellenceOverview(amoCode: string): Promise<ExcellenceOverview> {
  return apiRequest<ExcellenceOverview>(qualityPath(amoCode, "/excellence/overview/full"), {
    cacheTtlMs: 10_000,
    timeoutMs: 25_000,
  });
}

export function getAssuranceControls(amoCode: string): Promise<ControlListResponse> {
  return apiRequest<ControlListResponse>(qualityPath(amoCode, "/excellence/controls"), {
    cacheTtlMs: 12_000,
    timeoutMs: 20_000,
  });
}

export function createAssuranceControl(amoCode: string, payload: AssuranceControlCreate): Promise<AssuranceControl> {
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

export function decideControlApproval(
  amoCode: string,
  controlId: string,
  approvalStatus: Exclude<ControlApprovalStatus, "DRAFT">,
  note?: string,
): Promise<AssuranceControl> {
  return apiRequest<AssuranceControl>(qualityPath(amoCode, `/excellence/controls/${encodeURIComponent(controlId)}/approval`), {
    method: "POST",
    body: JSON.stringify({ approval_status: approvalStatus, note: note || null }),
    timeoutMs: 20_000,
  });
}

export function recordControlTest(
  amoCode: string,
  controlId: string,
  payload: {
    result: ControlTestResult;
    tested_at?: string | null;
    method?: string | null;
    notes?: string | null;
    evidence_summary?: Record<string, unknown>;
    next_test_due?: string | null;
  },
): Promise<ControlTest> {
  return apiRequest<ControlTest>(qualityPath(amoCode, `/excellence/controls/${encodeURIComponent(controlId)}/tests`), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 20_000,
  });
}

export function getControlTests(amoCode: string, controlId: string): Promise<{ items: ControlTest[]; total: number }> {
  return apiRequest<{ items: ControlTest[]; total: number }>(qualityPath(amoCode, `/excellence/controls/${encodeURIComponent(controlId)}/tests`), {
    cacheTtlMs: 10_000,
    timeoutMs: 20_000,
  });
}

export function getEvidenceSourceCatalog(amoCode: string): Promise<{ items: SourceCatalogItem[] }> {
  return apiRequest<{ items: SourceCatalogItem[] }>(qualityPath(amoCode, "/excellence/source-catalog"), {
    cacheTtlMs: 60_000,
    timeoutMs: 20_000,
  });
}

export function searchEvidenceSources(
  amoCode: string,
  sourceType: string,
  query: string,
): Promise<{ source_type: string; items: SourceSearchItem[]; warning?: string }> {
  const params = new URLSearchParams({ source_type: sourceType, q: query, limit: "25" });
  return apiRequest<{ source_type: string; items: SourceSearchItem[]; warning?: string }>(
    `${qualityPath(amoCode, "/excellence/source-search")}?${params.toString()}`,
    { cacheTtlMs: 5_000, timeoutMs: 20_000 },
  );
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

export function decideAssuranceEvidence(
  amoCode: string,
  evidenceId: string,
  evidenceStatus: EvidenceStatus,
  note?: string,
): Promise<AssuranceEvidence> {
  return apiRequest<AssuranceEvidence>(qualityPath(amoCode, `/excellence/evidence/${encodeURIComponent(evidenceId)}`), {
    method: "PATCH",
    body: JSON.stringify({ evidence_status: evidenceStatus, note: note || null }),
    timeoutMs: 20_000,
  });
}

export function getAssuranceEvidenceGraph(amoCode: string): Promise<EvidenceGraph> {
  return apiRequest<EvidenceGraph>(qualityPath(amoCode, "/excellence/evidence-graph"), {
    cacheTtlMs: 10_000,
    timeoutMs: 20_000,
  });
}

export function reconcileAssuranceEvidence(amoCode: string): Promise<{
  reviewed: number;
  changed: number;
  rejected: number;
  events_processed: number;
  errors: Array<{ evidence_id: string; message: string }>;
  as_of: string;
}> {
  return apiRequest(qualityPath(amoCode, "/excellence/reconcile"), {
    method: "POST",
    timeoutMs: 45_000,
  });
}

export function getAssuranceEvents(amoCode: string): Promise<{ items: AssuranceEvent[]; total: number }> {
  return apiRequest<{ items: AssuranceEvent[]; total: number }>(qualityPath(amoCode, "/excellence/events?limit=100"), {
    cacheTtlMs: 5_000,
    timeoutMs: 20_000,
  });
}

export function getManagementReviewPack(amoCode: string): Promise<ManagementReviewPack> {
  return apiRequest<ManagementReviewPack>(qualityPath(amoCode, "/excellence/management-review-pack"), {
    cacheTtlMs: 10_000,
    timeoutMs: 25_000,
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
