import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import { getApiBaseUrl } from "../../services/config";
import { authHeaders } from "../../services/auth";
import { portalFetch } from "../../services/offlineHttp";
import { retryPublicationOfficeLayout, verifyPublicationOfficeLayout } from "../../services/publications";
import { DocumentControlSection } from "./DocumentControlShell";
import "./documentMicrosoft.css";

type Status = {
  status: string;
  source_sha256?: string | null;
  pdf_sha256?: string | null;
  page_count?: number | null;
  source_media_count?: number | null;
  rendered_image_count?: number | null;
  warning?: string | null;
  error?: string | null;
  verified_at?: string | null;
  verified_by?: string | null;
};

export default function DocumentWordRenditionPanel({
  tenant, manualId, revisionId,
}: { tenant: string; manualId: string; revisionId: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const path = "/manuals/t/" + encodeURIComponent(tenant) + "/" + encodeURIComponent(manualId) + "/rev/" + encodeURIComponent(revisionId) + "/layout-status";
      const response = await portalFetch(getApiBaseUrl() + path, { headers: authHeaders(), credentials: "same-origin" });
      if (!response.ok) throw new Error("Rendition status unavailable (" + response.status + ")");
      setStatus(await response.json() as Status); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Rendition unavailable"); }
  }, [tenant, manualId, revisionId]);
  useEffect(() => { void load(); }, [load]);
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Rendition action failed"); }
    finally { setBusy(false); }
  };
  return <DocumentControlSection title="Word layout rendition verification"
    description="The original DOCX remains immutable. A PDF proof is a derivative and is not asserted to match Word until Document Control reviews it.">
    <div className="dms-microsoft">
      {error ? <p role="alert" className="dms-microsoft__error">{error}</p> : null}
      {status ? <>
        <div className="dms-microsoft__row"><ShieldCheck size={20} /><div>
          <strong>{status.status.replaceAll("_", " ")}</strong>
          <small>{status.page_count ? status.page_count + " rendered pages" : "Rendition not yet available"} · {status.verified_at ? "Verified " + new Date(status.verified_at).toLocaleString() : "Not visually verified"}</small>
        </div></div>
        {status.warning ? <p className="dms-microsoft__error">{status.warning}</p> : null}
        {status.error ? <p className="dms-microsoft__error">{status.error}</p> : null}
        <div className="dms-microsoft__actions">
          <button type="button" className="dc-button" onClick={() => void load()} disabled={busy}><RefreshCw size={14} /> Refresh</button>
          {status.status === "FAILED" ? <button type="button" className="dc-button" disabled={busy} onClick={() => void perform(async () => { await retryPublicationOfficeLayout(tenant, manualId, revisionId); })}>Retry conversion</button> : null}
        </div>
        {(status.status === "READY" || status.status === "REVIEW_REQUIRED") && !status.verified_at && status.pdf_sha256 ? <div className="dms-microsoft__form">
          <label className="dms-microsoft__wide"><span>Visual verification note</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Confirm pages, logos, tables, headers, footers and pagination against the original Word file." rows={2} /></label>
          <button type="button" className="dc-button dc-button--primary" disabled={busy || note.trim().length < 8} onClick={() => void perform(async () => {
            await verifyPublicationOfficeLayout(tenant, manualId, revisionId, status.pdf_sha256!, note.trim());
            setNote("");
          })}><CheckCircle2 size={15} /> Verify this rendition</button>
        </div> : null}
      </> : <p>Loading Word rendition status…</p>}
    </div>
  </DocumentControlSection>;
}
