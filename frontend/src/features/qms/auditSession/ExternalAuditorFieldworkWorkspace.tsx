import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash2, CloudOff, FileUp, RefreshCw, Save, ShieldAlert, UploadCloud } from "lucide-react";

import {
  getExternalAuditorFieldwork,
  type ExternalAuditorFieldworkItem,
  type ExternalAuditorFieldworkModel,
  type ExternalChecklistResponse,
} from "../../../services/qmsAuditExternalAccess";
import { uploadExternalAuditorEvidence } from "../../../services/qmsAuditEvidence";
import {
  buildExternalAuditorMutation,
  commitExternalAuditorMutation,
  ExternalAuditMutationError,
} from "../../../services/qmsExternalAuditorMutations";
import {
  clearExternalAuditMutations,
  enqueueExternalAuditMutation,
  listExternalAuditMutations,
  markExternalAuditMutationFailure,
  removeExternalAuditMutation,
  type ExternalAuditOutboxScope,
} from "../../../services/qmsExternalAuditOutbox";
import ExternalAuditorFindingDraftPanel from "./ExternalAuditorFindingDraftPanel";

const ALLOWED_RESPONSES: Array<{ value: ExternalChecklistResponse; label: string }> = [
  { value: "COMPLIANT", label: "Compliant" },
  { value: "NOT_APPLICABLE", label: "N/A" },
  { value: "NOT_VERIFIED", label: "Not verified" },
];
const EVIDENCE_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx,.mp4,.mov,.m4a,.wav";

function evidenceText(value: Array<Record<string, unknown> | string>): string {
  return value
    .filter((entry) => typeof entry === "string")
    .map((entry) => String(entry))
    .join("\n");
}

function evidenceRefs(value: string): string[] {
  return value.split(/\r?\n/).map((entry) => entry.trim()).filter(Boolean).slice(0, 200);
}

function governedEvidence(value: Array<Record<string, unknown> | string>) {
  return value.flatMap((entry) => {
    if (!entry || typeof entry === "string") return [];
    const artifactId = typeof entry.artifact_id === "string" ? entry.artifact_id : "";
    if (!artifactId) return [];
    return [{
      artifactId,
      filename: typeof entry.filename === "string" ? entry.filename : "Governed evidence",
      sha256: typeof entry.sha256 === "string" ? entry.sha256 : null,
      sizeBytes: typeof entry.size_bytes === "number" ? entry.size_bytes : null,
    }];
  });
}

function scopeOf(model: ExternalAuditorFieldworkModel): ExternalAuditOutboxScope {
  return { auditId: model.audit_id, participantId: model.participant_id };
}

