import { apiRequest, qmsPath } from "./apiClient";

export type QmsPrivilegeRule = {
  id: string;
  privilege_code: string;
  title: string;
  privilege_type: "AUDITOR" | "LEAD_AUDITOR" | "QUALITY_INSPECTOR" | "AUTHORIZATION_REVIEWER" | "CUSTOM";
  description?: string | null;
  required_training_course_codes: string[];
  independence_required: boolean;
  max_concurrent_assignments?: number | null;
  scope_schema: Record<string, unknown>;
  is_active: boolean;
  updated_at: string;
};

export type QmsPrivilegeDecision = {
  id: string;
  decision_type: "GRANT" | "RENEW" | "SUSPEND" | "REINSTATE" | "REVOKE" | "EXPIRE" | "REJECT";
  resulting_status: "DRAFT" | "ACTIVE" | "SUSPENDED" | "REVOKED" | "EXPIRED";
  rationale: string;
  eligibility_snapshot: Record<string, unknown>;
  source_references: Array<Record<string, unknown>>;
  effective_from?: string | null;
  expires_on?: string | null;
  decided_by_user_id?: string | null;
  decided_at: string;
};

export type QmsPrivilege = {
  id: string;
  rule_id: string;
  user_id: string;
  privilege_code: string;
  scope_key: string;
  scope: Record<string, unknown>;
  limitations: Array<Record<string, unknown> | string>;
  status: "DRAFT" | "ACTIVE" | "SUSPENDED" | "REVOKED" | "EXPIRED";
  effective_from?: string | null;
  expires_on?: string | null;
  latest_decision_id?: string | null;
  created_at: string;
  updated_at: string;
  decisions?: QmsPrivilegeDecision[];
};

export type QmsPeopleSummary = {
  active_privileges: number;
  expiring_within_60_days: number;
  suspended_privileges: number;
  independence_exceptions: number;
};

export type QmsEligibility = {
  eligible: boolean;
  as_of: string;
  person: { user_id: string; full_name: string; email?: string | null; role?: string | null };
  rule: { id: string; privilege_code: string; title: string; privilege_type: string };
  hard_gates: Record<string, boolean>;
  training: {
    required: string[];
    satisfied: string[];
    missing: string[];
    records: Array<Record<string, unknown>>;
    passed: boolean;
  };
  independence: Record<string, unknown>;
  workload: Record<string, unknown>;
  active_privilege?: Record<string, unknown> | null;
};

export type QmsAuditorAssignmentRole = "LEAD_AUDITOR" | "OBSERVER_AUDITOR" | "ASSISTANT_AUDITOR";

export type QmsAuditorAssignmentAssessment = {
  rule_id: string;
  privilege_code: string;
  privilege_type: string;
  hard_gates: Record<string, boolean>;
  active_privilege?: {
    id: string;
    scope_key?: string | null;
    effective_from?: string | null;
    expires_on?: string | null;
  } | null;
  training: {
    required: string[];
    satisfied: string[];
    missing: string[];
    records: Array<Record<string, unknown>>;
    passed: boolean;
  };
  capacity: Record<string, unknown> & { passed?: boolean };
  independence: Record<string, unknown> & { passed?: boolean; pending?: boolean; message?: string };
  eligible: boolean;
};

