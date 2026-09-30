import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileUp, Paperclip, ShieldCheck } from "lucide-react";

import {
  createEvidenceMutationId,
  downloadInternalAuditEvidence,
  listAuditEvidence,
  uploadInternalAuditEvidence,
} from "../../../services/qmsAuditEvidence";
import {
  enqueueOfflineAuditEvidence,
  listOfflineAuditEvidence,
  onOfflineAuditEvidenceChanged,
  replayOfflineAuditEvidence,
} from "../../../services/qmsOfflineAuditEvidence";
import type { ChecklistExecutionGovernanceRow } from "../../../services/qmsChecklistExecutionGovernance";
import { saveDownloadedFile } from "../../../utils/downloads";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx,.mp4,.mov,.m4a,.wav";

type Props = {
  amoCode: string;
  auditId: string;
  item: ChecklistExecutionGovernanceRow;
  canManage: boolean;
  onChanged: () => Promise<void> | void;
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
};

const LiveAuditEvidenceStrip: React.FC<Props> = ({ amoCode, auditId, item, canManage, onChanged, onError, onNotice }) => {
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  const evidenceQuery = useQuery({
    queryKey: ["qms", "audit-evidence", amoCode, auditId, item.checklist_item_id],
    queryFn: ({ signal }) => listAuditEvidence(amoCode, auditId, item.checklist_item_id, null, signal),
    staleTime: 1_500,
  });
  const pendingQuery = useQuery({
    queryKey: ["qms", "offline-audit-evidence", amoCode, auditId, item.checklist_item_id],
    queryFn: () => listOfflineAuditEvidence(amoCode, auditId, item.checklist_item_id),
    staleTime: 500,
    refetchInterval: 2_000,
  });
  const artifacts = evidenceQuery.data?.items || [];
  const pending = pendingQuery.data || [];

  const refreshPending = () => void pendingQuery.refetch();

  useEffect(() => onOfflineAuditEvidenceChanged(refreshPending), [auditId, item.checklist_item_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const syncPending = async () => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) return;
    try {
      const result = await replayOfflineAuditEvidence(amoCode, auditId);
      await pendingQuery.refetch();
      if (result.uploaded.length) {
        await evidenceQuery.refetch();
        await onChanged();
        onNotice(`Evidence synchronized · ${result.uploaded.length} file${result.uploaded.length === 1 ? "" : "s"} verified by SHA-256.`);
      } else if (result.conflicts) {
        onError(`${result.conflicts} pending evidence file${result.conflicts === 1 ? " requires" : "s require"} review before synchronization.`);
      } else if (result.deferred) {
        onNotice(`${result.deferred} evidence file${result.deferred === 1 ? " is" : "s are"} waiting for earlier checklist changes to synchronize first.`);
      }
    } catch (cause) {
      // Local encrypted files remain queued. Do not replace a durable local
      // state with a false "saved" or "synced" indication.
      onError(cause instanceof Error ? cause.message : "Pending evidence could not be synchronized.");
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onOnline = () => void syncPending();
    const onStructuredSync = () => {
      if (pending.length && navigator.onLine !== false) void syncPending();
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("amo:offline-sync-complete", onStructuredSync);
    if (pending.length && navigator.onLine !== false) void syncPending();
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("amo:offline-sync-complete", onStructuredSync);
    };
  }, [amoCode, auditId, pending.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async () => {
    if (!file || busy) return;
    setBusy(true); onError(null); onNotice(null);
    const clientMutationId = createEvidenceMutationId();
    const queueLocal = async () => {
      await enqueueOfflineAuditEvidence({
        amoCode,
        auditId,
        checklistItemId: item.checklist_item_id,
        findingId: item.finding_id || null,
        file,
        description,
        clientMutationId,
        baseVersion: item.entity_version,
      });
      setFile(null);
      setDescription("");
      onNotice("Evidence saved securely on this device · pending synchronization. The server record is unchanged until upload is accepted and hash-verified.");
      await pendingQuery.refetch();
    };
    try {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        await queueLocal();
        return;
      }
      const result = await uploadInternalAuditEvidence(amoCode, auditId, item.checklist_item_id, file, {
        baseVersion: item.entity_version,
        clientMutationId,
        description,
        findingId: item.finding_id || null,
      });
      setFile(null); setDescription("");
      onNotice(`Evidence attached · ${result.artifact.filename} · checklist v${result.committed_version}.`);
      await evidenceQuery.refetch();
      await onChanged();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Evidence upload failed.";
      const normalized = message.toLowerCase();
      const transportFailure = normalized.includes("failed to fetch")
        || normalized.includes("network")
        || normalized.includes("connection")
        || normalized.includes("timed out")
        || normalized.includes("load failed");
      if (transportFailure) {
        try {
          await queueLocal();
          return;
        } catch (queueCause) {
          onError(queueCause instanceof Error ? queueCause.message : message);
          return;
        }
      }
      onError(message);
    } finally { setBusy(false); }
  };

  const download = async (artifactId: string, filename: string) => {
    setDownloading(artifactId); onError(null);
    try { saveDownloadedFile(await downloadInternalAuditEvidence(amoCode, auditId, artifactId), filename); }
    catch (cause) { onError(cause instanceof Error ? cause.message : "Evidence download failed."); }
    finally { setDownloading(null); }
  };

  return (
    <section className="qms-live-audit-focus__evidence" aria-label="Governed evidence">
      <header><Paperclip size={16} /><div><strong>Governed evidence</strong><small>Immutable file objects · uploader attribution retained</small></div></header>
      {artifacts.length ? (
        <ul>
          {artifacts.map((artifact) => (
            <li key={artifact.id}>
              <div><ShieldCheck size={14} /><span><strong>{artifact.filename}</strong><small>{Math.ceil(artifact.size_bytes / 1024)} KB · {artifact.source_type.replaceAll("_", " ")}</small></span></div>
              <button type="button" onClick={() => void download(artifact.id, artifact.filename)} disabled={downloading === artifact.id}><Download size={14} /> {downloading === artifact.id ? "Opening…" : "Open"}</button>
            </li>
          ))}
        </ul>
      ) : <p>No governed evidence file is linked to this checklist item yet.</p>}
      {pending.length ? (
        <div className="qms-live-audit-focus__evidence-pending" role="status" aria-live="polite">
          <strong>{pending.length} local evidence file{pending.length === 1 ? "" : "s"} pending</strong>
          <ul>
            {pending.map((entry) => (
              <li key={entry.id}>
                <span><strong>{entry.filename}</strong><small>{Math.ceil(entry.sizeBytes / 1024)} KB · {entry.state.replaceAll("_", " ")}</small></span>
                {entry.lastError ? <small>{entry.lastError}</small> : null}
              </li>
            ))}
          </ul>
          <button type="button" disabled={busy || (typeof navigator !== "undefined" && navigator.onLine === false)} onClick={() => void syncPending()}>
            Retry pending evidence
          </button>
        </div>
      ) : null}
      {canManage ? (
        <div className="qms-live-audit-focus__evidence-upload">
          <label><span>Attach evidence</span><input type="file" accept={ACCEPT} disabled={busy} onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
          <label><span>Evidence context</span><input value={description} maxLength={4000} onChange={(event) => setDescription(event.target.value)} placeholder="What this file demonstrates" /></label>
          <button type="button" disabled={!file || busy} onClick={() => void upload()}><FileUp size={15} /> {busy ? "Uploading…" : "Attach to question"}</button>
        </div>
      ) : null}
    </section>
  );
};

export default LiveAuditEvidenceStrip;