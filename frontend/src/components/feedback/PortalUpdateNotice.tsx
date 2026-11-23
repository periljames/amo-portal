import React, { useEffect, useState, useSyncExternalStore } from "react";
import { getPortalRelease, reloadPortalRelease, startPortalReleaseChecks, subscribePortalRelease } from "../../services/portalRelease";
import "./portal-update-notice.css";
import { getPortalConnectivity, onPortalConnectivityChange } from "../../services/portalConnectivity";

export default function PortalUpdateNotice() {
  const release = useSyncExternalStore(subscribePortalRelease, getPortalRelease);
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(() => getPortalConnectivity().state === "ONLINE");
  const [fieldworkActive, setFieldworkActive] = useState(false);
  useEffect(startPortalReleaseChecks, []);
  useEffect(() => onPortalConnectivityChange(value => setConnected(value.state === "ONLINE")), []);
  useEffect(() => {
    const active = (event: Event) => setFieldworkActive(Boolean((event as CustomEvent<boolean>).detail));
    window.addEventListener("amo:fieldwork-active", active);
    return () => window.removeEventListener("amo:fieldwork-active", active);
  }, []);
  if (!release.available || dismissed || !connected || fieldworkActive) return null;
  return <aside className="portal-update-notice" role="status" aria-label="Portal update available">
    <strong>A portal update is available</strong>
    <p>Save your work, then reload to use the latest interface.</p>
    {error ? <p role="alert">{error}</p> : null}
    <div><button type="button" disabled={busy} onClick={() => { setBusy(true); setError(null); void reloadPortalRelease().catch(cause => { setError(cause instanceof Error ? cause.message : "Update could not be loaded."); setBusy(false); }); }}>{busy ? "Preparing update…" : "Reload portal"}</button><button type="button" disabled={busy} onClick={() => setDismissed(true)}>Later</button></div>
  </aside>;
}
