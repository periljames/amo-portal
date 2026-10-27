import { useEffect, useState } from "react";
import CarRcaWorkbench from "./CarRcaWorkbench";
import { getCarRcaInternal, reviewCarRcaAction, addCarRcaInternalAction, type CarRcaProjection, type CarRcaAction, type CarRcaActionCreate } from "../../../services/qmsCarRca";
import "./car-rca.css";
import CarRcaParetoSource from "./CarRcaParetoSource";
import { hasQmsRolePermission } from "../../../app/routeGuards";

export default function CarRcaInternalReview({ amoCode, carId, canReview }: {
  amoCode: string;
  carId: string;
  canReview: boolean;
}) {
  const [data, setData] = useState<CarRcaProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const [newAction, setNewAction] = useState<CarRcaActionCreate>({
    kind: "CORRECTIVE", description: "", cause_node_ids: [],
    evidence_references: [], external_owner_name: null, target_date: null,
    priority: "MEDIUM",
  });
  const submitInternalAction = async () => {
    if (busy || creating || newAction.description.trim().length < 5) return;
    setCreating(true); setError(null);
    try {
      await addCarRcaInternalAction(amoCode, carId, {
        ...newAction, description: newAction.description.trim(),
        external_owner_name: newAction.external_owner_name?.trim() || null,
      });
      setNewAction({ kind: "CORRECTIVE", description: "", cause_node_ids: [], evidence_references: [],
        external_owner_name: null, target_date: null, priority: "MEDIUM" });
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create a controlled CAR action."); }
    finally { setCreating(false); }
  };
  const load = async () => {
    setError(null);
    try { setData(await getCarRcaInternal(amoCode, carId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load investigation."); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    let active = true;
    setLoading(true);
    setData(null);
    setNotes({});
    setError(null);
    void getCarRcaInternal(amoCode, carId)
      .then(result => { if (active) setData(result); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Could not load investigation."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [amoCode, carId]);

  const review = async (action: CarRcaAction, state: "ACCEPTED" | "REJECTED" | "VERIFIED") => {
    if (busy) return;
    const reason = (notes[action.id] || "").trim();
    if (reason.length < 8) { setError("Enter a Quality decision reason of at least eight characters."); return; }
    setBusy(action.id); setError(null);
    try {
      await reviewCarRcaAction(amoCode, carId, action.id, state, reason);
      setNotes(value => ({ ...value, [action.id]: "" }));
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Quality review could not be saved."); }
    finally { setBusy(null); }
  };
  // A newly issued CAR may not yet have an RCA document, and older
  // API/mocked responses may omit newly added projection fields.
  // Keep the record readable without treating a partial response as an
  // approved investigation or silently substituting a fabricated RCA.
  const investigation = data?.submitted_snapshot?.investigation ?? data?.draft?.investigation;
  const causes = (investigation?.investigations ?? []).flatMap(method => method.nodes ?? [])
    .filter(node => node.entry_type === "CAUSAL_CONCLUSION");
  const actions = data?.actions ?? [];
  const retained = data?.retained_responses ?? [];
  const events = data?.action_events ?? [];
  const revisions = data?.history ?? [];

  return <section className="case-section car-rca car-rca-internal" aria-label="Structured CAR investigation and Quality action review">
    <h3>Investigation & action review</h3>
    {loading && <p role="status">Loading documented investigation…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => void load()}>Retry</button></p>}
    {data && <>
      <p>Revision {data.revision} · {data.submitted_revision == null ? "Not submitted" : `Submitted revision ${data.submitted_revision}`}
        {data.submitted_at ? ` · ${new Date(data.submitted_at).toLocaleString()}` : ""}</p>
      {data.revision && investigation ? <details>
        <summary>View structured investigation · revision {data.submitted_revision ?? data.revision}</summary>
        <CarRcaWorkbench
        value={investigation}
        disabled onChange={() => undefined} onSave={() => undefined}
        saveState="Controlled record — reviewer read only" /></details> :
        <p>No structured investigation recorded. Existing narrative responses remain above.</p>}
      {hasQmsRolePermission("qms.reports.view") && <details>
        <summary>Source frequency analysis</summary>
        <CarRcaParetoSource amoCode={amoCode} carId={carId}
          canSave={canReview && hasQmsRolePermission("qms.car.manage")} />
      </details>}
      {canReview && hasQmsRolePermission("qms.car.manage") && <details>
        <summary>Add a Quality-managed action</summary>
        <div className="car-rca" aria-label="Create an internal governed corrective action">
        <h4>Record a Quality-managed corrective action</h4>
        <p>This supplements the auditee's plan and retains an individual owner, deadline, causal linkage and independent review trail.</p>
        <div className="car-rca-grid">
          <label>Type<select value={newAction.kind} onChange={event => setNewAction(current => ({ ...current, kind: event.target.value as CarRcaActionCreate["kind"] }))}>
            <option value="CORRECTIVE">Corrective</option><option value="PREVENTIVE">Preventive</option><option value="CONTAINMENT">Containment</option>
          </select></label>
          <label>Responsible person's name<input value={newAction.external_owner_name || ""} onChange={event => setNewAction(current => ({ ...current, external_owner_name: event.target.value }))}/></label>
          <label>Target date<input type="date" value={newAction.target_date || ""} onChange={event => setNewAction(current => ({ ...current, target_date: event.target.value || null }))}/></label>
          <label>Priority<select value={newAction.priority} onChange={event => setNewAction(current => ({ ...current, priority: event.target.value as CarRcaActionCreate["priority"] }))}>
            {(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const).map(priority => <option key={priority}>{priority}</option>)}
          </select></label>
        </div>
        <label className="car-rca-field">Action description<textarea rows={3} maxLength={8000} value={newAction.description}
          onChange={event => setNewAction(current => ({ ...current, description: event.target.value }))}/></label>
        {causes.length > 0 &&
          <fieldset><legend>Documented causes addressed</legend>
            {causes.map(cause => <label key={cause.id} className="car-rca-check">
                <input type="checkbox" checked={newAction.cause_node_ids.includes(cause.id)}
                  onChange={event => setNewAction(current => ({
                    ...current, cause_node_ids: event.target.checked
                      ? [...current.cause_node_ids, cause.id] : current.cause_node_ids.filter(id => id !== cause.id),
                  }))}/>{cause.statement}
              </label>)}</fieldset>}
        <label className="car-rca-field">Evidence references<textarea rows={2} value={newAction.evidence_references.join("\n")}
          onChange={event => setNewAction(current => ({ ...current, evidence_references: event.target.value.split("\n").map(value => value.trim()).filter(Boolean) }))}/></label>
        <button type="button" disabled={creating || Boolean(busy) || newAction.description.trim().length < 5 || !newAction.target_date || !newAction.external_owner_name?.trim()}
          onClick={() => void submitInternalAction()}>{creating ? "Recording…" : "Create governed action"}</button>
      </div></details>}
      {actions.length > 0 ? <div className="car-rca-table-scroll"><table>
        <caption>Individually governed corrective and preventive actions — {actions.length}</caption>
        <thead><tr><th>Action</th><th>Owner / due</th><th>Status</th><th>Evidence</th><th>Quality decision</th></tr></thead>
        <tbody>{actions.map(action => <tr key={action.id}>
          <td><strong>{action.action_number} · {action.kind}</strong><p>{action.description}</p></td>
          <td>{action.external_owner_name || action.owner_user_id || "Unassigned"}<p>{action.target_date || "No due date"}</p></td>
          <td>{action.state.replaceAll("_", " ")}{action.completion_note && <p>{action.completion_note}</p>}</td>
          <td>{action.evidence_references.length ? <ul>{action.evidence_references.map((source, index) => <li key={index}>{source}</li>)}</ul> : "No evidence referenced"}</td>
          <td>{action.quality_review_note && <p>Last decision: {action.quality_review_note}</p>}
            {canReview && (action.state === "PROPOSED" || action.state === "SUBMITTED") && <div className="car-rca-analysis">
              <label className="car-rca-field">Independent Quality rationale
                <textarea rows={2} value={notes[action.id] || ""} disabled={Boolean(busy)}
                  onChange={e => setNotes(value => ({ ...value, [action.id]: e.target.value }))} /></label>
              {action.state === "PROPOSED" && <button type="button" disabled={Boolean(busy) || (notes[action.id] || "").trim().length < 8}
                onClick={() => void review(action, "ACCEPTED")}>Approve proposed action</button>}
              {action.state === "SUBMITTED" && <button type="button" disabled={Boolean(busy) || !action.evidence_references.length || (notes[action.id] || "").trim().length < 8}
                onClick={() => void review(action, "VERIFIED")}>Verify implementation</button>}
              <button type="button" disabled={Boolean(busy) || (notes[action.id] || "").trim().length < 8}
                onClick={() => void review(action, "REJECTED")}>Return for rework</button>
            </div>}
          </td></tr>)}</tbody>
      </table></div> : <p>No individual actions recorded.</p>}
      {retained.length > 0 && <details>
        <summary>Retained recalled CAR responses ({retained.length})</summary>
        <p>These revisions remain in the audit history but are excluded from the active Quality review queue.</p>
        <ol>{retained.map(record => <li key={record.id}>
          <strong>Original submission: {record.submitted_at ? new Date(record.submitted_at).toLocaleString() : "Unknown date"}</strong>
          <p>{record.reason}</p>
          <details><summary>View retained original fields</summary>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(record.snapshot, null, 2)}</pre>
          </details>
        </li>)}</ol>
      </details>}
      {events.length > 0 && <details>
        <summary>Attributable action implementation and Quality decisions ({events.length})</summary>
        <ol>{events.map(event => <li key={event.id}>
          <strong>{event.previous_state || "NEW"} → {event.next_state}</strong>
          <p>{event.actor_kind}: {event.actor_ref || "Unattributed"} · {new Date(event.created_at).toLocaleString()}</p>
          <p>{event.reason}</p>
        </li>)}</ol>
      </details>}
      {revisions.length > 0 && <details>
        <summary>Attributed investigation revisions ({revisions.length})</summary>
        <ol>{revisions.map(event => <li key={event.id}><strong>{event.event_type} · r{event.revision}</strong>
          <p>{event.actor_kind}: {event.actor_ref || "unattributed"} · {new Date(event.created_at).toLocaleString()}</p>
          <p>{event.reason}</p></li>)}</ol>
      </details>}
    </>}
  </section>;
}
