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
 * DEGRADED and RECOVERING are also advisory for mutations when the browser
 * itself reports online: writes must not be serialized behind a health-probe
 * round trip. OFFLINE and SESSION_EXPIRED remain hard blocks.
 */
export function isPortalRequestNetworkEligible(
  method: string,
  state: PortalConnectivityState,
  browserOnline: boolean,
): boolean {
  if (!browserOnline || state === "SESSION_EXPIRED") return false;
  if (method.toUpperCase() === "GET") return true;
  return state === "ONLINE" || state === "DEGRADED" || state === "RECOVERING";
}
