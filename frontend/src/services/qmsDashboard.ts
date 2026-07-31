// src/services/qmsDashboard.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsDashboardResponse, QmsOperationalDashboardResponse } from "../types/qms";

export function getQmsDashboard(amoCode: string): Promise<QmsDashboardResponse> {
  return apiRequest<QmsDashboardResponse>(qmsPath(amoCode, "/dashboard-lite"), {
    timeoutMs: 8_000,
    cacheTtlMs: 20_000,
  });
}

export function getQmsOperationalDashboard(
  amoCode: string,
  signal?: AbortSignal,
): Promise<QmsOperationalDashboardResponse> {
  return apiRequest<QmsOperationalDashboardResponse>(qmsPath(amoCode, "/dashboard-v2"), {
    timeoutMs: 12_000,
    cacheTtlMs: 15_000,
    signal,
  });
}
