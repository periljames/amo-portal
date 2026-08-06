import { authHeaders, getCachedUser } from "./auth";
import { apiGet, apiPost } from "./crs";

export type FleetAircraft = {
  serial_number: string;
  registration: string;
  model?: string | null;
  status?: string | null;
  home_base?: string | null;
};

export type UsageRow = {
  id: number;
  date: string;
  techlog_no: string;
  block_hours: number;
  cycles: number;
  hours_to_mx?: number | null;
  days_to_mx?: number | null;
  ttaf_after?: number | null;
  tca_after?: number | null;
  ttesn_after?: number | null;
  tcesn_after?: number | null;
  ttsoh_after?: number | null;
  ttshsi_after?: number | null;
  tcsoh_after?: number | null;
  pttsn_after?: number | null;
  aircraft_serial_number?: string;
  verification_status?: string | null;
  created_at?: string;
  updated_at: string;
  note?: string | null;
};

export type UsageCorrectionReceipt = {
  id: number;
  usage_id: number;
  aircraft_serial_number: string;
  reason: string;
  status: string;
  requested_at: string;
};

export function listFleetAircraft() {
  return apiGet<FleetAircraft[]>("/aircraft", { headers: authHeaders() });
}

export function usageSummary(serial: string) {
  return apiGet<any>(`/aircraft/${encodeURIComponent(serial)}/usage/summary`, { headers: authHeaders() });
}

export function listUsage(serial: string, params?: string) {
  return apiGet<UsageRow[]>(`/aircraft/${encodeURIComponent(serial)}/usage${params ? `?${params}` : ""}`, {
    headers: authHeaders(),
  });
}

export function createUsage(serial: string, row: Partial<UsageRow> & { date: string; techlog_no: string; block_hours: number; cycles: number }) {
  return apiPost<UsageRow>(`/aircraft/${encodeURIComponent(serial)}/usage`, row, { headers: authHeaders() });
}

export function updateUsage(id: number, payload: Record<string, unknown>) {
  const expectedUpdatedAt = String(payload.last_seen_updated_at || "");
  if (!expectedUpdatedAt) {
    return Promise.reject(new Error("Refresh the utilisation row before requesting a correction."));
  }

  const proposed: Record<string, unknown> = {
    expected_usage_updated_at: expectedUpdatedAt,
  };
  const mapping: Record<string, string> = {
    date: "entry_date",
    techlog_no: "techlog_no",
    station: "station",
    block_hours: "block_hours",
    cycles: "cycles",
    remarks: "remarks",
    note: "note",
  };
  const changedFields: string[] = [];
  Object.entries(mapping).forEach(([source, target]) => {
    if (payload[source] !== undefined && payload[source] !== null) {
      proposed[target] = payload[source];
      changedFields.push(source);
    }
  });
  const note = typeof payload.note === "string" ? payload.note.trim() : "";
  proposed.reason = note.length >= 8
    ? note
    : `Technical Records correction requested for ${changedFields.join(", ") || "accepted utilisation values"}.`;

  return apiPost<UsageCorrectionReceipt>(`/records/utilisation/${id}/corrections`, proposed, {
    headers: authHeaders(),
  });
}

export function listMaintenanceStatus(serial: string) {
  return apiGet<any[]>(`/aircraft/${encodeURIComponent(serial)}/maintenance-status`, { headers: authHeaders() });
}

export function listComponents(serial: string) {
  return apiGet<any[]>(`/aircraft/${encodeURIComponent(serial)}/components`, { headers: authHeaders() });
}

export function listAD() {
  return apiGet<any[]>("/records/airworthiness/AD", { headers: authHeaders() });
}

export function listSB() {
  return apiGet<any[]>("/records/airworthiness/SB", { headers: authHeaders() });
}

export function listDeferrals() {
  return apiGet<any[]>("/records/deferrals", { headers: authHeaders() });
}

export function listReconciliation() {
  return apiGet<any[]>("/records/reconciliation", { headers: authHeaders() });
}

export function canEditProduction(): boolean {
  const role = getCachedUser()?.role;
  return [
    "SUPERUSER",
    "AMO_ADMIN",
    "PRODUCTION_ENGINEER",
    "PLANNING_ENGINEER",
    "CERTIFYING_ENGINEER",
    "CERTIFYING_TECHNICIAN",
  ].includes(role || "");
}
