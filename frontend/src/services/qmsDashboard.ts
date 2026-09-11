// src/services/qmsDashboard.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsDashboardResponse, QmsOperationalDashboardResponse } from "../types/qms";

export function getQmsDashboard(amoCode: string, fresh = false): Promise<QmsDashboardResponse> {
  return apiRequest<QmsDashboardResponse>(qmsPath(amoCode, "/dashboard-lite"), {
    timeoutMs: 10_000,
    cacheTtlMs: fresh ? 0 : 30_000,
    persistCache: true,
    staleWhileOfflineMs: 30 * 60_000,
  });
}

export function getQmsOperationalDashboard(
  amoCode: string,
  signal?: AbortSignal,
): Promise<QmsOperationalDashboardResponse> {
  return apiRequest<QmsOperationalDashboardResponse>(qmsPath(amoCode, "/dashboard-v2"), {
    timeoutMs: 15_000,
    cacheTtlMs: 0,
    persistCache: true,
    staleWhileOfflineMs: 30 * 60_000,
    signal,
  });
}
