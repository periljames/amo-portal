// src/services/qmsDashboard.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsDashboardResponse } from "../types/qms";

export function getQmsDashboard(amoCode: string): Promise<QmsDashboardResponse> {
  return apiRequest<QmsDashboardResponse>(qmsPath(amoCode, "/dashboard"));
}
