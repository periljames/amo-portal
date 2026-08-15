import { apiBlob, apiJson, downloadBlob, jsonBody } from "./typedApi";

export const ROSTER_CALENDAR_QUERY_ROOT = [
  "rostering",
  "self-service",
  "calendar-subscription",
] as const;
export const ROSTER_CALENDAR_LINK_QUERY_KEY = [
  ...ROSTER_CALENDAR_QUERY_ROOT,
  "link",
] as const;
export const ROSTER_CALENDAR_STATUS_QUERY_KEY = [
  ...ROSTER_CALENDAR_QUERY_ROOT,
  "status",
] as const;

export type ControlledRosterSettings = {
  form_number: string;
  revision_label?: string | null;
  revision_date?: string | null;
  footer_note?: string | null;
  prepared_by_label: string;
  approved_by_label: string;
  page_size: "A3" | "A4";
};

export type CalendarSubscriptionStatus = {
  active: boolean;
  created_at?: string | null;
  rotated_at?: string | null;
  revoked_at?: string | null;
  last_used_at?: string | null;
  refresh_interval_minutes: number;
  includes: string[];
};

export type CalendarSubscriptionLink = CalendarSubscriptionStatus & {
  https_url: string;
  webcal_url: string;
  feed_path: string;
};

export function getControlledRosterSettings(): Promise<ControlledRosterSettings> {
  return apiJson("/rostering/controlled-document/settings", {
    offline: { cacheTtlMs: 15 * 60_000 },
  });
}

export function updateControlledRosterSettings(
  payload: Partial<ControlledRosterSettings>,
): Promise<ControlledRosterSettings> {
  return apiJson("/rostering/controlled-document/settings", {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

export async function downloadControlledRoster(
  versionId: string,
  format: "pdf" | "xlsx",
): Promise<void> {
  const result = await apiBlob(`/rostering/versions/${encodeURIComponent(versionId)}/controlled-roster.${format}`);
  downloadBlob(result.blob, result.filename || `controlled-roster-${versionId}.${format}`);
}

export function getCalendarSubscriptionStatus(): Promise<CalendarSubscriptionStatus> {
  return apiJson("/rostering/calendar/subscription/status", {
    offline: { cacheTtlMs: 60_000 },
  });
}

export function createCalendarSubscription(): Promise<CalendarSubscriptionLink> {
  return apiJson("/rostering/calendar/subscription", { method: "POST" });
}

export function rotateCalendarSubscription(): Promise<CalendarSubscriptionLink> {
  return apiJson("/rostering/calendar/subscription/rotate", { method: "POST" });
}

export function revokeCalendarSubscription(): Promise<void> {
  return apiJson("/rostering/calendar/subscription", { method: "DELETE" });
}
