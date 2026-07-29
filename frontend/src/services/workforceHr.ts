import { apiJson, jsonBody, queryString } from "./typedApi";
import type { HrDashboard, HrOvertimeRequest, HrPeoplePage } from "../types/workforceHr";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../types/workforce";

export type WorkforceHrPatternAssignmentCreate = {
  user_id: string;
  work_pattern_id: string;
  effective_from: string;
  effective_to?: string | null;
  cycle_anchor_date: string;
};

export function getWorkforceHrDashboard(peopleLimit = 200): Promise<HrDashboard> {
  return apiJson(`/workforce/hr/dashboard${queryString({ people_limit: peopleLimit })}`, {
    offline: { cacheTtlMs: 60_000 },
  });
}

export function listWorkforceHrPeople(params: {
    page?: number;
    page_size?: number;
    search?: string;
} = {}): Promise<HrPeoplePage> {
    return apiJson(`/workforce/hr/people${queryString(params)}`, {
        offline: { cacheTtlMs: 60_000 },
    });
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
