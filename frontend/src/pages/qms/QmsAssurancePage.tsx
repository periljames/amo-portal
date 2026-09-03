import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Beaker, CheckCircle2, FileSearch2, Plus, RefreshCw, ShieldCheck, X } from "lucide-react";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { clearQmsApiResponseCache } from "../../services/apiClient";
import {
  addQmsInvestigationEntry,
  concludeQmsEffectivenessPlan,
  createQmsAssuranceCase,
  createQmsEffectivenessPlan,
  getQmsAssuranceCase,
  listQmsAssuranceCases,
  transitionQmsAssuranceCase,
  type QmsAssuranceCase,
  type QmsAssuranceCaseStatus,
  type QmsAssuranceCaseType,
  type QmsAssuranceSeverity,
  type QmsEffectivenessConclusion,
  type QmsInvestigationEntryType,
  type QmsInvestigationMethod,
} from "../../services/qmsAssuranceCases";
import "../../styles/qms-assurance-cases.css";

type Props = { amoCode: string };

const CASE_TRANSITIONS: Record<QmsAssuranceCaseStatus, QmsAssuranceCaseStatus[]> = {
  OPEN: ["INVESTIGATING", "CANCELLED"],
  INVESTIGATING: ["ACTION_PENDING", "EFFECTIVENESS_REVIEW", "CANCELLED"],
  ACTION_PENDING: ["INVESTIGATING", "EFFECTIVENESS_REVIEW", "CANCELLED"],
  EFFECTIVENESS_REVIEW: ["CLOSED", "ACTION_PENDING", "CANCELLED"],
  CLOSED: ["OPEN"],
  CANCELLED: ["OPEN"],
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Assurance operation could not be completed.";
}

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function localDateKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function closureBlockReason(assuranceCase: QmsAssuranceCase): string | null {
  const plans = assuranceCase.effectiveness_plans || [];
  if (plans.some((plan) => plan.status !== "CONCLUDED")) return "Conclude every effectiveness plan before closing this case.";
  if (plans.some((plan) => ["INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"].includes(plan.conclusion || ""))) {
    return "A non-effective or inconclusive result requires further action before closure.";
  }
  return null;
}

function allowedTransitionsForCase(assuranceCase: QmsAssuranceCase): QmsAssuranceCaseStatus[] {
  const closureBlocked = closureBlockReason(assuranceCase);
  return CASE_TRANSITIONS[assuranceCase.status].filter((status) => status !== "CLOSED" || !closureBlocked);
}

function defaultTransitionStatus(assuranceCase: QmsAssuranceCase): QmsAssuranceCaseStatus {
  return allowedTransitionsForCase(assuranceCase)[0] || assuranceCase.status;
}

function statusLabel(status: QmsAssuranceCaseStatus): string {
  if (status === "OPEN") return "Open / reopen";
  return humanise(status);
}