export type QmsAuditorEligibilityPreflight = {
  eligible: boolean;
  governance_configured: boolean;
  mode: "GOVERNED" | "LEGACY_COMPATIBILITY" | string;
  assignment_role: QmsAuditorAssignmentRole;
  user_id: string;
  reason?: string;
  rule_id?: string;
  privilege_code?: string;
  independence_pending?: boolean;
  assessment?: QmsAuditorAssignmentAssessment;
  assessments: QmsAuditorAssignmentAssessment[];
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function getQmsPeopleSummary(amoCode: string, signal?: AbortSignal): Promise<QmsPeopleSummary> {
  return apiRequest<QmsPeopleSummary>(qmsPath(amoCode, "/people/summary"), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function listQmsPrivilegeRules(amoCode: string, signal?: AbortSignal): Promise<{ items: QmsPrivilegeRule[] }> {
  return apiRequest<{ items: QmsPrivilegeRule[] }>(qmsPath(amoCode, "/people/rules"), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function createQmsPrivilegeRule(
  amoCode: string,
  payload: {
    privilege_code: string;
    title: string;
    privilege_type: QmsPrivilegeRule["privilege_type"];
    description?: string;
    required_training_course_codes?: string[];
    independence_required?: boolean;
    max_concurrent_assignments?: number | null;
    scope_schema?: Record<string, unknown>;
  },
): Promise<QmsPrivilegeRule> {
  return apiRequest<QmsPrivilegeRule>(qmsPath(amoCode, "/people/rules"), jsonOptions("POST", payload));
}

export function listQmsPrivileges(
  amoCode: string,
  options: { userId?: string; status?: QmsPrivilege["status"] } = {},
  signal?: AbortSignal,
): Promise<{ items: QmsPrivilege[] }> {
  const params = new URLSearchParams();
  if (options.userId) params.set("user_id", options.userId);
  if (options.status) params.set("status", options.status);
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsPrivilege[] }>(qmsPath(amoCode, `/people/privileges${suffix}`), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function createQmsPrivilege(
  amoCode: string,
  payload: { rule_id: string; user_id: string; scope_key?: string; scope?: Record<string, unknown>; limitations?: Array<Record<string, unknown> | string> },
): Promise<QmsPrivilege> {
  return apiRequest<QmsPrivilege>(qmsPath(amoCode, "/people/privileges"), jsonOptions("POST", payload));
}

export function decideQmsPrivilege(
  amoCode: string,
  privilegeId: string,
  payload: {
    decision_type: QmsPrivilegeDecision["decision_type"];
    rationale: string;
    effective_from?: string;
    expires_on?: string;
    source_references?: Array<Record<string, unknown>>;
  },
): Promise<{ privilege: QmsPrivilege; decision: QmsPrivilegeDecision }> {
  return apiRequest<{ privilege: QmsPrivilege; decision: QmsPrivilegeDecision }>(
    qmsPath(amoCode, `/people/privileges/${encodeURIComponent(privilegeId)}/decisions`),
    jsonOptions("POST", payload),
  );
}

export function getQmsEligibility(
  amoCode: string,
  input: { userId: string; privilegeCode: string; asOf?: string; contextType?: string; contextId?: string },
  signal?: AbortSignal,
): Promise<QmsEligibility> {
  const params = new URLSearchParams({ user_id: input.userId, privilege_code: input.privilegeCode });
  if (input.asOf) params.set("as_of", input.asOf);
  if (input.contextType) params.set("context_type", input.contextType);
  if (input.contextId) params.set("context_id", input.contextId);
  return apiRequest<QmsEligibility>(qmsPath(amoCode, `/people/eligibility?${params.toString()}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function preflightQmsAuditorAssignment(
  amoCode: string,
  payload: {
    user_id: string;
    assignment_role: QmsAuditorAssignmentRole;
    assignment_date: string;
    assignment_scope_key: string;
    context_type?: "AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER";
    context_id?: string;
    enforce_independence?: boolean;
    exclude_schedule_id?: string;
  },
): Promise<QmsAuditorEligibilityPreflight> {
  return apiRequest<QmsAuditorEligibilityPreflight>(
    qmsPath(amoCode, "/integrations/calendar/auditor-eligibility"),
    jsonOptions("POST", payload),
  );
}

export function declareQmsIndependence(
  amoCode: string,
  payload: {
    user_id: string;
    context_type: "AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER";
    context_id: string;
    declaration: "INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW";
    relationship_to_subject?: string;
    rationale: string;
    source_references?: Array<Record<string, unknown>>;
  },
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(qmsPath(amoCode, "/people/independence"), jsonOptions("POST", payload));
}