const ExternalAuditorFieldworkWorkspace: React.FC = () => {
  const [model, setModel] = useState<ExternalAuditorFieldworkModel | null>(null);
  const modelRef = useRef<ExternalAuditorFieldworkModel | null>(null);
  const replayingRef = useRef(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceDescription, setEvidenceDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const updatePendingCount = async (nextModel: ExternalAuditorFieldworkModel | null = modelRef.current) => {
    if (!nextModel) { setPendingCount(0); return; }
    try { setPendingCount((await listExternalAuditMutations(scopeOf(nextModel))).length); }
    catch { setPendingCount(0); }
  };

  const load = async (): Promise<ExternalAuditorFieldworkModel | null> => {
    setLoading(true);
    setError(null);
    try {
      const next = await getExternalAuditorFieldwork();
      const prior = modelRef.current;
      if (prior && (prior.audit_id !== next.audit_id || prior.participant_id !== next.participant_id)) {
        await clearExternalAuditMutations(scopeOf(prior)).catch(() => undefined);
      }
      modelRef.current = next;
      setModel(next);
      await updatePendingCount(next);
      return next;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "External auditor fieldwork is unavailable.");
      return null;
    } finally {
      setLoading(false);
    }
  };

  const replayPending = async () => {
    if (replayingRef.current || (typeof navigator !== "undefined" && !navigator.onLine)) return;
    replayingRef.current = true;
    setReplaying(true);
    setError(null);
    try {
      const fresh = await getExternalAuditorFieldwork();
      const current = modelRef.current;
      if (current && (current.audit_id !== fresh.audit_id || current.participant_id !== fresh.participant_id)) {
        await clearExternalAuditMutations(scopeOf(current)).catch(() => undefined);
        modelRef.current = fresh;
        setModel(fresh);
        setNotice("The external audit session changed. Pending mutations from the prior audit identity were cleared and were not replayed.");
        await updatePendingCount(fresh);
        return;
      }
      modelRef.current = fresh;
      setModel(fresh);
      const scope = scopeOf(fresh);
      const queue = await listExternalAuditMutations(scope);
      if (!queue.length) { setPendingCount(0); return; }

      let committed = 0;
      for (const entry of queue) {
        try {
          await commitExternalAuditorMutation(fresh, entry.mutation);
          await removeExternalAuditMutation(entry.id);
          committed += 1;
        } catch (cause) {
          const message = cause instanceof Error ? cause.message : "Replay failed.";
          await markExternalAuditMutationFailure(entry.id, message).catch(() => undefined);
          if (cause instanceof ExternalAuditMutationError && cause.status === 409) {
            setError("A queued fieldwork change conflicts with a newer server version. It remains encrypted in the pending queue for deliberate reconciliation.");
          } else if (cause instanceof ExternalAuditMutationError && [401, 403, 404].includes(cause.status)) {
            setError("The guest session no longer authorizes replay. Pending work remains encrypted locally and was not sent to another identity or audit.");
          } else {
            setError("Pending fieldwork could not be replayed yet. The encrypted queue remains intact for a later retry.");
          }
          break;
        }
      }
      await updatePendingCount(fresh);
      if (committed > 0) {
        setNotice(`${committed} queued fieldwork change${committed === 1 ? "" : "s"} synchronized with original mutation identity preserved.`);
        await load();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Pending external fieldwork could not be synchronized.");
    } finally {
      replayingRef.current = false;
      setReplaying(false);
    }
  };

  useEffect(() => {
    void load().then(() => { if (typeof navigator === "undefined" || navigator.onLine) void replayPending(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const onOnline = () => { setNotice("Connection restored. Revalidating the purpose-bound audit session before replaying queued fieldwork."); void replayPending(); };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = useMemo(() => model?.items ?? [], [model?.items]);
  const effectiveSelectedId = selectedId && items.some((item) => item.checklist_item_id === selectedId) ? selectedId : items[0]?.checklist_item_id || null;
  const selected = items.find((item) => item.checklist_item_id === effectiveSelectedId) || null;
  const completed = items.filter((item) => item.canonical_response_status !== "NOT_VERIFIED").length;
  const percent = items.length ? Math.round((completed / items.length) * 100) : null;

  useEffect(() => {
    setEvidenceFile(null);
    setEvidenceDescription("");
  }, [effectiveSelectedId]);

  const save = async (item: ExternalAuditorFieldworkItem, response: ExternalChecklistResponse) => {
    if (!model || !model.can_execute_checklist) return;
    setSaving(true); setError(null); setNotice(null);
    const mutation = buildExternalAuditorMutation(item, {
      canonicalResponseStatus: response,
      auditorNotes: notes[item.checklist_item_id] ?? item.my_auditor_notes ?? null,
      evidenceReferences: [
        ...item.my_evidence_references.filter((entry) => typeof entry === "object"),
        ...evidenceRefs(evidence[item.checklist_item_id] ?? evidenceText(item.my_evidence_references)),
      ],
      reason: "External auditor assigned-checklist fieldwork update.",
    });
    const scope = scopeOf(model);
    try {
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        await enqueueExternalAuditMutation(scope, mutation);
        await updatePendingCount(model);
        setNotice("Offline: fieldwork change encrypted locally. Authentication and CSRF secrets were not stored; replay will revalidate the guest session first.");
        return;
      }
      try {
        await commitExternalAuditorMutation(model, mutation);
        setNotice("Fieldwork contribution saved to the authoritative audit record with participant attribution.");
        await load();
      } catch (cause) {
        const retryable = !(cause instanceof ExternalAuditMutationError) || [502, 503, 504].includes(cause.status);
        if (!retryable) throw cause;
        await enqueueExternalAuditMutation(scope, mutation);
        await updatePendingCount(model);
        setNotice("The server was unreachable. The exact idempotent mutation was encrypted locally for replay after a fresh session check.");
      }
    } catch (cause) {
      if (cause instanceof ExternalAuditMutationError && cause.status === 409) {
        setError("This checklist item changed on the server. Refresh before saving so the newer authoritative version is not overwritten.");
      } else {
        setError(cause instanceof Error ? cause.message : "External checklist update failed.");
      }
    } finally {
      setSaving(false);
    }
  };

  const uploadEvidence = async () => {
    if (!model || !selected || !evidenceFile || uploading) return;
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      setError("Evidence files require an online governed upload. Structured checklist notes and responses remain available through the encrypted offline queue.");
      return;
    }
    setUploading(true); setError(null); setNotice(null);
    try {
      const fresh = await getExternalAuditorFieldwork();
      if (fresh.audit_id !== model.audit_id || fresh.participant_id !== model.participant_id) {
        throw new Error("The external audit session changed before evidence upload. Refresh the workspace before attaching a file.");
      }
      const current = fresh.items.find((item) => item.checklist_item_id === selected.checklist_item_id);
      if (!current) throw new Error("The selected checklist item is no longer assigned to this external auditor.");
      const result = await uploadExternalAuditorEvidence(fresh, current, evidenceFile, evidenceDescription);
      setEvidenceFile(null); setEvidenceDescription("");
      setNotice(`Governed evidence uploaded · ${result.artifact.filename} · SHA ${result.artifact.sha256.slice(0, 12)}… · checklist v${result.committed_version}.`);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "External evidence upload failed.");
    } finally {
      setUploading(false);
    }
  };

  if (loading && !model) return <section className="qms-public-audit__card">Loading assigned external-auditor checklist…</section>;
  if (!model) return <section className="qms-public-audit__card" role="alert"><AlertTriangle size={18} /> {error || "External auditor fieldwork unavailable."}</section>;

  const selectedGovernedEvidence = selected ? governedEvidence(selected.my_evidence_references) : [];

  return (
    <section className="qms-public-audit__card qms-external-auditor-fieldwork" aria-label="External auditor fieldwork">
      <header>
        <ShieldAlert size={19} />
        <div><strong>Assigned audit checklist</strong><small>Scoped external-auditor fieldwork · {completed}/{items.length} resolved · {percent != null ? `${percent}%` : "N/A"}</small></div>
        <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button>
      </header>

      <div className="qms-external-auditor-fieldwork__sync" role="status">
        {typeof navigator !== "undefined" && !navigator.onLine ? <CloudOff size={15} /> : <UploadCloud size={15} />}
        <span>{pendingCount ? `${pendingCount} encrypted change${pendingCount === 1 ? "" : "s"} pending sync` : "No pending fieldwork changes"}</span>
        {pendingCount ? <button type="button" onClick={() => void replayPending()} disabled={replaying || (typeof navigator !== "undefined" && !navigator.onLine)}>{replaying ? "Synchronizing…" : "Sync now"}</button> : null}
      </div>
      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={15} /> {error}</div> : null}
      {notice ? <div className="qms-external-auditor-fieldwork__notice" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}
      {model.finding_draft_blocker ? <div className="qms-external-auditor-fieldwork__blocker"><AlertTriangle size={15} /><span>{model.finding_draft_blocker}</span></div> : null}

      <div className="qms-external-auditor-fieldwork__layout">
        <nav aria-label="Assigned checklist items">
          {items.map((item, index) => (
            <button key={item.checklist_item_id} type="button" className={item.checklist_item_id === selected?.checklist_item_id ? "is-selected" : ""} onClick={() => setSelectedId(item.checklist_item_id)}>
              <span>{index + 1}</span><div><strong>{item.checklist_ref || item.requirement_ref || `Item ${index + 1}`}</strong><small>{item.canonical_response_status.replaceAll("_", " ")} · v{item.entity_version}</small></div>
            </button>
          ))}
        </nav>

        {selected ? (
          <div className="qms-external-auditor-fieldwork__item">
            <span>{selected.section || "Checklist"}</span>
            <h2>{selected.prompt}</h2>
            <dl><div><dt>Requirement</dt><dd>{selected.requirement_ref || "—"}</dd></div><div><dt>Current response</dt><dd>{selected.canonical_response_status.replaceAll("_", " ")} · v{selected.entity_version}</dd></div></dl>
            <div className="qms-external-auditor-fieldwork__responses">
              {ALLOWED_RESPONSES.map((option) => <button type="button" key={option.value} disabled={!model.can_execute_checklist || saving} className={selected.canonical_response_status === option.value ? "is-active" : ""} onClick={() => void save(selected, option.value)}>{option.value === "COMPLIANT" ? <CheckCircle2 size={15} /> : option.value === "NOT_APPLICABLE" ? <CircleSlash2 size={15} /> : <ShieldAlert size={15} />}{option.label}</button>)}
            </div>
            <label><span>My attributable fieldwork note</span><textarea rows={5} value={notes[selected.checklist_item_id] ?? selected.my_auditor_notes ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <label><span>Text evidence references · one per line</span><textarea rows={3} value={evidence[selected.checklist_item_id] ?? evidenceText(selected.my_evidence_references)} onChange={(event) => setEvidence((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <button type="button" className="qms-external-auditor-fieldwork__save" disabled={!model.can_execute_checklist || saving} onClick={() => void save(selected, selected.canonical_response_status)}><Save size={15} /> {saving ? "Saving…" : "Save note / references"}</button>

            <section className="qms-external-auditor-fieldwork__evidence">
              <header><FileUp size={15} /><div><strong>Governed evidence files</strong><small>Online upload only · immutable checksum and participant attribution retained</small></div></header>
              {selectedGovernedEvidence.length ? <ul>{selectedGovernedEvidence.map((artifact) => <li key={artifact.artifactId}><b>{artifact.filename}</b><small>{artifact.sizeBytes ? `${Math.ceil(artifact.sizeBytes / 1024)} KB · ` : ""}{artifact.sha256 ? `SHA ${artifact.sha256.slice(0, 12)}…` : "Governed artifact"}</small></li>)}</ul> : <p>No governed file has been attached by this external auditor yet.</p>}
              <label><span>File</span><input type="file" accept={EVIDENCE_ACCEPT} disabled={uploading} onChange={(event) => setEvidenceFile(event.target.files?.[0] || null)} /></label>
              <label><span>Evidence context</span><input value={evidenceDescription} maxLength={4000} onChange={(event) => setEvidenceDescription(event.target.value)} placeholder="What this evidence demonstrates" /></label>
              <button type="button" disabled={!evidenceFile || uploading || (typeof navigator !== "undefined" && !navigator.onLine)} onClick={() => void uploadEvidence()}><FileUp size={15} /> {uploading ? "Uploading…" : "Attach governed evidence"}</button>
              {typeof navigator !== "undefined" && !navigator.onLine ? <small>File upload is paused offline; structured fieldwork can still be queued securely.</small> : null}
            </section>

            {model.can_draft_findings ? <ExternalAuditorFindingDraftPanel model={model} item={selected} /> : null}
          </div>
        ) : <p className="qms-public-audit__empty">No governed checklist items are assigned to this audit.</p>}
      </div>
    </section>
  );
};

export default ExternalAuditorFieldworkWorkspace;
