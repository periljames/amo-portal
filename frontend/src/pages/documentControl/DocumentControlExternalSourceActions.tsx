import { useMemo, useState, type FormEvent } from "react";
import { BookMarked, Plus, RadioTower } from "lucide-react";

import {
  createExternalRevisionReceipt,
  createExternalSource,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import DocumentEvidencePicker from "./DocumentEvidencePicker";
import { DocumentControlEmpty } from "./DocumentControlShell";


type Props = {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
};

function useMutation(onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(success);
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The external technical-data action failed.");
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, message, setError, run };
}

function RegisterSource({ detail, tenant, onChanged }: Props) {
  const mutation = useMutation(onChanged);
  const [provider, setProvider] = useState("");
  const [authority, setAuthority] = useState("");
  const [reference, setReference] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("MANUAL_CHECK");
  const [nextCheck, setNextCheck] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createExternalSource(tenant, {
      manual_id: detail.document.id,
      provider,
      authority: authority.trim() || null,
      subscription_reference: reference.trim() || null,
      access_url: url.trim() || null,
      update_method: method,
      next_check_due_at: nextCheck ? new Date(nextCheck).toISOString() : null,
      metadata: {},
    }), "External technical-data source registered.");
  };

  const externalClass = detail.document.profile.document_class === "EXTERNAL";
  return <form className="dc-form" onSubmit={submit} data-testid="document-control-external-source-register">
    <div className="dc-callout"><RadioTower size={17} /><div><strong>Register governed external source</strong><div>Record where this controlled technical data comes from and when currency must next be verified.</div></div></div>
    <label><span>Provider / publisher</span><input value={provider} onChange={(event) => setProvider(event.target.value)} required /></label>
    <label><span>Authority</span><input value={authority} onChange={(event) => setAuthority(event.target.value)} placeholder="KCAA, OEM, STC holder…" /></label>
    <label><span>Subscription / account reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} /></label>
    <label><span>Update method</span><select value={method} onChange={(event) => setMethod(event.target.value)}><option>MANUAL_CHECK</option><option>EMAIL</option><option>PORTAL</option><option>API</option><option>SUBSCRIPTION</option></select></label>
    <label className="wide"><span>Controlled access URL</span><input type="url" value={url} onChange={(event) => setUrl(event.target.value)} /></label>
    <label><span>Next currency check</span><input type="datetime-local" value={nextCheck} onChange={(event) => setNextCheck(event.target.value)} /></label>
    {!externalClass ? <div className="dc-form__error">Set the document class to EXTERNAL before registering its technical-data source.</div> : null}
    {mutation.error ? <div className="dc-form__error">{mutation.error}</div> : null}
    {mutation.message ? <div className="dc-form__hint">{mutation.message}</div> : null}
    <div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || !externalClass}><Plus size={14} /> Register external source</button></div>
  </form>;
}

function ReceiveExternalRevision({ detail, tenant, onChanged }: Props) {
  const sources = detail.external_sources;
  const mutation = useMutation(onChanged);
  const [sourceId, setSourceId] = useState(sources[0]?.id || "");
  const selected = useMemo(() => sources.find((item) => item.id === sourceId) || sources[0], [sourceId, sources]);
  const [revisionLabel, setRevisionLabel] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [currencyStatus, setCurrencyStatus] = useState("UNVERIFIED");
  const [notes, setNotes] = useState("");
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);
  const primary = evidence[0];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    if (currencyStatus === "CURRENT" && !primary) {
      mutation.setError("Upload or select the received revision file before marking the revision current.");
      return;
    }
    if (currencyStatus === "UNKNOWN" && !notes.trim()) {
      mutation.setError("Explain why external revision currency is unknown.");
      return;
    }
    void mutation.run(() => createExternalRevisionReceipt(tenant, selected.id, {
      revision_label: revisionLabel.trim(),
      publication_date: publicationDate || null,
      checksum_sha256: primary?.sha256 || null,
      currency_status: currencyStatus,
      applicability_status: "PENDING",
      evidence,
      notes: notes.trim() || null,
    }), "External revision receipt recorded. Applicability assessment is now actionable in Compliance / My Work.");
  };

  if (!sources.length) return <DocumentControlEmpty title="Register the external source first" message="A revision receipt must be traceable to the governed OEM, authority, subscription or portal source." />;

  return <form className="dc-form" onSubmit={submit} data-testid="document-control-external-revision-receipt">
    <div className="dc-callout"><BookMarked size={17} /><div><strong>Receive a new external revision</strong><div>Retain the received file, record publication identity and create the downstream applicability-assessment obligation.</div></div></div>
    <label className="wide"><span>External source</span><select value={selected?.id || ""} onChange={(event) => { setSourceId(event.target.value); setEvidence([]); }} required>{sources.map((source) => <option key={source.id} value={source.id}>{source.provider}{source.authority ? ` · ${source.authority}` : ""} · {source.status}</option>)}</select></label>
    <label><span>Revision / issue label</span><input value={revisionLabel} onChange={(event) => setRevisionLabel(event.target.value)} placeholder="Revision 42 / Issue 7 / 2026-08" required /></label>
    <label><span>Publisher date</span><input type="date" value={publicationDate} max={new Date().toISOString().slice(0, 10)} onChange={(event) => setPublicationDate(event.target.value)} /></label>
    <label><span>Currency determination</span><select value={currencyStatus} onChange={(event) => setCurrencyStatus(event.target.value)}><option value="UNVERIFIED">Unverified</option><option value="CURRENT">Current</option><option value="UNKNOWN">Unknown</option></select></label>
    <label className="wide"><span>Receipt / currency notes</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Portal notice, subscription email, OEM publication note, uncertainty or other receipt context." /></label>
    <DocumentEvidencePicker
      tenant={tenant}
      manualId={detail.document.id}
      revisionId={detail.document.latest_revision?.id || null}
      category="EXTERNAL_SOURCE"
      purpose="EXTERNAL_REVISION_RECEIPT"
      value={evidence}
      onChange={setEvidence}
      label="Received revision and source evidence"
      help="Select the received revision file first. Its retained SHA-256 becomes the receipt checksum automatically; add supporting notice/correspondence after it."
    />
    {primary ? <div className="dc-form__hint">Primary retained checksum: {primary.sha256}</div> : <div className="dc-form__hint">No primary source file selected. Currency may remain unverified, but cannot be marked current.</div>}
    {mutation.error ? <div className="dc-form__error">{mutation.error}</div> : null}
    {mutation.message ? <div className="dc-form__hint">{mutation.message}</div> : null}
    <div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || !revisionLabel.trim()}><BookMarked size={14} /> Record received revision</button></div>
  </form>;
}

export default function DocumentControlExternalSourceActions(props: Props) {
  return <div className="dc-grid">
    <RegisterSource {...props} />
    <ReceiveExternalRevision {...props} />
  </div>;
}
