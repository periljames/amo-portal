import { authHeaders } from "./auth";
import { apiGet, apiPatch, apiPost } from "./crs";

export type AmpRevision = {
  id: number;
  template_code: string;
  revision_code: string;
  title: string;
  status: "DRAFT" | "APPROVED" | "SUPERSEDED" | string;
  effective_date?: string | null;
  source_reference?: string | null;
  notes?: string | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  task_count: number;
  active_aircraft_count: number;
};

export type AmpBaseline = {
  id: number;
  aircraft_serial_number: string;
  revision_id: number;
  template_code: string;
  revision_code: string;
  revision_title: string;
  status: string;
  applied_by_user_id?: string | null;
  applied_at: string;
  notes?: string | null;
  requirements_created: number;
  requirements_existing: number;
};

export type AmpCoverageRow = {
  aircraft_serial_number: string;
  registration: string;
  model?: string | null;
  template_code?: string | null;
  revision_code?: string | null;
  revision_status?: string | null;
  baseline_status: string;
  applied_at?: string | null;
  active_requirement_count: number;
  unbaselined_requirement_count: number;
};

export type AmpCoverage = {
  generated_at: string;
  summary: {
    fleet_aircraft: number;
    active_baselines: number;
    missing_baselines: number;
    active_requirements: number;
    unbaselined_requirements: number;
  };
  rows: AmpCoverageRow[];
};

export function listAmpRevisions(params: { templateCode?: string; status?: string } = {}) {
  const query = new URLSearchParams();
  if (params.templateCode) query.set("template_code", params.templateCode);
  if (params.status) query.set("status_filter", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<AmpRevision[]>(`/maintenance-program/revisions${suffix}`, { headers: authHeaders() });
}

export function createAmpRevision(payload: {
  template_code: string;
  revision_code: string;
  title: string;
  effective_date?: string;
  source_reference?: string;
  notes?: string;
}) {
  return apiPost<AmpRevision>("/maintenance-program/revisions", payload, { headers: authHeaders() });
}

export function updateAmpRevision(id: number, payload: Partial<AmpRevision>) {
  return apiPatch<AmpRevision>(`/maintenance-program/revisions/${id}`, payload, { headers: authHeaders() });
}

export function approveAmpRevision(id: number, notes?: string) {
  return apiPost<AmpRevision>(`/maintenance-program/revisions/${id}/approve`, { notes }, { headers: authHeaders() });
}

export function applyAmpRevision(id: number, aircraftSerialNumber: string, notes?: string) {
  return apiPost<AmpBaseline>(`/maintenance-program/revisions/${id}/apply`, {
    aircraft_serial_number: aircraftSerialNumber,
    notes,
  }, { headers: authHeaders() });
}

export function listAmpBaselines(aircraftSerialNumber?: string) {
  const suffix = aircraftSerialNumber
    ? `?aircraft_serial_number=${encodeURIComponent(aircraftSerialNumber)}`
    : "";
  return apiGet<AmpBaseline[]>(`/maintenance-program/baselines${suffix}`, { headers: authHeaders() });
}

export function getAmpCoverage() {
  return apiGet<AmpCoverage>("/maintenance-program/coverage", { headers: authHeaders() });
}
