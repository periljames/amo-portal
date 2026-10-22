import { apiRequest, qmsPath } from "./apiClient";
import { getApiBaseUrl } from "./config";

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
export interface CarRcaDocument {
  version: number;
  problem_statement: string;
  investigations: CarRcaInvestigation[];
  conclusion: string;
  supported_cause_ids: string[];
  conclusion_evidence_references: string[];
  evidence_notes: string;
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
  history: Array<{ id: string; revision: number; event_type: string; actor_kind: string; actor_ref: string | null; reason: string; created_at: string; snapshot: unknown }>;
}
export type CarRcaSavePayload = {
  expected_revision: number;
  mutation_key: string;
  investigation: CarRcaDocument;
  form: Record<string, string>;
};
export type CarRcaActionCreate = Pick<CarRcaAction, "kind" | "description" | "cause_node_ids" | "evidence_references" | "target_date" | "priority"> & {
  external_owner_name: string | null;
  owner_user_id?: string | null;
};

export const emptyCarRca = (problem_statement = ""): CarRcaDocument => ({
  version: 1, problem_statement, investigations: [], conclusion: "",
  supported_cause_ids: [], conclusion_evidence_references: [], evidence_notes: "",
});

const publicPath = (token: string, path: string) => `/quality/cars/invite/${encodeURIComponent(token)}${path}`;

export class CarRcaRequestError extends Error {
  constructor(readonly status: number, message: string) { super(message); this.name = "CarRcaRequestError"; }
}

async function publicRcaRequest<T>(token: string, path: string, method: "GET" | "PUT" | "POST" | "PATCH" = "GET", body?: unknown): Promise<T> {
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
  } finally { window.clearTimeout(timeout); }
}

export const getCarRcaInvite = (token: string) => publicRcaRequest<CarRcaProjection>(token, "/draft");
export const saveCarRcaInvite = (token: string, payload: CarRcaSavePayload) => publicRcaRequest<CarRcaProjection>(token, "/draft", "PUT", payload);
export const addCarRcaInviteAction = (token: string, payload: CarRcaActionCreate) => publicRcaRequest<CarRcaAction>(token, "/corrective-actions", "POST", payload);
export const reviseCarRcaInviteAction = (token: string, actionId: string, payload: CarRcaActionCreate) =>
  publicRcaRequest<CarRcaAction>(token, `/corrective-actions/${encodeURIComponent(actionId)}`, "PUT", payload);
export const progressCarRcaInviteAction = (token: string, actionId: string, payload: { state: "IN_PROGRESS" | "SUBMITTED"; completion_note: string; evidence_references: string[] }) =>
  publicRcaRequest<CarRcaAction>(token, `/corrective-actions/${encodeURIComponent(actionId)}`, "PATCH", payload);

export const getCarRcaInternal = (amoCode: string, carId: string) =>
  apiRequest<CarRcaProjection>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/investigation`), { cacheTtlMs: 0, timeoutMs: 20000 });
export const saveCarRcaInternal = (amoCode: string, carId: string, payload: CarRcaSavePayload) =>
  apiRequest<CarRcaProjection>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/investigation`), {
    method: "PUT", body: JSON.stringify(payload), cacheTtlMs: 0,
  });
export const addCarRcaInternalAction = (amoCode: string, carId: string, payload: CarRcaActionCreate) =>
  apiRequest<CarRcaAction>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/corrective-actions`), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0,
  });
export const reviewCarRcaAction = (amoCode: string, carId: string, actionId: string, state: "ACCEPTED" | "REJECTED" | "VERIFIED", reason: string) =>
  apiRequest<CarRcaAction>(qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/corrective-actions/${encodeURIComponent(actionId)}/review`), {
    method: "PATCH", body: JSON.stringify({ state, reason }), cacheTtlMs: 0,
  });
