import { apiRequest, qmsPath } from "./apiClient";
import { apiBlob } from "./typedApi";

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
  active_holders?: number;
  live_holders?: number;
  total_holders?: number;
};

export type QmsAuthorizationPermissions = {
  can_view: boolean;
  can_prepare: boolean;
  can_approve: boolean;
  can_review: boolean;
  can_approve_exemption: boolean;
  can_manage_policy: boolean;
  can_oversight: boolean;
};

export type QmsAuthorizationOverview = {
  permissions: QmsAuthorizationPermissions;
  metrics: {
    active_authorizations: number;
    suspended_authorizations: number;
    expiring_within_60_days: number;
    open_authorization_cases: number;
    reviews_due: number;
    active_controlled_exemptions: number;
  };
  attention: Array<{
    type: string;
    person: string;
    authorization?: string | null;
    status: string;
    reason: string;
    updated_at?: string | null;
  }>;
};

export type QmsAuthorizationPerson = {
  key: string;
  name: string;
  staff_code?: string | null;
  home_role?: string | null;
  department?: string | null;
  workforce_status: string;
  authorizations: Array<{
    authorization: string;
    status: string;
    scope: string;
    expires_on?: string | null;
  }>;
  open_cases: number;
};

export type QmsAuthorizationReadiness = {
  authorization: string;
  as_of: string;
  status: string;
  hard_blockers: Array<{ code: string; message: string }>;
  training: {
    status: string;
    current: boolean;
    developmental_exception: boolean;
    courses: Array<{ course: string; status: string; valid_until?: string | null }>;
    required: string[];
    missing: string[];
  };
  development: {
    observed_audits: number;
    target: number;
    progress_label: string;
    target_is_hard_gate: boolean;
    supervision_required: boolean;
    audit_participation: Array<{
      reference?: string | null;
      title?: string | null;
      status?: string | null;
      roles: string[];
      planned_start?: string | null;
      planned_end?: string | null;
      actual_end?: string | null;
    }>;
  };
  annual_review?: {
    last_reviewed: string;
    next_review_due?: string | null;
    outcome: string;
    reason: string;
    reviewed_at?: string | null;
  } | null;
  controlled_exemption?: QmsControlledExemption | null;
  affected_assignments: Array<{
    reference?: string | null;
    title?: string | null;
    role?: string | null;
    planned_start?: string | null;
    planned_end?: string | null;
  }>;
};

export type QmsAuthorization = {
  key: string;
  person?: string;
  authorization: string;
  status: string;
  scope: string;
  effective_from?: string | null;
  expires_on?: string | null;
  last_reviewed?: string | null;
  next_review_due?: string | null;
  limitations?: unknown[];
  readiness?: QmsAuthorizationReadiness;
};

export type QmsAuthorizationCaseSummary = {
  id: string;
  person: string;
  home_role?: string | null;
  department?: string | null;
  authorization: string;
  case_type: string;
  status: string;
  nomination_date: string;
  nominator: string;
  recommendation?: string | null;
  updated_at?: string | null;
  next_action: string;
};

export type QmsAuthorizationEvidence = {
  id: string;
  type: string;
  label: string;
  source_module?: string | null;
  source_reference: Record<string, unknown>;
  has_file: boolean;
  filename?: string | null;
  created_at?: string | null;
};

export type QmsControlledExemption = {
  id: string;
  status: string;
  authorization: string;
  criterion: string;
  reason: string;
  equivalent_evidence: Array<Record<string, unknown>>;
  limitations: unknown[];
  supervision_required: boolean;
  supervisor?: string | null;
  conditions: unknown[];
  effective_from: string;
  expires_on: string;
  approved_by: string;
  approved_at?: string | null;
};

