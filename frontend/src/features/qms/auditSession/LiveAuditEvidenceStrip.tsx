import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileUp, Paperclip, ShieldCheck } from "lucide-react";

import {
  createEvidenceMutationId,
  downloadInternalAuditEvidence,
  listAuditEvidence,
  uploadInternalAuditEvidence,
} from "../../../services/qmsAuditEvidence";
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
  const artifacts = evidenceQuery.data?.items || [];

  const upload = async () => {
    if (!file || busy) return;
    setBusy(true); onError(null); onNotice(null);
    try {
      const result = await uploadInternalAuditEvidence(amoCode, auditId, item.checklist_item_id, file, {
        baseVersion: item.entity_version,
        clientMutationId: createEvidenceMutationId(),
        description,
        findingId: item.finding_id || null,
      });
      setFile(null); setDescription("");
      onNotice(`Evidence attached · ${result.artifact.filename} · SHA-256 ${result.artifact.sha256.slice(0, 12)}… · checklist v${result.committed_version}.`);
      await evidenceQuery.refetch();
      await onChanged();
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : "Evidence upload failed.");
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
      <header><Paperclip size={16} /><div><strong>Governed evidence</strong><small>Immutable file objects · checksum and uploader attribution retained</small></div></header>
      {artifacts.length ? (
        <ul>
          {artifacts.map((artifact) => (
            <li key={artifact.id}>
              <div><ShieldCheck size={14} /><span><strong>{artifact.filename}</strong><small>{Math.ceil(artifact.size_bytes / 1024)} KB · {artifact.source_type.replaceAll("_", " ")} · SHA {artifact.sha256.slice(0, 12)}…</small></span></div>
              <button type="button" onClick={() => void download(artifact.id, artifact.filename)} disabled={downloading === artifact.id}><Download size={14} /> {downloading === artifact.id ? "Opening…" : "Open"}</button>
            </li>
          ))}
        </ul>
      ) : <p>No governed evidence file is linked to this checklist item yet.</p>}
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
