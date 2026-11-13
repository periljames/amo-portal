import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  createGovernedProcess, decideGovernedProcess, getProcessParticipants,
  listGovernedProcesses, readGovernedProcess, submitProcessPerformance, verifyProcessPerformance,
  type QmsObjective, type QmsProcess, type ProcessDetail, type ProcessMetricDefinition, type ProcessPerson,
} from "../../services/qmsProcessGovernance";
import "./qms-management-review.css";

const err = (failure: unknown) => failure instanceof Error ? failure.message : "Unable to verify this process.";
const lines = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);
const blankMetric: ProcessMetricDefinition = { code: "", title: "", measure: "", target: "", direction: "AT_LEAST", unit: "" };

export default function QmsProcessGovernancePage() {
  const { amoCode = "" } = useParams();
  const myId = getCachedUser()?.id || "";
  const [query, setQuery] = useSearchParams();
  const processId = query.get("process") || "";
  const [records, setRecords] = useState<QmsProcess[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [people, setPeople] = useState<ProcessPerson[]>([]);
  const [detail, setDetail] = useState<ProcessDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [scope, setScope] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [reviewDue, setReviewDue] = useState("");
  const [metric, setMetric] = useState<ProcessMetricDefinition>(blankMetric);
  const [metrics, setMetrics] = useState<ProcessMetricDefinition[]>([]);
  const [decisionReason, setDecisionReason] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [measurement, setMeasurement] = useState<Record<string, string>>({});
  const [measureBasis, setMeasureBasis] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState("");
  const [verifierReason, setVerifierReason] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [followupOwner, setFollowupOwner] = useState("");
  const [followupDue, setFollowupDue] = useState("");
  const [followupAction, setFollowupAction] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [list, participants, current] = await Promise.all([
      listGovernedProcesses(amoCode, offset), getProcessParticipants(amoCode),
      processId ? readGovernedProcess(amoCode, processId) : Promise.resolve(null),
    ]);
    setRecords(list.items); setTotal(list.total);
    setPeople(participants.items); setDetail(current);
  }, [amoCode, offset, processId]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    refresh().catch((failure: unknown) => { if (active) setError(err(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  const run = async (action: () => Promise<unknown>, message: string) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(message); }
    catch (failure) { setError(err(failure)); }
    finally { setBusy(false); }
  };
  const choose = (id: string) => setQuery((previous) => {
    const next = new URLSearchParams(previous);
    if (id) next.set("process", id); else next.delete("process");
    return next;
  });
  const create = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const response = await createGovernedProcess(amoCode, {
        title: title.trim(), scope: scope.trim(), owner_user_id: ownerId,
        process_purpose: purpose.trim(), review_due: reviewDue,
        metrics: metrics.map((item) => ({ ...item, target: item.target })),
      });
      choose(response.process.id);
    }, "Controlled process draft and metric definitions recorded.");
  };
  const addMetric = () => {
    if (!metric.code || !metric.title || !metric.measure || !metric.target || !metric.unit) {
      setError("Complete the metric fields before adding this objective."); return;
    }
    if (metrics.some((item) => item.code === metric.code)) {
      setError("Metric codes must be unique within this process."); return;
    }
    setError("");
    setMetrics((current) => [...current, metric]);
    setMetric(blankMetric);
  };
  const submitPerformance = (event: FormEvent) => {
    event.preventDefault();
    if (!detail) return;
    void run(() => submitProcessPerformance(amoCode, detail.process.id, {
      expected_version: detail.process.payload.version,
      reason: decisionReason.trim(),
      period_start: periodStart, period_end: periodEnd,
      evidence_ids: lines(evidence),
      measures: detail.objectives.map((obj) => ({
        objective_id: obj.id, actual: measurement[obj.id] || "",
        explanation: measureBasis[obj.id] || "",
      })),
    }), "Measured objectives submitted for an independent verification.");
  };
  const process = detail?.process;
  const canApprove = process?.status === "PENDING_APPROVAL" &&
    myId !== process.owner_user_id && myId !== process.created_by;
  const canSubmit = process?.status === "ACTIVE" && myId === process.owner_user_id;
  const displayMeasure = (item: QmsObjective) => item.payload.code + " · " + item.title;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-review">
      <header className="qms-review__header"><div><p>QUALITY SYSTEM GOVERNANCE</p><h1>Process Management</h1>
        <span>Owned processes, versioned objectives, attributable performance measurement and independent review.</span>
      </div>{processId ? <button type="button" onClick={() => choose("")}>Back to processes</button> : null}</header>
      {error ? <div className="qms-review__error" role="alert">{error}
        <button type="button" disabled={busy} onClick={() => void refresh().catch((failure: unknown) => setError(err(failure)))}>Refresh</button></div> : null}
      {notice ? <p role="status" className="qms-review__success">{notice}</p> : null}
      {loading ? <p role="status">Loading controlled process records…</p> : null}
      <div className="qms-review__grid">
        <section className="qms-review__panel">
          <h2>Process register <small>{total}</small></h2>
          <div className="qms-review__meeting-list">{records.map((item) =>
            <button key={item.id} type="button" onClick={() => choose(item.id)}
              className={item.id === processId ? "selected" : ""}
              aria-current={item.id === processId ? "true" : undefined}>
              <strong>{item.title}</strong><small>{item.status} · Review due {item.due_date || "not set"}</small>
            </button>)}</div>
          <div className="qms-review__pager">
            <button type="button" disabled={offset === 0 || busy} onClick={() => setOffset((v) => Math.max(0, v - 25))}>Previous</button>
            <span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} of {total}</span>
            <button type="button" disabled={offset + 25 >= total || busy} onClick={() => setOffset((v) => v + 25)}>Next</button>
          </div>
          <form className="qms-review__form" onSubmit={create}>
            <h3>Define a controlled process</h3>
            <label>Title<input minLength={4} required value={title} onChange={(e) => setTitle(e.target.value)} /></label>
            <label>Scope<textarea required minLength={12} value={scope} onChange={(e) => setScope(e.target.value)} /></label>
            <label>Purpose<textarea required minLength={8} value={purpose} onChange={(e) => setPurpose(e.target.value)} /></label>
            <label>Responsible owner<select required value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
              <option value="">Select active process owner</option>
              {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
            </select></label>
            <label>Next review due<input type="date" required value={reviewDue} onChange={(e) => setReviewDue(e.target.value)} /></label>
            <fieldset className="qms-review__form"><legend>Defined performance indicators</legend>
              {metrics.map((item) => <div key={item.code} className="qms-review__action">
                <strong>{item.code} · {item.title}</strong>
                <span>{item.direction} {item.target} {item.unit}</span>
                <button type="button" disabled={busy} onClick={() => setMetrics((current) => current.filter((v) => v.code !== item.code))}>Remove</button>
              </div>)}
              <label>Metric code<input value={metric.code} onChange={(e) => setMetric((v) => ({ ...v, code: e.target.value.toUpperCase() }))} placeholder="AUDIT_TIMELINESS" /></label>
              <label>Metric title<input value={metric.title} onChange={(e) => setMetric((v) => ({ ...v, title: e.target.value }))} /></label>
              <label>Measurement definition<textarea value={metric.measure} onChange={(e) => setMetric((v) => ({ ...v, measure: e.target.value }))} /></label>
              <label>Decision rule<select value={metric.direction} onChange={(e) => setMetric((v) => ({ ...v, direction: e.target.value as ProcessMetricDefinition["direction"] }))}>
                <option value="AT_LEAST">At least</option><option value="AT_MOST">At most</option><option value="EQUAL">Exactly</option>
              </select></label>
              <label>Target<input type="number" step="any" value={metric.target} onChange={(e) => setMetric((v) => ({ ...v, target: e.target.value }))} /></label>
              <label>Unit<input value={metric.unit} onChange={(e) => setMetric((v) => ({ ...v, unit: e.target.value }))} /></label>
              <button type="button" disabled={busy || metrics.length >= 20} onClick={addMetric}>Add metric</button>
            </fieldset>
            <button type="submit" disabled={busy || !ownerId || metrics.length === 0}>Create governed process</button>
          </form>
        </section>
        <div className="qms-review__detail">
          {!detail ? <section className="qms-review__panel"><h2>Select a process</h2>
            <p>Define an accountable process, approve its measurable objectives, then evaluate actual performance against retained evidence.</p></section> : <>
            <section className="qms-review__panel"><h2>{process?.title}</h2>
              <p>{process?.description}</p><p>Purpose: {process?.payload.purpose}</p>
              <p><strong>Status:</strong> {process?.status} · Version {process?.payload.version} · Owner {people.find((item) => item.id === process?.owner_user_id)?.name || process?.owner_user_id}</p>
              <h3>Measurable objectives</h3>
              <div className="qms-review__record-list">{detail.objectives.map((objective) => <article key={objective.id}>
                <strong>{displayMeasure(objective)}</strong><span>{objective.status}</span>
                <p>{objective.description}</p><small>Target: {objective.payload.direction} {objective.payload.target} {objective.payload.unit}</small>
              </article>)}</div>
            </section>
            {process?.status === "DRAFT" || canApprove ? <section className="qms-review__panel qms-review__form">
              <h3>Governed approval</h3>
              <label>Decision rationale<textarea required minLength={12} value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} /></label>
              {process?.status === "DRAFT" ? <button type="button" disabled={busy || decisionReason.trim().length < 12}
                onClick={() => void run(() => decideGovernedProcess(amoCode, process.id, "submit", process.payload.version, decisionReason), "Submitted for independent approval.")}>Submit process definition</button> : null}
              {canApprove && process ? <button type="button" disabled={busy || decisionReason.trim().length < 12}
                onClick={() => void run(() => decideGovernedProcess(amoCode, process.id, "approve", process.payload.version, decisionReason), "Controlled process approved.")}>Approve independently</button> : null}
            </section> : null}
            {canSubmit ? <section className="qms-review__panel qms-review__form">
              <h3>Record periodic process performance</h3>
              <Link to={"/maintenance/" + encodeURIComponent(amoCode) + "/quality/evidence-vault/search"}>Browse retained Quality evidence</Link>
              <form className="qms-review__form" onSubmit={submitPerformance}>
                <label>Review period start<input type="date" required value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} /></label>
                <label>Review period end<input type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} /></label>
                {detail.objectives.map((item) => <fieldset key={item.id} className="qms-review__form">
                  <legend>{displayMeasure(item)} · Target {item.payload.target} {item.payload.unit}</legend>
                  <label>Actual measured value<input type="number" step="any" required value={measurement[item.id] || ""}
                    onChange={(e) => setMeasurement((v) => ({ ...v, [item.id]: e.target.value }))} /></label>
                  <label>Measurement method and findings<textarea required minLength={8} value={measureBasis[item.id] || ""}
                    onChange={(e) => setMeasureBasis((v) => ({ ...v, [item.id]: e.target.value }))} /></label>
                </fieldset>)}
                <label>Retained evidence IDs (one per line)<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
                <label>Assessment reasoning<textarea required minLength={12} value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} /></label>
                <button type="submit" disabled={busy || lines(evidence).length === 0}>Submit performance for verification</button>
              </form>
            </section> : null}
            <section className="qms-review__panel"><h3>Performance reviews ({detail.reviews.length})</h3>
              {detail.reviews.map((review) => <article className="qms-review__records" key={review.id}>
                <h3>{review.period_start} – {review.period_end} · {review.status}</h3>
                <div className="qms-review__record-list">{review.measurements.map((measure) =>
                  <p key={measure.objective_id}><strong>{measure.code}</strong> · Actual {measure.actual} / target {measure.target} · {measure.target_met ? "Target met" : "Below/above target"}</p>)}</div>
                <p>{review.owner_reason}</p>
                {review.status === "PENDING_VERIFICATION" && review.owner_user_id !== myId ? <div className="qms-review__form">
                  <label>Reviewer justification<textarea required minLength={12} value={verifierReason} onChange={(e) => setVerifierReason(e.target.value)} /></label>
                  <label>Verification evidence IDs<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
                  <label>Next review due date<input type="date" value={nextDue} onChange={(e) => setNextDue(e.target.value)} /></label>
                  {review.measurements.some((item) => !item.target_met) ? <fieldset className="qms-review__form"><legend>Accountable corrective follow-up</legend>
                    <label>Assigned owner<select value={followupOwner} onChange={(e) => setFollowupOwner(e.target.value)}>
                      <option value="">Choose owner</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
                    </select></label>
                    <label>Due date<input type="date" value={followupDue} onChange={(e) => setFollowupDue(e.target.value)} /></label>
                    <label>Action statement<textarea minLength={12} value={followupAction} onChange={(e) => setFollowupAction(e.target.value)} /></label>
                  </fieldset> : null}
                  <button type="button" disabled={busy || verifierReason.trim().length < 12 || !nextDue || !lines(evidence).length ||
                    (review.measurements.some((item) => !item.target_met) && (!followupOwner || !followupDue || followupAction.trim().length < 12))}
                    onClick={() => void run(() => verifyProcessPerformance(amoCode, process!.id, review.id, {
                      accepted: true, reason: verifierReason, evidence_ids: lines(evidence), next_review_due: nextDue,
                      followup_owner_user_id: followupOwner || null, followup_due_date: followupDue || null,
                      followup_action: followupAction || null,
                    }), "Process performance independently verified and follow-up assigned where required.")}>Verify with accountable follow-up</button>
                  <button type="button" disabled={busy || verifierReason.trim().length < 12 || !lines(evidence).length}
                    onClick={() => void run(() => verifyProcessPerformance(amoCode, process!.id, review.id, {
                      accepted: false, reason: verifierReason, evidence_ids: lines(evidence),
                    }), "Performance report returned for rework.")}>Return for rework</button>
                </div> : null}
              </article>)}
            </section>
          </>}
        </div>
      </div>
    </main>
  </DepartmentLayout>;
}
