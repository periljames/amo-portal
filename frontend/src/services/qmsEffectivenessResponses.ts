import { apiRequest, qmsPath } from "./apiClient";

export type EffectivenessPlanOption = {
  id: string;
  case_id: string;
  status: string;
  conclusion?: string | null;
  expected_outcome?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  source_route?: string | null;
};

export type AssuranceCaseOption = {
  id: string;
  case_ref: string;
  title: string;
  status: string;
  effectiveness_plans?: EffectivenessPlanOption[];
};

export type EffectivenessResponseAction = {
  id: string;
  case_id: string;
  effectiveness_plan_id: string;
  action_type: "ADDITIONAL_ACTION" | "FOLLOW_UP_AUDIT" | "REOPEN_CAR" | "MANAGEMENT_ESCALATION" | "RISK_REASSESSMENT";
  status: "OPEN" | "COMPLETED" | "CANCELLED";
  rationale: string;
  target_source_type?: string | null;
  target_source_id?: string | null;
  target_route?: string | null;
  schedule_id?: string | null;
  due_date?: string | null;
  owner_user_id?: string | null;
  created_at: string;
  completion_reason?: string | null;
  events: Array<{ id: string; event_type: string; reason: string; actor_user_id?: string | null; created_at: string }>;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listAssuranceCasesForResponses(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: AssuranceCaseOption[] }>(qmsPath(amoCode, "/assurance-cases?limit=100"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getAssuranceCaseForResponses(amoCode: string, caseId: string, signal?: AbortSignal) {
  return apiRequest<AssuranceCaseOption>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function listEffectivenessResponses(amoCode: string, caseId: string, signal?: AbortSignal) {
  return apiRequest<{ items: EffectivenessResponseAction[] }>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-responses`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function createEffectivenessResponse(
  amoCode: string,
  caseId: string,
  planId: string,
  payload: {
    action_type: EffectivenessResponseAction["action_type"];
    rationale: string;
    target_source_type?: string;
    target_source_id?: string;
    target_route?: string;
    due_date?: string;
    owner_user_id?: string;
    schedule?: {
      title: string;
      next_due_date: string;
      start_time: string;
      duration_days: number;
      timezone_name: string;
      location?: string;
      scope?: string;
      criteria?: string;
      lead_auditor_user_id?: string;
      frequency: "ONE_TIME";
      allow_conflicts: false;
    };
  },
) {
  return apiRequest<EffectivenessResponseAction>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-plans/${encodeURIComponent(planId)}/responses`), json("POST", payload));
}

export function decideEffectivenessResponse(amoCode: string, caseId: string, responseId: string, decision: "COMPLETE" | "CANCEL", reason: string) {
  return apiRequest<EffectivenessResponseAction>(qmsPath(amoCode, `/assurance-cases/${encodeURIComponent(caseId)}/effectiveness-responses/${encodeURIComponent(responseId)}/decision`), json("POST", { decision, reason }));
}
