import { apiBlob, apiJson, downloadBlob, jsonBody, queryString } from "./typedApi";
import type {
  HrBulkOperation,
  HrBulkOperationItemsPage,
  HrBulkOperationsPage,
  HrContractBatchPreview,
  HrContractDefaults,
  HrContractOverride,
  HrDashboard,
  HrDefaultDayBatchPreview,
  HrDefaultDayBatchResult,
  HrDefaultDayBootstrap,
  HrGrade,
  HrGradeWrite,
  HrHierarchyBlueprint,
  HrJobFamily,
  HrJobFamilyWrite,
  HrOrgUnit,
  HrOrgUnitWrite,
  HrOvertimeRequest,
  HrPeopleFacets,
  HrPeopleFilters,
  HrPeoplePage,
  HrPeopleSelection,
  HrPersonnelMutationPayload,
  HrPosition,
  HrPositionWrite,
  HrSupervisorOptionsPage,
  HrWorkPatternBatchOptions,
  HrWorkPatternBatchPreview,
} from "../types/workforceHr";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../types/workforce";

export type WorkforceHrPatternAssignmentCreate = {
  user_id: string; work_pattern_id: string; effective_from: string;
  effective_to?: string | null; cycle_anchor_date: string;
};

const defaultDayPreviewTokens = new Map<string, string>();
function selectionKey(selection: HrPeopleSelection): string {
  const userIds = [...(selection.user_ids || [])].sort();
  const excludedIds = [...(selection.exclude_user_ids || [])].sort();
  const filters = Object.fromEntries(
    Object.entries(selection.filters || {}).sort(([left], [right]) => left.localeCompare(right)),
  );
  return JSON.stringify({ mode: selection.mode, user_ids: userIds, exclude_user_ids: excludedIds, filters });
}

export function getWorkforceHrDashboard(peopleLimit = 50): Promise<HrDashboard> {
  const boundedPeopleLimit = Math.max(1, Math.min(200, Math.trunc(peopleLimit)));
  return apiJson(`/workforce/hr/dashboard${queryString({ people_limit: boundedPeopleLimit })}`, {
    offline: { cacheTtlMs: 60_000 },
  });
}
export function listWorkforceHrPeople(params: HrPeopleFilters & { page?: number; page_size?: number } = {}): Promise<HrPeoplePage> {
  return apiJson(`/workforce/hr/people/governed${queryString(params)}`, { offline: { cacheTtlMs: 60_000 } });
}
export function getWorkforceHrPeopleFacets(): Promise<HrPeopleFacets> {
  return apiJson("/workforce/hr/people/governed/facets", { offline: { cacheTtlMs: 5 * 60_000 } });
}
export function previewWorkforceHrSelection(selection: HrPeopleSelection): Promise<{ matched_count: number; selection_token: string }> {
  return apiJson("/workforce/hr/people/governed/selection-preview", { method: "POST", body: jsonBody(selection) });
}
export async function previewWorkforceHrDefaultDayBatch(selection: HrPeopleSelection): Promise<HrDefaultDayBatchPreview> {
  const result = await apiJson<HrDefaultDayBatchPreview>("/workforce/hr/people/default-day-pattern/preview", {
    method: "POST", body: jsonBody(selection),
  });
  defaultDayPreviewTokens.set(selectionKey(selection), result.selection_token);
  return result;
}
export async function applyWorkforceHrDefaultDayBatch(
  selection: HrPeopleSelection, expectedMatchCount: number, expectedSelectionToken?: string,
): Promise<HrDefaultDayBatchResult> {
  const key = selectionKey(selection);
  const token = expectedSelectionToken || defaultDayPreviewTokens.get(key);
  if (!token) throw new Error("Preview this exact employee selection before applying the default work pattern.");
  const result = await apiJson<HrDefaultDayBatchResult>("/workforce/hr/people/default-day-pattern/apply", {
    method: "POST",
    body: jsonBody({ selection, expected_match_count: expectedMatchCount, expected_selection_token: token }),
  });
  defaultDayPreviewTokens.delete(key);
  return result;
}
export async function exportWorkforceHrPeople(selection: HrPeopleSelection): Promise<void> {
  const result = await apiBlob("/workforce/hr/people/export", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: jsonBody(selection),
  });
  downloadBlob(result.blob, result.filename || "workforce-people.csv");
}
/** @deprecated Tenant-wide bootstrap is default-denied; use controlled selection preview and durable submission. */
export function bootstrapWorkforceHrDefaultDayPattern(): Promise<HrDefaultDayBootstrap> {
  return apiJson("/workforce/hr/default-day-pattern", { method: "POST" });
}
export function listWorkforceHrPatterns(includeInactive = false): Promise<WorkPatternRead[]> {
  return apiJson(`/workforce/hr/work-patterns${queryString({ include_inactive: includeInactive })}`, {
    cache: "no-store",
    offline: { cacheTtlMs: 5 * 60_000 },
  });
}
export function assignWorkforceHrPattern(payload: WorkforceHrPatternAssignmentCreate): Promise<WorkPatternAssignmentRead> {
  return apiJson("/workforce/hr/work-pattern-assignments", { method: "POST", body: jsonBody(payload) });
}

