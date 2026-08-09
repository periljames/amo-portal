import { apiRequest, qmsPath } from "./apiClient";

export type QmsMissionType =
  | "CAPABILITY_ADDITION"
  | "CAPABILITY_CHANGE"
  | "LINE_STATION"
  | "SUPPLIER_APPROVAL"
  | "SUBCONTRACTOR_APPROVAL"
  | "REGULATORY_TRANSITION"
  | "AMO_RENEWAL"
  | "AUTHORIZATION_CAMPAIGN"
  | "PROCEDURE_CHANGE"
  | "IMPROVEMENT";

export type QmsMissionStatus =
  | "DRAFT"
  | "PLANNING"
  | "IN_PROGRESS"
  | "GATE_REVIEW"
  | "READY_FOR_APPROVAL"
  | "APPROVED"
  | "SUBMITTED_TO_AUTHORITY"
  | "COMPLETE"
  | "CANCELLED";

export type QmsMissionRisk = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type QmsMissionGateStatus = "PENDING" | "IN_PROGRESS" | "PASS" | "FAIL" | "BLOCKED";
export type QmsMissionEvidenceStatus = "UNLINKED" | "LINKED" | "VERIFIED" | "REJECTED" | "EXPIRED";
export type QmsMissionDecisionType =
  | "QUALITY_SELF_EVALUATION"
  | "ACCOUNTABLE_EXECUTIVE"
  | "AUTHORITY_SUBMISSION"
  | "AUTHORITY_ACCEPTANCE"
  | "CUSTOM";
export type QmsMissionDecisionStatus = "APPROVED" | "REJECTED" | "RETURNED";

export type QmsMissionReadiness = {
  hard_gates: { passed: number; total: number };
  soft_gates: { passed: number; total: number };
  ready_for_quality_self_evaluation: boolean;
  blocking_gates: Array<{
    id: string;
    gate_code: string;
    title: string;
    status: QmsMissionGateStatus;
    evidence_status: QmsMissionEvidenceStatus;
    blocking_reason?: string | null;
  }>;
};

export type QmsMissionGate = {
  id: string;
  gate_code: string;
  title: string;
  category: string;
  description?: string | null;
  gate_type: "HARD" | "SOFT";
  status: QmsMissionGateStatus;
  requirement_ref?: string | null;
  source_owner_module?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  source_route?: string | null;
  source_snapshot?: Record<string, unknown> | null;
  evidence_status: QmsMissionEvidenceStatus;
  owner_user_id?: string | null;
  due_date?: string | null;
  blocking_reason?: string | null;
  sort_order: number;
  passed_at?: string | null;
  passed_by_user_id?: string | null;
  updated_at?: string | null;
};

export type QmsMissionDecision = {
  id: string;
  decision_type: QmsMissionDecisionType;
  status: QmsMissionDecisionStatus;
  rationale: string;
  evidence_snapshot?: Record<string, unknown> | null;
  decided_by_user_id?: string | null;
  decided_at: string;
};

export type QmsMission = {
  id: string;
  mission_ref: string;
  mission_type: QmsMissionType;
  title: string;
  description?: string | null;
  scope: Record<string, unknown>;
  regulatory_basis: Array<Record<string, unknown> | string>;
  risk_level: QmsMissionRisk;
  status: QmsMissionStatus;
  owner_user_id?: string | null;
  requested_by_user_id?: string | null;
  sponsor_user_id?: string | null;
  requested_at: string;
  target_date?: string | null;
  started_at?: string | null;
  approved_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  readiness: QmsMissionReadiness;
  gates?: QmsMissionGate[];
  decisions?: QmsMissionDecision[];
};

export type QmsMissionListResponse = {
  items: QmsMission[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type QmsMissionCreate = {
  mission_type: QmsMissionType;
  title: string;
  description?: string;
  scope?: Record<string, unknown>;
  regulatory_basis?: Array<Record<string, unknown> | string>;
  risk_level?: QmsMissionRisk;
  owner_user_id?: string;
  sponsor_user_id?: string;
  target_date?: string;
};

export type QmsMissionGatePatch = {
  status?: QmsMissionGateStatus;
  source_owner_module?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  source_route?: string | null;
  source_snapshot?: Record<string, unknown> | null;
  evidence_status?: QmsMissionEvidenceStatus;
  owner_user_id?: string | null;
  due_date?: string | null;
  blocking_reason?: string | null;
};

export type QmsMissionDecisionCreate = {
  decision_type: QmsMissionDecisionType;
  status: QmsMissionDecisionStatus;
  rationale: string;
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function listQmsMissions(
  amoCode: string,
  options: { status?: QmsMissionStatus; missionType?: QmsMissionType; ownerUserId?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<QmsMissionListResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.missionType) params.set("mission_type", options.missionType);
  if (options.ownerUserId) params.set("owner_user_id", options.ownerUserId);
  params.set("limit", String(options.limit ?? 25));
  params.set("offset", String(options.offset ?? 0));
  return apiRequest<QmsMissionListResponse>(qmsPath(amoCode, `/missions?${params.toString()}`), {
    timeoutMs: 15_000,
    cacheTtlMs: 10_000,
    signal,
  });
}

export function getQmsMission(amoCode: string, missionId: string, signal?: AbortSignal): Promise<QmsMission> {
  return apiRequest<QmsMission>(qmsPath(amoCode, `/missions/${encodeURIComponent(missionId)}`), {
    timeoutMs: 15_000,
    cacheTtlMs: 5_000,
    signal,
  });
}

export function createQmsMission(amoCode: string, payload: QmsMissionCreate): Promise<QmsMission> {
  return apiRequest<QmsMission>(qmsPath(amoCode, "/missions"), jsonOptions("POST", payload));
}

export function updateQmsMissionGate(
  amoCode: string,
  missionId: string,
  gateId: string,
  payload: QmsMissionGatePatch,
): Promise<QmsMission> {
  return apiRequest<QmsMission>(
    qmsPath(amoCode, `/missions/${encodeURIComponent(missionId)}/gates/${encodeURIComponent(gateId)}`),
    jsonOptions("PATCH", payload),
  );
}

export function recordQmsMissionDecision(
  amoCode: string,
  missionId: string,
  payload: QmsMissionDecisionCreate,
): Promise<QmsMission> {
  return apiRequest<QmsMission>(
    qmsPath(amoCode, `/missions/${encodeURIComponent(missionId)}/decisions`),
    jsonOptions("POST", payload),
  );
}
