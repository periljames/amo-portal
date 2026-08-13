import { useEffect, useState } from "react";
import { ArchiveRestore, CheckCircle2, Download, Loader2, ShieldCheck } from "lucide-react";

import type { DocumentDetailResponse } from "../../services/documentControl";
import {
  downloadDocumentEvidencePack,
  downloadDocumentEvidencePackJob,
  getDocumentEvidencePackJob,
  queueDocumentEvidencePackJob,
  saveDocumentEvidencePack,
  type DocumentEvidencePackJob,
} from "../../services/documentControlEvidence";

const ACTIVE_JOB_STATUSES = new Set(["PENDING", "RUNNING", "RETRY"]);

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
  const [largeJob, setLargeJob] = useState<DocumentEvidencePackJob | null>(null);
  const latest = detail.document.latest_revision;

  useEffect(() => {
    if (!largeJob?.job_id || !ACTIVE_JOB_STATUSES.has(largeJob.status)) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await getDocumentEvidencePackJob(tenant, detail.document.id, largeJob.job_id);
        if (!cancelled) setLargeJob(next);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Large evidence pack status could not be refreshed.");
      }
    };
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [tenant, detail.document.id, largeJob?.job_id, largeJob?.status]);

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

  const queueLarge = async (revisionOnly: boolean) => {
    setBusy(true);
    setError("");
    try {
      setLargeJob(await queueDocumentEvidencePackJob(
        tenant,
        detail.document.id,
        revisionOnly ? latest?.id || null : null,
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The large evidence pack could not be queued.");
    } finally {
      setBusy(false);
    }
  };

  const downloadLarge = async () => {
    if (!largeJob || largeJob.status !== "SUCCEEDED") return;
    setBusy(true);
    setError("");
    try {
      const result = await downloadDocumentEvidencePackJob(tenant, detail.document.id, largeJob.job_id);
      saveDocumentEvidencePack(result);
      setLastResult({ sha256: result.sha256, attachments: result.attachmentCount });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The completed large evidence pack could not be downloaded.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="dc-form" data-testid="document-evidence-pack-action">
    <div className="dc-callout">
      <ShieldCheck size={17} />
      <div>
        <strong>Auditable evidence package</strong>
        <div>Generate one server-built ZIP containing controlled datasets, audit history, retained supporting evidence and verified revision source files. Every package carries a SHA-256 integrity value and its own manifest.</div>
      </div>
    </div>
    <div className="dc-form__actions">
      <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void generate(false)}>
        {busy ? <Loader2 size={14} className="dms-spin" /> : <ArchiveRestore size={14} />}
        {busy ? "Working…" : "Download complete document evidence pack"}
      </button>
      <button type="button" className="dc-button" disabled={busy || !latest} onClick={() => void generate(true)}>
        <Download size={14} /> Latest revision only
      </button>
    </div>
    <div className="dc-form__hint">The immediate download path is deliberately bounded and never returns a partial audit package. Use the durable queue for evidence sets above those limits.</div>
    <div className="dc-form__actions">
      <button type="button" className="dc-button" disabled={busy || Boolean(largeJob && ACTIVE_JOB_STATUSES.has(largeJob.status))} onClick={() => void queueLarge(false)}>
        {largeJob && ACTIVE_JOB_STATUSES.has(largeJob.status) ? <Loader2 size={14} className="dms-spin" /> : <ArchiveRestore size={14} />}
        Queue large complete pack
      </button>
      <button type="button" className="dc-button" disabled={busy || !latest || Boolean(largeJob && ACTIVE_JOB_STATUSES.has(largeJob.status))} onClick={() => void queueLarge(true)}>
        Queue large latest revision
      </button>
      {largeJob?.status === "SUCCEEDED" ? <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void downloadLarge()}>
        <Download size={14} /> Download completed large pack
      </button> : null}
    </div>
    {largeJob ? <div className={largeJob.status === "SUCCEEDED" ? "dc-callout dc-callout--success" : "dc-callout"} role="status">
      {largeJob.status === "SUCCEEDED" ? <CheckCircle2 size={15} /> : <Loader2 size={15} className={ACTIVE_JOB_STATUSES.has(largeJob.status) ? "dms-spin" : undefined} />}
      <div>
        <strong>Large evidence pack · {largeJob.status}</strong>
        <div>{largeJob.status === "SUCCEEDED" ? `${largeJob.attachments ?? 0} retained files · ${largeJob.size_bytes ?? 0} bytes${largeJob.sha256 ? ` · SHA-256 ${largeJob.sha256}` : ""}` : largeJob.error || `Attempt ${largeJob.attempt_count} of ${largeJob.max_attempts}. The durable worker will continue without keeping this page open.`}</div>
      </div>
    </div> : null}
    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}
    {lastResult ? <div className="dc-callout dc-callout--success" role="status"><CheckCircle2 size={15} /><div><strong>Evidence pack downloaded</strong><div>{lastResult.attachments === null ? "Attachment count retained in the manifest." : `${lastResult.attachments} retained file${lastResult.attachments === 1 ? "" : "s"} included.`}{lastResult.sha256 ? ` ZIP SHA-256: ${lastResult.sha256}` : ""}</div></div></div> : null}
  </div>;
}
