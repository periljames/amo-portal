import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useRealtime } from "../realtime/realtimeContext";
import {
  emitSessionEvent,
  fetchCurrentUser,
  getCachedUser,
} from "../../services/auth";

/**
 * Turns committed accounts.access_sync SSE events into immediate portal state.
 *
 * The backend remains authoritative. This bridge only refreshes cached frontend
 * projections after the committed change has been announced by the server.
 */
export default function AccessRealtimeBridge() {
  const queryClient = useQueryClient();
  const { activity } = useRealtime();
  const lastHandledId = useRef("");
  const latest = activity[0];

  useEffect(() => {
    if (!latest || latest.id === lastHandledId.current) return;
    if (latest.entityType !== "accounts.access_sync") return;
    lastHandledId.current = latest.id;

    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
    void queryClient.invalidateQueries({ queryKey: ["access-elevation-requests"] });
    void queryClient.invalidateQueries({ queryKey: ["access-context"] });

    const current = getCachedUser();
    if (!current) return;
    const subjectUserId = String(latest.metadata?.subjectUserId || "");
    const profileId = String(latest.metadata?.profileId || "");
    const affectsCurrentUser = latest.action === "FRAMEWORK_INITIALIZED"
      || subjectUserId === current.id
      || (Boolean(profileId) && profileId === current.access_profile_id);
    if (!affectsCurrentUser) return;

    void fetchCurrentUser()
      .then((refreshed) => {
        queryClient.setQueryData(["current-user-profile"], refreshed);
        void queryClient.invalidateQueries({ queryKey: ["current-user-profile"] });
        emitSessionEvent({
          type: "authenticated",
          reason: "access-context-changed",
          at: Date.now(),
        });
      })
      .catch(() => {
        // The normal authenticated request path remains authoritative. A later
        // SSE event, route transition, focus refetch or manual refresh retries.
      });
  }, [latest, queryClient]);

  return null;
}
