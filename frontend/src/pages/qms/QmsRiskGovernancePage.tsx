import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  acceptGovernedResidual, addGovernedRiskControl, addGovernedRiskTreatment,
  assessGovernedRisk, createGovernedRisk, getGovernedRiskMatrix,
  getRiskParticipants, listGovernedRisks, readGovernedRisk, reopenGovernedRisk,
  type GovernedRisk, type GovernedRiskMatrix, type RiskDetail, type RiskKind, type RiskParticipant,
} from "../../services/qmsRisk";
import "./qms-management-review.css";

function message(error: unknown) {
  return error instanceof Error ? error.message : "Could not verify the current governed risk record.";
}
function entries(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}
export default function QmsRiskGovernancePage() {
  const { amoCode = "" } = useParams();
  const [query, setQuery] = useSearchParams();
  const kind: RiskKind = query.get("kind") === "OPPORTUNITY" ? "OPPORTUNITY" : "RISK";
  const riskId = query.get("id") || "";
  const userId = getCachedUser()?.id || "";
  const [records, setRecords] = useState<GovernedRisk[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [matrix, setMatrix] = useState<GovernedRiskMatrix>({});
  const [people, setPeople] = useState<RiskParticipant[]>([]);
  const [detail, setDetail] = useState<RiskDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [sourceSystem, setSourceSystem] = useState<"QUALITY" | "SMS_LINKED">("QUALITY");
  const [sourceReference, setSourceReference] = useState("");
  const [assessmentType, setAssessmentType] = useState<"INITIAL" | "RESIDUAL">("INITIAL");
  const [likelihood, setLikelihood] = useState("");
  const [consequence, setConsequence] = useState("");
  const [rating, setRating] = useState("");
  const [basis, setBasis] = useState("");
  const [evidence, setEvidence] = useState("");
  const [controlTitle, setControlTitle] = useState("");
  const [controlDescription, setControlDescription] = useState("");
  const [measure, setMeasure] = useState("");
  const [treatmentTitle, setTreatmentTitle] = useState("");
  const [treatmentDescription, setTreatmentDescription] = useState("");
  const [treatmentOwner, setTreatmentOwner] = useState("");
  const [treatmentDue, setTreatmentDue] = useState("");
  const [acceptReason, setAcceptReason] = useState("");
  const [reassessReason, setReassessReason] = useState("");
  const [reassessDate, setReassessDate] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [list, policy, participants, selected] = await Promise.all([
      listGovernedRisks(amoCode, kind, offset),
      getGovernedRiskMatrix(amoCode),
      getRiskParticipants(amoCode),
      riskId ? readGovernedRisk(amoCode, kind, riskId) : Promise.resolve(null),
    ]);
    setRecords(list.items);
    setTotal(list.total);
    setMatrix(policy.matrix || {});
    setPeople(participants.items);
    setDetail(selected);
  }, [amoCode, kind, riskId, offset]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    refresh().catch((failure) => { if (active) setError(message(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  const run = async (fn: () => Promise<unknown>, text = "Recorded in the governed risk history.") => {
    if (busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await fn();
      await refresh();
      setSuccess(text);
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  };
  const choose = (newKind: RiskKind, id = "") => {
    setOffset(0);
    setQuery((previous) => {
      const next = new URLSearchParams(previous);
      next.set("kind", newKind);
      if (id) next.set("id", id); else next.delete("id");
      return next;
    });
  };
  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run(async () => {
      const result = await createGovernedRisk(amoCode, {
        kind, title: title.trim(), description: description.trim(),
        owner_user_id: owner, reassess_by: due, source_system: sourceSystem,
        source_reference: sourceReference.trim() || undefined,
      });
      choose(kind, result.record.id);
      setTitle(""); setDescription(""); setOwner(""); setDue("");
    }, "Risk or opportunity identified. Add a governed assessment and treatment.");
  };

  const row = detail?.record;
  const version = row?.payload.version || 0;
  const act = (type: "controls" | "actions", fields: Record<string, unknown>) => {
    if (!row) return;
    void run(() => type === "controls"
      ? addGovernedRiskControl(amoCode, kind, row.id, { ...fields, expected_version: version })
      : addGovernedRiskTreatment(amoCode, kind, row.id, { ...fields, expected_version: version }));
  };
  const assessed = row?.status === "ASSESSED" || row?.status === "TREATING" || row?.status === "RESIDUAL_PENDING";
  const last = row?.payload.assessment_history?.at(-1);
  const matrixReady = Boolean(matrix.version && matrix.likelihood_levels?.length && matrix.consequence_levels?.length && matrix.rating_levels?.length);
  const editable = row && !["ACCEPTED", "CLOSED"].includes(row.status);
  const assignedToMe = row?.owner_user_id === userId;

  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-review">
      <header className="qms-review__header"><div><p>QUALITY GOVERNANCE</p><h1>Risk and Opportunities</h1>
        <span>Evidence-based assessment, accountable treatment and independent residual-risk acceptance.</span>
      </div></header>
      {error ? <div className="qms-review__error" role="alert">{error} <button type="button" disabled={busy} onClick={() => void refresh()}>Reload</button></div> : null}
      {success ? <p role="status" className="qms-review__success">{success}</p> : null}
      {!matrixReady ? <div role="status" className="qms-review__panel">The tenant does not have a supported, versioned risk matrix. Risk identification remains available; assessments are blocked until Quality configures likelihood, consequence and rating levels in governed QMS settings. No default scores or acceptance thresholds will be invented.</div> : null}
      <div className="qms-review__grid">
        <div>
          <section className="qms-review__panel">
            <h2>Governed register</h2>
            <div className="qms-review__pager">
              <button type="button" aria-pressed={kind === "RISK"} onClick={() => choose("RISK")}>Risks</button>
              <button type="button" aria-pressed={kind === "OPPORTUNITY"} onClick={() => choose("OPPORTUNITY")}>Opportunities</button>
            </div>
            {loading ? <p role="status">Loading current records…</p> : null}
            <div className="qms-review__meeting-list">{records.map((item) => <button
              type="button" key={item.id} aria-current={riskId === item.id ? "true" : undefined}
              onClick={() => choose(kind, item.id)} className={riskId === item.id ? "selected" : ""}>
                <strong>{item.title}</strong><small>{item.status} · Reassess {item.due_date || "date not set"}</small>
              </button>)}</div>
            <div className="qms-review__pager">
              <button type="button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
              <span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} of {total}</span>
              <button type="button" disabled={offset + 25 >= total || busy} onClick={() => setOffset(offset + 25)}>Next</button>
            </div>
          </section>
          <form className="qms-review__panel qms-review__form" onSubmit={create}>
            <h3>Identify {kind === "RISK" ? "a risk" : "an opportunity"}</h3>
            <label>Title<input required minLength={4} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
            <label>Situation / consequence<textarea required minLength={12} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            <label>Accountable owner<select required value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Choose user</option>
              {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
            </select></label>
            <label>Reassessment due<input type="date" required value={due} onChange={(e) => setDue(e.target.value)} /></label>
            <label>Source authority<select value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value as "QUALITY" | "SMS_LINKED")}>
              <option value="QUALITY">Quality-owned assessment</option><option value="SMS_LINKED">Link to SMS-owned source (do not duplicate)</option>
            </select></label>
            <label>Source reference<input value={sourceReference} required={sourceSystem === "SMS_LINKED"} onChange={(e) => setSourceReference(e.target.value)} /></label>
            <button type="submit" disabled={busy || !owner}>Create identified record</button>
          </form>
        </div>
        <div>
          {!row ? <section className="qms-review__panel"><h2>Select a risk or opportunity</h2><p>Choose a record to conduct an assessment, document controls, assign treatment and record residual acceptance.</p></section> : <>
            <section className="qms-review__panel">
              <h2>{row.title}</h2><p>{row.description}</p>
              <p>Status: <strong>{row.status}</strong> · Version {version} · Owner {people.find((p) => p.id === row.owner_user_id)?.name || row.owner_user_id}</p>
              <p>Source: {row.payload.source_system || "Not linked"} {row.payload.source_reference || ""}</p>
              <h3>Assessment history</h3>
              {row.payload.assessment_history?.length ? <ol>{row.payload.assessment_history.map((item, i) =>
                <li key={i}><strong>{item.type}</strong>: {item.rating} (Likelihood {item.likelihood}, consequence {item.consequence})
                  <p>{item.basis}</p><small>Matrix {item.matrix_version} · by {item.actor_user_id}</small></li>
              )}</ol> : <p>Not yet assessed.</p>}
              {row.status === "ACCEPTED" ? <p>Residual accepted by {row.payload.accepted_by}: {row.payload.acceptance_reason}</p> : null}
            </section>
            <div className="qms-review__record-grid">
              {(["controls", "actions"] as const).map((name) => <section key={name} className="qms-review__records"><h3>{name === "controls" ? "Controls" : "Treatment actions"}</h3>
                {!detail?.[name].length ? <p>None recorded.</p> : detail[name].map((item) => <article key={item.id}>
                  <strong>{item.title}</strong><p>{item.description}</p><small>{item.status} · {item.due_date || "No date"}</small>
                </article>)}
              </section>)}
            </div>
            {editable ? <>
              <form className="qms-review__panel qms-review__form" onSubmit={(e) => {e.preventDefault(); void run(() =>
                assessGovernedRisk(amoCode, kind, row.id, {
                  expected_version: version, assessment_type: assessmentType,
                  matrix_version: matrix.version || "", likelihood, consequence, rating,
                  evidence_basis: basis.trim(), evidence_record_ids: entries(evidence),
                }), "Recorded the human assessment with its matrix version.");}}>
                <h3>Governed assessment</h3>
                <p>Active tenant matrix: {matrix.version || "Not configured"}</p>
                <label>Assessment stage<select value={assessmentType} onChange={(e) => setAssessmentType(e.target.value as "INITIAL" | "RESIDUAL")}>
                  <option value="INITIAL">Initial</option><option value="RESIDUAL">Residual after controls</option>
                </select></label>
                <label>Likelihood<select required value={likelihood} onChange={(e) => setLikelihood(e.target.value)}>
                  <option value="">Choose matrix level</option>{(matrix.likelihood_levels || []).map((item) => <option key={item} value={item}>{item}</option>)}
                </select></label>
                <label>Consequence<select required value={consequence} onChange={(e) => setConsequence(e.target.value)}>
                  <option value="">Choose matrix level</option>{(matrix.consequence_levels || []).map((item) => <option key={item} value={item}>{item}</option>)}
                </select></label>
                <label>Rating selected under tenant methodology<select required value={rating} onChange={(e) => setRating(e.target.value)}>
                  <option value="">Choose rating</option>{(matrix.rating_levels || []).map((item) => <option key={item} value={item}>{item}</option>)}
                </select></label>
                <label>Evidence and assessment rationale<textarea minLength={12} required value={basis} onChange={(e) => setBasis(e.target.value)} /></label>
                <label>Evidence record IDs (optional, one per line)<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
                <button type="submit" disabled={busy || !matrixReady}>Retain {assessmentType.toLowerCase()} assessment</button>
              </form>
              <div className="qms-review__forms qms-review__panel">
                <form className="qms-review__form" onSubmit={(e) => {e.preventDefault(); act("controls", {
                  title: controlTitle.trim(), description: controlDescription.trim(), effectiveness_measure: measure.trim(),
                });}}>
                  <h3>Document an active control</h3>
                  <label>Control name<input minLength={4} required value={controlTitle} onChange={(e) => setControlTitle(e.target.value)} /></label>
                  <label>Control description<textarea minLength={8} required value={controlDescription} onChange={(e) => setControlDescription(e.target.value)} /></label>
                  <label>Effectiveness measurement<textarea minLength={8} required value={measure} onChange={(e) => setMeasure(e.target.value)} /></label>
                  <button type="submit" disabled={busy}>Record control</button>
                </form>
                <form className="qms-review__form" onSubmit={(e) => {e.preventDefault(); act("actions", {
                  title: treatmentTitle.trim(), description: treatmentDescription.trim(),
                  owner_user_id: treatmentOwner, due_date: treatmentDue,
                });}}>
                  <h3>Assign treatment</h3>
                  <label>Action title<input minLength={4} required value={treatmentTitle} onChange={(e) => setTreatmentTitle(e.target.value)} /></label>
                  <label>Required action<textarea minLength={8} required value={treatmentDescription} onChange={(e) => setTreatmentDescription(e.target.value)} /></label>
                  <label>Owner<select required value={treatmentOwner} onChange={(e) => setTreatmentOwner(e.target.value)}>
                    <option value="">Choose accountable person</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
                  </select></label>
                  <label>Due date<input type="date" required value={treatmentDue} onChange={(e) => setTreatmentDue(e.target.value)} /></label>
                  <button type="submit" disabled={busy || !assessed || !treatmentOwner}>Assign treatment</button>
                </form>
              </div>
              {row.status === "RESIDUAL_PENDING" ? <form className="qms-review__form qms-review__panel" onSubmit={(e) => {
                e.preventDefault(); void run(() => acceptGovernedResidual(amoCode, kind, row.id, {
                  expected_version: version, reason: acceptReason.trim(), acceptance_evidence_ids: entries(evidence),
                }), "Independently recorded residual-risk acceptance.");
              }}>
                <h3>Independent residual-risk decision</h3>
                <p>Most recent assessment: {last?.rating} on matrix {last?.matrix_version}</p>
                <label>Recorded acceptance rationale<textarea required minLength={16} value={acceptReason} onChange={(e) => setAcceptReason(e.target.value)} /></label>
                <label>Acceptance evidence IDs (one per line)<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
                <button type="submit" disabled={busy || assignedToMe || !entries(evidence).length || acceptReason.trim().length < 16}>
                  Accept residual risk independently</button>
                {assignedToMe ? <p>The risk owner cannot self-approve residual acceptance.</p> : null}
              </form> : null}
            </> : null}
            {["ACCEPTED", "RESIDUAL_PENDING", "ASSESSED", "TREATING"].includes(row.status) ? <form className="qms-review__form qms-review__panel" onSubmit={(e) => {
              e.preventDefault(); void run(() => reopenGovernedRisk(amoCode, kind, row.id, {
                expected_version: version, reason: reassessReason.trim(), reassess_by: reassessDate,
              }), "Reassessment reopened with accountable due date.");
            }}>
              <h3>Governed reassessment</h3>
              <label>Reason for reconsideration<textarea required minLength={12} value={reassessReason} onChange={(e) => setReassessReason(e.target.value)} /></label>
              <label>Next due date<input required type="date" value={reassessDate} onChange={(e) => setReassessDate(e.target.value)} /></label>
              <button type="submit" disabled={busy}>Reopen for reassessment</button>
            </form> : null}
          </>}
        </div>
      </div>
    </main>
  </DepartmentLayout>;
}
