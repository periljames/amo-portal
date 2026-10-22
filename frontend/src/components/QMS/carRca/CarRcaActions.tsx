import { useState } from "react";
import type { CarRcaAction, CarRcaActionCreate } from "../../../services/qmsCarRca";
import { addCarRcaInviteAction, reviseCarRcaInviteAction, progressCarRcaInviteAction } from "../../../services/qmsCarRca";

const EMPTY: CarRcaActionCreate = {
  kind: "CORRECTIVE", description: "", cause_node_ids: [], evidence_references: [],
  external_owner_name: null, target_date: null, priority: "MEDIUM",
};

export default function CarRcaActions({ token, actions, disabled, canProgress = false, onChanged, causeIds }: {
  token: string;
  actions: CarRcaAction[];
  disabled: boolean;
  canProgress?: boolean;
  onChanged: () => Promise<void>;
  causeIds: Array<{ id: string; statement: string }>;
}) {
  const [draft, setDraft] = useState<CarRcaActionCreate>(EMPTY);
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [proof, setProof] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const create = async () => {
    if (!draft.description.trim() || !draft.external_owner_name?.trim() || !draft.target_date || busy) return;
    setBusy("create"); setError(null);
    try {
      const payload = { ...draft,
        description: draft.description.trim(), external_owner_name: draft.external_owner_name?.trim(),
      };
      if (editingActionId) await reviseCarRcaInviteAction(token, editingActionId, payload);
      else await addCarRcaInviteAction(token, payload);
      setDraft(EMPTY); setEditingActionId(null); await onChanged();
      setMessage(editingActionId ? "Proposed action revision retained for Quality review." : "Corrective action recorded for Quality review.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save corrective action."); }
    finally { setBusy(null); }
  };
  const progress = async (actionId: string, state: "IN_PROGRESS" | "SUBMITTED") => {
    if (busy) return;
    setBusy(actionId); setError(null);
    try {
      await progressCarRcaInviteAction(token, actionId, {
        state, completion_note: note.trim(),
        evidence_references: proof.split("\n").map(x => x.trim()).filter(Boolean),
      });
      await onChanged(); setActiveId(null); setNote(""); setProof("");
      setMessage(state === "SUBMITTED" ? "Implementation submitted for independent Quality verification." : "Implementation marked in progress.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update action."); }
    finally { setBusy(null); }
  };
  return <section className="car-rca car-rca-actions" aria-label="Individual corrective actions">
    <div className="car-rca-heading"><div><h4>Corrective actions and implementation</h4>
      <p>Separate containment from permanent correction and systemic prevention. Each action has its own owner, due date, evidence and Quality decision.</p>
    </div></div>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    {actions.length > 0 ? <div className="car-rca-table-scroll"><table>
      <caption>{actions.length} linked actions</caption>
      <thead><tr><th>No.</th><th>Action</th><th>Responsible</th><th>Due</th><th>State / review</th><th>Implementation</th></tr></thead>
      <tbody>{actions.map(action => <tr key={action.id}>
        <td>{action.action_number}</td><td><strong>{action.kind}</strong><p>{action.description}</p>
          {!disabled && ["PROPOSED", "REJECTED"].includes(action.state) && <button type="button" disabled={Boolean(busy)}
            onClick={() => { setEditingActionId(action.id); setDraft({ kind: action.kind, description: action.description,
              cause_node_ids: action.cause_node_ids, evidence_references: action.evidence_references,
              external_owner_name: action.external_owner_name, target_date: action.target_date, priority: action.priority }); }}>
            Revise proposed action</button>}
          {action.cause_node_ids.length > 0 && <small>Causes: {action.cause_node_ids.join(", ")}</small>}</td>
        <td>{action.external_owner_name || "Not assigned"}</td><td>{action.target_date || "Not set"}</td>
        <td>{action.state.replaceAll("_", " ")}{action.quality_review_note && <p>Quality: {action.quality_review_note}</p>}
          {action.state === "PROPOSED" && <p>Awaiting independent Quality approval.</p>}
          {action.state === "REJECTED" && <p>Returned for revision.</p>}</td>
        <td>{canProgress && ["ACCEPTED", "IN_PROGRESS"].includes(action.state) &&
          <button type="button" disabled={Boolean(busy)} onClick={() => { setActiveId(activeId === action.id ? null : action.id); setNote(action.completion_note || ""); setProof(action.evidence_references.join("\n")); }}>Record progress</button>}
          {activeId === action.id && canProgress && <div className="car-rca-action-progress">
            <label className="car-rca-field">Completion declaration<textarea value={note} disabled={Boolean(busy)} onChange={e => setNote(e.target.value)} rows={2}/></label>
            <label className="car-rca-field">Evidence references, one per line<textarea value={proof} disabled={Boolean(busy)} onChange={e => setProof(e.target.value)} rows={2}/></label>
            <button type="button" disabled={Boolean(busy)} onClick={() => void progress(action.id, "IN_PROGRESS")}>Save in progress</button>
            <button type="button" disabled={Boolean(busy) || !note.trim() || !proof.trim()} onClick={() => void progress(action.id, "SUBMITTED")}>Submit implementation evidence</button>
          </div>}</td>
      </tr>)}</tbody></table></div> : <p>No individually tracked actions yet. An accountable corrective action is required for a new governed CAR.</p>}
    {!disabled && <div className="car-rca-analysis">
      <h4>{editingActionId ? "Revise proposed action" : "New accountable action"}</h4>
      <div className="car-rca-grid">
        <label>Action category<select value={draft.kind} onChange={e => setDraft(d => ({ ...d, kind: e.target.value as CarRcaActionCreate["kind"] }))}>
          <option value="CORRECTIVE">Corrective — remove a cause</option>
          <option value="PREVENTIVE">Preventive / systemic control</option>
          <option value="CONTAINMENT">Containment — immediate correction</option>
        </select></label>
        <label>Responsible person<input value={draft.external_owner_name || ""} onChange={e => setDraft(d => ({ ...d, external_owner_name: e.target.value }))} placeholder="Full name / authorized provider representative" /></label>
        <label>Target date<input type="date" value={draft.target_date || ""} onChange={e => setDraft(d => ({ ...d, target_date: e.target.value || null }))}/></label>
        <label>Priority<select value={draft.priority} onChange={e => setDraft(d => ({ ...d, priority: e.target.value as CarRcaActionCreate["priority"] }))}>
          {(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const).map(x => <option key={x}>{x}</option>)}</select></label>
        <div className="car-rca-field"><strong>Causes addressed (multiple allowed)</strong>
          {causeIds.length ? causeIds.map(cause => <label className="car-rca-check" key={cause.id}>
            <input type="checkbox" checked={draft.cause_node_ids.includes(cause.id)}
              onChange={e => setDraft(d => ({ ...d, cause_node_ids: e.target.checked
                ? [...d.cause_node_ids, cause.id] : d.cause_node_ids.filter(id => id !== cause.id) }))}/>
            {cause.statement}</label>) : <span>No supported causes recorded yet.</span>}
        </div>
      </div>
      <label className="car-rca-field">What specifically changes?<textarea value={draft.description} maxLength={8000} rows={3} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}/></label>
      <label className="car-rca-field">Supporting evidence references (one per line)<textarea value={draft.evidence_references.join("\n")} rows={2}
        onChange={e => setDraft(d => ({ ...d, evidence_references: e.target.value.split("\n").map(s => s.trim()).filter(Boolean) }))}/></label>
      <button type="button" disabled={Boolean(busy) || draft.description.trim().length < 5 || !draft.external_owner_name?.trim() || !draft.target_date} onClick={() => void create()}>
        {busy === "create" ? "Saving action…" : editingActionId ? "Save revised action" : "Add corrective action"}
      </button>
      {editingActionId && <button type="button" disabled={Boolean(busy)} onClick={() => { setEditingActionId(null); setDraft(EMPTY); }}>Cancel revision</button>}
    </div>}
  </section>;
}
