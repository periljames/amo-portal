import { apiRequest, qmsPath } from "./apiClient";
import { getApiBaseUrl } from "./config";
import { validateCarRcaProjection, validateCarInviteAccess, validateCarParetoSnapshots } from "./qmsCarRcaContracts";

export type CauseEntryType = "FACT" | "HYPOTHESIS" | "CAUSAL_CONCLUSION" | "RULED_OUT";
export type CarRcaMethod = "FIVE_WHYS" | "ISHIKAWA" | "PARETO" | "CAUSAL_FACTOR" | "BARRIER_ANALYSIS" | "CHANGE_ANALYSIS" | "HUMAN_ORGANIZATIONAL" | "EIGHT_D" | "FMEA";
export interface CarRcaNode {
  id: string;
  parent_id: string | null;
  statement: string;
  category: string;
  entry_type: CauseEntryType;
  evidence_references: string[];
  rationale: string;
}
export interface CarRcaInvestigation {
  id: string;
  method: CarRcaMethod;
  version: number;
  nodes: CarRcaNode[];
  context: Record<string, unknown>;
}
export interface CarRcaEffectivenessProposal {
  expected_result: string;
  verification_method: string;
  measurable_success_criterion: string;
  observation_period: string;
  proposed_review_date: string | null;
  supporting_records: string[];
}
export interface CarRcaDocument {
  version: number;
  problem_statement: string;
  investigations: CarRcaInvestigation[];
  conclusion: string;
  supported_cause_ids: string[];
  conclusion_evidence_references: string[];
  evidence_notes: string;
  effectiveness_proposal: CarRcaEffectivenessProposal | null;
}
export type CarRcaActionState = "PROPOSED" | "ACCEPTED" | "IN_PROGRESS" | "SUBMITTED" | "VERIFIED" | "REJECTED" | "CANCELLED";
export interface CarRcaAction {
  id: string;
  car_id: string;
  sequence_no: number;
  action_number: string;
  kind: "CORRECTIVE" | "PREVENTIVE" | "CONTAINMENT";
  description: string;
  cause_node_ids: string[];
  evidence_references: string[];
  owner_user_id: string | null;
  external_owner_name: string | null;
  target_date: string | null;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  state: CarRcaActionState;
  completion_note: string | null;
  completed_at: string | null;
  quality_review_note: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
}
export interface CarRcaProjection {
  car_id: string;
  revision: number;
  draft: { form: Record<string, string>; investigation: CarRcaDocument };
  submitted_revision: number | null;
  submitted_snapshot: { form: Record<string, string>; investigation: CarRcaDocument } | null;
  submitted_at: string | null;
  actions: CarRcaAction[];
  action_events: Array<{ id: string; action_id: string; previous_state: string | null; next_state: string; actor_kind: string; actor_ref: string | null; reason: string; created_at: string; snapshot: unknown }>;
  retained_responses: Array<{ id: string; original_response_id: string; event_type: string; submitted_at: string | null; retained_at: string; reason: string; snapshot: Record<string, unknown> }>;
  history: Array<{ id: string; revision: number; event_type: string; actor_kind: string; actor_ref: string | null; reason: string; created_at: string; snapshot: unknown }>;
}
export type CarRcaSavePayload = {
  expected_revision: number;
  mutation_key: string;
  investigation: CarRcaDocument;
  form: Record<string, string>;
};
export type CarRcaActionCreate = Pick<CarRcaAction, "kind" | "description" | "cause_node_ids" | "evidence_references" | "target_date" | "priority"> & {
  mutation_key?: string;
  external_owner_name: string | null;
  owner_user_id?: string | null;
};

export const emptyCarRca = (problem_statement = ""): CarRcaDocument => ({
  version: 1, problem_statement, investigations: [], conclusion: "",
  supported_cause_ids: [], conclusion_evidence_references: [], evidence_notes: "",
  effectiveness_proposal: null,
});

const publicPath = (token: string, path: string) => `/quality/cars/invite/${encodeURIComponent(token)}${path}`;

export class CarRcaRequestError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "CarRcaRequestError";
  }
}