export type WorkforceHrOvertimeCreate = {
  user_id?: string | null; roster_assignment_id?: string | null; starts_at: string; ends_at: string;
  requested_minutes?: number | null; reason: string;
};
export type WorkforceHrOvertimeDecision = { stage: "SUPERVISOR" | "HR"; decision: "APPROVED" | "REJECTED"; comment: string };
export function listWorkforceHrOvertime(pendingOnly = true): Promise<HrOvertimeRequest[]> {
  return apiJson(`/workforce/hr/overtime-requests${queryString({ pending_only: pendingOnly })}`, {
    offline: { cacheTtlMs: 30_000 },
  });
}
export function createWorkforceHrOvertime(payload: WorkforceHrOvertimeCreate): Promise<HrOvertimeRequest> {
  return apiJson("/workforce/hr/overtime-requests", { method: "POST", body: jsonBody(payload) });
}
export function decideWorkforceHrOvertime(requestId: string, payload: WorkforceHrOvertimeDecision): Promise<HrOvertimeRequest> {
  return apiJson(`/workforce/hr/overtime-requests/${encodeURIComponent(requestId)}/decision`, {
    method: "POST", body: jsonBody(payload),
  });
}

export type HrContractBatchPayload = {
  selection: HrPeopleSelection;
  defaults: HrContractDefaults;
  overrides?: HrContractOverride[];
  preview_limit?: number;
};
export function previewWorkforceHrContractBatch(payload: HrContractBatchPayload): Promise<HrContractBatchPreview> {
  return apiJson("/workforce/hr/people/contracts/preview", { method: "POST", body: jsonBody(payload) });
}
export function submitWorkforceHrContractBatch(
  payload: HrContractBatchPayload & { expected_match_count: number; expected_selection_token: string },
  idempotencyKey: string,
): Promise<HrBulkOperation> {
  return apiJson("/workforce/hr/bulk-operations/contracts", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: jsonBody(payload),
  });
}
export type HrWorkPatternBatchPayload = {
  selection: HrPeopleSelection;
  options: HrWorkPatternBatchOptions;
  preview_limit?: number;
};
export function previewWorkforceHrPatternBatch(payload: HrWorkPatternBatchPayload): Promise<HrWorkPatternBatchPreview> {
  return apiJson("/workforce/hr/people/work-patterns/preview", { method: "POST", body: jsonBody(payload) });
}
export function submitWorkforceHrPatternBatch(
  payload: HrWorkPatternBatchPayload & { expected_match_count: number; expected_selection_token: string },
  idempotencyKey: string,
): Promise<HrBulkOperation> {
  return apiJson("/workforce/hr/bulk-operations/work-patterns", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: jsonBody(payload),
  });
}
export function submitWorkforceHrDefaultDayOperation(
  selection: HrPeopleSelection, expectedMatchCount: number, expectedSelectionToken: string, idempotencyKey: string,
): Promise<HrBulkOperation> {
  return apiJson("/workforce/hr/bulk-operations/default-day-pattern", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: jsonBody({ selection, expected_match_count: expectedMatchCount, expected_selection_token: expectedSelectionToken }),
  });
}
export function submitWorkforceHrPersonnelMutation(payload: HrPersonnelMutationPayload, idempotencyKey: string): Promise<HrBulkOperation> {
  return apiJson("/workforce/hr/bulk-operations/personnel", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: jsonBody(payload),
  });
}
export function getWorkforceHrBulkOperation(operationId: string): Promise<HrBulkOperation> {
  return apiJson(`/workforce/hr/bulk-operations/${encodeURIComponent(operationId)}`, {
    offline: { cacheTtlMs: 0 },
  });
}
export function listWorkforceHrBulkOperations(params: { page?: number; page_size?: number; status?: string; operation_type?: string } = {}): Promise<HrBulkOperationsPage> {
  return apiJson(`/workforce/hr/bulk-operations${queryString(params)}`, { offline: { cacheTtlMs: 10_000 } });
}
export function listWorkforceHrBulkOperationItems(
  operationId: string, params: { page?: number; page_size?: number; status?: string } = {},
): Promise<HrBulkOperationItemsPage> {
  return apiJson(`/workforce/hr/bulk-operations/${encodeURIComponent(operationId)}/items${queryString(params)}`, {
    offline: { cacheTtlMs: 5_000 },
  });
}
export function retryWorkforceHrBulkOperation(operationId: string, idempotencyKey: string): Promise<HrBulkOperation> {
  return apiJson(`/workforce/hr/bulk-operations/${encodeURIComponent(operationId)}/retry`, {
    method: "POST", body: jsonBody({ idempotency_key: idempotencyKey }),
  });
}
export function resumeWorkforceHrBulkOperation(operationId: string): Promise<HrBulkOperation> {
  return apiJson(`/workforce/hr/bulk-operations/${encodeURIComponent(operationId)}/resume`, { method: "POST" });
}
export async function downloadWorkforceHrBulkFailures(operationId: string): Promise<void> {
  const result = await apiBlob(`/workforce/hr/bulk-operations/${encodeURIComponent(operationId)}/failures.csv`);
  downloadBlob(result.blob, result.filename || `workforce-bulk-${operationId}-failures.csv`);
}