export type QmsAuthorizationCaseDetail = {
  case: Omit<QmsAuthorizationCaseSummary, "person"> & {
    person: {
      name?: string;
      home_role?: string | null;
      department?: string | null;
      staff_code?: string | null;
      active?: boolean;
    };
    current_authorization: Record<string, unknown>;
    requested_authorization: Record<string, unknown>;
    recommendation?: string | null;
    recommendation_by?: string | null;
    recommendation_at?: string | null;
    decision?: string | null;
    decision_reason?: string | null;
    decided_by?: string | null;
    decided_at?: string | null;
    effective_from?: string | null;
    expires_on?: string | null;
    next_review_due?: string | null;
  };
  readiness: QmsAuthorizationReadiness;
  evidence: QmsAuthorizationEvidence[];
  controlled_exemption?: QmsControlledExemption | null;
  history: Array<{
    action: string;
    from?: string | null;
    to?: string | null;
    reason: string;
    actor: string;
    occurred_at?: string | null;
  }>;
  permissions: QmsAuthorizationPermissions;
};

export type QmsAuthorizationPersonDetail = {
  person: {
    name: string;
    home_role?: string | null;
    department?: string | null;
    staff_code?: string | null;
    active: boolean;
  };
  appointments: Array<{
    function: string;
    status: string;
    effective_from?: string | null;
    effective_until?: string | null;
  }>;
  authorizations: QmsAuthorization[];
  cases: QmsAuthorizationCaseSummary[];
  audit_participation: {
    items: Array<{
      reference?: string | null;
      title?: string | null;
      status?: string | null;
      roles: string[];
      planned_start?: string | null;
      planned_end?: string | null;
      actual_end?: string | null;
    }>;
    observed_completed: number;
    observed_target: number;
  };
};

export type QmsAuthorizationReview = {
  id: string;
  person?: string | null;
  authorization?: string | null;
  last_reviewed: string;
  next_review_due?: string | null;
  outcome: string;
  reason: string;
  reviewed_by: string;
  reviewed_at?: string | null;
  notes?: string | null;
  evidence: Array<Record<string, unknown>>;
};

export type QmsIndependencePolicy = {
  enforced: boolean;
  allow_impartiality_form: boolean;
  editable_by?: string;
  rules: Array<{ code: string; title: string; standard: string; summary: string }>;
  remediations: Array<{ code: string; label: string; detail: string }>;
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getQmsAuthorizationOverview(amoCode: string, signal?: AbortSignal) {
  return apiRequest<QmsAuthorizationOverview>(
    qmsPath(amoCode, "/people/authorization-control/overview"),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function listQmsAuthorizationPeople(
  amoCode: string,
  options: { search?: string; includeInactive?: boolean; limit?: number } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.includeInactive) params.set("include_inactive", "true");
  if (options.limit) params.set("limit", String(options.limit));
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsAuthorizationPerson[]; total: number }>(
    qmsPath(amoCode, `/people/authorization-control/people${suffix}`),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function getQmsAuthorizationPerson(amoCode: string, personKey: string, signal?: AbortSignal) {
  return apiRequest<QmsAuthorizationPersonDetail>(
    qmsPath(amoCode, `/people/authorization-control/people/${encodeURIComponent(personKey)}`),
    { timeoutMs: 15_000, cacheTtlMs: 3_000, signal },
  );
}

export function listQmsAuthorizationCases(
  amoCode: string,
  options: { status?: string; search?: string; limit?: number } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.limit) params.set("limit", String(options.limit));
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsAuthorizationCaseSummary[]; total: number }>(
    qmsPath(amoCode, `/people/authorization-control/cases${suffix}`),
    { timeoutMs: 15_000, cacheTtlMs: 3_000, signal },
  );
}

export function createQmsAuthorizationCase(
  amoCode: string,
  payload: {
    user_id: string;
    requested_rule_id: string;
    requested_scope_key?: string;
    requested_scope?: Record<string, unknown>;
    nomination_reason: string;
  },
) {
  return apiRequest<{ case: QmsAuthorizationCaseSummary; readiness: QmsAuthorizationReadiness }>(
    qmsPath(amoCode, "/people/authorization-control/cases"),
    jsonOptions("POST", payload),
  );
}

export function createQmsAuthorizationCasesBatch(
  amoCode: string,
  payload: { user_ids: string[]; requested_rule_id: string; nomination_reason: string },
) {
  return apiRequest<{
    created: Array<{ person: string; case_id: string }>;
    skipped: Array<{ person: string; reason: string }>;
    created_count: number;
    skipped_count: number;
  }>(qmsPath(amoCode, "/people/authorization-control/cases/batch"), jsonOptions("POST", payload));
}

export function getQmsAuthorizationCase(amoCode: string, caseId: string, signal?: AbortSignal) {
  return apiRequest<QmsAuthorizationCaseDetail>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function prepareQmsAuthorizationCase(
  amoCode: string,
  caseId: string,
  payload: { status?: "UNDER_REVIEW" | "DEVELOPMENT" | "AWAITING_EVIDENCE" | "RETURNED"; recommendation?: string; reason: string },
) {
  return apiRequest<{ status: string; readiness: QmsAuthorizationReadiness }>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/preparation`),
    jsonOptions("PATCH", payload),
  );
}

export function submitQmsAuthorizationCase(
  amoCode: string,
  caseId: string,
  payload: { recommendation: string; reason: string },
) {
  return apiRequest<{ status: string; readiness: QmsAuthorizationReadiness }>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/submit`),
    jsonOptions("POST", payload),
  );
}

