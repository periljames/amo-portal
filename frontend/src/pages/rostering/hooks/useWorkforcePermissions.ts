import { useQuery } from "@tanstack/react-query";

import { getCurrentWorkforcePermissions } from "../../../services/workforce";

export const WORKFORCE_PERMISSIONS_QUERY_KEY = ["workforce", "permissions", "current"] as const;

/**
 * Permission checks are authorization state, not offline business data.
 * Keep every consumer on one live, non-persisted query and never turn a
 * transport pause or stale browser snapshot into an access-denied decision.
 */
export function useWorkforcePermissions() {
  return useQuery({
    queryKey: WORKFORCE_PERMISSIONS_QUERY_KEY,
    queryFn: getCurrentWorkforcePermissions,
    staleTime: 0,
    gcTime: 5 * 60_000,
    networkMode: "online",
    refetchOnMount: "always",
    refetchOnReconnect: "always",
    refetchOnWindowFocus: true,
    retry: (failureCount, error) => {
      const status = typeof error === "object" && error && "status" in error
        ? Number((error as { status?: unknown }).status)
        : 0;
      return failureCount < 2 && status !== 401 && status !== 403;
    },
  });
}
