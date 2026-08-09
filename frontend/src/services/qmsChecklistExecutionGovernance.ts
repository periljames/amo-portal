import { apiRequest, qmsPath } from "./apiClient";

export type CanonicalChecklistResponse = "COMPLIANT" | "NONCOMPLIANT" | "OBSERVATION" | "NOT_APPLICABLE" | "NOT_VERIFIED";

export type ChecklistExecutionGovernanceRow = {
  checklist_item_id: string;
  audit_id: string;
  section?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  prompt: string;
  legacy_response_status: string;
  canonical_response_status: CanonicalChecklistResponse;
  objective_evidence?: string | null;
  finding_id?: string | null;
  auditor_notes?: string | null;
  evidence_references: Array<Record<string, unknown> | string>;
  governance_id?: string | null;
  updated_by_user_id?: string | null;
  updated_at?: string | null;
  events: Array<{
    id: string;
    event_type: "CREATED" | "UPDATED";
    reason: string;
    before_snapshot?: Record<string, unknown> | null;
    after_snapshot: Record<string, unknown>;
    actor_user_id?: string | null;
    created_at: string;
  }>;
};

export type ChecklistExecutionGovernanceResponse = {
  items: ChecklistExecutionGovernanceRow[];
  canonical_response_values: CanonicalChecklistResponse[];
  legacy_compatibility: Record<string, string>;
};

export function listChecklistExecutionGovernance(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<ChecklistExecutionGovernanceResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-execution-governance`),
    { timeoutMs: 15_000, cacheTtlMs: 2_000, signal },
  );
}

export function updateChecklistExecutionGovernance(
  amoCode: string,
  auditId: string,
  itemId: string,
  payload: {
    canonical_response_status: CanonicalChecklistResponse;
    auditor_notes?: string | null;
    evidence_references?: Array<Record<string, unknown> | string>;
    reason: string;
  },
) {
  return apiRequest<ChecklistExecutionGovernanceRow>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(itemId)}/execution-governance`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}
