import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileWarning, RefreshCw, Send, Trash2 } from "lucide-react";

import type { ExternalAuditorFieldworkItem, ExternalAuditorFieldworkModel } from "../../../services/qmsAuditExternalAccess";
import {
  createExternalFindingDraft,
  listMyExternalFindingDrafts,
  submitExternalFindingDraft,
  withdrawExternalFindingDraft,
  type ExternalFindingDraft,
  type ExternalFindingDraftType,
} from "../../../services/qmsExternalFindingDrafts";
import type { FieldworkFindingLevel, FieldworkFindingSeverity } from "../../../services/qmsChecklistExecutionGovernance";

type Props = {
  model: ExternalAuditorFieldworkModel;
  item: ExternalAuditorFieldworkItem;
};

type DraftForm = {
  type: ExternalFindingDraftType;
  level: FieldworkFindingLevel;
  severity: FieldworkFindingSeverity;
  description: string;
  objectiveEvidence: string;
  evidenceRefs: string;
  supersedesDraftId: string | null;
};

const initialForm: DraftForm = {
  type: "NON_CONFORMITY",
  level: "LEVEL_2",
  severity: "MAJOR",
  description: "",
  objectiveEvidence: "",
  evidenceRefs: "",
  supersedesDraftId: null,
};

function evidenceLines(value: string): string[] {
  return value.split(/\r?\n/).map((entry) => entry.trim()).filter(Boolean).slice(0, 200);
}

function latestReviewNote(draft: ExternalFindingDraft): string | null {
  for (let index = draft.events.length - 1; index >= 0; index -= 1) {
    if (draft.events[index].review_note) return draft.events[index].review_note;
  }
  return null;
}

