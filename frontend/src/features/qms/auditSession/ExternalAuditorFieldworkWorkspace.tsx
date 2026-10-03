import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash2, CloudOff, FileUp, RefreshCw, Save, ShieldAlert, UploadCloud } from "lucide-react";

import {
  getExternalAuditorFieldwork,
  type ExternalAuditorFieldworkItem,
  type ExternalAuditorFieldworkModel,
  type ExternalChecklistResponseOption,
} from "../../../services/qmsAuditExternalAccess";
import { createEvidenceMutationId, uploadExternalAuditorEvidence, type AuditEvidenceContext } from "../../../services/qmsAuditEvidence";
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
import {
  clearExternalOfflineEvidence,
  enqueueExternalOfflineEvidence,
  listExternalOfflineEvidence,
  replayExternalOfflineEvidence,
} from "../../../services/qmsExternalOfflineEvidence";
import ExternalAuditorFindingDraftPanel from "./ExternalAuditorFindingDraftPanel";

const DEFAULT_RESPONSES: ExternalChecklistResponseOption[] = [
  { value: "COMPLIANT", label: "Compliant", canonical_status: "COMPLIANT" },
  { value: "NONCOMPLIANT", label: "NCR", canonical_status: "NONCOMPLIANT" },
  { value: "OBSERVATION", label: "Observation", canonical_status: "OBSERVATION" },
  { value: "NOT_APPLICABLE", label: "N/A", canonical_status: "NOT_APPLICABLE" },
  { value: "NOT_VERIFIED", label: "Not verified", canonical_status: "NOT_VERIFIED" },
];

function responseOptions(item: ExternalAuditorFieldworkItem): ExternalChecklistResponseOption[] {
  if (item.response_options?.length) return item.response_options;
  if (item.response_type === "YES_NO_NA") {
    return [
      { value: "YES", label: "Yes", canonical_status: "COMPLIANT" },
      { value: "NO", label: "No", canonical_status: "NONCOMPLIANT" },
      { value: "N/A", label: "N/A", canonical_status: "NOT_APPLICABLE" },
    ];
  }
  return DEFAULT_RESPONSES;
}
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
    const context = entry.context && typeof entry.context === "object"
      ? entry.context as Record<string, unknown>
      : null;
    return [{
      artifactId,
      filename: typeof entry.filename === "string" ? entry.filename : "Governed evidence",
      sha256: typeof entry.sha256 === "string" ? entry.sha256 : null,
      sizeBytes: typeof entry.size_bytes === "number" ? entry.size_bytes : null,
      context,
    }];
  });
}

