import { authHeaders, getCachedUser } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";

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
  updated_at: string;
  note?: string | null;
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
  return apiPut<UsageRow>(`/aircraft/usage/${id}`, payload, { headers: authHeaders() });
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
