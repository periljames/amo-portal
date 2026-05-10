// src/services/qmsReports.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsReports(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/reports"));
}