function responseRuleError(
  item: ExternalAuditorFieldworkItem,
  option: ExternalChecklistResponseOption,
  note: string,
): string | null {
  const status = option.canonical_status;
  const notePresent = Boolean(note.trim());
  if (status === "NOT_APPLICABLE" && item.na_justification_required && !notePresent) {
    return "This governed checklist item requires an auditor reason before it can be marked N/A.";
  }
  if ((item.notes_required_when || []).includes(status) && !notePresent) {
    return `Auditor notes are required before recording ${status.replaceAll("_", " ").toLowerCase()}.`;
  }
  if ((item.evidence_required_when || []).includes(status) && !item.my_evidence_references.length) {
    return "Governed evidence is required for this response. Upload and synchronize the evidence before finalizing the outcome.";
  }
  return null;
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
  const [evidenceContext, setEvidenceContext] = useState({
    locationRef: "",
    personRef: "",
    facilityRef: "",
    assetRef: "",
    toolRef: "",
    componentRef: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [pendingEvidenceCount, setPendingEvidenceCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const updatePendingCount = async (nextModel: ExternalAuditorFieldworkModel | null = modelRef.current) => {
    if (!nextModel) { setPendingCount(0); setPendingEvidenceCount(0); return; }
    const scope = scopeOf(nextModel);
    try { setPendingCount((await listExternalAuditMutations(scope)).length); }
    catch { setPendingCount(0); }
    try { setPendingEvidenceCount((await listExternalOfflineEvidence(scope)).length); }
    catch { setPendingEvidenceCount(0); }
  };

  const load = async (): Promise<ExternalAuditorFieldworkModel | null> => {
    setLoading(true);
    setError(null);
    try {
      const next = await getExternalAuditorFieldwork();
      const prior = modelRef.current;
      if (prior && (prior.audit_id !== next.audit_id || prior.participant_id !== next.participant_id)) {
        await clearExternalAuditMutations(scopeOf(prior)).catch(() => undefined);
        await clearExternalOfflineEvidence(scopeOf(prior)).catch(() => undefined);
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
      const currentModel = committed > 0 ? await getExternalAuditorFieldwork() : fresh;
      modelRef.current = currentModel;
      setModel(currentModel);
      const evidenceResult = await replayExternalOfflineEvidence(scope);
      await updatePendingCount(currentModel);
      if (committed > 0 || evidenceResult.uploaded.length > 0) {
        const parts = [];
        if (committed > 0) parts.push(`${committed} fieldwork change${committed === 1 ? "" : "s"}`);
        if (evidenceResult.uploaded.length > 0) parts.push(`${evidenceResult.uploaded.length} evidence file${evidenceResult.uploaded.length === 1 ? "" : "s"}`);
        setNotice(`${parts.join(" and ")} synchronized with original mutation identity and evidence SHA-256 preserved.`);
        await load();
      } else if (evidenceResult.deferred > 0) {
        setNotice(`${evidenceResult.deferred} evidence file${evidenceResult.deferred === 1 ? " is" : "s are"} waiting for earlier checklist changes to synchronize first.`);
      } else if (evidenceResult.conflicts > 0) {
        setError(`${evidenceResult.conflicts} evidence file${evidenceResult.conflicts === 1 ? " requires" : "s require"} deliberate conflict review.`);
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
    setEvidenceContext({
      locationRef: "",
      personRef: "",
      facilityRef: "",
      assetRef: "",
      toolRef: "",
      componentRef: "",
    });
  }, [effectiveSelectedId]);

  const save = async (item: ExternalAuditorFieldworkItem, option: ExternalChecklistResponseOption) => {
    if (!model || !model.can_execute_checklist) return;
    const itemNote = notes[item.checklist_item_id] ?? item.my_auditor_notes ?? "";
    const ruleError = responseRuleError(item, option, itemNote);
    if (ruleError) {
      setError(ruleError);
      return;
    }
    setSaving(true); setError(null); setNotice(null);
    const mutation = buildExternalAuditorMutation(item, {
      canonicalResponseStatus: option.canonical_status,
      responseValue: option.value,
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

  const capturedEvidenceContext = (): AuditEvidenceContext => ({
    location_ref: evidenceContext.locationRef.trim() || undefined,
    person_ref: evidenceContext.personRef.trim() || undefined,
    facility_ref: evidenceContext.facilityRef.trim() || undefined,
    asset_ref: evidenceContext.assetRef.trim() || undefined,
    tool_ref: evidenceContext.toolRef.trim() || undefined,
    component_ref: evidenceContext.componentRef.trim() || undefined,
  });

  const resetEvidenceCapture = () => {
    setEvidenceFile(null);
    setEvidenceDescription("");
    setEvidenceContext({
      locationRef: "",
      personRef: "",
      facilityRef: "",
      assetRef: "",
      toolRef: "",
      componentRef: "",
    });
  };

  const uploadEvidence = async () => {
    if (!model || !model.can_create_evidence || !selected || !evidenceFile || uploading) return;
    setUploading(true); setError(null); setNotice(null);
    const queueLocal = async () => {
      await enqueueExternalOfflineEvidence(model, selected, evidenceFile, evidenceDescription, capturedEvidenceContext());
      resetEvidenceCapture();
      await updatePendingCount(model);
      setNotice("Evidence saved encrypted on this device. No guest credential or CSRF token was stored; upload will revalidate the active external-auditor session.");
    };
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      try { await queueLocal(); }
      catch (cause) { setError(cause instanceof Error ? cause.message : "Evidence could not be stored securely offline."); }
      finally { setUploading(false); }
      return;
    }
    try {
      const fresh = await getExternalAuditorFieldwork();
      if (fresh.audit_id !== model.audit_id || fresh.participant_id !== model.participant_id) {
        throw new Error("The external audit session changed before evidence upload. Refresh the workspace before attaching a file.");
      }
      const current = fresh.items.find((item) => item.checklist_item_id === selected.checklist_item_id);
      if (!current) throw new Error("The selected checklist item is no longer assigned to this external auditor.");
      const result = await uploadExternalAuditorEvidence(fresh, current, evidenceFile, evidenceDescription, createEvidenceMutationId(), capturedEvidenceContext());
      resetEvidenceCapture();
      setNotice(`Governed evidence uploaded · ${result.artifact.filename} · checklist v${result.committed_version}.`);
      await load();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "External evidence upload failed.";
      const normalized = message.toLowerCase();
      const transportFailure = normalized.includes("failed to fetch")
        || normalized.includes("network")
        || normalized.includes("connection")
        || normalized.includes("timed out")
        || normalized.includes("load failed");
      if (transportFailure) {
        try { await queueLocal(); }
        catch (queueCause) { setError(queueCause instanceof Error ? queueCause.message : message); }
      } else {
        setError(message);
      }
    } finally {
      setUploading(false);
    }
  };

  if (loading && !model) return <section className="qms-public-audit__card">Loading assigned external-auditor checklist…</section>;
  if (!model) return <section className="qms-public-audit__card" role="alert"><AlertTriangle size={18} /> {error || "External auditor fieldwork unavailable."}</section>;

  const selectedGovernedEvidence = selected ? governedEvidence(selected.my_evidence_references) : [];
  const selectedResponseOptions = selected ? responseOptions(selected) : [];

  return (
    <section className="qms-public-audit__card qms-external-auditor-fieldwork" aria-label="External auditor fieldwork">
      <header>
        <ShieldAlert size={19} />
        <div><strong>Assigned audit checklist</strong><small>Scoped external-auditor fieldwork · {completed}/{items.length} resolved · {percent != null ? `${percent}%` : "N/A"}</small></div>
        <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button>
      </header>

      <div className="qms-external-auditor-fieldwork__sync" role="status">
        {typeof navigator !== "undefined" && !navigator.onLine ? <CloudOff size={15} /> : <UploadCloud size={15} />}
        <span>
          {pendingCount || pendingEvidenceCount ? (
            <>
              {pendingCount ? `${pendingCount} encrypted change${pendingCount === 1 ? "" : "s"} pending sync` : null}
              {pendingCount && pendingEvidenceCount ? " · " : null}
              {pendingEvidenceCount ? `${pendingEvidenceCount} encrypted evidence file${pendingEvidenceCount === 1 ? "" : "s"} pending sync` : null}
            </>
          ) : "No pending fieldwork changes"}
        </span>
        {pendingCount || pendingEvidenceCount ? <button type="button" onClick={() => void replayPending()} disabled={replaying || (typeof navigator !== "undefined" && !navigator.onLine)}>{replaying ? "Synchronizing…" : "Sync now"}</button> : null}
      </div>
      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={15} /> {error}</div> : null}
      {notice ? <div className="qms-external-auditor-fieldwork__notice" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}
      {!model.fieldwork_available && model.fieldwork_blocker ? <div className="qms-external-auditor-fieldwork__blocker" role="alert"><AlertTriangle size={15} /><span>{model.fieldwork_blocker}</span></div> : null}
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
            <dl><div><dt>Requirement</dt><dd>{selected.requirement_ref || "—"}</dd></div><div><dt>Current response</dt><dd>{selected.response_value || selected.canonical_response_status.replaceAll("_", " ")} · v{selected.entity_version}</dd></div>{selected.audit_method ? <div><dt>Method</dt><dd>{selected.audit_method.replaceAll("_", " ")}</dd></div> : null}{selected.sampling_requirement ? <div><dt>Sampling</dt><dd>{selected.sampling_requirement}</dd></div> : null}</dl>
            {selected.expected_evidence || selected.guidance ? <section className="qms-external-auditor-fieldwork__verification"><strong>Verification plan</strong>{selected.expected_evidence ? <p>{selected.expected_evidence}</p> : null}{selected.guidance ? <small>{selected.guidance}</small> : null}</section> : null}
            <div className="qms-external-auditor-fieldwork__responses">
              {selectedResponseOptions.map((option) => {
                const adverse = option.canonical_status === "NONCOMPLIANT" || option.canonical_status === "OBSERVATION";
                const active = selected.response_value
                  ? selected.response_value === option.value
                  : selected.canonical_response_status === option.canonical_status;
                return <button
                  type="button"
                  key={option.value}
                  disabled={!model.can_execute_checklist || saving}
                  className={active ? "is-active" : ""}
                  onClick={() => {
                    if (adverse) {
                      setNotice(`${option.label} requires the governed finding-draft workflow below; Quality promotion controls the official adverse response.`);
                      document.querySelector(".qms-external-finding-drafts")?.scrollIntoView({ behavior: "smooth", block: "start" });
                      return;
                    }
                    void save(selected, option);
                  }}
                >{option.canonical_status === "COMPLIANT" ? <CheckCircle2 size={15} /> : option.canonical_status === "NOT_APPLICABLE" ? <CircleSlash2 size={15} /> : <ShieldAlert size={15} />}{option.label}</button>;
              })}
            </div>
            <label><span>My attributable fieldwork note</span><textarea rows={5} value={notes[selected.checklist_item_id] ?? selected.my_auditor_notes ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <label><span>Text evidence references · one per line</span><textarea rows={3} value={evidence[selected.checklist_item_id] ?? evidenceText(selected.my_evidence_references)} onChange={(event) => setEvidence((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <button
              type="button"
              className="qms-external-auditor-fieldwork__save"
              disabled={!model.can_execute_checklist || saving}
              onClick={() => {
                const currentOption = selectedResponseOptions.find((option) =>
                  selected.response_value
                    ? option.value === selected.response_value
                    : option.canonical_status === selected.canonical_response_status,
                );
                if (currentOption) void save(selected, currentOption);
                else setError("This checklist item has no governed response option matching the current record.");
              }}
            ><Save size={15} /> {saving ? "Saving…" : "Save note / references"}</button>

            {model.can_create_evidence ? <section className="qms-external-auditor-fieldwork__evidence">
              <header><FileUp size={15} /><div><strong>Governed evidence files</strong><small>Online upload or encrypted offline queue · participant attribution retained</small></div></header>
              {selectedGovernedEvidence.length ? <ul>{selectedGovernedEvidence.map((artifact) => {
                const contextValues = artifact.context
                  ? ["location_ref", "person_ref", "facility_ref", "asset_ref", "tool_ref", "component_ref"]
                    .map((key) => typeof artifact.context?.[key] === "string" ? String(artifact.context[key]).trim() : "")
                    .filter(Boolean)
                  : [];
                return <li key={artifact.artifactId}><b>{artifact.filename}</b><small>{artifact.sizeBytes ? `${Math.ceil(artifact.sizeBytes / 1024)} KB` : "Governed artifact"}</small>{contextValues.length ? <small>{contextValues.join(" · ")}</small> : null}</li>;
              })}</ul> : <p>No governed file has been attached by this external auditor yet.</p>}
              <label><span>File</span><input type="file" accept={EVIDENCE_ACCEPT} disabled={uploading} onChange={(event) => setEvidenceFile(event.target.files?.[0] || null)} /></label>
              <label><span>What this demonstrates</span><input value={evidenceDescription} maxLength={4000} onChange={(event) => setEvidenceDescription(event.target.value)} placeholder="Objective evidence observed or reviewed" /></label>
              <div className="qms-external-auditor-fieldwork__evidence-context" aria-label="Structured evidence context">
                <label><span>Location</span><input value={evidenceContext.locationRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, locationRef: event.target.value }))} placeholder="Base / line / station" /></label>
                <label><span>Person</span><input value={evidenceContext.personRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, personRef: event.target.value }))} placeholder="Name or personnel ID" /></label>
                <label><span>Facility</span><input value={evidenceContext.facilityRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, facilityRef: event.target.value }))} placeholder="Hangar / workshop / store" /></label>
                <label><span>Asset</span><input value={evidenceContext.assetRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, assetRef: event.target.value }))} placeholder="Aircraft / equipment / asset" /></label>
                <label><span>Tool</span><input value={evidenceContext.toolRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, toolRef: event.target.value }))} placeholder="Tool or calibration ID" /></label>
                <label><span>Component</span><input value={evidenceContext.componentRef} maxLength={255} onChange={(event) => setEvidenceContext((current) => ({ ...current, componentRef: event.target.value }))} placeholder="P/N, S/N or component ref" /></label>
              </div>
              <button type="button" disabled={!evidenceFile || uploading} onClick={() => void uploadEvidence()}><FileUp size={15} /> {uploading ? "Saving…" : typeof navigator !== "undefined" && !navigator.onLine ? "Queue governed evidence" : "Attach governed evidence"}</button>
              {typeof navigator !== "undefined" && !navigator.onLine ? <small>The file will be encrypted on this device and uploaded only after the active external-auditor session is revalidated online.</small> : null}
            </section> : <div className="qms-external-auditor-fieldwork__blocker"><ShieldAlert size={15} /><span>This invitation does not permit governed evidence upload.</span></div>}

            {model.can_draft_findings ? <ExternalAuditorFindingDraftPanel model={model} item={selected} /> : null}
          </div>
        ) : <p className="qms-public-audit__empty">No governed checklist items are assigned to this audit.</p>}
      </div>
    </section>
  );
};

export default ExternalAuditorFieldworkWorkspace;