import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";

export type DashboardTile = { key: string; label: string; count: number };

export type CanonicalUtilisation = {
  id: number;
  tail_id: string;
  entry_date: string;
  techlog_no: string;
  station?: string | null;
  block_hours: number;
  entry_cycles: number;
  hours: number;
  cycles: number;
  source: string;
  conflict_flag: boolean;
  correction_reason?: string | null;
  verification_status: string;
  created_at: string;
  updated_at: string;
};

export type UsageCorrection = {
  id: number;
  usage_id: number;
  aircraft_serial_number: string;
  reason: string;
  proposed_values_json: Record<string, unknown>;
  status: "PENDING" | "APPLIED" | "REJECTED" | string;
  expected_usage_updated_at: string;
  requested_by_user_id?: string | null;
  reviewed_by_user_id?: string | null;
  review_notes?: string | null;
  requested_at: string;
  reviewed_at?: string | null;
  applied_at?: string | null;
};

export type ReconciliationSummary = {
  generated_at: string;
  open_total: number;
  by_type: Record<string, number>;
  affected_aircraft: number;
};

export type ReconciliationScanResult = {
  generated_at: string;
  created: number;
  existing: number;
  checked_aircraft: number;
  checks: Record<string, number>;
};

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

export function fetchReconciliationSummary() {
  return apiGet<ReconciliationSummary>("/records/reconciliation/summary", { headers: authHeaders() });
}

export function runReconciliationScan() {
  return apiPost<ReconciliationScanResult>("/records/reconciliation/scan", {}, { headers: authHeaders() });
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

export function listCanonicalUtilisation(tailId: string) {
  return apiGet<CanonicalUtilisation[]>(`/records/aircraft/${encodeURIComponent(tailId)}/utilisation`, { headers: authHeaders() });
}

export function postUtilisation(tailId: string, payload: {
  tail_id: string;
  entry_date: string;
  techlog_no: string;
  station?: string;
  hours: number;
  cycles: number;
  block_hours?: number;
  entry_cycles?: number;
  source?: string;
  remarks?: string;
  note?: string;
}) {
  return apiPost<CanonicalUtilisation>(`/records/aircraft/${encodeURIComponent(tailId)}/utilisation`, payload, { headers: authHeaders() });
}

export function listUsageCorrections(params: { status?: string; aircraftSerialNumber?: string } = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set("status_filter", params.status);
  if (params.aircraftSerialNumber) query.set("aircraft_serial_number", params.aircraftSerialNumber);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<UsageCorrection[]>(`/records/utilisation/corrections${suffix}`, { headers: authHeaders() });
}

export function requestUsageCorrection(usageId: number, payload: {
  reason: string;
  expected_usage_updated_at: string;
  entry_date?: string;
  techlog_no?: string;
  station?: string;
  block_hours?: number;
  cycles?: number;
  remarks?: string;
  note?: string;
}) {
  return apiPost<UsageCorrection>(`/records/utilisation/${usageId}/corrections`, payload, { headers: authHeaders() });
}

export function decideUsageCorrection(correctionId: number, decision: "APPROVE" | "REJECT", reviewNotes: string) {
  return apiPost<UsageCorrection>(`/records/utilisation/corrections/${correctionId}/decision`, {
    decision,
    review_notes: reviewNotes,
  }, { headers: authHeaders() });
}
