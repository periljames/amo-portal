import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  addQmsRiskControl, createQmsRisk, listQmsRiskEvidence, listQmsRiskOwners, listQmsRiskSources,
  listQmsRisks, readQmsRisk, transitionQmsRisk, verifyQmsRiskControl,
  type QmsRisk, type QmsRiskSourceType, type RiskControl, type RiskOption, type RiskOwner,
} from "../../services/qmsRiskWorkflow";
import "./qms-management-review.css";

const kinds: QmsRiskSourceType[] = ["AUDIT", "CAR", "FINDING", "PROCESS", "SUPPLIER"];
const errText = (error: unknown) => error instanceof Error ? error.message : "The request failed.";
type RiskDetail = { risk: QmsRisk; controls: RiskControl[] };
function SelectOption({ label, choices, value, onChange }: {
  label: string; choices: RiskOption[]; value: string; onChange: (value: string) => void;
}) {
  return <label>{label}<select required value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="">Select a verified record</option>
    {choices.map((choice) => <option key={choice.id} value={choice.id}>{choice.title}</option>)}
  </select></label>;
}
export default function QmsRiskWorkflowPage() {
  const { amoCode = "" } = useParams();
  const userId = getCachedUser()?.id || "";
  const [params, setParams] = useSearchParams();
  const riskId = params.get("risk") || "";
  const [page, setPage] = useState(0);
  const [list, setList] = useState<QmsRisk[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<RiskDetail | null>(null);
  const [owners, setOwners] = useState<RiskOwner[]>([]);
  const [sources, setSources] = useState<RiskOption[]>([]);
  const [evidenceItems, setEvidenceItems] = useState<RiskOption[]>([]);
  const [kind, setKind] = useState<QmsRiskSourceType>("AUDIT");
  const [sourceId, setSourceId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [consequence, setConsequence] = useState("");
  const [basis, setBasis] = useState("");
  const [likelihood, setLikelihood] = useState(3);
  const [severity, setSeverity] = useState(3);
  const [sms, setSms] = useState(false);
  const [controlTitle, setControlTitle] = useState("");
  const [controlDescription, setControlDescription] = useState("");
  const [controlOwner, setControlOwner] = useState("");
  const [controlDue, setControlDue] = useState("");
  const [controlOutcome, setControlOutcome] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [rationale, setRationale] = useState("");
  const [residualLikelihood, setResidualLikelihood] = useState(1);
  const [residualSeverity, setResidualSeverity] = useState(1);
  const [treatment, setTreatment] = useState("");
  const [policy, setPolicy] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [rows, users, files, current] = await Promise.all([
      listQmsRisks(amoCode, page * 25), listQmsRiskOwners(amoCode), listQmsRiskEvidence(amoCode),
      riskId ? readQmsRisk(amoCode, riskId) : Promise.resolve(null),
    ]);
    setList(rows.items); setTotal(rows.total); setOwners(users.items);
    setEvidenceItems(files.items); setDetail(current);
  }, [amoCode, page, riskId]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    refresh().catch((failure: unknown) => { if (active) setError(errText(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    setSourceId("");
    if (amoCode) listQmsRiskSources(amoCode, kind).then((result) => {
      if (active) setSources(result.items);
    }).catch((failure: unknown) => { if (active) setError(errText(failure)); });
    return () => { active = false; };
  }, [amoCode, kind]);

  const run = async (action: () => Promise<unknown>, message = "Governed record saved.") => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(message); }
    catch (failure) { setError(errText(failure)); }
    finally { setBusy(false); }
  };
  const chooseRisk = (id: string) => setParams((previous) => {
    const updated = new URLSearchParams(previous);
    if (id) updated.set("risk", id); else updated.delete("risk");
    return updated;
  });
  const create = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const result = await createQmsRisk(amoCode, {
        title: title.trim(), description: description.trim(), owner_user_id: ownerId,
        source_type: kind, source_id: sourceId, consequence: consequence.trim(),
        likelihood, severity, assessment_basis: basis.trim(),
        safety_boundary: sms ? "SMS_ESCALATION_REQUIRED" : "QUALITY_ONLY",
      });
      chooseRisk(result.risk.id);
    }, "Source-backed risk identified; treatment and independent acceptance remain outstanding.");
  };
  const risk = detail?.risk;
  const controls = detail?.controls || [];
  const version = risk?.payload.version ?? 0;
  const mayTreat = risk?.status === "DRAFT" || risk?.status === "TREATMENT";
  const canDecide = risk?.status === "PENDING_ACCEPTANCE" && risk.created_by !== userId && risk.owner_user_id !== userId;
  const action = (name: "reassess" | "submit-residual" | "decide-residual" | "monitor", fields: Record<string, unknown>, note: string) =>
    risk && void run(() => transitionQmsRisk(amoCode, risk.id, name, { expected_version: version, ...fields }), note);
  const evidenceSelector = <SelectOption label="Retained Quality evidence" choices={evidenceItems} value={evidenceId} onChange={setEvidenceId} />;

  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="qms-review">
    <header className="qms-review__header"><div>
      <p>QUALITY ASSURANCE · HUMAN DECISIONS · SMS BOUNDARY</p><h1>Risk and Opportunities</h1>
      <span>Identify sourced risks, verify treatment controls and obtain a documented residual decision.</span></div>
      {riskId ? <button type="button" onClick={() => chooseRisk("")}>Back to register</button> : null}
    </header>
    {error ? <div className="qms-review__error" role="alert">{error} <button type="button" disabled={busy}
      onClick={() => void refresh().catch((failure: unknown) => setError(errText(failure)))}>Refresh</button></div> : null}
    {notice ? <p role="status" className="qms-review__success">{notice}</p> : null}
    {loading ? <p role="status">Loading risk governance records…</p> : null}
    <div className="qms-review__grid">
      <section className="qms-review__panel">
        <h2>Current risk register <small>{total}</small></h2>
        <div className="qms-review__meeting-list">{list.map((row) => <button type="button" key={row.id}
          aria-current={row.id === riskId ? "true" : undefined} className={row.id === riskId ? "selected" : ""}
          onClick={() => chooseRisk(row.id)}><strong>{row.title}</strong>
          <small>{row.status} · Assessed score {row.payload.assessment.score}</small></button>)}</div>
        <div className="qms-review__pager">
          <button type="button" disabled={page === 0 || busy} onClick={() => setPage((v) => Math.max(0, v - 1))}>Previous</button>
          <span>{total ? page * 25 + 1 : 0}–{Math.min(total, (page + 1) * 25)} of {total}</span>
          <button type="button" disabled={(page + 1) * 25 >= total || busy} onClick={() => setPage((v) => v + 1)}>Next</button>
        </div>
        <form className="qms-review__form" onSubmit={create}>
          <h3>Identify risk</h3>
          <label>Title<input required minLength={4} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label>Nature and context<textarea required minLength={12} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label>Source category<select value={kind} onChange={(e) => setKind(e.target.value as QmsRiskSourceType)}>
            {kinds.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
          <SelectOption label="Authoritative source" choices={sources} value={sourceId} onChange={setSourceId} />
          <label>Accountable owner<select required value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
            <option value="">Select active employee</option>
            {owners.map((person) => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
          <label>Consequence<textarea required minLength={8} value={consequence} onChange={(e) => setConsequence(e.target.value)} /></label>
          <label>Likelihood (1–5)<input type="number" required min={1} max={5} value={likelihood} onChange={(e) => setLikelihood(Number(e.target.value))} /></label>
          <label>Severity (1–5)<input type="number" required min={1} max={5} value={severity} onChange={(e) => setSeverity(Number(e.target.value))} /></label>
          <p>Score: {likelihood * severity}. Interpretation and acceptance remain policy-specific.</p>
          <label>Assessment basis<textarea required minLength={12} value={basis} onChange={(e) => setBasis(e.target.value)} /></label>
          <label className="qms-review__check"><input type="checkbox" checked={sms} onChange={(e) => setSms(e.target.checked)} /> Refer decision to Safety Management System</label>
          <button type="submit" disabled={busy || !ownerId || !sourceId}>Record risk</button>
        </form>
      </section>
      <div className="qms-review__detail">
        {!risk ? <section className="qms-review__panel"><h2>Select a risk</h2><p>Review source evidence, treatment controls and residual decisions.</p></section> : <>
          <section className="qms-review__panel"><h2>{risk.title}</h2><p>{risk.description}</p>
            <p>{risk.status} · Revision {version} · Owner {owners.find((person) => person.id === risk.owner_user_id)?.name || risk.owner_user_id}</p>
            <p>Initial score {risk.payload.assessment.score} (likelihood {risk.payload.assessment.likelihood} × severity {risk.payload.assessment.severity})</p>
            <p>Basis: {risk.payload.assessment.basis}</p>
            <p>Source: {risk.payload.source_type} · {risk.payload.source_id}</p>
            {risk.payload.safety_boundary === "SMS_ESCALATION_REQUIRED" ? <p role="status">SMS escalation is required. Quality is not authorised to accept this safety risk.</p> : null}
            {risk.payload.residual_request ? <p>Residual score: {risk.payload.residual_request.score} · Policy reference: {risk.payload.residual_request.policy_reference}</p> : null}
            {risk.payload.residual_decision ? <p>Decision: {risk.payload.residual_decision.accepted ? "Accepted" : "Rejected"} · {risk.payload.residual_decision.rationale}</p> : null}
          </section>
          <section className="qms-review__panel"><h3>Controls</h3>
            <div className="qms-review__record-list">{controls.map((control) => <article key={control.id}>
              <strong>{control.title}</strong><span>{control.status}</span><p>{control.description}</p>
              <small>Owner {control.owner_user_id} · Deadline {control.due_date}</small></article>)}</div>
            {!controls.length ? <p>Controls have not yet been assigned.</p> : null}
            {mayTreat ? <form className="qms-review__form" onSubmit={(e) => { e.preventDefault(); void run(() =>
              addQmsRiskControl(amoCode, risk.id, { expected_version: version,
                title: controlTitle.trim(), description: controlDescription.trim(),
                owner_user_id: controlOwner, due_date: controlDue, expected_outcome: controlOutcome.trim() }),
              "Control assigned."); }}>
              <h3>Assign treatment</h3>
              <label>Title<input required minLength={4} value={controlTitle} onChange={(e) => setControlTitle(e.target.value)} /></label>
              <label>Action<textarea required minLength={8} value={controlDescription} onChange={(e) => setControlDescription(e.target.value)} /></label>
              <label>Owner<select required value={controlOwner} onChange={(e) => setControlOwner(e.target.value)}>
                <option value="">Select owner</option>{owners.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
              <label>Due date<input required type="date" value={controlDue} onChange={(e) => setControlDue(e.target.value)} /></label>
              <label>Expected outcome<textarea required minLength={8} value={controlOutcome} onChange={(e) => setControlOutcome(e.target.value)} /></label>
              <button type="submit" disabled={busy || !controlOwner}>Assign control</button>
            </form> : null}
          </section>
          {mayTreat || canDecide ? <section className="qms-review__panel qms-review__form">
            <h3>Evidence and verification</h3>
            <Link to={"/maintenance/" + encodeURIComponent(amoCode) + "/quality/evidence-vault/search"}>Browse evidence vault</Link>
            {evidenceSelector}
            <label>Reasoned verification or decision<textarea minLength={12} value={rationale} onChange={(e) => setRationale(e.target.value)} /></label>
            {mayTreat ? controls.filter((control) => control.status === "ASSIGNED" && control.owner_user_id !== userId).map((control) =>
              <div className="qms-review__action" key={control.id}><strong>{control.title}</strong>
                <button type="button" disabled={busy || !evidenceId || rationale.trim().length < 8} onClick={() => void run(() =>
                  verifyQmsRiskControl(amoCode, risk.id, control.id, { effective: true, evidence_id: evidenceId, rationale }), "Control independently verified.")}>Verify effective</button>
                <button type="button" disabled={busy || !evidenceId || rationale.trim().length < 8} onClick={() => void run(() =>
                  verifyQmsRiskControl(amoCode, risk.id, control.id, { effective: false, evidence_id: evidenceId, rationale }), "Control returned as ineffective.")}>Mark ineffective</button>
              </div>) : null}
            {canDecide ? <>
              <button type="button" disabled={busy || !evidenceId || rationale.trim().length < 12}
                onClick={() => action("decide-residual", { accept: true, rationale, evidence_id: evidenceId }, "Residual risk accepted.")}>Accept residual risk</button>
              <button type="button" disabled={busy || !evidenceId || rationale.trim().length < 12}
                onClick={() => action("decide-residual", { accept: false, rationale, evidence_id: evidenceId }, "More treatment required.")}>Reject acceptance</button>
            </> : null}
          </section> : null}
          {mayTreat ? <section className="qms-review__panel qms-review__form">
            <h3>Request residual acceptance</h3>
            {evidenceSelector}
            <label>Residual likelihood<input type="number" min={1} max={5} value={residualLikelihood} onChange={(e) => setResidualLikelihood(Number(e.target.value))} /></label>
            <label>Residual severity<input type="number" min={1} max={5} value={residualSeverity} onChange={(e) => setResidualSeverity(Number(e.target.value))} /></label>
            <p>Residual score: {residualLikelihood * residualSeverity} (not an automatic pass/fail threshold).</p>
            <label>Policy reference<input minLength={4} required value={policy} onChange={(e) => setPolicy(e.target.value)} /></label>
            <label>Treatment evidence and remaining risk<textarea required minLength={12} value={treatment} onChange={(e) => setTreatment(e.target.value)} /></label>
            <button type="button" disabled={busy || !evidenceId || treatment.trim().length < 12 || policy.trim().length < 4 ||
              risk.payload.safety_boundary === "SMS_ESCALATION_REQUIRED" || !controls.length || controls.some((item) => item.status !== "VERIFIED")}
              onClick={() => action("submit-residual", { residual_likelihood: residualLikelihood, residual_severity: residualSeverity,
                treatment_summary: treatment, policy_reference: policy, evidence_id: evidenceId }, "Submitted for independent acceptance.")}>
              Submit for independent decision
            </button>
          </section> : null}
          {risk.status === "ACCEPTED" ? <section className="qms-review__panel qms-review__form">
            <h3>Monitoring</h3><label>Monitoring plan<textarea required minLength={12} value={rationale} onChange={(e) => setRationale(e.target.value)} /></label>
            <button type="button" disabled={busy || rationale.trim().length < 12}
              onClick={() => action("monitor", { reason: rationale }, "Risk monitoring initiated.")}>Start monitored review</button>
          </section> : null}
        </>}
      </div>
    </div>
  </main></DepartmentLayout>;
}
