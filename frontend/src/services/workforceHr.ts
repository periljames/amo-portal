import { apiBlob, apiJson, downloadBlob, jsonBody, queryString } from "./typedApi";
import type {
  HrDashboard,
  HrDefaultDayBatchPreview,
  HrDefaultDayBatchResult,
  HrDefaultDayBootstrap,
  HrOvertimeRequest,
  HrPeopleFacets,
  HrPeopleFilters,
  HrPeoplePage,
  HrPeopleSelection,
} from "../types/workforceHr";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../types/workforce";

export type WorkforceHrPatternAssignmentCreate = {
  user_id: string;
  work_pattern_id: string;
  effective_from: string;
  effective_to?: string | null;
  cycle_anchor_date: string;
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

export function listWorkforceHrPeople(params: HrPeopleFilters & {
  page?: number;
  page_size?: number;
} = {}): Promise<HrPeoplePage> {
  return apiJson(`/workforce/hr/people${queryString(params)}`, {
    offline: { cacheTtlMs: 60_000 },
  });
}

export function getWorkforceHrPeopleFacets(): Promise<HrPeopleFacets> {
  return apiJson("/workforce/hr/people/facets", {
    offline: { cacheTtlMs: 5 * 60_000 },
  });
}

export async function previewWorkforceHrDefaultDayBatch(
  selection: HrPeopleSelection,
): Promise<HrDefaultDayBatchPreview> {
  const result = await apiJson<HrDefaultDayBatchPreview>(
    "/workforce/hr/people/default-day-pattern/preview",
    {
      method: "POST",
      body: jsonBody(selection),
    },
  );
  defaultDayPreviewTokens.set(selectionKey(selection), result.selection_token);
  return result;
}

export async function applyWorkforceHrDefaultDayBatch(
  selection: HrPeopleSelection,
  expectedMatchCount: number,
  expectedSelectionToken?: string,
): Promise<HrDefaultDayBatchResult> {
  const key = selectionKey(selection);
  const token = expectedSelectionToken || defaultDayPreviewTokens.get(key);
  if (!token) {
    throw new Error("Preview this exact employee selection before applying the default work pattern.");
  }
  const result = await apiJson<HrDefaultDayBatchResult>(
    "/workforce/hr/people/default-day-pattern/apply",
    {
      method: "POST",
      body: jsonBody({
        selection,
        expected_match_count: expectedMatchCount,
        expected_selection_token: token,
      }),
    },
  );
  defaultDayPreviewTokens.delete(key);
  return result;
}

export async function exportWorkforceHrPeople(selection: HrPeopleSelection): Promise<void> {
  const result = await apiBlob("/workforce/hr/people/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonBody(selection),
  });
  downloadBlob(result.blob, result.filename || "workforce-people.csv");
}

export function bootstrapWorkforceHrDefaultDayPattern(): Promise<HrDefaultDayBootstrap> {
  return apiJson("/workforce/hr/default-day-pattern", { method: "POST" });
}

export function listWorkforceHrPatterns(includeInactive = false): Promise<WorkPatternRead[]> {
  return apiJson(`/workforce/hr/work-patterns${queryString({ include_inactive: includeInactive })}`, {
    offline: { cacheTtlMs: 5 * 60_000 },
  });
}

export function assignWorkforceHrPattern(
  payload: WorkforceHrPatternAssignmentCreate,
): Promise<WorkPatternAssignmentRead> {
  return apiJson("/workforce/hr/work-pattern-assignments", {
    method: "POST",
    body: jsonBody(payload),
  });
}

export type WorkforceHrOvertimeCreate = {
  user_id?: string | null;
  roster_assignment_id?: string | null;
  starts_at: string;
  ends_at: string;
  requested_minutes?: number | null;
  reason: string;
};

export type WorkforceHrOvertimeDecision = {
  stage: "SUPERVISOR" | "HR";
  decision: "APPROVED" | "REJECTED";
  comment: string;
};

export function listWorkforceHrOvertime(pendingOnly = true): Promise<HrOvertimeRequest[]> {
  return apiJson(`/workforce/hr/overtime-requests${queryString({ pending_only: pendingOnly })}`, {
    offline: { cacheTtlMs: 30_000 },
  });
}

export function createWorkforceHrOvertime(payload: WorkforceHrOvertimeCreate): Promise<HrOvertimeRequest> {
  return apiJson("/workforce/hr/overtime-requests", { method: "POST", body: jsonBody(payload) });
}

export function decideWorkforceHrOvertime(
  requestId: string,
  payload: WorkforceHrOvertimeDecision,
): Promise<HrOvertimeRequest> {
  return apiJson(`/workforce/hr/overtime-requests/${encodeURIComponent(requestId)}/decision`, {
    method: "POST",
    body: jsonBody(payload),
  });
}
