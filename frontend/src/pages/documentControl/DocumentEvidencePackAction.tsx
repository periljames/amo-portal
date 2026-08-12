import { useState } from "react";
import { ArchiveRestore, CheckCircle2, Download, Loader2, ShieldCheck } from "lucide-react";

import type { DocumentDetailResponse } from "../../services/documentControl";
import {
  downloadDocumentEvidencePack,
  saveDocumentEvidencePack,
} from "../../services/documentControlEvidence";

export default function DocumentEvidencePackAction({
  tenant,
  detail,
}: {
  tenant: string;
  detail: DocumentDetailResponse;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<{ sha256: string | null; attachments: number | null } | null>(null);
  const latest = detail.document.latest_revision;

  const generate = async (revisionOnly: boolean) => {
    setBusy(true);
    setError("");
    try {
      const result = await downloadDocumentEvidencePack(
        tenant,
        detail.document.id,
        revisionOnly ? latest?.id || null : null,
      );
      saveDocumentEvidencePack(result);
      setLastResult({ sha256: result.sha256, attachments: result.attachmentCount });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled evidence pack could not be generated.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="dc-form" data-testid="document-evidence-pack-action">
    <div className="dc-callout">
      <ShieldCheck size={17} />
      <div>
        <strong>Auditable evidence package</strong>
        <div>Generate one server-built ZIP containing controlled datasets, audit history, retained supporting evidence and verified revision source files. The ZIP is returned with a SHA-256 integrity header and contains its own manifest.</div>
      </div>
    </div>
    <div className="dc-form__actions">
      <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void generate(false)}>
        {busy ? <Loader2 size={14} className="dms-spin" /> : <ArchiveRestore size={14} />}
        {busy ? "Building evidence pack…" : "Download complete document evidence pack"}
      </button>
      <button type="button" className="dc-button" disabled={busy || !latest} onClick={() => void generate(true)}>
        <Download size={14} /> Latest revision only
      </button>
    </div>
    <div className="dc-form__hint">Synchronous packs are deliberately bounded. Oversized evidence sets fail explicitly rather than returning a partial audit package.</div>
    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}
    {lastResult ? <div className="dc-callout dc-callout--success" role="status"><CheckCircle2 size={15} /><div><strong>Evidence pack generated</strong><div>{lastResult.attachments === null ? "Attachment count retained in the manifest." : `${lastResult.attachments} retained file${lastResult.attachments === 1 ? "" : "s"} included.`}{lastResult.sha256 ? ` ZIP SHA-256: ${lastResult.sha256}` : ""}</div></div></div> : null}
  </div>;
}