const ExternalAuditorFindingDraftPanel: React.FC<Props> = ({ model, item }) => {
  const [drafts, setDrafts] = useState<ExternalFindingDraft[]>([]);
  const [form, setForm] = useState<DraftForm>(initialForm);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listMyExternalFindingDrafts();
      setDrafts(response.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "External finding drafts are unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [item.checklist_item_id]);

  const itemDrafts = useMemo(
    () => drafts.filter((draft) => draft.checklist_item_id === item.checklist_item_id),
    [drafts, item.checklist_item_id],
  );

  const changeType = (type: ExternalFindingDraftType) => {
    setForm((current) => type === "OBSERVATION"
      ? { ...current, type, level: "LEVEL_4", severity: "MINOR" }
      : { ...current, type, level: current.level === "LEVEL_4" ? "LEVEL_2" : current.level, severity: current.level === "LEVEL_1" ? "CRITICAL" : current.level === "LEVEL_3" ? "MINOR" : "MAJOR" });
  };

  const changeLevel = (level: FieldworkFindingLevel) => {
    const severity: FieldworkFindingSeverity = level === "LEVEL_1" ? "CRITICAL" : level === "LEVEL_2" ? "MAJOR" : "MINOR";
    setForm((current) => ({ ...current, level, severity }));
  };

  const save = async () => {
    if (form.description.trim().length < 8) return;
    setBusyId("create");
    setError(null);
    setNotice(null);
    try {
      const created = await createExternalFindingDraft(model, item, {
        draft_type: form.type,
        proposed_level: form.level,
        proposed_severity: form.severity,
        description: form.description.trim(),
        objective_evidence: form.objectiveEvidence.trim() || null,
        evidence_references: evidenceLines(form.evidenceRefs),
        supersedes_draft_id: form.supersedesDraftId,
      });
      setNotice(`Draft ${created.id.slice(0, 8)} saved. Submit it when ready for Quality review.`);
      setForm(initialForm);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Draft creation failed.");
    } finally {
      setBusyId(null);
    }
  };

  const transition = async (draft: ExternalFindingDraft, action: "submit" | "withdraw") => {
    setBusyId(draft.id);
    setError(null);
    setNotice(null);
    try {
      if (action === "submit") {
        await submitExternalFindingDraft(model, draft.id, "External auditor submitted the draft for Quality review.");
        setNotice("Draft submitted to Quality review.");
      } else {
        await withdrawExternalFindingDraft(model, draft.id, "External auditor withdrew this draft revision.");
        setNotice("Draft withdrawn.");
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Draft ${action} failed.`);
    } finally {
      setBusyId(null);
    }
  };

  const revise = (draft: ExternalFindingDraft) => {
    setForm({
      type: draft.draft_type,
      level: draft.proposed_level,
      severity: draft.proposed_severity,
      description: draft.description,
      objectiveEvidence: draft.objective_evidence || "",
      evidenceRefs: draft.evidence_references.map((entry) => typeof entry === "string" ? entry : JSON.stringify(entry)).join("\n"),
      supersedesDraftId: draft.id,
    });
    setNotice("Revision loaded. Saving creates a new immutable draft linked to the returned revision.");
  };

  return (
    <section className="qms-external-finding-drafts" aria-label="External finding drafts">
      <header>
        <div><FileWarning size={17} /><span><strong>Finding drafts</strong><small>Drafts are not official findings or CARs until Quality promotes them.</small></span></div>
        <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button>
      </header>
      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={14} /> {error}</div> : null}
      {notice ? <p className="qms-external-finding-drafts__notice" role="status">{notice}</p> : null}

      <div className="qms-external-finding-drafts__form">
        <label><span>Draft type</span><select value={form.type} onChange={(event) => changeType(event.target.value as ExternalFindingDraftType)}><option value="NON_CONFORMITY">Non-conformity draft</option><option value="OBSERVATION">Observation draft</option></select></label>
        {form.type === "NON_CONFORMITY" ? <label><span>Proposed level</span><select value={form.level} onChange={(event) => changeLevel(event.target.value as FieldworkFindingLevel)}><option value="LEVEL_1">Level 1 · Critical</option><option value="LEVEL_2">Level 2 · Major</option><option value="LEVEL_3">Level 3 · Minor</option></select></label> : <label><span>Proposed level</span><input readOnly value="LEVEL_4 · Observation" /></label>}
        <label className="is-wide"><span>Finding statement</span><textarea rows={4} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /></label>
        <label className="is-wide"><span>Objective evidence</span><textarea rows={3} value={form.objectiveEvidence} onChange={(event) => setForm((current) => ({ ...current, objectiveEvidence: event.target.value }))} /></label>
        <label className="is-wide"><span>Evidence references · one per line</span><textarea rows={3} value={form.evidenceRefs} onChange={(event) => setForm((current) => ({ ...current, evidenceRefs: event.target.value }))} /></label>
        <footer className="is-wide"><span>{form.supersedesDraftId ? `Revising returned draft ${form.supersedesDraftId.slice(0, 8)}` : "New immutable draft revision"}</span><button type="button" disabled={busyId === "create" || form.description.trim().length < 8} onClick={() => void save()}>{busyId === "create" ? "Saving…" : "Save draft"}</button></footer>
      </div>

      <div className="qms-external-finding-drafts__list">
        {!itemDrafts.length ? <p className="qms-public-audit__empty">No finding drafts for this checklist item.</p> : itemDrafts.map((draft) => {
          const reviewNote = latestReviewNote(draft);
          return <article key={draft.id} data-status={draft.status}>
            <div><span>{draft.status}</span><strong>{draft.draft_type.replaceAll("_", " ")} · {draft.proposed_level}</strong><p>{draft.description}</p>{reviewNote ? <blockquote>Quality review: {reviewNote}</blockquote> : null}</div>
            <footer>
              {draft.status === "CREATED" ? <button type="button" disabled={busyId === draft.id} onClick={() => void transition(draft, "submit")}><Send size={14} /> Submit to Quality</button> : null}
              {draft.status === "RETURNED" ? <button type="button" onClick={() => revise(draft)}>Create revision</button> : null}
              {["CREATED", "SUBMITTED", "RETURNED"].includes(draft.status) ? <button type="button" disabled={busyId === draft.id} onClick={() => void transition(draft, "withdraw")}><Trash2 size={14} /> Withdraw</button> : null}
            </footer>
          </article>;
        })}
      </div>
    </section>
  );
};

export default ExternalAuditorFindingDraftPanel;
