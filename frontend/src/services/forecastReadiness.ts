import { authHeaders } from "./auth";
import { apiGet, apiPatch, apiPost } from "./crs";

export type ForecastScenarioItem = {
  id: string;
  scenario_id: string;
  aircraft_serial_number: string;
  registration: string;
  program_item_id: number;
  aircraft_program_item_id: number;
  task_code?: string | null;
  task_title: string;
  status: string;
  projected_due_date?: string | null;
  projected_trigger?: string | null;
  projected_days?: number | null;
  remaining_hours?: number | null;
  remaining_cycles?: number | null;
  remaining_days?: number | null;
  daily_hours: number;
  daily_cycles: number;
};

export type ForecastScenario = {
  id: string;
  name: string;
  status: string;
  start_date: string;
  horizon_days: number;
  default_daily_hours: number;
  default_daily_cycles: number;
  aircraft_assumptions_json: Record<string, { daily_hours?: number; daily_cycles?: number }>;
  summary_json: Record<string, unknown>;
  generated_at?: string | null;
  created_at: string;
  updated_at: string;
  items: ForecastScenarioItem[];
};

export type ReadinessRequirement = {
  id: string;
  work_package_id: number;
  category: "MANPOWER" | "AUTHORIZATION" | "MATERIAL" | "TOOL" | "FACILITY" | "DOCUMENT" | "SLOT";
  reference?: string | null;
  description: string;
  quantity_required: number;
  quantity_confirmed: number;
  status: string;
  required_by?: string | null;
  owner_user_id?: string | null;
  evidence_json: string[];
  notes?: string | null;
};

export type ReadinessAssessment = {
  id: string;
  work_package_id: number;
  version: number;
  status: string;
  blockers_json: string[];
  warnings_json: string[];
  metrics_json: Record<string, unknown>;
  assessed_at: string;
};

export type PackageFreeze = {
  id: string;
  work_package_id: number;
  version: number;
  status: string;
  manifest_hash: string;
  manifest_json: Record<string, unknown>;
  reason: string;
  frozen_at: string;
};

export type ReadinessDashboard = {
  scenarios: number;
  completed_scenarios: number;
  packages_assessed: number;
  ready_packages: number;
  blocked_packages: number;
  shortages: number;
  active_freezes: number;
};

const base = "/work-packages/planning-control";

export function getReadinessDashboard() {
  return apiGet<ReadinessDashboard>(`${base}/dashboard`, { headers: authHeaders() });
}

export function listForecastScenarios() {
  return apiGet<ForecastScenario[]>(`${base}/scenarios`, { headers: authHeaders() });
}

export function createForecastScenario(payload: {
  name: string;
  start_date: string;
  horizon_days: number;
  default_daily_hours: number;
  default_daily_cycles: number;
  aircraft_assumptions_json?: Record<string, { daily_hours?: number; daily_cycles?: number }>;
}) {
  return apiPost<ForecastScenario>(`${base}/scenarios`, payload, { headers: authHeaders() });
}

export function updateForecastScenario(scenarioId: string, payload: Partial<ForecastScenario>) {
  return apiPatch<ForecastScenario>(`${base}/scenarios/${encodeURIComponent(scenarioId)}`, payload, { headers: authHeaders() });
}

export function runForecastScenario(scenarioId: string) {
  return apiPost<ForecastScenario>(`${base}/scenarios/${encodeURIComponent(scenarioId)}/run`, {}, { headers: authHeaders() });
}

export function listPackageRequirements(packageId: number) {
  return apiGet<ReadinessRequirement[]>(`${base}/packages/${packageId}/requirements`, { headers: authHeaders() });
}

export function createPackageRequirement(packageId: number, payload: {
  category: ReadinessRequirement["category"];
  reference?: string;
  description: string;
  quantity_required: number;
  quantity_confirmed: number;
  required_by?: string;
  notes?: string;
}) {
  return apiPost<ReadinessRequirement>(`${base}/packages/${packageId}/requirements`, payload, { headers: authHeaders() });
}

export function updatePackageRequirement(requirementId: string, payload: Partial<ReadinessRequirement>) {
  return apiPatch<ReadinessRequirement>(`${base}/requirements/${encodeURIComponent(requirementId)}`, payload, { headers: authHeaders() });
}

export function assessWorkPackage(packageId: number) {
  return apiPost<ReadinessAssessment>(`${base}/packages/${packageId}/assess`, {}, { headers: authHeaders() });
}

export function listPackageAssessments(packageId: number) {
  return apiGet<ReadinessAssessment[]>(`${base}/packages/${packageId}/assessments`, { headers: authHeaders() });
}

export function freezeWorkPackage(packageId: number, reason: string) {
  return apiPost<PackageFreeze>(`${base}/packages/${packageId}/freeze`, { reason }, { headers: authHeaders() });
}

export function listPackageFreezes(packageId: number) {
  return apiGet<PackageFreeze[]>(`${base}/packages/${packageId}/freezes`, { headers: authHeaders() });
}
