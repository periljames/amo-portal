import React, { useState, useSyncExternalStore } from "react";
import { RefreshCw } from "lucide-react";
import { checkPortalRelease, getPortalRelease, reloadPortalRelease, subscribePortalRelease } from "../../services/portalRelease";

export default function PortalUpdateMenuItem() {
  const release = useSyncExternalStore(subscribePortalRelease, getPortalRelease);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  return <>
    <button type="button" role="menuitem" disabled={busy || release.checking} onClick={() => {
      setMessage("");
      if (release.available) {
        setBusy(true);
        void reloadPortalRelease().catch(error => { setMessage(error instanceof Error ? error.message : "Update could not be loaded."); setBusy(false); });
      } else void checkPortalRelease().then(() => { const result = getPortalRelease(); setMessage(result.error || (result.available ? "Save your work before reloading." : "You’re using the latest portal version.")); });
    }}><RefreshCw size={15}/>{busy ? "Preparing update…" : release.checking ? "Checking portal version…" : release.available ? "Reload portal update" : "Check for portal updates"}</button>
    {message ? <p role="status" style={{ margin: "4px 12px 8px", fontSize: 12 }}>{message}</p> : null}
  </>;
}
