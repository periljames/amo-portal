// src/services/analytics.ts
// Lightweight telemetry helper that reuses the billing audit endpoint.

import { apiPost } from "./crs";
import { authHeaders } from "./auth";

type AnalyticsDetails = Record<string, unknown>;

export async function trackEvent(
  event: string,
  details: AnalyticsDetails = {}
): Promise<void> {
  if (!event || !event.trim()) return;

  try {
    await apiPost<{ id: string | null }>(
      "/billing/audit-events",
      {
        event_type: event,
        details,
      },
      {
        headers: authHeaders(),
      }
    );
  } catch (err) {
    // Telemetry should never block the UX; surface debug info only.
    console.debug("Analytics track failed:", err);
  }
}
