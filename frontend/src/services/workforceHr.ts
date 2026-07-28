import { apiJson, jsonBody, queryString } from "./typedApi";
import type { HrDashboard } from "../types/workforceHr";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../types/workforce";

export type WorkforceHrPatternAssignmentCreate = {
  user_id: string;
  work_pattern_id: string;
  effective_from: string;
  effective_to?: string | null;
  cycle_anchor_date?: string | null;
};

export function getWorkforceHrDashboard(peopleLimit = 200): Promise<HrDashboard> {
  return apiJson(`/workforce/hr/dashboard${queryString({ people_limit: peopleLimit })}`, {
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
