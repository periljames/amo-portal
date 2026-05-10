// src/services/qmsTraining.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsTrainingDashboardResponse } from "../types/qms";

export function getQmsTrainingDashboard(amoCode: string): Promise<QmsTrainingDashboardResponse> {
  return apiRequest<QmsTrainingDashboardResponse>(qmsPath(amoCode, "/training-competence/dashboard"));
}
