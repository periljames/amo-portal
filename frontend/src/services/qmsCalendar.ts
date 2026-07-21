// src/services/qmsCalendar.ts
import { apiRequest, qualityPath } from "./apiClient";
import type { QmsCalendarResponse } from "../types/qms";

export type QualityCalendarParams = {
  start?: string;
  end?: string;
  source?: "all" | "audits" | "cars" | "training" | string;
  view?: string;
  limit?: number;
  offset?: number;
};

function qs(params: QualityCalendarParams = {}): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") search.set(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export function getQmsCalendar(amoCode: string, params: QualityCalendarParams = {}): Promise<QmsCalendarResponse> {
  return apiRequest<QmsCalendarResponse>(qualityPath(amoCode, `/integrations/calendar${qs(params)}`), {
    timeoutMs: 8000,
    cacheTtlMs: 20_000,
  });
}

export const getQualityCalendar = getQmsCalendar;
