// src/hooks/useAnalytics.ts
// Shared hook for emitting non-blocking analytics events.

import { useCallback } from "react";
import { trackEvent } from "../services/analytics";

export type AnalyticsPayload = Record<string, unknown>;

export function useAnalytics() {
  const track = useCallback(
    (event: string, details: AnalyticsPayload = {}) => {
      void trackEvent(event, details);
    },
    []
  );

  return { trackEvent: track };
}
