import { apiRequest, qmsPath } from "./apiClient";

export type AuditAssignmentRole = "LEAD_AUDITOR" | "OBSERVER_AUDITOR" | "ASSISTANT_AUDITOR";

export type AuditAssignmentIndependence = {
  required?: boolean;
  passed?: boolean;
  pending?: boolean;
  declaration?: string | null;
  declaration_id?: string | null;
  rationale?: string | null;
  declared_at?: string | null;
  message?: string | null;
};

export type AuditAssignmentAssessment = {
  rule_id?: string;
  privilege_code?: string;
  privilege_type?: string;
  hard_gates?: Record<string, boolean>;
  active_privilege?: Record<string, unknown> | null;
  training?: Record<string, unknown> | null;
  capacity?: Record<string, unknown> | null;
  independence?: AuditAssignmentIndependence | null;
  eligible?: boolean;
};

export type AuditAssignmentEligibility = {
  eligible: boolean;
  governance_configured: boolean;
  mode: "GOVERNED" | "LEGACY_COMPATIBILITY" | string;
  assignment_role: AuditAssignmentRole;
  user_id: string;
  reason?: string | null;
  rule_id?: string | null;
  privilege_code?: string | null;
  independence_pending?: boolean;
  assessment?: AuditAssignmentAssessment | null;
  assessments: AuditAssignmentAssessment[];
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
    previous_assignments: {
      lead_auditor_user_id: string | null;
      observer_auditor_user_id: string | null;
      assistant_auditor_user_id: string | null;
    };
    assignment_gate: AuditAssignmentEligibility[];
    reason: string;
  }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/assignments`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
