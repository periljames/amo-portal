import { apiRequest, qmsPath } from "./apiClient";

export type AuditAssignmentRole = "LEAD_AUDITOR" | "OBSERVER_AUDITOR" | "ASSISTANT_AUDITOR";

export type AuditAssignmentEligibility = {
  governed: boolean;
  eligible: boolean;
  blockers: Array<{ code: string; message: string }>;
  user_id: string;
  assignment_role: AuditAssignmentRole;
  as_of?: string;
  assignment_scope_key?: string | null;
  privilege?: Record<string, unknown> | null;
  training?: Record<string, unknown> | null;
  independence?: {
    required?: boolean;
    state?: string;
    declaration?: string | null;
    relationship_to_subject?: string | null;
    rationale?: string | null;
    declaration_id?: string | null;
  } | null;
  workload?: Record<string, unknown> | null;
};

export function getAuditAssignmentEligibility(
  amoCode: string,
  auditId: string,
  userId: string,
  assignmentRole: AuditAssignmentRole,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ user_id: userId, assignment_role: assignmentRole });
  return apiRequest<AuditAssignmentEligibility>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/assignment-eligibility?${params.toString()}`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function declareAuditIndependence(
  amoCode: string,
  auditId: string,
  payload: {
    user_id: string;
    declaration: "INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW";
    relationship_to_subject?: string | null;
    rationale: string;
    source_references?: Array<Record<string, unknown>>;
  },
) {
  return apiRequest<{
    id: string;
    user_id: string;
    declaration: string;
    rationale: string;
    declared_at: string | null;
  }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/independence`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateAuditAssignments(
  amoCode: string,
  auditId: string,
  payload: {
    lead_auditor_user_id?: string | null;
    observer_auditor_user_id?: string | null;
    assistant_auditor_user_id?: string | null;
    reason: string;
  },
) {
  return apiRequest<{
    audit_id: string;
    lead_auditor_user_id: string | null;
    observer_auditor_user_id: string | null;
    assistant_auditor_user_id: string | null;
    assignment_gate: AuditAssignmentEligibility[];
    reason: string;
  }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/assignments`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
