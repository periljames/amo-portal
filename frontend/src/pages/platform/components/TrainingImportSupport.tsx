import React, { useState } from "react";
import TrainingWorkbookImportDialog from "../../../components/training/TrainingWorkbookImportDialog";
import { openTrainingImportSupport } from "../../../services/trainingWorkbookImport";
import type { TrainingWorkbookImportJob } from "../../../types/trainingWorkbookImport";

export default function TrainingImportSupport() {
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [job, setJob] = useState<TrainingWorkbookImportJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const open = async () => {
    const jobId = reference.trim();
    const supportReason = reason.trim();
    if (!jobId || supportReason.length < 5) return;
    setBusy(true);
    setError("");
    try {
      const opened = await openTrainingImportSupport(jobId, supportReason);
      setJob(opened);
    } catch (err) {
      setJob(null);
      setError(err instanceof Error ? err.message : "Could not open import.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="platform-card">
      <h2>Training import support</h2>
      <p>
        Paste a job reference to inspect progress, decisions and every failed row. Read-only access opens immediately;
        repairs require a tenant-approved ADMIN support session.
      </p>
      <form
        className="platform-actions"
        onSubmit={(event) => {
          event.preventDefault();
          void open();
        }}
      >
        <label>
          Job reference
          <input required value={reference} onChange={(event) => setReference(event.target.value)} placeholder="ID-…" autoComplete="off" spellCheck={false} />
        </label>
        <label>
          Support reason
          <input
            required
            minLength={5}
            maxLength={1000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Describe the reported import issue"
          />
        </label>
        <button className="platform-btn primary" disabled={busy || !reference.trim() || reason.trim().length < 5}>
          {busy ? "Opening…" : "Open import job"}
        </button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      {job ? (
        <p role="status">
          Opened <code>{job.id}</code> · {job.status}
          {job.failed_count ? ` · ${job.failed_count} failed` : ""}
          {job.review_count ? ` · ${job.review_count} review` : ""}
          {job.summary?.support_can_manage ? " · repair access granted" : " · read-only"}
        </p>
      ) : null}
      <TrainingWorkbookImportDialog isOpen={Boolean(job)} initialJob={job || undefined} support onClose={() => setJob(null)} />
    </section>
  );
}
