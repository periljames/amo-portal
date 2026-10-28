import { useCallback, useEffect, useState } from "react";
import { Cloud, Link2, RefreshCw, Unplug } from "lucide-react";
import {
  microsoftConnection, startMicrosoftConnection, disconnectMicrosoft,
  type MicrosoftConnection,
} from "../../services/documentMicrosoft";
import { DocumentControlSection } from "./DocumentControlShell";
import "./documentMicrosoft.css";

export default function DocumentMicrosoftConnectionPanel({ tenant }: { tenant: string }) {
  const [state, setState] = useState<MicrosoftConnection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    if (!tenant) return;
    try { setState(await microsoftConnection(tenant)); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Connection status unavailable"); }
  }, [tenant]);
  useEffect(() => { void load(); }, [load]);

  const connect = async () => {
    setBusy(true); setError("");
    try {
      const next = await startMicrosoftConnection(tenant);
      const url = new URL(next.authorization_url);
      if (!url.hostname.endsWith(".microsoftonline.com") || url.protocol !== "https:") {
        throw new Error("Unexpected Microsoft authorization destination");
      }
      window.location.assign(url.href);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not initiate Microsoft authorization");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect Microsoft 365? Published manuals and past import records will remain unchanged.")) return;
    setBusy(true); setError("");
    try { await disconnectMicrosoft(tenant); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Disconnect failed"); }
    finally { setBusy(false); }
  };

  return <DocumentControlSection
    title="Microsoft 365 and SharePoint"
    description="Optional tenant-owned connection. Continue editing manuals in desktop Word or Word for the web; import a stable copy only when starting a controlled DMS revision."
    actions={<button type="button" className="dc-button" onClick={() => void load()} disabled={busy}><RefreshCw size={14} /> Refresh</button>}
  >
    <div className="dms-microsoft" data-testid="dms-microsoft-settings">
      {error ? <p role="alert" className="dms-microsoft__error">{error}</p> : null}
      {!state ? <p>Loading Microsoft 365 connection…</p> : <>
        <div className="dms-microsoft__row">
          <Cloud size={22} />
          <div><strong>{state.connected ? "Connected to Microsoft 365" : state.configured ? "Microsoft 365 is not connected" : "Microsoft 365 setup required"}</strong>
            <small>{state.connected ? state.microsoft_user_name || state.microsoft_tenant_id || "Authorized Microsoft account" : state.configured ? "The tenant administrator can authorize the connection." : "Platform administrator must configure the Microsoft app ID, secret, redirect URI and portal URL."}</small></div>
        </div>
        {state.last_error ? <p className="dms-microsoft__error">{state.last_error}</p> : null}
        <div className="dms-microsoft__actions">
          {state.can_configure && state.configured && !state.connected ? <button type="button" className="dc-button dc-button--primary" onClick={() => void connect()} disabled={busy}><Link2 size={15} /> Connect Microsoft 365</button> : null}
          {state.can_configure && state.connected ? <button type="button" className="dc-button" onClick={() => void disconnect()} disabled={busy}><Unplug size={15} /> Disconnect</button> : null}
        </div>
      </>}
      <p className="dms-microsoft__hint">Connection uses an authorized Microsoft account. SharePoint permissions still apply. No Microsoft sign-in is needed to read a manual already published in AMO Portal.</p>
    </div>
  </DocumentControlSection>;
}
