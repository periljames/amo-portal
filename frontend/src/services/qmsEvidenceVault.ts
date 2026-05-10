// src/services/qmsEvidenceVault.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsEvidenceVault(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/evidence-vault"));
}