export function listWorkforceHrOrgUnits(includeInactive = false): Promise<HrOrgUnit[]> {
  return apiJson(`/workforce/hr/organization-units${queryString({ include_inactive: includeInactive })}`);
}
export function saveWorkforceHrOrgUnit(payload: HrOrgUnitWrite, id?: string): Promise<HrOrgUnit> {
  return apiJson(id ? `/workforce/hr/organization-units/${encodeURIComponent(id)}` : "/workforce/hr/organization-units", {
    method: id ? "PUT" : "POST", body: jsonBody(payload),
  });
}
export function listWorkforceHrJobFamilies(includeInactive = false): Promise<HrJobFamily[]> {
  return apiJson(`/workforce/hr/job-families${queryString({ include_inactive: includeInactive })}`);
}
export function saveWorkforceHrJobFamily(payload: HrJobFamilyWrite, id?: string): Promise<HrJobFamily> {
  return apiJson(id ? `/workforce/hr/job-families/${encodeURIComponent(id)}` : "/workforce/hr/job-families", {
    method: id ? "PUT" : "POST", body: jsonBody(payload),
  });
}
export function listWorkforceHrGrades(includeInactive = false): Promise<HrGrade[]> {
  return apiJson(`/workforce/hr/grades${queryString({ include_inactive: includeInactive })}`);
}
export function saveWorkforceHrGrade(payload: HrGradeWrite, id?: string): Promise<HrGrade> {
  return apiJson(id ? `/workforce/hr/grades/${encodeURIComponent(id)}` : "/workforce/hr/grades", {
    method: id ? "PUT" : "POST", body: jsonBody(payload),
  });
}
export function listWorkforceHrPositions(includeInactive = false): Promise<HrPosition[]> {
  return apiJson(`/workforce/hr/positions${queryString({ include_inactive: includeInactive })}`);
}
export function getWorkforceHrHierarchyBlueprint(): Promise<HrHierarchyBlueprint> {
  return apiJson("/workforce/hr/positions/hierarchy-blueprint", { offline: { cacheTtlMs: 60_000 } });
}
export function initializeWorkforceHrKcars2025Hierarchy(): Promise<HrHierarchyBlueprint> {
  return apiJson("/workforce/hr/positions/initialize-kcars-2025", { method: "POST" });
}
export function saveWorkforceHrPosition(payload: HrPositionWrite, id?: string): Promise<HrPosition> {
  return apiJson(id ? `/workforce/hr/positions/${encodeURIComponent(id)}` : "/workforce/hr/positions", {
    method: id ? "PUT" : "POST", body: jsonBody(payload),
  });
}
export function listWorkforceHrSupervisors(params: { page?: number; page_size?: number; search?: string; org_unit_id?: string; exclude_user_id?: string } = {}): Promise<HrSupervisorOptionsPage> {
  return apiJson(`/workforce/hr/supervisors${queryString(params)}`, { offline: { cacheTtlMs: 60_000 } });
}
