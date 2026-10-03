import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileUp, Paperclip, ShieldCheck } from "lucide-react";

import {
  createEvidenceMutationId,
  downloadInternalAuditEvidence,
  listAuditEvidence,
  uploadInternalAuditEvidence,
  type AuditEvidenceContext,
} from "../../../services/qmsAuditEvidence";
import {
  enqueueOfflineAuditEvidence,
  listOfflineAuditEvidence,
  onOfflineAuditEvidenceChanged,
  replayOfflineAuditEvidence,
} from "../../../services/qmsOfflineAuditEvidence";
import type { ChecklistExecutionGovernanceRow } from "../../../services/qmsChecklistExecutionGovernance";
import { projectOfflineEvidence, readAuditOfflinePack } from "../../../services/qmsAuditOfflinePack";
import { saveDownloadedFile } from "../../../utils/downloads";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx,.mp4,.mov,.m4a,.wav";

type Props = {
  amoCode: string;
  auditId: string;
  item: ChecklistExecutionGovernanceRow;
  canManage: boolean;
  selectedAssessmentEvidenceIds?: string[];
  onAssessmentEvidenceChange?: (artifactId: string, selected: boolean) => void;
  onChanged: () => Promise<void> | void;
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
};

const LiveAuditEvidenceStrip: React.FC<Props> = ({
  amoCode,
  auditId,
  item,
  canManage,
  selectedAssessmentEvidenceIds = [],
  onAssessmentEvidenceChange,
  onChanged,
  onError,
  onNotice,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  const [contextDraft, setContextDraft] = useState({
    locationRef: "",
    personRef: "",
    facilityRef: "",
    assetRef: "",
    toolRef: "",
    componentRef: "",
  });
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    setFile(null);
    setDescription("");
    setContextDraft({
      locationRef: "",
      personRef: "",
      facilityRef: "",
      assetRef: "",
      toolRef: "",
      componentRef: "",
    });
  }, [item.checklist_item_id]);

  const evidenceQuery = useQuery({
    queryKey: ["qms", "audit-evidence", amoCode, auditId, item.checklist_item_id],
    queryFn: async ({ signal }) => {
      const offline = async () => {
        const pack = await readAuditOfflinePack(amoCode, auditId);
        return pack ? { items: projectOfflineEvidence(pack, item.checklist_item_id, null) } : null;
      };
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        const local = await offline();
        if (local) return local;
      }
      try {
        return await listAuditEvidence(amoCode, auditId, item.checklist_item_id, null, signal);
      } catch (error) {
        const message = error instanceof Error ? error.message.toLowerCase() : "";
        if (!message.includes("offline") && !message.includes("could not be reached") && !message.includes("cached copy")) throw error;
        const local = await offline();
        if (local) return local;
        throw error;
      }
    },
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
  const evidenceContext = (): AuditEvidenceContext => ({
    location_ref: contextDraft.locationRef.trim() || undefined,
    person_ref: contextDraft.personRef.trim() || undefined,
    facility_ref: contextDraft.facilityRef.trim() || undefined,
    asset_ref: contextDraft.assetRef.trim() || undefined,
    tool_ref: contextDraft.toolRef.trim() || undefined,
    component_ref: contextDraft.componentRef.trim() || undefined,
    regulation_refs: item.assessment?.regulation_refs || [],
    procedure_refs: item.assessment?.procedure_refs || [],
    document_revision_ids: item.assessment?.document_revision_ids || [],
  });
  const resetCapture = () => {
    setFile(null);
    setDescription("");
    setContextDraft({
      locationRef: "",
      personRef: "",
      facilityRef: "",
      assetRef: "",
      toolRef: "",
      componentRef: "",
    });
  };
  const contextSummary = (context?: AuditEvidenceContext | null) => {
    if (!context) return [];
    return [
      context.location_ref ? `Location ${context.location_ref}` : "",
      context.person_ref ? `Person ${context.person_ref}` : "",
      context.facility_ref ? `Facility ${context.facility_ref}` : "",
      context.asset_ref ? `Asset ${context.asset_ref}` : "",
      context.tool_ref ? `Tool ${context.tool_ref}` : "",
      context.component_ref ? `Component ${context.component_ref}` : "",
      context.regulation_refs?.length ? `${context.regulation_refs.length} regulation ref(s)` : "",
      context.procedure_refs?.length ? `${context.procedure_refs.length} procedure ref(s)` : "",
      context.document_revision_ids?.length ? `${context.document_revision_ids.length} document revision(s)` : "",
    ].filter(Boolean);
  };

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
        context: evidenceContext(),
        clientMutationId,
        baseVersion: item.entity_version,
      });
      resetCapture();
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
        context: evidenceContext(),
      });
      resetCapture();
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
          {artifacts.map((artifact) => {
            const reliedUpon = selectedAssessmentEvidenceIds.includes(artifact.id);
            return (
              <li key={artifact.id} className={reliedUpon ? "is-assessment-evidence" : ""}>
                <div><ShieldCheck size={14} /><span><strong>{artifact.filename}</strong><small>{Math.ceil(artifact.size_bytes / 1024)} KB · {artifact.source_type.replaceAll("_", " ")}</small>{contextSummary(artifact.context).length ? <small>{contextSummary(artifact.context).join(" · ")}</small> : null}</span></div>
                <div className="qms-live-audit-focus__evidence-actions">
                  {onAssessmentEvidenceChange ? (
                    <label title="Attaching a file does not automatically make it evidence relied upon for the compliance assessment.">
                      <input
                        type="checkbox"
                        checked={reliedUpon}
                        disabled={!canManage}
                        onChange={(event) => onAssessmentEvidenceChange(artifact.id, event.target.checked)}
                      />
                      <span>Use in assessment</span>
                    </label>
                  ) : null}
                  <button type="button" onClick={() => void download(artifact.id, artifact.filename)} disabled={downloading === artifact.id || (typeof navigator !== "undefined" && navigator.onLine === false)} title={typeof navigator !== "undefined" && navigator.onLine === false ? "Reconnect to open server-retained evidence content." : undefined}><Download size={14} /> {typeof navigator !== "undefined" && navigator.onLine === false ? "Metadata only offline" : downloading === artifact.id ? "Opening…" : "Open"}</button>
                </div>
              </li>
            );
          })}
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
          <label><span>What this demonstrates</span><input value={description} maxLength={4000} onChange={(event) => setDescription(event.target.value)} placeholder="Objective evidence observed or reviewed" /></label>
          <div className="qms-live-audit-focus__evidence-context-grid" aria-label="Structured evidence context">
            <label><span>Location</span><input value={contextDraft.locationRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, locationRef: event.target.value }))} placeholder="Base / line / station" /></label>
            <label><span>Person</span><input value={contextDraft.personRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, personRef: event.target.value }))} placeholder="Name or personnel ID" /></label>
            <label><span>Facility</span><input value={contextDraft.facilityRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, facilityRef: event.target.value }))} placeholder="Hangar / workshop / store" /></label>
            <label><span>Asset</span><input value={contextDraft.assetRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, assetRef: event.target.value }))} placeholder="Aircraft / equipment / asset" /></label>
            <label><span>Tool</span><input value={contextDraft.toolRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, toolRef: event.target.value }))} placeholder="Tool or calibration ID" /></label>
            <label><span>Component</span><input value={contextDraft.componentRef} maxLength={255} onChange={(event) => setContextDraft((current) => ({ ...current, componentRef: event.target.value }))} placeholder="P/N, S/N or component ref" /></label>
          </div>
          <small className="qms-live-audit-focus__evidence-context-note">Regulation, procedure and document-revision references are inherited from the current structured assessment and stored with this evidence.</small>
          <button type="button" disabled={!file || busy} onClick={() => void upload()}><FileUp size={15} /> {busy ? "Uploading…" : "Attach to question"}</button>
        </div>
      ) : null}
    </section>
  );
};

export default LiveAuditEvidenceStrip;