import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";

export type DashboardTile = { key: string; label: string; count: number };

export function fetchTechnicalDashboard() {
  return apiGet<{ tiles: DashboardTile[] }>("/records/dashboard", { headers: authHeaders() });
}

export function fetchTechnicalAircraft() {
  return apiGet<any[]>("/records/aircraft", { headers: authHeaders() });
}

export function fetchDeferrals() {
  return apiGet<any[]>("/records/deferrals", { headers: authHeaders() });
}

export function fetchMaintenanceRecords() {
  return apiGet<any[]>("/records/maintenance-records", { headers: authHeaders() });
}

export function fetchAirworthiness(type: "ad" | "sb") {
  return apiGet<any[]>(`/records/airworthiness/${type.toUpperCase()}`, { headers: authHeaders() });
}

export function fetchReconciliation() {
  return apiGet<any[]>("/records/reconciliation", { headers: authHeaders() });
}

export function fetchTraceability(params = "") {
  return apiGet<any>(`/records/traceability${params ? `?${params}` : ""}`, { headers: authHeaders() });
}

export function fetchSettings() {
  return apiGet<any>("/records/settings", { headers: authHeaders() });
}

export function updateSettings(payload: any) {
  return apiPut<any>("/records/settings", payload, { headers: authHeaders() });
}

export function fetchPacks(packType: string, targetId?: string) {
  const qs = new URLSearchParams({ pack_type: packType });
  if (targetId) qs.set("target_id", targetId);
  return apiGet<any>(`/records/packs?${qs.toString()}`, { headers: authHeaders() });
}

export function postUtilisation(tailId: string, payload: any) {
  return apiPost<any>(`/records/aircraft/${encodeURIComponent(tailId)}/utilisation`, payload, { headers: authHeaders() });
}
