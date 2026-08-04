import { authHeaders } from "./auth";
import { apiGet, apiPatch, apiPost } from "./crs";

export type WinAirAuthority = "PORTAL" | "WINAIR" | "SHARED";
export type WinAirDataset =
  | "AIRCRAFT_MASTER"
  | "AIRCRAFT_COUNTER"
  | "FLIGHT_LOG"
  | "MAINTENANCE_DUE"
  | "INSPECTION_STATUS"
  | "DEFERRAL";

export type WinAirProfile = {
  id: string;
  integration_config_id: string;
  name: string;
  status: "ACTIVE" | "DISABLED";
  mode: "SHADOW" | "ACTIVE";
  transport: "API" | "FILE" | "WEBHOOK";
  direction: "BIDIRECTIONAL" | "INBOUND_ONLY" | "OUTBOUND_ONLY";
  authority_json: Partial<Record<WinAirDataset, WinAirAuthority>>;
  mapping_json: Record<string, unknown>;
  dataset_config_json: Record<string, unknown>;
  last_cursor_json: Record<string, unknown>;
  hours_tolerance: number;
  cycles_tolerance: number;
  last_success_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type WinAirRun = {
  id: string;
  profile_id: string;
  run_type: string;
  status: string;
  dry_run: boolean;
  requested_datasets_json: string[];
  cursor_before_json: Record<string, unknown>;
  cursor_after_json: Record<string, unknown>;
  counts_json: Record<string, number>;
  started_at: string;
  finished_at?: string | null;
  error_summary?: string | null;
  created_at: string;
};

export type WinAirConflict = {
  id: string;
  profile_id: string;
  run_id: string;
  record_id: string;
  dataset: string;
  external_key: string;
  conflict_type: string;
  source_payload_json: Record<string, unknown>;
  local_payload_json: Record<string, unknown>;
  field_differences_json: Record<string, unknown>;
  status: string;
  resolution_notes?: string | null;
  resolved_at?: string | null;
  created_at: string;
};

export type WinAirDashboard = {
  profiles: number;
  active_profiles: number;
  shadow_profiles: number;
  open_conflicts: number;
  failed_records: number;
  pending_outbox: number;
  latest_run?: WinAirRun | null;
  dataset_counts: Record<string, number>;
};

export type WinAirProfileCreate = {
  integration_config_id: string;
  name: string;
  status?: "ACTIVE" | "DISABLED";
  mode?: "SHADOW" | "ACTIVE";
  transport?: "API" | "FILE" | "WEBHOOK";
  direction?: "BIDIRECTIONAL" | "INBOUND_ONLY" | "OUTBOUND_ONLY";
  authority_json?: Partial<Record<WinAirDataset, WinAirAuthority>>;
  mapping_json?: Record<string, unknown>;
  dataset_config_json?: Record<string, unknown>;
  hours_tolerance?: number;
  cycles_tolerance?: number;
};

export function getWinAirDashboard() {
  return apiGet<WinAirDashboard>("/integrations/winair/dashboard", { headers: authHeaders() });
}

export function listWinAirProfiles() {
  return apiGet<WinAirProfile[]>("/integrations/winair/profiles", { headers: authHeaders() });
}

export function createWinAirProfile(payload: WinAirProfileCreate) {
  return apiPost<WinAirProfile>("/integrations/winair/profiles", payload, { headers: authHeaders() });
}

export function updateWinAirProfile(profileId: string, payload: Partial<WinAirProfileCreate>) {
  return apiPatch<WinAirProfile>(`/integrations/winair/profiles/${encodeURIComponent(profileId)}`, payload, {
    headers: authHeaders(),
  });
}

export function exportWinAirSnapshot(
  profileId: string,
  payload: {
    datasets?: Array<"MAINTENANCE_DUE" | "INSPECTION_STATUS" | "DEFERRAL">;
    horizon_days?: number;
    aircraft_serial_numbers?: string[];
  } = {},
) {
  return apiPost<WinAirRun>(
    `/integrations/winair/profiles/${encodeURIComponent(profileId)}/export`,
    {
      datasets: payload.datasets ?? ["MAINTENANCE_DUE", "INSPECTION_STATUS", "DEFERRAL"],
      horizon_days: payload.horizon_days ?? 90,
      aircraft_serial_numbers: payload.aircraft_serial_numbers ?? [],
    },
    { headers: authHeaders() },
  );
}

export function reconcileWinAirProfile(profileId: string) {
  return apiPost<WinAirRun>(
    `/integrations/winair/profiles/${encodeURIComponent(profileId)}/reconcile`,
    {
      datasets: ["AIRCRAFT_COUNTER", "FLIGHT_LOG", "MAINTENANCE_DUE", "DEFERRAL"],
    },
    { headers: authHeaders() },
  );
}

export function listWinAirRuns(profileId?: string, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (profileId) params.set("profile_id", profileId);
  return apiGet<WinAirRun[]>(`/integrations/winair/runs?${params.toString()}`, { headers: authHeaders() });
}

export function listWinAirConflicts(profileId?: string, statusFilter = "OPEN") {
  const params = new URLSearchParams({ status_filter: statusFilter });
  if (profileId) params.set("profile_id", profileId);
  return apiGet<WinAirConflict[]>(`/integrations/winair/conflicts?${params.toString()}`, { headers: authHeaders() });
}

export function decideWinAirConflict(
  conflictId: string,
  decision: "ACCEPT_EXTERNAL" | "KEEP_LOCAL" | "MERGED" | "IGNORED",
  resolutionNotes: string,
  mergedPayload?: Record<string, unknown>,
) {
  return apiPost<WinAirConflict>(
    `/integrations/winair/conflicts/${encodeURIComponent(conflictId)}/decision`,
    {
      decision,
      resolution_notes: resolutionNotes,
      merged_payload: mergedPayload,
    },
    { headers: authHeaders() },
  );
}
