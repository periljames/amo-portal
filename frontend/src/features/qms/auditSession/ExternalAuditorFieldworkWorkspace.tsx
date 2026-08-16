import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash2, RefreshCw, Save, ShieldAlert } from "lucide-react";

import {
  getExternalAuditorFieldwork,
  mutateExternalAuditorChecklist,
  type ExternalAuditorFieldworkItem,
  type ExternalAuditorFieldworkModel,
  type ExternalChecklistResponse,
} from "../../../services/qmsAuditExternalAccess";

const ALLOWED_RESPONSES: Array<{ value: ExternalChecklistResponse; label: string }> = [
  { value: "COMPLIANT", label: "Compliant" },
  { value: "NOT_APPLICABLE", label: "N/A" },
  { value: "NOT_VERIFIED", label: "Not verified" },
];

function evidenceText(value: Array<Record<string, unknown> | string>): string {
  return value.map((entry) => typeof entry === "string" ? entry : JSON.stringify(entry)).join("\n");
}

function evidenceRefs(value: string): string[] {
  return value.split(/\r?\n/).map((entry) => entry.trim()).filter(Boolean).slice(0, 200);
}

const ExternalAuditorFieldworkWorkspace: React.FC = () => {
  const [model, setModel] = useState<ExternalAuditorFieldworkModel | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getExternalAuditorFieldwork();
      setModel(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "External auditor fieldwork is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const items = useMemo(() => model?.items ?? [], [model?.items]);
  const effectiveSelectedId = selectedId && items.some((item) => item.checklist_item_id === selectedId)
    ? selectedId
    : items[0]?.checklist_item_id || null;
  const selected = items.find((item) => item.checklist_item_id === effectiveSelectedId) || null;
  const completed = items.filter((item) => item.canonical_response_status !== "NOT_VERIFIED").length;
  const percent = items.length ? Math.round((completed / items.length) * 100) : 0;

  const save = async (item: ExternalAuditorFieldworkItem, response: ExternalChecklistResponse) => {
    if (!model || !model.can_execute_checklist) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await mutateExternalAuditorChecklist(model, item, {
        canonical_response_status: response,
        auditor_notes: notes[item.checklist_item_id] ?? item.my_auditor_notes ?? null,
        evidence_references: evidenceRefs(evidence[item.checklist_item_id] ?? evidenceText(item.my_evidence_references)),
        reason: "External auditor assigned-checklist fieldwork update.",
      });
      setNotice("Fieldwork contribution saved to the authoritative audit record with participant attribution.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "External checklist update failed.");
    } finally {
      setSaving(false);
    }
  };

  if (loading && !model) return <section className="qms-public-audit__card">Loading assigned external-auditor checklist…</section>;
  if (!model) return <section className="qms-public-audit__card" role="alert"><AlertTriangle size={18} /> {error || "External auditor fieldwork unavailable."}</section>;

  return (
    <section className="qms-public-audit__card qms-external-auditor-fieldwork" aria-label="External auditor fieldwork">
      <header>
        <ShieldAlert size={19} />
        <div><strong>Assigned audit checklist</strong><small>Scoped external-auditor fieldwork · {completed}/{items.length} resolved · {percent}%</small></div>
        <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button>
      </header>

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
              {ALLOWED_RESPONSES.map((option) => (
                <button type="button" key={option.value} disabled={!model.can_execute_checklist || saving} className={selected.canonical_response_status === option.value ? "is-active" : ""} onClick={() => void save(selected, option.value)}>
                  {option.value === "COMPLIANT" ? <CheckCircle2 size={15} /> : option.value === "NOT_APPLICABLE" ? <CircleSlash2 size={15} /> : <ShieldAlert size={15} />}{option.label}
                </button>
              ))}
            </div>

            <label><span>My attributable fieldwork note</span><textarea rows={5} value={notes[selected.checklist_item_id] ?? selected.my_auditor_notes ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <label><span>My evidence references · one per line</span><textarea rows={4} value={evidence[selected.checklist_item_id] ?? evidenceText(selected.my_evidence_references)} onChange={(event) => setEvidence((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} /></label>
            <button type="button" className="qms-external-auditor-fieldwork__save" disabled={!model.can_execute_checklist || saving} onClick={() => void save(selected, selected.canonical_response_status)}><Save size={15} /> {saving ? "Saving…" : "Save note / evidence"}</button>
          </div>
        ) : <p className="qms-public-audit__empty">No governed checklist items are assigned to this audit.</p>}
      </div>
    </section>
  );
};

export default ExternalAuditorFieldworkWorkspace;
