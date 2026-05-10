// src/services/qmsCalendar.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsCalendarResponse } from "../types/qms";

export function getQmsCalendar(amoCode: string): Promise<QmsCalendarResponse> {
  return apiRequest<QmsCalendarResponse>(qmsPath(amoCode, "/calendar"));
}
