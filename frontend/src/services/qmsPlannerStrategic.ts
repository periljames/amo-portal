import { apiRequest, qmsPath } from "./apiClient";

export type StrategicUniverseItem = {
  id: string;
  label: string;
  entity_type: string;
  source_owner_module: string;
  source_type: string;
  source_id: string;
  source_route?: string | null;
  risk_classification: string;
  regulatory_criticality: string;
  mandatory_surveillance: boolean;
  surveillance_interval_days?: number | null;
  programme_states: string[];
};

export type QmsPlannerStrategicView = {
  year: number;
  timezone_name: string;
  schedule_count: number;
  months: Array<{ month: number; schedule_count: number }>;
  quarters: Array<{ quarter: number; schedule_count: number }>;
  lifecycle_states: Record<string, number>;
  auditor_workload: Array<{ user_id: string; name: string; department: string; schedule_count: number }>;
  department_coverage: Array<{ department: string; assigned_audit_slots: number }>;
  location_coverage: Array<{ location: string; schedule_count: number }>;
  supplier_surveillance: StrategicUniverseItem[];
  regulatory_commitments: StrategicUniverseItem[];
  data_quality: { unresolved_department_assignments: number; statement: string };
};

export function getQmsPlannerStrategicView(amoCode: string, year: number, signal?: AbortSignal) {
  return apiRequest<QmsPlannerStrategicView>(qmsPath(amoCode, `/planner/strategic?year=${year}`), { timeoutMs: 20_000, cacheTtlMs: 5_000, signal });
}
