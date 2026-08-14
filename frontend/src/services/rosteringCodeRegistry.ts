import { apiJson, jsonBody } from "./typedApi";

export type RosterCalendarMode = "TIMED" | "ALL_DAY" | "HIDDEN";
export type RosterDutySemantic = "DUTY" | "STANDBY" | "TRAINING" | "REST" | "OFF" | "LEAVE" | "SICK" | "OTHER";
export type RosterCodeVerificationStatus = "CONFIRMED" | "REVIEW_REQUIRED" | "UNRESOLVED";

export type RosterCodePolicy = {
  unpaid_break_minutes: number;
  calendar_mode: RosterCalendarMode;
  duty_semantic: RosterDutySemantic;
  verification_status: RosterCodeVerificationStatus;
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

export type RosterLegacyAlias = {
  id: string;
  alias: string;
  shift_template_id: string;
  context_label?: string | null;
  aircraft_registration?: string | null;
  notes?: string | null;
  created_at: string;
};

export type RosterLegacyAliasCreate = {
  alias: string;
  context_label?: string | null;
  aircraft_registration?: string | null;
  notes?: string | null;
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

export function listRosterLegacyAliases(templateId?: string): Promise<RosterLegacyAlias[]> {
  const query = templateId ? `?template_id=${encodeURIComponent(templateId)}` : "";
  return apiJson(`/rostering/shift-templates/aliases${query}`, {
    offline: { cacheTtlMs: 15 * 60_000 },
  });
}

export function createRosterLegacyAlias(
  templateId: string,
  payload: RosterLegacyAliasCreate,
): Promise<RosterLegacyAlias> {
  return apiJson(`/rostering/shift-templates/${encodeURIComponent(templateId)}/aliases`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function deleteRosterLegacyAlias(aliasId: string): Promise<void> {
  return apiJson(`/rostering/shift-templates/aliases/${encodeURIComponent(aliasId)}`, {
    method: "DELETE",
  });
}
