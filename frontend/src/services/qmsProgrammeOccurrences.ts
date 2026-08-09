import { apiRequest, qmsPath } from "./apiClient";

export type ProgrammeSummary = { id: string; programme_ref: string; title: string; status: string; period_start: string; period_end: string };
export type ProgrammeOccurrenceItem = {
  id: string;
  state: string;
  recurrence: string;
  target_start?: string | null;
  target_end?: string | null;
  mandatory_surveillance: boolean;
  rationale?: string | null;
  universe_item?: { display_label?: string; source_owner_module?: string; source_type?: string; risk_classification?: string; regulatory_criticality?: string };
};
export type ProgrammeDetail = ProgrammeSummary & { items: ProgrammeOccurrenceItem[] };
export type ProgrammeOccurrenceLink = { id: string; schedule_id: string; occurrence_type: "CUSTOM" | "RISK_TRIGGERED"; occurrence_key: string; source_signal_id?: string | null; rationale: string; lifecycle_status?: string | null; created_at: string };
export type OpenSignal = { id: string; rule_code?: string; metric: string; severity: string; explanation: string; triggered: boolean; state?: string };
export type PlannerPerson = { id: string; full_name: string; role?: string | null };

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listOccurrenceProgrammes(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: ProgrammeSummary[] }>(qmsPath(amoCode, "/audit-programmes?limit=100"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getOccurrenceProgramme(amoCode: string, programmeId: string, signal?: AbortSignal) {
  return apiRequest<ProgrammeDetail>(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function listProgrammeOccurrenceLinks(amoCode: string, programmeId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ProgrammeOccurrenceLink[] }>(qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/occurrence-links`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function listOccurrenceSignals(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: OpenSignal[] }>(qmsPath(amoCode, "/intelligence/signals?triggered_only=true&limit=100"), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function getOccurrencePlannerOptions(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ timezone_name: string; people: PlannerPerson[] }>(qmsPath(amoCode, "/planner/options"), { timeoutMs: 15_000, cacheTtlMs: 5_000, signal });
}

export function createProgrammeOccurrence(
  amoCode: string,
  programmeId: string,
  itemId: string,
  occurrenceType: "CUSTOM" | "RISK_TRIGGERED",
  payload: {
    occurrence_key: string;
    rationale: string;
    signal_id?: string;
    schedule: {
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
  return apiRequest<{ id: string; title: string; next_due_date: string; lifecycle_status: string }>(
    qmsPath(amoCode, `/audit-programmes/${encodeURIComponent(programmeId)}/items/${encodeURIComponent(itemId)}/occurrences/${occurrenceType}`),
    json("POST", payload),
  );
}