const QmsAssurancePage: React.FC<Props> = ({ amoCode }) => {
  const canManageAudits = hasQmsRolePermission("qms.audit.manage");
  const canManageEffectiveness = hasQmsRolePermission("qms.car.manage");

  const [cases, setCases] = useState<QmsAssuranceCase[]>([]);
  const [selected, setSelected] = useState<QmsAssuranceCase | null>(null);
  const selectedIdRef = useRef("");
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

  const [conclusionPlanId, setConclusionPlanId] = useState("");
  const [conclusion, setConclusion] = useState<QmsEffectivenessConclusion>("EFFECTIVE");
  const [conclusionRationale, setConclusionRationale] = useState("");
  const [conclusionEvidence, setConclusionEvidence] = useState("");
  const [concluding, setConcluding] = useState(false);

  const [transitionStatus, setTransitionStatus] = useState<QmsAssuranceCaseStatus>("INVESTIGATING");
  const [transitionReason, setTransitionReason] = useState("");
  const [transitioning, setTransitioning] = useState(false);

  const applySelectedDetail = useCallback((detail: QmsAssuranceCase) => {
    selectedIdRef.current = detail.id;
    setSelected(detail);
    setTransitionStatus(defaultTransitionStatus(detail));
    const today = localDateKey();
    const reviewablePlans = (detail.effectiveness_plans || []).filter((plan) => plan.status !== "CONCLUDED" && plan.planned_review_date <= today);
    setConclusionPlanId((current) => reviewablePlans.some((plan) => plan.id === current) ? current : reviewablePlans[0]?.id || "");
  }, []);

  const loadCases = useCallback(async (signal?: AbortSignal) => {
    if (!signal) clearQmsApiResponseCache();
    setLoading(true);
    setError("");
    try {
      const response = await listQmsAssuranceCases(amoCode, { limit: 150 }, signal);
      if (signal?.aborted) return;
      setCases(response.items);
      const selectedId = selectedIdRef.current;
      if (selectedId) {
        const stillExists = response.items.some((item) => item.id === selectedId);
        if (!stillExists) {
          selectedIdRef.current = "";
          setSelected(null);
        } else {
          const detail = await getQmsAssuranceCase(amoCode, selectedId, signal);
          if (signal?.aborted) return;
          applySelectedDetail(detail);
        }
      }
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError")) {
        if (selectedIdRef.current) setSelected(null);
        setError(errorMessage(nextError));
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [amoCode, applySelectedDetail]);

  useEffect(() => {
    const controller = new AbortController();
    void loadCases(controller.signal);
    return () => controller.abort();
  }, [loadCases]);

  async function selectCase(caseId: string) {
    setError("");
    try {
      applySelectedDetail(await getQmsAssuranceCase(amoCode, caseId));
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  const visibleCases = useMemo(() => statusFilter === "ALL" ? cases : cases.filter((item) => item.status === statusFilter), [cases, statusFilter]);
  const openCount = cases.filter((item) => !["CLOSED", "CANCELLED"].includes(item.status)).length;
  const criticalCount = cases.filter((item) => item.severity === "CRITICAL" && !["CLOSED", "CANCELLED"].includes(item.status)).length;
  const effectivenessDue = cases.filter((item) => item.status === "EFFECTIVENESS_REVIEW").length;
  const isTerminal = selected ? ["CLOSED", "CANCELLED"].includes(selected.status) : false;
  const hasRecordedFact = Boolean(selected?.investigation_entries?.some((entry) => entry.entry_type === "FACT"));
  const causalEvidenceRequired = entryType === "CAUSAL_CONCLUSION";
  const causalConclusionReady = !causalEvidenceRequired || (hasRecordedFact && Boolean(evidenceSource.trim()));
  const today = localDateKey();
  const reviewablePlans = (selected?.effectiveness_plans || []).filter((plan) => plan.status !== "CONCLUDED" && plan.planned_review_date <= today);
  const futurePlans = (selected?.effectiveness_plans || []).filter((plan) => plan.status !== "CONCLUDED" && plan.planned_review_date > today);
  const allowedTransitions = selected ? allowedTransitionsForCase(selected) : [];
  const closeBlock = selected ? closureBlockReason(selected) : null;

  async function submitCase(event: FormEvent) {
    event.preventDefault();
    if (!canManageAudits || caseTitle.trim().length < 3) return;
    setCreating(true);
    setError("");
    try {
      const created = await createQmsAssuranceCase(amoCode, { case_type: caseType, title: caseTitle.trim(), description: caseDescription.trim() || undefined, severity: caseSeverity });
      setShowCreate(false);
      setCaseTitle("");
      setCaseDescription("");
      selectedIdRef.current = created.id;
      await loadCases();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setCreating(false);
    }
  }

  async function submitInvestigation(event: FormEvent) {
    event.preventDefault();
    if (!canManageAudits || !selected || isTerminal || statement.trim().length < 3 || !causalConclusionReady) return;
    setAddingEntry(true);
    setError("");
    try {
      const evidence = evidenceSource.trim() ? [{ source_ref: evidenceSource.trim(), source_type: "AUTHORITATIVE_REFERENCE" }] : [];
      await addQmsInvestigationEntry(amoCode, selected.id, {
        method,
        entry_type: entryType,
        sequence_no: (selected.investigation_entries?.length || 0) + 1,
        statement: statement.trim(),
        evidence_references: evidence,
      });
      setStatement("");
      setEvidenceSource("");
      await loadCases();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setAddingEntry(false);
    }
  }

  async function submitEffectiveness(event: FormEvent) {
    event.preventDefault();
    if (!canManageEffectiveness || !selected || isTerminal || expectedOutcome.trim().length < 8 || measure.trim().length < 8 || verification.trim().length < 8 || !reviewDate || reviewDate < today) return;
    setCreatingPlan(true);
    setError("");
    try {
      await createQmsEffectivenessPlan(amoCode, selected.id, {
        expected_outcome: expectedOutcome.trim(),
        effectiveness_measure: measure.trim(),
        verification_method: verification.trim(),
        planned_review_date: reviewDate,
      });
      setExpectedOutcome("");
      setMeasure("");
      setVerification("");
      setReviewDate("");
      await loadCases();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setCreatingPlan(false);
    }
  }

  async function submitConclusion(event: FormEvent) {
    event.preventDefault();
    if (!canManageEffectiveness || !selected || isTerminal || !conclusionPlanId || conclusionRationale.trim().length < 8 || !conclusionEvidence.trim()) return;
    if (!reviewablePlans.some((plan) => plan.id === conclusionPlanId)) return;
    setConcluding(true);
    setError("");
    try {
      await concludeQmsEffectivenessPlan(amoCode, selected.id, conclusionPlanId, {
        conclusion,
        rationale: conclusionRationale.trim(),
        evidence_references: [{ source_ref: conclusionEvidence.trim(), source_type: "AUTHORITATIVE_REFERENCE" }],
      });
      setConclusionRationale("");
      setConclusionEvidence("");
      setConclusionPlanId("");
      await loadCases();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setConcluding(false);
    }
  }

  async function submitTransition(event: FormEvent) {
    event.preventDefault();
    if (!canManageAudits || !selected || !allowedTransitions.includes(transitionStatus) || transitionReason.trim().length < 8) return;
    setTransitioning(true);
    setError("");
    try {
      await transitionQmsAssuranceCase(amoCode, selected.id, transitionStatus, transitionReason.trim());
      setTransitionReason("");
      await loadCases();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setTransitioning(false);
    }
  }

  return (
    <main className="qms-assurance-cases" aria-label="Assurance case register">
      <header className="qms-assurance-cases__hero">
        <div><span>Assurance · Case register</span><h1>Investigation & effectiveness cases</h1><p>Connect source signals to evidence, causal analysis and verified corrective-action outcomes without replacing the source audit, CAR, supplier or maintenance records. Operational audits live under Audits.</p></div>
        <div className="qms-assurance-cases__hero-actions">{canManageAudits ? <button type="button" onClick={() => setShowCreate(true)}><Plus size={16} aria-hidden="true" /> New case</button> : null}<button type="button" onClick={() => void loadCases()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button></div>
      </header>

      {error ? <div className="qms-assurance-cases__error" role="alert"><AlertTriangle size={17} aria-hidden="true" /> {error}</div> : null}
      <section className="qms-assurance-cases__metrics"><article><strong>{openCount}</strong><span>Open assurance cases</span></article><article><strong>{criticalCount}</strong><span>Critical exposure</span></article><article><strong>{effectivenessDue}</strong><span>Effectiveness review</span></article><article><strong>{cases.length}</strong><span>Total governed cases</span></article></section>

      {showCreate && canManageAudits ? (
        <section className="qms-assurance-cases__panel" role="dialog" aria-modal="true" aria-label="Create assurance case">
          <div className="qms-assurance-cases__panel-head"><div><span>Open governed case</span><h2>Source-backed assurance problem</h2></div><button type="button" aria-label="Close create assurance case" onClick={() => setShowCreate(false)}><X size={17} aria-hidden="true" /> Close</button></div>
          <form className="qms-assurance-cases__form qms-assurance-cases__form--wide" onSubmit={submitCase}><label htmlFor="case-type">Case type<select id="case-type" value={caseType} onChange={(event) => setCaseType(event.target.value as QmsAssuranceCaseType)}><option value="SIGNAL">Signal</option><option value="INVESTIGATION">Investigation</option><option value="RECURRING_FINDING">Recurring finding</option><option value="EFFECTIVENESS">Effectiveness</option><option value="SUPPLIER">Supplier</option><option value="REGULATORY">Regulatory</option><option value="OTHER">Other</option></select></label><label htmlFor="case-severity">Severity<select id="case-severity" value={caseSeverity} onChange={(event) => setCaseSeverity(event.target.value as QmsAssuranceSeverity)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label><label className="span-2" htmlFor="case-title">Title<input id="case-title" value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} required /></label><label className="span-2" htmlFor="case-description">Description<textarea id="case-description" value={caseDescription} onChange={(event) => setCaseDescription(event.target.value)} rows={3} /></label><button type="submit" disabled={creating || caseTitle.trim().length < 3}>{creating ? "Opening…" : "Open assurance case"}</button></form>
        </section>
      ) : null}

      <section className="qms-assurance-cases__layout">
        <section className="qms-assurance-cases__panel qms-assurance-cases__list"><div className="qms-assurance-cases__panel-head"><div><span>Case portfolio</span><h2>Governed assurance work</h2></div><label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="OPEN">Open</option><option value="INVESTIGATING">Investigating</option><option value="ACTION_PENDING">Action pending</option><option value="EFFECTIVENESS_REVIEW">Effectiveness review</option><option value="CLOSED">Closed</option><option value="CANCELLED">Cancelled</option></select></label></div><div className="qms-assurance-cases__case-list">{visibleCases.length ? visibleCases.map((item) => <button key={item.id} type="button" className={selected?.id === item.id ? "is-selected" : ""} onClick={() => void selectCase(item.id)}><span><strong>{item.case_ref}</strong><small>{item.case_type}</small></span><b>{item.title}</b><span><small>{item.severity}</small><small>{humanise(item.status)}</small></span></button>) : <p className="qms-assurance-cases__empty">{loading ? "Loading cases…" : "No assurance cases match this view."}</p>}</div></section>
        <section className="qms-assurance-cases__panel qms-assurance-cases__detail">{selected ? <><div className="qms-assurance-cases__panel-head"><div><span>{selected.case_ref} · {selected.severity}</span><h2>{selected.title}</h2></div><span className={`qms-assurance-cases__status qms-assurance-cases__status--${selected.status.toLowerCase()}`}>{humanise(selected.status)}</span></div><div className="qms-assurance-cases__detail-body"><p>{selected.description || "No additional case description."}</p><div className="qms-assurance-cases__facts"><span><strong>{selected.investigation_entries?.length || 0}</strong> investigation statements</span><span><strong>{selected.effectiveness_plans?.length || 0}</strong> effectiveness plans</span><span><strong>{selected.events?.length || 0}</strong> immutable events</span></div></div></> : <div className="qms-assurance-cases__placeholder"><FileSearch2 size={28} aria-hidden="true" /><strong>Select an assurance case</strong><p>Case detail, investigation methods and effectiveness gates will appear here.</p></div>}</section>
      </section>

      {selected ? (
        <div className="qms-assurance-cases__workgrid">
          <section className="qms-assurance-cases__panel"><div className="qms-assurance-cases__panel-head"><div><span>Investigation Studio</span><h2>Fact → hypothesis → causal conclusion</h2></div><Beaker size={20} aria-hidden="true" /></div>{canManageAudits && !isTerminal ? <form className="qms-assurance-cases__form" onSubmit={submitInvestigation}><label htmlFor="investigation-method">Method<select id="investigation-method" value={method} onChange={(event) => setMethod(event.target.value as QmsInvestigationMethod)}><option value="FIVE_WHYS">5 Whys</option><option value="ISHIKAWA">Ishikawa</option><option value="CAUSAL_FACTOR">Causal factor analysis</option><option value="BARRIER_ANALYSIS">Barrier analysis</option><option value="CHANGE_ANALYSIS">Change analysis</option><option value="HUMAN_ORGANIZATIONAL">Human / organizational factors</option></select></label><label htmlFor="investigation-type">Statement class<select id="investigation-type" value={entryType} onChange={(event) => setEntryType(event.target.value as QmsInvestigationEntryType)}><option value="FACT">Fact</option><option value="HYPOTHESIS">Hypothesis</option><option value="CAUSAL_CONCLUSION">Causal conclusion</option></select></label><label htmlFor="investigation-statement">Statement<textarea id="investigation-statement" value={statement} onChange={(event) => setStatement(event.target.value)} rows={4} required /></label><label htmlFor="investigation-evidence">Authoritative evidence reference{causalEvidenceRequired ? <span>Required for a causal conclusion.</span> : null}<input id="investigation-evidence" value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} required={causalEvidenceRequired} placeholder="record ID / controlled source route" /></label>{causalEvidenceRequired && !hasRecordedFact ? <p className="qms-assurance-cases__empty">Record at least one FACT before promoting a statement to a causal conclusion.</p> : null}<button type="submit" disabled={addingEntry || statement.trim().length < 3 || !causalConclusionReady}>{addingEntry ? "Recording…" : "Record immutable statement"}</button></form> : <p className="qms-assurance-cases__empty">{isTerminal ? "Reopen this case before adding investigation evidence." : "You have read access to investigation evidence; recording statements requires Audit management permission."}</p>}<div className="qms-assurance-cases__entries">{selected.investigation_entries?.map((entry) => <article key={entry.id}><span>{humanise(entry.entry_type)} · {humanise(entry.method)}</span><p>{entry.statement}</p><small>{entry.evidence_references.length ? `${entry.evidence_references.length} evidence reference(s)` : "No evidence linked"}</small></article>)}</div></section>

          <section className="qms-assurance-cases__panel"><div className="qms-assurance-cases__panel-head"><div><span>Effectiveness engineering</span><h2>Define, observe & conclude effectiveness</h2></div><CheckCircle2 size={20} aria-hidden="true" /></div>{canManageEffectiveness && !isTerminal ? <form className="qms-assurance-cases__form" onSubmit={submitEffectiveness}><label htmlFor="expected-outcome">Expected outcome<textarea id="expected-outcome" value={expectedOutcome} onChange={(event) => setExpectedOutcome(event.target.value)} rows={3} required /></label><label htmlFor="effectiveness-measure">Effectiveness measure<textarea id="effectiveness-measure" value={measure} onChange={(event) => setMeasure(event.target.value)} rows={3} required /></label><label htmlFor="verification-method">Verification method<textarea id="verification-method" value={verification} onChange={(event) => setVerification(event.target.value)} rows={3} required /></label><label htmlFor="review-date">Planned review date<input id="review-date" type="date" min={today} value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} required /></label><button type="submit" disabled={creatingPlan || expectedOutcome.trim().length < 8 || measure.trim().length < 8 || verification.trim().length < 8 || !reviewDate || reviewDate < today}>{creatingPlan ? "Planning…" : "Create effectiveness plan"}</button></form> : !canManageEffectiveness ? <p className="qms-assurance-cases__empty">Effectiveness planning and conclusions require CAR management permission.</p> : null}<div className="qms-assurance-cases__entries">{selected.effectiveness_plans?.map((plan) => <article key={plan.id}><span>{humanise(plan.status)}{plan.conclusion ? ` · ${humanise(plan.conclusion)}` : ""}</span><p><strong>Outcome:</strong> {plan.expected_outcome}</p><small>Review {plan.planned_review_date} · {plan.verification_method}</small>{plan.conclusion_rationale ? <p><strong>Conclusion:</strong> {plan.conclusion_rationale}</p> : null}</article>)}</div>{canManageEffectiveness && !isTerminal && reviewablePlans.length ? <form className="qms-assurance-cases__form" onSubmit={submitConclusion}><label htmlFor="conclusion-plan">Plan ready for review<select id="conclusion-plan" value={conclusionPlanId} onChange={(event) => setConclusionPlanId(event.target.value)} required><option value="">Select plan</option>{reviewablePlans.map((plan) => <option key={plan.id} value={plan.id}>{plan.planned_review_date} · {plan.expected_outcome.slice(0, 60)}</option>)}</select></label><label htmlFor="effectiveness-conclusion">Conclusion<select id="effectiveness-conclusion" value={conclusion} onChange={(event) => setConclusion(event.target.value as QmsEffectivenessConclusion)}><option value="EFFECTIVE">Effective</option><option value="PARTIALLY_EFFECTIVE">Partially effective</option><option value="INEFFECTIVE">Ineffective</option><option value="INCONCLUSIVE">Inconclusive</option></select></label><label htmlFor="conclusion-rationale">Evidence-backed rationale<textarea id="conclusion-rationale" value={conclusionRationale} onChange={(event) => setConclusionRationale(event.target.value)} minLength={8} rows={3} required /></label><label htmlFor="conclusion-evidence">Authoritative evidence reference<input id="conclusion-evidence" value={conclusionEvidence} onChange={(event) => setConclusionEvidence(event.target.value)} required placeholder="record ID / controlled source route" /></label><button type="submit" disabled={concluding || !conclusionPlanId || conclusionRationale.trim().length < 8 || !conclusionEvidence.trim()}>{concluding ? "Recording…" : "Record immutable effectiveness conclusion"}</button></form> : null}{canManageEffectiveness && !isTerminal && futurePlans.length ? <p className="qms-assurance-cases__empty">{futurePlans.length} effectiveness plan{futurePlans.length === 1 ? " has" : "s have"} not yet reached the planned review date.</p> : null}</section>

          <section className="qms-assurance-cases__panel qms-assurance-cases__transition"><div className="qms-assurance-cases__panel-head"><div><span>Governed lifecycle</span><h2>Move the case deliberately</h2></div><ShieldCheck size={20} aria-hidden="true" /></div>{canManageAudits ? <form className="qms-assurance-cases__form qms-assurance-cases__form--transition" onSubmit={submitTransition}><label htmlFor="case-transition">Next state<select id="case-transition" value={transitionStatus} onChange={(event) => setTransitionStatus(event.target.value as QmsAssuranceCaseStatus)}>{allowedTransitions.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</select></label>{selected.status === "EFFECTIVENESS_REVIEW" && closeBlock ? <p className="qms-assurance-cases__empty">Closure gate: {closeBlock}</p> : null}<label htmlFor="case-transition-reason">Reason<textarea id="case-transition-reason" value={transitionReason} onChange={(event) => setTransitionReason(event.target.value)} minLength={8} rows={3} required /></label><button type="submit" disabled={transitioning || !allowedTransitions.includes(transitionStatus) || transitionReason.trim().length < 8}>{transitioning ? "Recording…" : "Record lifecycle decision"}</button></form> : <p className="qms-assurance-cases__empty">Lifecycle decisions require Audit management permission.</p>}</section>
        </div>
      ) : null}
    </main>
  );
};

export default QmsAssurancePage;
