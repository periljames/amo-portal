import { useCallback, useEffect, useState } from "react";
import { Download, ExternalLink, Link2, RefreshCw, Unlink } from "lucide-react";
import {
  checkMicrosoftDocument, getMicrosoftDocument, importMicrosoftDocument,
  linkMicrosoftDocument, microsoftConnection, unlinkMicrosoftDocument,
  type MicrosoftLinkState,
} from "../../services/documentMicrosoft";
import { DocumentControlSection } from "./DocumentControlShell";
import "./documentMicrosoft.css";

export default function DocumentMicrosoftFilePanel({
  tenant, manualId, onChanged,
}: { tenant: string; manualId: string; onChanged: () => void }) {
  const [connected, setConnected] = useState(false);
  const [link, setLink] = useState<MicrosoftLinkState | null>(null);
  const [shareUrl, setShareUrl] = useState("");
  const [revision, setRevision] = useState("");
  const [issue, setIssue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    if (!tenant || !manualId) return;
    try {
      const [connection, linked] = await Promise.all([
        microsoftConnection(tenant), getMicrosoftDocument(tenant, manualId),
      ]);
      setConnected(connection.connected);
      setLink(linked);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the SharePoint document link");
    }
  }, [tenant, manualId]);
  useEffect(() => { void load(); }, [load]);

  const action = async (perform: () => Promise<void>) => {
    setBusy(true); setError(""); setSuccess("");
    try { await perform(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The requested SharePoint action failed"); }
    finally { setBusy(false); }
  };
  const selected = link?.file;

  return <DocumentControlSection title="Word working document (SharePoint)"
    description="Link the working Microsoft Word file. Edits remain in SharePoint; a checked import creates a separate DMS draft, never a published revision.">
    <div className="dms-microsoft" data-testid="dms-microsoft-document">
      {error ? <p role="alert" className="dms-microsoft__error">{error}</p> : null}
      {success ? <p role="status" className="dms-microsoft__success">{success}</p> : null}
      {!connected ? <p>Microsoft 365 is not connected for this tenant. A tenant administrator can enable it under Document Control Administration. DOCX upload and controlled reading remain available without it.</p> : selected ? <>
        <div className="dms-microsoft__row">
          <Link2 size={20} />
          <div><strong>{selected.item_name}</strong>
            <small>{selected.imported ? selected.newer_version_available ? "Newer SharePoint version available" : "Latest observed version already imported" : "Linked working document · not yet imported"} · {selected.modified_at || "Date unavailable"}</small></div>
        </div>
        <div className="dms-microsoft__actions">
          <a className="dc-button" href={selected.web_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} /> Open in Word / SharePoint</a>
          <button type="button" className="dc-button" disabled={busy} onClick={() => void action(async () => { setLink(await checkMicrosoftDocument(tenant, manualId)); })}><RefreshCw size={15} /> Check for changes</button>
          <button type="button" className="dc-button" disabled={busy} onClick={() => void action(async () => {
            if (!window.confirm("Unlink this SharePoint working file? Imported revisions remain in the DMS history.")) return;
            await unlinkMicrosoftDocument(tenant, manualId); setLink({ linked: false, file: null });
          })}><Unlink size={15} /> Unlink</button>
        </div>
        <div className="dms-microsoft__form">
          <label><span>New controlled revision number</span><input value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="e.g. 04" /></label>
          <label><span>Issue number</span><input value={issue} onChange={(event) => setIssue(event.target.value)} placeholder="e.g. 01" /></label>
          <button type="button" className="dc-button dc-button--primary" disabled={busy || !revision.trim() || (selected.imported && !selected.newer_version_available)} onClick={() => void action(async () => {
            const next = await importMicrosoftDocument(tenant, manualId, revision.trim(), issue.trim(), selected.observed_etag);
            setSuccess("SharePoint version imported as DMS draft " + revision.trim() + ". Continue with the controlled review workflow.");
            setLink(await getMicrosoftDocument(tenant, manualId));
            setRevision(""); onChanged();
          })}><Download size={15} /> Import Word revision to DMS</button>
        </div>
        <p className="dms-microsoft__hint">Only a stable, rechecked SharePoint version is imported. The source is retained with a checksum and goes through existing approval, release and distribution controls.</p>
      </> : <>
        <div className="dms-microsoft__form">
          <label className="dms-microsoft__wide"><span>SharePoint file sharing link</span><input value={shareUrl} onChange={(event) => setShareUrl(event.target.value)} placeholder="https://your-company.sharepoint.com/…" /></label>
          <button type="button" className="dc-button dc-button--primary" disabled={busy || !shareUrl.trim()} onClick={() => void action(async () => {
            setLink(await linkMicrosoftDocument(tenant, manualId, shareUrl.trim()));
            setShareUrl(""); setSuccess("SharePoint working file linked to this manual.");
          })}><Link2 size={15} /> Link Word file</button>
        </div>
      </>}
    </div>
  </DocumentControlSection>;
}
