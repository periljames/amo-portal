// src/services/qmsEquipment.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsEquipment(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/equipment-calibration"));
}
