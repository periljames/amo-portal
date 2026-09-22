import { apiRequest, qmsPath } from "./apiClient";

export type AnalysisFilters = { start: string; end: string; severity: string; finding_type: string; requirement: string };
export type AnalysisCount = { name: string; count: number };
export type AnalysisSource = {
  id: string; audit_id: string; reference: string; audit_reference: string;
  description: string; severity: string; finding_type: string; requirement: string | null;
  objective_evidence: string | null; created_at: string; closed_at: string | null;
};
export type AnalysisSnapshot = {
  generated_at: string; filters: AnalysisFilters; population: string;
  total: number; open: number; missing_evidence: number; missing_requirement: number;
  severity: AnalysisCount[]; types: AnalysisCount[]; requirements: AnalysisCount[]; requirement_tail: number;
  trend: (AnalysisCount & { partial: boolean })[];
  cars: { total: number; closed: number; overdue: number; measurable: number; on_time: number; cancelled: number };
  sources: AnalysisSource[]; offset: number; limit: number; has_more: boolean;
};
export function getAnalysisSnapshot(tenant: string, filters: AnalysisFilters, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ start: filters.start, end: filters.end, offset: String(offset), limit: "50" });
  for (const key of ["severity", "finding_type", "requirement"] as const) if (filters[key]) params.set(key, filters[key]);
  return apiRequest<AnalysisSnapshot>(qmsPath(tenant, `/analysis/snapshot?${params}`), { signal, cacheTtlMs: 15_000, timeoutMs: 20_000 });
}
