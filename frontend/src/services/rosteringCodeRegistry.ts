import { apiJson, jsonBody } from "./typedApi";

export type RosterCalendarMode = "TIMED" | "ALL_DAY" | "HIDDEN";

export type RosterCodePolicy = {
  unpaid_break_minutes: number;
  calendar_mode: RosterCalendarMode;
  effective_from?: string | null;
  effective_to?: string | null;
  source_reference?: string | null;
};

export type RosterCodeRegistryEntry = {
  id: string;
  code: string;
  label: string;
  kind: string;
  default_start_time?: string | null;
  default_end_time?: string | null;
  duration_minutes?: number | null;
  counts_as_duty: boolean;
  is_active: boolean;
  description?: string | null;
  policy: RosterCodePolicy;
  usage_count: number;
  can_delete: boolean;
};

export type StarterPackResult = {
  created_codes: string[];
  skipped_existing_codes: string[];
  recommended_codes: string[];
};

export function listRosterCodeRegistry(): Promise<RosterCodeRegistryEntry[]> {
  return apiJson("/rostering/shift-templates/code-registry", {
    offline: { cacheTtlMs: 15 * 60_000 },
  });
}

export function installRecommendedRosterCodes(): Promise<StarterPackResult> {
  return apiJson("/rostering/shift-templates/starter-pack", { method: "POST" });
}

export function updateRosterCodePolicy(
  templateId: string,
  payload: Partial<RosterCodePolicy>,
): Promise<RosterCodePolicy> {
  return apiJson(`/rostering/shift-templates/${encodeURIComponent(templateId)}/policy`, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

export function deleteUnusedRosterCode(templateId: string): Promise<void> {
  return apiJson(`/rostering/shift-templates/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
  });
}