export function decideQmsAuthorizationCase(
  amoCode: string,
  caseId: string,
  payload: {
    decision: "APPROVE" | "REJECT" | "RETURN";
    reason: string;
    effective_from?: string | null;
    expires_on?: string | null;
    next_review_due?: string | null;
    incomplete_development_basis?: string | null;
    source_references?: Array<Record<string, unknown>>;
    confirmed: boolean;
  },
) {
  return apiRequest<Record<string, unknown>>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/decision`),
    jsonOptions("POST", payload),
  );
}

export function addQmsAuthorizationEvidenceReference(
  amoCode: string,
  caseId: string,
  payload: {
    evidence_type: string;
    label: string;
    source_module?: string | null;
    source_reference?: Record<string, unknown>;
  },
) {
  return apiRequest<QmsAuthorizationEvidence>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/evidence`),
    jsonOptions("POST", payload),
  );
}

export function uploadQmsAuthorizationCaseEvidence(
  amoCode: string,
  caseId: string,
  input: { file: File; label: string; evidence_type?: string },
) {
  const body = new FormData();
  body.append("file", input.file);
  body.append("label", input.label);
  body.append("evidence_type", input.evidence_type || "OTHER");
  return apiRequest<QmsAuthorizationEvidence>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/evidence-file`),
    { method: "POST", body },
  );
}

export function downloadQmsAuthorizationEvidence(amoCode: string, evidenceId: string) {
  return apiBlob(
    qmsPath(amoCode, `/people/authorization-control/evidence/${encodeURIComponent(evidenceId)}/download`),
  );
}

export function createQmsCaseControlledExemption(
  amoCode: string,
  caseId: string,
  payload: {
    criterion: string;
    reason_normal_compliance_impossible: string;
    equivalent_evidence?: Array<Record<string, unknown>>;
    limitations?: unknown[];
    supervision_required?: boolean;
    supervisor_user_id?: string | null;
    conditions: unknown[];
    effective_from: string;
    expires_on: string;
    source_references?: Array<Record<string, unknown>>;
    confirmed: boolean;
  },
) {
  return apiRequest<{ controlled_exemption: QmsControlledExemption; readiness: QmsAuthorizationReadiness }>(
    qmsPath(amoCode, `/people/authorization-control/cases/${encodeURIComponent(caseId)}/controlled-exemptions`),
    jsonOptions("POST", payload),
  );
}

export function createQmsAuthorizationControlledExemption(
  amoCode: string,
  authorizationKey: string,
  payload: {
    criterion: string;
    reason_normal_compliance_impossible: string;
    equivalent_evidence?: Array<Record<string, unknown>>;
    limitations?: unknown[];
    supervision_required?: boolean;
    supervisor_user_id?: string | null;
    conditions: unknown[];
    effective_from: string;
    expires_on: string;
    source_references?: Array<Record<string, unknown>>;
    confirmed: boolean;
  },
) {
  return apiRequest<{ controlled_exemption: QmsControlledExemption }>(
    qmsPath(amoCode, `/people/authorization-control/authorizations/${encodeURIComponent(authorizationKey)}/controlled-exemptions`),
    jsonOptions("POST", payload),
  );
}

export function listQmsAuthorizations(
  amoCode: string,
  options: { status?: string } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsAuthorization[] }>(
    qmsPath(amoCode, `/people/authorization-control/authorizations${suffix}`),
    { timeoutMs: 15_000, cacheTtlMs: 3_000, signal },
  );
}

export function decideQmsAuthorizationLifecycle(
  amoCode: string,
  authorizationKey: string,
  payload: {
    decision: "SUSPEND" | "REVOKE" | "REINSTATE" | "RENEW";
    reason: string;
    effective_date: string;
    expires_on?: string | null;
    next_review_due?: string | null;
    source_references?: Array<Record<string, unknown>>;
    confirmed: boolean;
  },
) {
  return apiRequest<Record<string, unknown>>(
    qmsPath(amoCode, `/people/authorization-control/authorizations/${encodeURIComponent(authorizationKey)}/lifecycle`),
    jsonOptions("POST", payload),
  );
}

export function listQmsAuthorizationReviews(
  amoCode: string,
  options: { dueOnly?: boolean } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.dueOnly) params.set("due_only", "true");
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsAuthorizationReview[] }>(
    qmsPath(amoCode, `/people/authorization-control/reviews${suffix}`),
    { timeoutMs: 15_000, cacheTtlMs: 3_000, signal },
  );
}

export function createQmsAuthorizationReview(
  amoCode: string,
  authorizationKey: string,
  payload: {
    review_outcome: "CONTINUE" | "CONTINUE_WITH_CONDITIONS" | "SUSPEND" | "REVOKE" | "REQUIRES_ACTION";
    review_reason: string;
    next_review_due?: string | null;
    review_evidence?: Array<Record<string, unknown>>;
    review_notes?: string | null;
    confirmed: boolean;
  },
) {
  return apiRequest<{ review: QmsAuthorizationReview; readiness: QmsAuthorizationReadiness }>(
    qmsPath(amoCode, `/people/authorization-control/authorizations/${encodeURIComponent(authorizationKey)}/reviews`),
    jsonOptions("POST", payload),
  );
}

export function downloadQmsAuthorizationRecord(amoCode: string, authorizationKey: string) {
  return apiBlob(
    qmsPath(amoCode, `/people/authorization-control/authorizations/${encodeURIComponent(authorizationKey)}/record`),
  );
}

export function listQmsPrivilegeRules(
  amoCode: string,
  options: { includeInactive?: boolean } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.includeInactive) params.set("include_inactive", "true");
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<{ items: QmsPrivilegeRule[] }>(
    qmsPath(amoCode, `/people/rules${suffix}`),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function ensureQmsDefaultPrivilegeRules(amoCode: string) {
  return apiRequest<{ items: QmsPrivilegeRule[] }>(
    qmsPath(amoCode, "/people/rules/ensure-defaults"),
    { method: "POST" },
  );
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
) {
  return apiRequest<QmsPrivilegeRule>(qmsPath(amoCode, "/people/rules"), jsonOptions("POST", payload));
}

export function updateQmsPrivilegeRule(
  amoCode: string,
  ruleId: string,
  payload: {
    title?: string;
    description?: string | null;
    required_training_course_codes?: string[];
    independence_required?: boolean;
    max_concurrent_assignments?: number | null;
    scope_schema?: Record<string, unknown>;
    is_active?: boolean;
  },
) {
  return apiRequest<QmsPrivilegeRule>(
    qmsPath(amoCode, `/people/rules/${encodeURIComponent(ruleId)}`),
    jsonOptions("PATCH", payload),
  );
}

export function getQmsIndependencePolicy(amoCode: string, signal?: AbortSignal) {
  return apiRequest<QmsIndependencePolicy>(
    qmsPath(amoCode, "/people/independence/policy"),
    { timeoutMs: 15_000, cacheTtlMs: 10_000, signal },
  );
}

export function updateQmsIndependencePolicy(
  amoCode: string,
  payload: { enforced?: boolean; allow_impartiality_form?: boolean },
) {
  return apiRequest<QmsIndependencePolicy>(
    qmsPath(amoCode, "/people/independence/policy"),
    jsonOptions("PATCH", payload),
  );
}
