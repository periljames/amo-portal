import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Beaker, CheckCircle2, FileSearch2, Plus, RefreshCw, ShieldCheck } from "lucide-react";

import {
  addQmsInvestigationEntry,
  createQmsAssuranceCase,
  createQmsEffectivenessPlan,
  getQmsAssuranceCase,
  listQmsAssuranceCases,
  transitionQmsAssuranceCase,
  type QmsAssuranceCase,
  type QmsAssuranceCaseStatus,
  type QmsAssuranceCaseType,
  type QmsAssuranceSeverity,
  type QmsInvestigationEntryType,
  type QmsInvestigationMethod,
} from "../../services/qmsAssuranceCases";
import "../../styles/qms-assurance-cases.css";

type Props = { amoCode: string };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Assurance operation could not be completed.";
}

const QmsAssurancePage: React.FC<Props> = ({ amoCode }) => {
  const [cases, setCases] = useState<QmsAssuranceCase[]>([]);
  const [selected, setSelected] = useState<QmsAssuranceCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<QmsAssuranceCaseStatus | "ALL">("ALL");

  const [showCreate, setShowCreate] = useState(false);
  const [caseType, setCaseType] = useState<QmsAssuranceCaseType>("INVESTIGATION");
  const [caseTitle, setCaseTitle] = useState("");
  const [caseDescription, setCaseDescription] = useState("");
  const [caseSeverity, setCaseSeverity] = useState<QmsAssuranceSeverity>("MEDIUM");
  const [creating, setCreating] = useState(false);

  const [method, setMethod] = useState<QmsInvestigationMethod>("FIVE_WHYS");
  const [entryType, setEntryType] = useState<QmsInvestigationEntryType>("FACT");
  const [statement, setStatement] = useState("");
  const [evidenceSource, setEvidenceSource] = useState("");
  const [addingEntry, setAddingEntry] = useState(false);

  const [expectedOutcome, setExpectedOutcome] = useState("");
  const [measure, setMeasure] = useState("");
  const [verification, setVerification] = useState("");
  const [reviewDate, setReviewDate] = useState("");
  const [creatingPlan, setCreatingPlan] = useState(false);

  const [transitionStatus, setTransitionStatus] = useState<QmsAssuranceCaseStatus>("INVESTIGATING");
  const [transitionReason, setTransitionReason] = useState("");
  const [transitioning, setTransitioning] = useState(false);

  const loadCases = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const response = await listQmsAssuranceCases(amoCode, { limit: 150 }, signal);
      setCases(response.items);
      if (selected) {
        const stillExists = response.items.find((item) => item.id === selected.id);
        if (!stillExists) setSelected(null);
      }
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setError(errorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }, [amoCode, selected]);

  useEffect(() => {
    const controller = new AbortController();
    void loadCases(controller.signal);
    return () => controller.abort();
  }, [loadCases]);

  async function selectCase(caseId: string) {
    setError("");
    try {
      const detail = await getQmsAssuranceCase(amoCode, caseId);
      setSelected(detail);
      setTransitionStatus(detail.status === "OPEN" ? "INVESTIGATING" : detail.status === "INVESTIGATING" ? "ACTION_PENDING" : "EFFECTIVENESS_REVIEW");
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  const visibleCases = useMemo(
    () => statusFilter === "ALL" ? cases : cases.filter((item) => item.status === statusFilter),
    [cases, statusFilter],
  );
  const openCount = cases.filter((item) => !["CLOSED", "CANCELLED"].includes(item.status)).length;
  const criticalCount = cases.filter((item) => item.severity === "CRITICAL" && !["CLOSED", "CANCELLED"].includes(item.status)).length;
  const effectivenessDue = cases.filter((item) => item.status === "EFFECTIVENESS_REVIEW").length;

  async function submitCase(event: FormEvent) {
    event.preventDefault();
    if (caseTitle.trim().length < 3) return;
    setCreating(true); setError("");
    try {
      const created = await createQmsAssuranceCase(amoCode, {
        case_type: caseType,
        title: caseTitle.trim(),
        description: caseDescription.trim() || undefined,
        severity: caseSeverity,
      });
      setShowCreate(false); setCaseTitle(""); setCaseDescription("");
      await loadCases();
      await selectCase(created.id);
    } catch (nextError) { setError(errorMessage(nextError)); }
    finally { setCreating(false); }
  }

  async function submitInvestigation(event: FormEvent) {
    event.preventDefault();
    if (!selected || statement.trim().length < 3) return;
    setAddingEntry(true); setError("");
    try {
      const evidence = evidenceSource.trim()
        ? [{ source_ref: evidenceSource.trim(), source_type: "AUTHORITATIVE_REFERENCE" }]
        : [];
      await addQmsInvestigationEntry(amoCode, selected.id, {
        method,
        entry_type: entryType,
        sequence_no: (selected.investigation_entries?.length || 0) + 1,
        statement: statement.trim(),
        evidence_references: evidence,
      });
      setStatement(""); setEvidenceSource("");
      await selectCase(selected.id); await loadCases();
    } catch (nextError) { setError(errorMessage(nextError)); }
    finally { setAddingEntry(false); }
  }

  async function submitEffectiveness(event: FormEvent) {
    event.preventDefault();
    if (!selected || expectedOutcome.trim().length < 8 || measure.trim().length < 8 || verification.trim().length < 8 || !reviewDate) return;
    setCreatingPlan(true); setError("");
    try {
      await createQmsEffectivenessPlan(amoCode, selected.id, {
        expected_outcome: expectedOutcome.trim(),
        effectiveness_measure: measure.trim(),
        verification_method: verification.trim(),
        planned_review_date: reviewDate,
      });
      setExpectedOutcome(""); setMeasure(""); setVerification(""); setReviewDate("");
      await selectCase(selected.id); await loadCases();
    } catch (nextError) { setError(errorMessage(nextError)); }
    finally { setCreatingPlan(false); }
  }

  async function submitTransition(event: FormEvent) {
    event.preventDefault();
    if (!selected || transitionReason.trim().length < 8) return;
    setTransitioning(true); setError("");
    try {
      await transitionQmsAssuranceCase(amoCode, selected.id, transitionStatus, transitionReason.trim());
      setTransitionReason("");
      await selectCase(selected.id); await loadCases();
    } catch (nextError) { setError(errorMessage(nextError)); }
    finally { setTransitioning(false); }
  }

  return (
    <main className="qms-assurance-cases" aria-label="Assurance workspace">
      <header className="qms-assurance-cases__hero">
        <div><span>Assurance</span><h1>Cases, investigation & effectiveness</h1><p>Connect source signals to evidence, causal analysis and verified corrective-action outcomes without replacing the source audit, CAR, supplier or maintenance records.</p></div>
        <div className="qms-assurance-cases__hero-actions"><button type="button" onClick={() => setShowCreate((value) => !value)}><Plus size={16} aria-hidden="true" /> New case</button><button type="button" onClick={() => void loadCases()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button></div>
      </header>

      {error ? <div className="qms-assurance-cases__error" role="alert"><AlertTriangle size={17} aria-hidden="true" /> {error}</div> : null}

      <section className="qms-assurance-cases__metrics"><article><strong>{openCount}</strong><span>Open assurance cases</span></article><article><strong>{criticalCount}</strong><span>Critical exposure</span></article><article><strong>{effectivenessDue}</strong><span>Effectiveness review</span></article><article><strong>{cases.length}</strong><span>Total governed cases</span></article></section>

      {showCreate ? <section className="qms-assurance-cases__panel"><div className="qms-assurance-cases__panel-head"><div><span>Open governed case</span><h2>Source-backed assurance problem</h2></div></div><form className="qms-assurance-cases__form qms-assurance-cases__form--wide" onSubmit={submitCase}><label htmlFor="case-type">Case type<select id="case-type" value={caseType} onChange={(event) => setCaseType(event.target.value as QmsAssuranceCaseType)}><option value="SIGNAL">Signal</option><option value="INVESTIGATION">Investigation</option><option value="RECURRING_FINDING">Recurring finding</option><option value="EFFECTIVENESS">Effectiveness</option><option value="SUPPLIER">Supplier</option><option value="REGULATORY">Regulatory</option><option value="OTHER">Other</option></select></label><label htmlFor="case-severity">Severity<select id="case-severity" value={caseSeverity} onChange={(event) => setCaseSeverity(event.target.value as QmsAssuranceSeverity)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label><label className="span-2" htmlFor="case-title">Title<input id="case-title" value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} required /></label><label className="span-2" htmlFor="case-description">Description<textarea id="case-description" value={caseDescription} onChange={(event) => setCaseDescription(event.target.value)} rows={3} /></label><button type="submit" disabled={creating || caseTitle.trim().length < 3}>{creating ? "Opening…" : "Open assurance case"}</button></form></section> : null}

      <section className="qms-assurance-cases__layout">
        <section className="qms-assurance-cases__panel qms-assurance-cases__list"><div className="qms-assurance-cases__panel-head"><div><span>Case portfolio</span><h2>Governed assurance work</h2></div><label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="OPEN">Open</option><option value="INVESTIGATING">Investigating</option><option value="ACTION_PENDING">Action pending</option><option value="EFFECTIVENESS_REVIEW">Effectiveness review</option><option value="CLOSED">Closed</option></select></label></div><div className="qms-assurance-cases__case-list">{visibleCases.length ? visibleCases.map((item) => <button key={item.id} type="button" className={selected?.id === item.id ? "is-selected" : ""} onClick={() => void selectCase(item.id)}><span><strong>{item.case_ref}</strong><small>{item.case_type}</small></span><b>{item.title}</b><span><small>{item.severity}</small><small>{item.status.replaceAll("_", " ")}</small></span></button>) : <p className="qms-assurance-cases__empty">{loading ? "Loading cases…" : "No assurance cases match this view."}</p>}</div></section>

        <section className="qms-assurance-cases__panel qms-assurance-cases__detail">{selected ? <><div className="qms-assurance-cases__panel-head"><div><span>{selected.case_ref} · {selected.severity}</span><h2>{selected.title}</h2></div><span className={`qms-assurance-cases__status qms-assurance-cases__status--${selected.status.toLowerCase()}`}>{selected.status.replaceAll("_", " ")}</span></div><div className="qms-assurance-cases__detail-body"><p>{selected.description || "No additional case description."}</p><div className="qms-assurance-cases__facts"><span><strong>{selected.investigation_entries?.length || 0}</strong> investigation statements</span><span><strong>{selected.effectiveness_plans?.length || 0}</strong> effectiveness plans</span><span><strong>{selected.events?.length || 0}</strong> immutable events</span></div></div></> : <div className="qms-assurance-cases__placeholder"><FileSearch2 size={28} aria-hidden="true" /><strong>Select an assurance case</strong><p>Case detail, investigation methods and effectiveness gates will appear here.</p></div>}</section>
      </section>

      {selected ? <div className="qms-assurance-cases__workgrid">
        <section className="qms-assurance-cases__panel"><div className="qms-assurance-cases__panel-head"><div><span>Investigation Studio</span><h2>Fact → hypothesis → causal conclusion</h2></div><Beaker size={20} aria-hidden="true" /></div><form className="qms-assurance-cases__form" onSubmit={submitInvestigation}><label htmlFor="investigation-method">Method<select id="investigation-method" value={method} onChange={(event) => setMethod(event.target.value as QmsInvestigationMethod)}><option value="FIVE_WHYS">5 Whys</option><option value="ISHIKAWA">Ishikawa</option><option value="CAUSAL_FACTOR">Causal factor analysis</option><option value="BARRIER_ANALYSIS">Barrier analysis</option><option value="CHANGE_ANALYSIS">Change analysis</option><option value="HUMAN_ORGANIZATIONAL">Human / organizational factors</option></select></label><label htmlFor="investigation-type">Statement class<select id="investigation-type" value={entryType} onChange={(event) => setEntryType(event.target.value as QmsInvestigationEntryType)}><option value="FACT">Fact</option><option value="HYPOTHESIS">Hypothesis</option><option value="CAUSAL_CONCLUSION">Causal conclusion</option></select></label><label htmlFor="investigation-statement">Statement<textarea id="investigation-statement" value={statement} onChange={(event) => setStatement(event.target.value)} rows={4} required /></label><label htmlFor="investigation-evidence">Authoritative evidence reference<input id="investigation-evidence" value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} placeholder="record ID / controlled source route" /></label><button type="submit" disabled={addingEntry || statement.trim().length < 3}>{addingEntry ? "Recording…" : "Record immutable statement"}</button></form><div className="qms-assurance-cases__entries">{selected.investigation_entries?.map((entry) => <article key={entry.id}><span>{entry.entry_type.replaceAll("_", " ")} · {entry.method.replaceAll("_", " ")}</span><p>{entry.statement}</p><small>{entry.evidence_references.length ? `${entry.evidence_references.length} evidence reference(s)` : "No evidence linked"}</small></article>)}</div></section>

        <section className="qms-assurance-cases__panel"><div className="qms-assurance-cases__panel-head"><div><span>Effectiveness engineering</span><h2>Define success before closure</h2></div><CheckCircle2 size={20} aria-hidden="true" /></div><form className="qms-assurance-cases__form" onSubmit={submitEffectiveness}><label htmlFor="expected-outcome">Expected outcome<textarea id="expected-outcome" value={expectedOutcome} onChange={(event) => setExpectedOutcome(event.target.value)} rows={3} required /></label><label htmlFor="effectiveness-measure">Effectiveness measure<textarea id="effectiveness-measure" value={measure} onChange={(event) => setMeasure(event.target.value)} rows={3} required /></label><label htmlFor="verification-method">Verification method<textarea id="verification-method" value={verification} onChange={(event) => setVerification(event.target.value)} rows={3} required /></label><label htmlFor="review-date">Planned review date<input id="review-date" type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} required /></label><button type="submit" disabled={creatingPlan || expectedOutcome.trim().length < 8 || measure.trim().length < 8 || verification.trim().length < 8 || !reviewDate}>{creatingPlan ? "Planning…" : "Create effectiveness plan"}</button></form><div className="qms-assurance-cases__entries">{selected.effectiveness_plans?.map((plan) => <article key={plan.id}><span>{plan.status.replaceAll("_", " ")}{plan.conclusion ? ` · ${plan.conclusion.replaceAll("_", " ")}` : ""}</span><p><strong>Outcome:</strong> {plan.expected_outcome}</p><small>Review {plan.planned_review_date} · {plan.verification_method}</small></article>)}</div></section>

        <section className="qms-assurance-cases__panel qms-assurance-cases__transition"><div className="qms-assurance-cases__panel-head"><div><span>Governed lifecycle</span><h2>Move the case deliberately</h2></div><ShieldCheck size={20} aria-hidden="true" /></div><form className="qms-assurance-cases__form qms-assurance-cases__form--transition" onSubmit={submitTransition}><label htmlFor="case-transition">Next state<select id="case-transition" value={transitionStatus} onChange={(event) => setTransitionStatus(event.target.value as QmsAssuranceCaseStatus)}><option value="OPEN">Open / reopen</option><option value="INVESTIGATING">Investigating</option><option value="ACTION_PENDING">Action pending</option><option value="EFFECTIVENESS_REVIEW">Effectiveness review</option><option value="CLOSED">Closed</option><option value="CANCELLED">Cancelled</option></select></label><label htmlFor="case-transition-reason">Reason<textarea id="case-transition-reason" value={transitionReason} onChange={(event) => setTransitionReason(event.target.value)} minLength={8} rows={3} required /></label><button type="submit" disabled={transitioning || transitionReason.trim().length < 8}>{transitioning ? "Recording…" : "Record lifecycle decision"}</button></form></section>
      </div> : null}
    </main>
  );
};

export default QmsAssurancePage;
