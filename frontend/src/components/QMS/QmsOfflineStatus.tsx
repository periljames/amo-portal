import { useSyncExternalStore } from "react";
import { getPortalConnectivity, onPortalConnectivityChange, probePortalReadiness } from "../../services/portalConnectivity";

const subscribe = (listener: () => void) => onPortalConnectivityChange(listener);
const snapshot = () => getPortalConnectivity().state;

export default function QmsOfflineStatus() {
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  if (state === "ONLINE" || state === "SESSION_EXPIRED") return null;
  return <aside className="qms-offline-status" role="status">
    <strong>{state === "RECOVERING" ? "Reconnecting to Quality" : "Quality is using saved data"}</strong>
    <span>Previously opened records remain available on this device. Approvals, team verification and document issue require a live connection.</span>
    <button type="button" onClick={() => void probePortalReadiness(true)}>Check connection</button>
  </aside>;
}
