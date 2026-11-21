import { apiRequest, qmsPath } from "./apiClient";
export type ProcessMetricDefinition = { code: string; title: string; measure: string; target: string; direction: "AT_LEAST" | "AT_MOST" | "EQUAL"; unit: string };
export type QmsProcess = {
  id: string; title: string; description: string; owner_user_id: string;
  status: "DRAFT" | "PENDING_APPROVAL" | "ACTIVE";
  due_date: string; created_by: string;
  payload: { version: number; purpose: string; review_due: string; approval?: { approved_by: string; reason: string } };
};
export type QmsObjective = {
  id: string; title: string; description: string; status: string;
  payload: { process_id: string; code: string; target: string; direction: "AT_LEAST" | "AT_MOST" | "EQUAL"; unit: string };
};
export type QmsProcessReview = {
  id: string; status: "PENDING_VERIFICATION" | "VERIFIED" | "REWORK";
  period_start: string; period_end: string; owner_user_id: string;
  measurements: Array<{ objective_id: string; code: string; actual: string; target: string; target_met: boolean }>;
  evidence_ids: string[]; owner_reason: string; review_reason?: string;
};
export type ProcessDetail = { process: QmsProcess; objectives: QmsObjective[]; reviews: QmsProcessReview[] };
export type ProcessPerson = { id: string; name: string };
const url = (tenant: string, fragment: string) => qmsPath(tenant, "/system/governance" + fragment);
const post = <T>(tenant: string, fragment: string, data: Record<string, unknown>): Promise<T> =>
  apiRequest<T>(url(tenant, fragment), { method: "POST", cacheTtlMs: 0, timeoutMs: 20000, body: JSON.stringify(data) });
export function listGovernedProcesses(tenant: string, offset: number) {
  return apiRequest<{ items: QmsProcess[]; total: number; offset: number; limit: number }>(url(tenant, "/processes?limit=25&offset=" + offset), { cacheTtlMs: 0 });
}
export function getProcessParticipants(tenant: string) {
  return apiRequest<{ items: ProcessPerson[] }>(url(tenant, "/participants"), { cacheTtlMs: 20000 });
}
export function readGovernedProcess(tenant: string, id: string) {
  return apiRequest<ProcessDetail>(url(tenant, "/processes/" + encodeURIComponent(id)), { cacheTtlMs: 0 });
}
export function createGovernedProcess(tenant: string, data: Record<string, unknown>) {
  return post<{ process: QmsProcess }>(tenant, "/processes", data);
}
export function decideGovernedProcess(tenant: string, id: string, action: "submit" | "approve", version: number, reason: string) {
  return post<{ process: QmsProcess }>(tenant, "/processes/" + encodeURIComponent(id) + "/" + action, { expected_version: version, reason });
}
export function submitProcessPerformance(tenant: string, id: string, data: Record<string, unknown>) {
  return post<{ review: QmsProcessReview; process: QmsProcess }>(tenant, "/processes/" + encodeURIComponent(id) + "/reviews", data);
}
export function verifyProcessPerformance(tenant: string, id: string, reviewId: string, data: Record<string, unknown>) {
  return post<{ process: QmsProcess; followup_task_id?: string | null }>(
    tenant, "/processes/" + encodeURIComponent(id) + "/reviews/" + encodeURIComponent(reviewId) + "/verify", data);
}