async function publicRcaRequest<T>(token: string, path: string, method: "GET" | "PUT" | "POST" | "PATCH" = "GET", body?: unknown, readRetry = true): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), method === "GET" ? 20000 : 45000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${publicPath(token, path)}`, {
      method,
      headers: { Accept: "application/json", ...(method !== "GET" ? { "Content-Type": "application/json" } : {}) },
      cache: "no-store",
      credentials: "omit",
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string | { message?: string; server_revision?: number } } | null;
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : detail?.message;
      throw new CarRcaRequestError(response.status, message || `CAR investigation request failed (${response.status}).`);
    }
    return await response.json() as T;
  } catch(error) {
    const transient=error instanceof TypeError || (error instanceof DOMException && error.name==="AbortError") ||
      (error instanceof CarRcaRequestError && [502,503,504].includes(error.status));
    if(method==="GET" && readRetry && transient){
      window.clearTimeout(timeout);
      await new Promise(resolve=>window.setTimeout(resolve,400));
      return publicRcaRequest<T>(token,path,method,body,false);
    }
    throw error;
  } finally { window.clearTimeout(timeout); }
}

export const getCarRcaInvite = (token: string) => publicRcaRequest<CarRcaProjection>(token, "/draft").then(validateCarRcaProjection);
export const saveCarRcaInvite = (token: string, payload: CarRcaSavePayload) => publicRcaRequest<CarRcaProjection>(token, "/draft", "PUT", payload).then(validateCarRcaProjection);
export const addCarRcaInviteAction = (token: string, payload: CarRcaActionCreate) => publicRcaRequest<CarRcaAction>(token, "/corrective-actions", "POST", payload);
export const reviseCarRcaInviteAction = (token: string, actionId: string, payload: CarRcaActionCreate) =>
  publicRcaRequest<CarRcaAction>(token, `/corrective-actions/${encodeURIComponent(actionId)}`, "PUT", payload);
export const progressCarRcaInviteAction = (token: string, actionId: string, payload: { state: "IN_PROGRESS" | "SUBMITTED"; completion_note: string; evidence_references: string[] }) =>
  publicRcaRequest<CarRcaAction>(token, `/corrective-actions/${encodeURIComponent(actionId)}`, "PATCH", payload);

export const adoptCarEffectivenessProposal = (amoCode: string, carId: string, responsible_reviewer_user_id: string, reason: string) =>
  apiRequest<{ case_id: string; case_ref: string; plan_id: string; planned_review_date: string; reviewer_user_id: string }>(
    qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/effectiveness-plan`),
    { method: "POST", body: JSON.stringify({ responsible_reviewer_user_id, reason }), cacheTtlMs: 0 },
  );

export const getCarRcaInternal = (amoCode: string, carId: string) =>
  apiRequest<CarRcaProjection>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/investigation`), { cacheTtlMs: 0, timeoutMs: 20000 }).then(validateCarRcaProjection);
export const saveCarRcaInternal = (amoCode: string, carId: string, payload: CarRcaSavePayload) =>
  apiRequest<CarRcaProjection>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/investigation`), {
    method: "PUT", body: JSON.stringify(payload), cacheTtlMs: 0,
  }).then(validateCarRcaProjection);
export const addCarRcaInternalAction = (amoCode: string, carId: string, payload: CarRcaActionCreate) =>
  apiRequest<CarRcaAction>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/corrective-actions`), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0,
  });
export const reviewCarRcaAction = (amoCode: string, carId: string, actionId: string, state: "ACCEPTED" | "REJECTED" | "VERIFIED", reason: string) =>
  apiRequest<CarRcaAction>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/corrective-actions/${encodeURIComponent(actionId)}/review`), {
    method: "PATCH", body: JSON.stringify({ state, reason }), cacheTtlMs: 0,
  });

export type CarRcaParetoSnapshot = {
  id: string;
  car_id: string;
  source_kind: "QMS_AUDIT_FINDINGS";
  filters: { start: string; end: string; group_by: "severity" | "finding_type" | "requirement"; cohort_definition: string };
  population: string;
  sample_size: number;
  categories: Array<{ category: string; count: number; share_percent: number; cumulative_percent: number }>;
  source_references: Array<{ id: string; audit_id: string; reference: string | null; audit_reference: string | null; created_at: string | null; requirement: string | null; severity: string; finding_type: string }>;
  source_reference_count: number;
  source_references_truncated: boolean;
  created_at: string;
  created_by_user_id: string;
  fingerprint: string;
};

export const listCarRcaParetoSnapshots = (amoCode: string, carId: string) =>
  apiRequest<CarRcaParetoSnapshot[]>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/pareto-snapshots`), {
    cacheTtlMs: 0, timeoutMs: 20000,
  }).then(validateCarParetoSnapshots);

export const saveCarRcaParetoSnapshot = (
  amoCode: string, carId: string,
  payload: { start: string; end: string; group_by: "severity" | "finding_type" | "requirement" },
) =>
  apiRequest<CarRcaParetoSnapshot>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/pareto-snapshots`), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0, timeoutMs: 45000,
  });


export type CarInviteAccessControl = {
  expires_at: string | null;
  revoked_at: string | null;
  reason: string;
  updated_by_user_id: string | null;
  updated_at: string | null;
};

export const getCarInviteAccessControl = (amoCode: string, carId: string) =>
  apiRequest<CarInviteAccessControl>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/invite-access`), { cacheTtlMs: 0 }).then(validateCarInviteAccess);

export const updateCarInviteAccessControl = (
  amoCode: string, carId: string,
  payload: { expires_at?: string | null; revoke: boolean; reason: string },
) =>
  apiRequest<CarInviteAccessControl>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/invite-access`), {
    method: "PUT", body: JSON.stringify(payload), cacheTtlMs: 0,
  });

export const rotateCarInviteAccess = (amoCode: string, carId: string, reason: string) =>
  apiRequest<CarInviteAccessControl & { new_invite_url: string }>(
    qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/invite-access/rotate`),
    { method: "POST", body: JSON.stringify({ reason }), cacheTtlMs: 0 },
  );
