import { apiJson, jsonBody, queryString } from "./typedApi";
import type { HrDashboard } from "../types/workforceHr";
import type {
  EmployeeWorkPatternAssignmentCreate,
  EmployeeWorkPatternAssignmentRead,
  WorkPatternRead,
} from "../types/workforce";

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
  payload: EmployeeWorkPatternAssignmentCreate,
): Promise<EmployeeWorkPatternAssignmentRead> {
  return apiJson("/workforce/hr/work-pattern-assignments", {
    method: "POST",
    body: jsonBody(payload),
  });
}
