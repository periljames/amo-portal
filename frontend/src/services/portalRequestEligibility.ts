import type { PortalConnectivityState } from "./portalConnectivity";

/**
 * Decide whether a request may use the network without consulting a health
 * endpoint synchronously.
 *
 * Read requests deliberately ignore the shared portal OFFLINE/RECOVERING state
 * while the browser itself is online. That shared state is advisory and can be
 * stale (for example, a liveness probe may fail while an application route is
 * already recoverable). Mutations remain protected until ONLINE is confirmed.
 */
export function isPortalRequestNetworkEligible(
  method: string,
  state: PortalConnectivityState,
  browserOnline: boolean,
): boolean {
  if (!browserOnline || state === "SESSION_EXPIRED") return false;
  return method.toUpperCase() === "GET" || state === "ONLINE";
}
