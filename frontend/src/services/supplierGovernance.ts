import { apiRequest } from "./apiClient";

export type SupplierGovernancePolicy = {
  configured: boolean;
  id?: string;
  amo_id: string;
  revision_no?: number;
  risk_review_days?: Record<string, number>;
  re_evaluation_rules?: Record<string, number>;
  require_independent_review?: boolean;
  conditional_approval_allowed?: boolean;
};

export type SupplierEvaluationCriterion = {
  id: string;
  criterion_key: string;
  sequence_no: number;
  label: string;
  guidance?: string | null;
  response_type: string;
  weight: number | string;
  mandatory: boolean;
  evidence_required: boolean;
  failure_is_blocking: boolean;
  scoring_rule: Record<string, unknown>;
};

export type SupplierEvaluationTemplate = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  revision_no: number;
  status: string;
  pass_threshold?: number | string | null;
  manual_references: string[];
  criteria: SupplierEvaluationCriterion[];
};

export type SupplierEvaluationResponse = {
  id: string;
  criterion_id: string;
  answer: unknown;
  score_percent?: number | string | null;
  evidence_references: string[];
  comment?: string | null;
};

export type SupplierEvaluation = {
  id: string;
  supplier_id: number;
  template_id: string;
  template_revision_no: number;
  status: string;
  version: number;
  intended_scope: Array<Record<string, unknown>>;
  policy_snapshot: Record<string, unknown>;
  score?: number | string | null;
  outcome?: string | null;
  valid_until?: string | null;
  qms_finding_id?: string | null;
  qms_car_id?: string | null;
  created_by_user_id?: string | null;
  submitted_by_user_id?: string | null;
  reviewed_by_user_id?: string | null;
  review_comment?: string | null;
  responses: SupplierEvaluationResponse[];
};

export type SupplierGovernanceDetail = {
  supplier_id: number;
  policy_configured: boolean;
  current_evaluation?: SupplierEvaluation | null;
  evaluations: SupplierEvaluation[];
  decisions: Array<{
    id: string;
    action: string;
    rationale: string;
    created_at: string;
    actor_user_id?: string | null;
  }>;
  re_evaluation_actions: Array<{
    id: string;
    trigger_type: string;
    status: string;
    due_on?: string | null;
    trigger_snapshot: Record<string, unknown>;
  }>;
};

function base(amoCode: string): string {
  return `/api/maintenance/${encodeURIComponent(amoCode)}/procurement`;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export function getSupplierGovernancePolicy(amoCode: string): Promise<SupplierGovernancePolicy> {
  return apiRequest<SupplierGovernancePolicy>(`${base(amoCode)}/supplier-governance/policy`, { cacheTtlMs: 0 });
}

export function updateSupplierGovernancePolicy(amoCode: string, payload: Record<string, unknown>): Promise<SupplierGovernancePolicy> {
  return apiRequest<SupplierGovernancePolicy>(`${base(amoCode)}/supplier-governance/policy`, json("PUT", payload));
}

export function listSupplierEvaluationTemplates(amoCode: string, activeOnly = false): Promise<SupplierEvaluationTemplate[]> {
  return apiRequest<SupplierEvaluationTemplate[]>(
    `${base(amoCode)}/supplier-governance/templates${activeOnly ? "?active_only=true" : ""}`,
    { cacheTtlMs: 0 },
  );
}

export function createSupplierEvaluationTemplate(amoCode: string, payload: Record<string, unknown>): Promise<SupplierEvaluationTemplate> {
  return apiRequest<SupplierEvaluationTemplate>(`${base(amoCode)}/supplier-governance/templates`, json("POST", payload));
}

export function activateSupplierEvaluationTemplate(amoCode: string, templateId: string, rationale: string): Promise<SupplierEvaluationTemplate> {
  return apiRequest<SupplierEvaluationTemplate>(
    `${base(amoCode)}/supplier-governance/templates/${encodeURIComponent(templateId)}/activate`,
    json("POST", { rationale }),
  );
}

export function getSupplierGovernance(amoCode: string, supplierId: number): Promise<SupplierGovernanceDetail> {
  return apiRequest<SupplierGovernanceDetail>(`${base(amoCode)}/suppliers/${supplierId}/governance`, { cacheTtlMs: 0 });
}

export function createSupplierEvaluation(
  amoCode: string,
  supplierId: number,
  payload: Record<string, unknown>,
): Promise<SupplierEvaluation> {
  return apiRequest<SupplierEvaluation>(`${base(amoCode)}/suppliers/${supplierId}/evaluations`, json("POST", payload));
}

export function updateSupplierEvaluationResponses(
  amoCode: string,
  evaluationId: string,
  payload: Record<string, unknown>,
): Promise<SupplierEvaluation> {
  return apiRequest<SupplierEvaluation>(
    `${base(amoCode)}/supplier-governance/evaluations/${encodeURIComponent(evaluationId)}/responses`,
    json("PATCH", payload),
  );
}

export function submitSupplierEvaluation(
  amoCode: string,
  evaluationId: string,
  expectedVersion: number,
  submissionNote?: string,
): Promise<SupplierEvaluation> {
  return apiRequest<SupplierEvaluation>(
    `${base(amoCode)}/supplier-governance/evaluations/${encodeURIComponent(evaluationId)}/submit`,
    json("POST", { expected_version: expectedVersion, submission_note: submissionNote || null }),
  );
}

export function reviewSupplierEvaluation(
  amoCode: string,
  evaluationId: string,
  payload: Record<string, unknown>,
): Promise<SupplierEvaluation> {
  return apiRequest<SupplierEvaluation>(
    `${base(amoCode)}/supplier-governance/evaluations/${encodeURIComponent(evaluationId)}/review`,
    json("POST", payload),
  );
}

export function scanSupplierReevaluation(amoCode: string): Promise<Record<string, unknown>> {
  return apiRequest(`${base(amoCode)}/supplier-governance/re-evaluation/scan`, json("POST"));
}
