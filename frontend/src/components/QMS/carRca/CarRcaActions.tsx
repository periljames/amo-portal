import { useState } from "react";
import type { CarRcaAction, CarRcaActionCreate } from "../../../services/qmsCarRca";
import { addCarRcaInviteAction, progressCarRcaInviteAction } from "../../../services/qmsCarRca";

const EMPTY: CarRcaActionCreate = {
  kind: "CORRECTIVE", description: "", cause_node_ids: [], evidence_references: [],
  external_owner_name: null, target_date: null, priority: "MEDIUM",
};

export default function CarRcaActions({ token, actions, disabled, onChanged, causeIds }: {
  token: string;
  actions: CarRcaAction[];
  disabled: boolean;
  onChanged: () => Promise<void>;
  causeIds: Array<{ id: string; statement: string }>;
}) {
  const [draft, setDraft] = useState<CarRcaActionCreate>(EMPTY);
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
      await addCarRcaInviteAction(token, {
        ...draft,
        description: draft.description.trim(), external_owner_name: draft.external_owner_name?.trim(),
      });
      setDraft(EMPTY); await onChanged(); setMessage("Corrective action recorded for Quality review.");
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
          {action.cause_node_ids.length > 0 && <small>Causes: {action.cause_node_ids.join(", ")}</small>}</td>
        <td>{action.external_owner_name || "Not assigned"}</td><td>{action.target_date || "Not set"}</td>
        <td>{action.state.replaceAll("_", " ")}{action.quality_review_note && <p>Quality: {action.quality_review_note}</p>}</td>
        <td>{!disabled && ["PROPOSED", "ACCEPTED", "IN_PROGRESS", "REJECTED"].includes(action.state) &&
          <button type="button" disabled={Boolean(busy)} onClick={() => { setActiveId(activeId === action.id ? null : action.id); setNote(action.completion_note || ""); setProof(action.evidence_references.join("\n")); }}>Record progress</button>}
          {activeId === action.id && <div className="car-rca-action-progress">
            <label className="car-rca-field">Completion declaration<textarea value={note} disabled={Boolean(busy)} onChange={e => setNote(e.target.value)} rows={2}/></label>
            <label className="car-rca-field">Evidence references, one per line<textarea value={proof} disabled={Boolean(busy)} onChange={e => setProof(e.target.value)} rows={2}/></label>
            <button type="button" disabled={Boolean(busy)} onClick={() => void progress(action.id, "IN_PROGRESS")}>Save in progress</button>
            <button type="button" disabled={Boolean(busy) || !note.trim() || !proof.trim()} onClick={() => void progress(action.id, "SUBMITTED")}>Submit implementation evidence</button>
          </div>}</td>
      </tr>)}</tbody></table></div> : <p>No individually tracked actions yet. Add a specific, owned action below.</p>}
    {!disabled && <div className="car-rca-analysis">
      <h4>New accountable action</h4>
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
        <label>Cause addressed<select value={draft.cause_node_ids[0] || ""} onChange={e => setDraft(d => ({ ...d, cause_node_ids: e.target.value ? [e.target.value] : [] }))}>
          <option value="">General or preventive action</option>{causeIds.map(x => <option key={x.id} value={x.id}>{x.statement.slice(0, 100)}</option>)}
        </select></label>
      </div>
      <label className="car-rca-field">What specifically changes?<textarea value={draft.description} maxLength={8000} rows={3} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}/></label>
      <label className="car-rca-field">Supporting evidence references (one per line)<textarea value={draft.evidence_references.join("\n")} rows={2}
        onChange={e => setDraft(d => ({ ...d, evidence_references: e.target.value.split("\n").map(s => s.trim()).filter(Boolean) }))}/></label>
      <button type="button" disabled={Boolean(busy) || draft.description.trim().length < 5 || !draft.external_owner_name?.trim() || !draft.target_date} onClick={() => void create()}>
        {busy === "create" ? "Saving action…" : "Add corrective action"}
      </button>
    </div>}
  </section>;
}
