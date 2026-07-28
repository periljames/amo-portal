import { apiJson, queryString } from "./typedApi";
import type { HrDashboard } from "../types/workforceHr";

export function getWorkforceHrDashboard(peopleLimit = 200): Promise<HrDashboard> {
  return apiJson(`/workforce/hr/dashboard${queryString({ people_limit: peopleLimit })}`, {
    offline: { cacheTtlMs: 60_000 },
  });
}
