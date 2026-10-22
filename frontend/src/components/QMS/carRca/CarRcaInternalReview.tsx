import { useEffect, useState } from "react";
import CarRcaWorkbench from "./CarRcaWorkbench";
import { emptyCarRca, getCarRcaInternal, reviewCarRcaAction, type CarRcaProjection, type CarRcaAction } from "../../../services/qmsCarRca";
import "./car-rca.css";

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
  const load = async () => {
    setError(null);
    try { setData(await getCarRcaInternal(amoCode, carId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load investigation."); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    let active = true;
    setLoading(true);
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
  return <section className="case-section car-rca-internal" aria-label="Structured CAR investigation and Quality action review">
    <h3>Structured investigation and corrective action assurance</h3>
    {loading && <p role="status">Loading documented investigation…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => void load()}>Retry</button></p>}
    {data && <>
      <p>Investigation revision {data.revision}. Submitted revision: {data.submitted_revision ?? "not yet submitted"}.
        {data.submitted_at ? ` Submitted ${new Date(data.submitted_at).toLocaleString()}.` : ""}
        Proposed causes are not automatically accepted by Quality.</p>
      {data.revision ? <CarRcaWorkbench
        value={data.submitted_snapshot?.investigation || data.draft.investigation}
        disabled onChange={() => undefined} onSave={() => undefined}
        saveState="Controlled record — reviewer read only" /> :
        <p>Only legacy free-text RCA is available for this CAR. No new structured analysis has been recorded.</p>}
      <div className="car-rca-table-scroll"><table>
        <caption>Individually governed corrective and preventive actions — {data.actions.length}</caption>
        <thead><tr><th>Action</th><th>Owner / due</th><th>Status</th><th>Evidence</th><th>Quality decision</th></tr></thead>
        <tbody>{data.actions.map(action => <tr key={action.id}>
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
      </table></div>
      {data.action_events.length > 0 && <details>
        <summary>Attributable action implementation and Quality decisions ({data.action_events.length})</summary>
        <ol>{data.action_events.map(event => <li key={event.id}>
          <strong>{event.previous_state || "NEW"} → {event.next_state}</strong>
          <p>{event.actor_kind}: {event.actor_ref || "Unattributed"} · {new Date(event.created_at).toLocaleString()}</p>
          <p>{event.reason}</p>
        </li>)}</ol>
      </details>}
      {data.history.length > 0 && <details>
        <summary>Attributed investigation revisions ({data.history.length})</summary>
        <ol>{data.history.map(event => <li key={event.id}><strong>{event.event_type} · r{event.revision}</strong>
          <p>{event.actor_kind}: {event.actor_ref || "unattributed"} · {new Date(event.created_at).toLocaleString()}</p>
          <p>{event.reason}</p></li>)}</ol>
      </details>}
    </>}
  </section>;
}
