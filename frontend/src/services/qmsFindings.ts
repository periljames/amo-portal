// src/services/qmsFindings.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsFindings(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/findings"));
}
