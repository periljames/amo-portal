import { useEffect, useState } from "react";

import { onSessionEvent } from "../services/auth";

/**
 * Re-render access-sensitive UI when the authenticated user's effective access
 * context changes. The access realtime bridge refreshes /auth/me first, then
 * emits the authenticated access-context-changed session event. onSessionEvent
 * also receives the same event from other tabs through the existing session
 * sync channel.
 */
export function useAccessRevision(): number {
  const [revision, setRevision] = useState(0);

  useEffect(() => onSessionEvent((detail) => {
    if (detail.type !== "authenticated" || detail.reason !== "access-context-changed") return;
    setRevision((value) => value + 1);
  }), []);

  return revision;
}
