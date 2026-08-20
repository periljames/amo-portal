import type { PortalConnectivityState } from "./portalConnectivity";

/**
 * Decide whether a request may use the network without consulting a health
 * endpoint synchronously.
 *
 * Read requests deliberately ignore the shared portal OFFLINE/RECOVERING state
 * while the browser itself is online. That shared state is advisory and can be
 * stale (for example, a liveness probe may fail while an application route is
 * already recoverable).
 *
 * DEGRADED still means the API is reachable, so mutations must be allowed to
 * reach their authoritative endpoint and receive the real response. OFFLINE and
 * RECOVERING remain protected; RECOVERING mutations are handled by the caller's
 * readiness wait/reprobe path before this predicate is evaluated again.
 */
export function isPortalRequestNetworkEligible(
  method: string,
  state: PortalConnectivityState,
  browserOnline: boolean,
): boolean {
  if (!browserOnline || state === "SESSION_EXPIRED") return false;
  if (method.toUpperCase() === "GET") return true;
  return state === "ONLINE" || state === "DEGRADED";
}
