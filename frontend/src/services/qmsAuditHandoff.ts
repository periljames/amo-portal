import { apiRequest, qmsPath } from "./apiClient";

export type AuditHandoffSource = { id: string; label: string; detail?: string };
export type PlannerPersonOption = { id: string; full_name: string; email?: string | null; role?: string | null; department_name?: string | null };
export type PlannerOptions = { timezone_name: string; people: PlannerPersonOption[]; kinds: string[]; frequencies: string[]; scopes: Array<{ id: string; code: string; name: string; default_kind: string }> };

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export async function listMissionHandoffSources(amoCode: string, signal?: AbortSignal): Promise<AuditHandoffSource[]> {
  const response = await apiRequest<{ items: Array<{ id: string; mission_ref: string; title: string; status: string; mission_type: string }> }>(qmsPath(amoCode, "/missions?limit=100"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
  return response.items.filter((row) => row.status !== "CANCELLED").map((row) => ({ id: row.id, label: `${row.mission_ref} · ${row.title}`, detail: `${row.mission_type} · ${row.status}` }));
}

export async function listSignalHandoffSources(amoCode: string, signal?: AbortSignal): Promise<AuditHandoffSource[]> {
  const response = await apiRequest<{ items: Array<{ id: string; rule_code?: string; metric: string; severity: string; explanation: string; state?: string; triggered: boolean }> }>(qmsPath(amoCode, "/intelligence/signals?triggered_only=true&limit=100"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
  return response.items.filter((row) => row.triggered && row.state !== "CLOSED").map((row) => ({ id: row.id, label: `${row.rule_code || row.metric} · ${row.severity}`, detail: row.explanation }));
}

export function getPlannerHandoffOptions(amoCode: string, signal?: AbortSignal): Promise<PlannerOptions> {
  return apiRequest<PlannerOptions>(qmsPath(amoCode, "/planner/options"), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function createAuditHandoff(
  amoCode: string,
  sourceType: "MISSION" | "SIGNAL",
  sourceId: string,
  payload: {
    rationale: string;
    schedule: {
      title: string;
      next_due_date: string;
      start_time?: string;
      duration_days?: number;
      location?: string;
      scope?: string;
      criteria?: string;
      lead_auditor_user_id?: string;
      audit_scope_code?: string;
      kind?: string;
      frequency?: "ONE_TIME";
      timezone_name?: string;
      allow_conflicts?: boolean;
    };
  },
): Promise<{ id: string; title: string; next_due_date: string; lifecycle_status: string }> {
  const suffix = sourceType === "MISSION"
    ? `/missions/${encodeURIComponent(sourceId)}/audit-handoffs`
    : `/intelligence/signals/${encodeURIComponent(sourceId)}/audit-handoffs`;
  return apiRequest(qmsPath(amoCode, suffix), json("POST", payload));
}
