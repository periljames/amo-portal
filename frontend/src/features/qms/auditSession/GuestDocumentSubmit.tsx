import React, { useState } from "react";
import { FileUp } from "lucide-react";

import { submitAuditGuestDocument } from "../../../services/qmsAuditExternalAccess";
import "../../../styles/qms-public-audit-document-submit.css";

type Props = {
  requestId: string;
  onSubmitted: () => Promise<void> | void;
};

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx";

const GuestDocumentSubmit: React.FC<Props> = ({ requestId, onSubmitted }) => {
  const [file, setFile] = useState<File | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const submit = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const row = await submitAuditGuestDocument(requestId, file, comment);
      setSuccess(`${row.filename} submitted · SHA-256 ${row.sha256.slice(0, 12)}…`);
      setFile(null);
      setComment("");
      await onSubmitted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Document submission failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qms-public-audit__document-submit">
      <label>
        <span>Provide document</span>
        <input type="file" accept={ACCEPT} disabled={busy} onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </label>
      <label>
        <span>Response / context</span>
        <textarea rows={2} maxLength={4000} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional note for the audit team" />
      </label>
      {file ? <small>{file.name} · {Math.ceil(file.size / 1024)} KB</small> : null}
      {error ? <small className="is-error" role="alert">{error}</small> : null}
      {success ? <small className="is-success" role="status">{success}</small> : null}
      <button type="button" disabled={!file || busy} onClick={() => void submit()}><FileUp size={15} /> {busy ? "Submitting…" : "Submit securely"}</button>
    </div>
  );
};

export default GuestDocumentSubmit;
