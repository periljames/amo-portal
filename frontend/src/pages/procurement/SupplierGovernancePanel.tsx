import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Plus, RefreshCw, ShieldCheck, X } from "lucide-react";

import {
  activateSupplierEvaluationTemplate,
  createSupplierEvaluation,
  createSupplierEvaluationTemplate,
  getSupplierGovernance,
  getSupplierGovernancePolicy,
  listSupplierEvaluationTemplates,
  reviewSupplierEvaluation,
  scanSupplierReevaluation,
  submitSupplierEvaluation,
  updateSupplierEvaluationResponses,
  updateSupplierGovernancePolicy,
  type SupplierEvaluation,
  type SupplierEvaluationTemplate,
  type SupplierGovernanceDetail,
  type SupplierGovernancePolicy,
} from "../../services/supplierGovernance";
import { addSupplierApprovalScope, decideProcurementSupplier } from "../../services/procurement";
import type { ProcurementSupplier } from "../../types/procurement";
import { dateLabel, humanize } from "./procurementUiModel";
import "../../styles/supplier-governance.css";

type Props = {
  amoCode: string;
  supplier: ProcurementSupplier;
  canQuality: boolean;
  currentUserId?: string | null;
  onClose: () => void;
  onChanged: () => Promise<void>;
};

type CriterionDraft = {
  key: string;
  label: string;
  weight: string;
  evidenceRequired: boolean;
  blocking: boolean;
  minimumScore: string;
};

type ResponseDraft = { answer: string; score: string; evidence: string; comment: string };

const EMPTY_CRITERION: CriterionDraft = {
  key: "",
  label: "",
  weight: "1",
  evidenceRequired: false,
  blocking: false,
  minimumScore: "",
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : "The governed supplier action failed.";
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function SupplierGovernancePanel({ amoCode, supplier, canQuality, currentUserId, onClose, onChanged }: Props) {
  const [policy, setPolicy] = useState<SupplierGovernancePolicy | null>(null);
  const [templates, setTemplates] = useState<SupplierEvaluationTemplate[]>([]);
  const [detail, setDetail] = useState<SupplierGovernanceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [riskDays, setRiskDays] = useState<Record<string, string>>({ LOW: "", MEDIUM: "", HIGH: "", CRITICAL: "" });
  const [reRules, setReRules] = useState<Record<string, string>>({ expiry: "", lookback: "", rejection: "", hold: "", due: "" });

  const [templateCode, setTemplateCode] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templateThreshold, setTemplateThreshold] = useState("");
  const [templateManualRefs, setTemplateManualRefs] = useState("");
  const [criteria, setCriteria] = useState<CriterionDraft[]>([{ ...EMPTY_CRITERION }]);
  const [activationReason, setActivationReason] = useState<Record<string, string>>({});

  const [templateId, setTemplateId] = useState("");
  const [scope, setScope] = useState({ site: "PRIMARY", category: "", family: "ALL", manufacturer: "", authority: "TENANT_QMS", restrictions: "", inspection: "STANDARD" });
  const [selectedEvaluationId, setSelectedEvaluationId] = useState("");
  const [responses, setResponses] = useState<Record<string, ResponseDraft>>({});
  const [submissionNote, setSubmissionNote] = useState("");
  const [reviewDecision, setReviewDecision] = useState("APPROVE");
  const [reviewReason, setReviewReason] = useState("");
  const [reviewConditions, setReviewConditions] = useState("");
  const [findingId, setFindingId] = useState("");
  const [carId, setCarId] = useState("");
  const [supplierDecision, setSupplierDecision] = useState("APPROVE");
  const [supplierDecisionReason, setSupplierDecisionReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextPolicy, nextTemplates, nextDetail] = await Promise.all([
        getSupplierGovernancePolicy(amoCode),
        listSupplierEvaluationTemplates(amoCode),
        getSupplierGovernance(amoCode, supplier.id),
      ]);
      setPolicy(nextPolicy);
      setTemplates(nextTemplates);
      setDetail(nextDetail);
      setTemplateId((value) => value || nextTemplates.find((item) => item.status === "ACTIVE")?.id || "");
      setSelectedEvaluationId((value) => value || nextDetail.evaluations[0]?.id || "");
      if (nextPolicy.configured && nextPolicy.risk_review_days) {
        setRiskDays(Object.fromEntries(Object.entries(nextPolicy.risk_review_days).map(([key, value]) => [key, String(value)])));
      }
      if (nextPolicy.configured && nextPolicy.re_evaluation_rules) {
        const rules = nextPolicy.re_evaluation_rules;
        setReRules({
          expiry: String(rules.expiry_lead_days ?? ""),
          lookback: String(rules.lookback_days ?? ""),
          rejection: String(rules.rejected_inspection_threshold ?? ""),
          hold: String(rules.active_hold_threshold ?? ""),
          due: String(rules.action_due_days ?? ""),
        });
      }
    } catch (caught) {
      setError(message(caught));
    } finally {
      setLoading(false);
    }
  }, [amoCode, supplier.id]);

  useEffect(() => { void load(); }, [load]);

  const selectedEvaluation = useMemo(
    () => detail?.evaluations.find((item) => item.id === selectedEvaluationId) || null,
    [detail, selectedEvaluationId],
  );
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === (selectedEvaluation?.template_id || templateId)) || null,
    [templates, selectedEvaluation?.template_id, templateId],
  );

  useEffect(() => {
    if (!selectedEvaluation || !selectedTemplate) return;
    const existing = new Map(selectedEvaluation.responses.map((item) => [item.criterion_id, item]));
    setResponses(Object.fromEntries(selectedTemplate.criteria.map((criterion) => {
      const row = existing.get(criterion.id);
      return [criterion.id, {
        answer: row?.answer == null ? "" : String(row.answer),
        score: row?.score_percent == null ? "" : String(row.score_percent),
        evidence: row?.evidence_references?.join(", ") || "",
        comment: row?.comment || "",
      }];
    })));
  }, [selectedEvaluation, selectedTemplate]);

  async function run(label: string, operation: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
      setNotice(label);
      await load();
      await onChanged();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  async function savePolicy(event: React.FormEvent) {
    event.preventDefault();
    const values = [...Object.values(riskDays), ...Object.values(reRules)];
    if (values.some((value) => !value.trim() || Number(value) <= 0)) {
      setError("Enter every tenant review interval and re-evaluation trigger threshold before saving policy.");
      return;
    }
    await run("Supplier governance policy saved.", () => updateSupplierGovernancePolicy(amoCode, {
      risk_review_days: Object.fromEntries(Object.entries(riskDays).map(([key, value]) => [key, Number(value)])),
      re_evaluation_rules: {
        expiry_lead_days: Number(reRules.expiry),
        lookback_days: Number(reRules.lookback),
        rejected_inspection_threshold: Number(reRules.rejection),
        active_hold_threshold: Number(reRules.hold),
        action_due_days: Number(reRules.due),
      },
      require_independent_review: true,
      conditional_approval_allowed: true,
    }));
  }

  async function createTemplate(event: React.FormEvent) {
    event.preventDefault();
    if (!criteria.length || criteria.some((item) => !item.key.trim() || !item.label.trim() || Number(item.weight) < 0)) {
      setError("Every evaluation criterion needs a key, label and valid weight.");
      return;
    }
    await run("Supplier evaluation template draft created.", () => createSupplierEvaluationTemplate(amoCode, {
      code: templateCode,
      name: templateName,
      pass_threshold: Number(templateThreshold),
      manual_references: templateManualRefs.split(",").map((item) => item.trim()).filter(Boolean),
      criteria: criteria.map((item, index) => ({
        criterion_key: item.key,
        sequence_no: index + 1,
        label: item.label,
        weight: Number(item.weight),
        mandatory: true,
        evidence_required: item.evidenceRequired,
        failure_is_blocking: item.blocking,
        scoring_rule: item.blocking ? { minimum_score_percent: Number(item.minimumScore) } : {},
      })),
    }));
  }

  async function startEvaluation(event: React.FormEvent) {
    event.preventDefault();
    if (!templateId || !scope.category.trim()) return;
    let created: SupplierEvaluation | null = null;
    await run("Supplier evaluation started.", async () => {
      created = await createSupplierEvaluation(amoCode, supplier.id, {
        template_id: templateId,
        intended_scope: [{
          site_code: scope.site,
          category: scope.category,
          product_family: scope.family,
          manufacturer: scope.manufacturer || null,
          authority: scope.authority,
          restrictions: scope.restrictions || null,
          incoming_inspection_level: scope.inspection,
        }],
      });
    });
    if (created) setSelectedEvaluationId((created as SupplierEvaluation).id);
  }

  async function saveResponses() {
    if (!selectedEvaluation || !selectedTemplate) return;
    const payload = selectedTemplate.criteria.map((criterion) => {
      const row = responses[criterion.id] || { answer: "", score: "", evidence: "", comment: "" };
      return {
        criterion_id: criterion.id,
        answer: row.answer,
        score_percent: numberOrNull(row.score),
        evidence_references: row.evidence.split(",").map((item) => item.trim()).filter(Boolean),
        comment: row.comment || null,
      };
    });
    await run("Evaluation responses saved.", () => updateSupplierEvaluationResponses(amoCode, selectedEvaluation.id, {
      expected_version: selectedEvaluation.version,
      responses: payload,
    }));
  }

  async function submitEvaluation() {
    if (!selectedEvaluation) return;
    await run("Evaluation submitted for independent review.", () => submitSupplierEvaluation(
      amoCode,
      selectedEvaluation.id,
      selectedEvaluation.version,
      submissionNote,
    ));
  }

  async function reviewEvaluation(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedEvaluation) return;
    await run("Independent supplier evaluation decision recorded.", () => reviewSupplierEvaluation(amoCode, selectedEvaluation.id, {
      expected_version: selectedEvaluation.version,
      decision: reviewDecision,
      rationale: reviewReason,
      conditions: reviewConditions.split("\n").map((item) => item.trim()).filter(Boolean),
      qms_finding_id: findingId || null,
      qms_car_id: carId || null,
    }));
  }

  async function createScopeFromEvaluation() {
    if (!selectedEvaluation || !selectedEvaluation.intended_scope[0]) return;
    const intended = selectedEvaluation.intended_scope[0];
    await run("Governed supplier approval scope drafted.", () => addSupplierApprovalScope(amoCode, supplier.id, {
      site_code: String(intended.site_code || "PRIMARY"),
      category: String(intended.category || ""),
      product_family: String(intended.product_family || "ALL"),
      manufacturer: intended.manufacturer || null,
      authority: String(intended.authority || "TENANT_QMS"),
      restrictions: intended.restrictions || null,
      incoming_inspection_level: String(intended.incoming_inspection_level || "STANDARD"),
      qms_evaluation_id: selectedEvaluation.id,
    }));
  }

  async function applySupplierDecision(event: React.FormEvent) {
    event.preventDefault();
    await run("Supplier lifecycle decision recorded.", () => decideProcurementSupplier(amoCode, supplier.id, {
      action: supplierDecision,
      reason: supplierDecisionReason,
    }));
  }

  if (loading && !detail) return <aside className="supplier-gov"><p>Loading governed supplier evidence…</p></aside>;

  return (
    <aside className="supplier-gov" aria-label={`Supplier governance for ${supplier.legal_name}`}>
      <header className="supplier-gov__header">
        <div><span>Governed supplier evaluation</span><h3>{supplier.legal_name}</h3><p>{supplier.supplier_code} · {humanize(supplier.risk_level)} risk · {humanize(supplier.status)}</p></div>
        <div><button type="button" onClick={() => void load()} aria-label="Refresh supplier governance"><RefreshCw size={16} /></button><button type="button" onClick={onClose} aria-label="Close supplier governance"><X size={17} /></button></div>
      </header>
      {error ? <div className="supplier-gov__message is-error" role="alert"><AlertTriangle size={17} />{error}</div> : null}
      {notice ? <div className="supplier-gov__message is-success" role="status"><CheckCircle2 size={17} />{notice}</div> : null}

      <section className="supplier-gov__summary">
        <article><strong>{policy?.configured ? `Rev ${policy.revision_no}` : "Blocked"}</strong><span>Tenant policy</span></article>
        <article><strong>{detail?.current_evaluation?.score ?? "—"}</strong><span>Current score</span></article>
        <article><strong>{dateLabel(detail?.current_evaluation?.valid_until)}</strong><span>Evaluation validity</span></article>
        <article><strong>{detail?.re_evaluation_actions.filter((item) => item.status === "OPEN").length || 0}</strong><span>Re-evaluation actions</span></article>
      </section>

      {!policy?.configured ? (
        <section className="supplier-gov__section is-attention"><header><ShieldCheck size={18} /><div><h4>Tenant supplier policy required</h4><p>No portal default is applied. Quality must set the approved risk intervals and surveillance triggers.</p></div></header>{canQuality ? <form className="supplier-gov__grid" onSubmit={savePolicy}>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((risk) => <label key={risk}>{humanize(risk)} review days<input type="number" min="1" value={riskDays[risk]} onChange={(event) => setRiskDays((current) => ({ ...current, [risk]: event.target.value }))} required /></label>)}<label>Expiry lead days<input type="number" min="0" value={reRules.expiry} onChange={(event) => setReRules((current) => ({ ...current, expiry: event.target.value }))} required /></label><label>Receiving lookback days<input type="number" min="1" value={reRules.lookback} onChange={(event) => setReRules((current) => ({ ...current, lookback: event.target.value }))} required /></label><label>Rejected inspections trigger<input type="number" min="1" value={reRules.rejection} onChange={(event) => setReRules((current) => ({ ...current, rejection: event.target.value }))} required /></label><label>Active holds trigger<input type="number" min="1" value={reRules.hold} onChange={(event) => setReRules((current) => ({ ...current, hold: event.target.value }))} required /></label><label>Action due days<input type="number" min="1" value={reRules.due} onChange={(event) => setReRules((current) => ({ ...current, due: event.target.value }))} required /></label><footer><button type="submit" disabled={busy}>Save governed tenant policy</button></footer></form> : <p>Quality Manager access is required to configure this tenant policy.</p>}</section>
      ) : null}

      {policy?.configured && canQuality ? <section className="supplier-gov__section"><header><ClipboardCheck size={18} /><div><h4>Evaluation templates</h4><p>Templates are revisioned. A different Quality reviewer must activate a draft.</p></div></header><form onSubmit={createTemplate} className="supplier-gov__grid"><label>Template code<input value={templateCode} onChange={(event) => setTemplateCode(event.target.value)} required /></label><label>Template name<input value={templateName} onChange={(event) => setTemplateName(event.target.value)} required /></label><label>Pass threshold %<input type="number" min="0" max="100" value={templateThreshold} onChange={(event) => setTemplateThreshold(event.target.value)} required /></label><label>Manual references<input value={templateManualRefs} onChange={(event) => setTemplateManualRefs(event.target.value)} placeholder="MPM 3.4, QMSM 8.4" /></label><div className="supplier-gov__criteria">{criteria.map((criterion, index) => <div key={index} className="supplier-gov__criterion"><label>Criterion key<input value={criterion.key} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, key: event.target.value } : item))} required /></label><label>Criterion label<input value={criterion.label} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, label: event.target.value } : item))} required /></label><label>Weight<input type="number" min="0" step="0.1" value={criterion.weight} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, weight: event.target.value } : item))} required /></label><label className="supplier-gov__check"><input type="checkbox" checked={criterion.evidenceRequired} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, evidenceRequired: event.target.checked } : item))} />Evidence required</label><label className="supplier-gov__check"><input type="checkbox" checked={criterion.blocking} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, blocking: event.target.checked } : item))} />Blocking criterion</label>{criterion.blocking ? <label>Minimum score %<input type="number" min="0" max="100" value={criterion.minimumScore} onChange={(event) => setCriteria((current) => current.map((item, row) => row === index ? { ...item, minimumScore: event.target.value } : item))} required /></label> : null}{criteria.length > 1 ? <button type="button" onClick={() => setCriteria((current) => current.filter((_, row) => row !== index))}>Remove criterion</button> : null}</div>)}</div><footer><button type="button" onClick={() => setCriteria((current) => [...current, { ...EMPTY_CRITERION }])}><Plus size={15} />Add criterion</button><button type="submit" disabled={busy || !templateThreshold}>Create revisioned template</button></footer></form><div className="supplier-gov__records">{templates.map((item) => <article key={item.id}><div><strong>{item.code} · Rev {item.revision_no}</strong><span>{item.name} · threshold {String(item.pass_threshold ?? "not set")}%</span></div><span>{humanize(item.status)}</span>{item.status === "DRAFT" ? <div><input value={activationReason[item.id] || ""} onChange={(event) => setActivationReason((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Independent activation rationale" /><button type="button" disabled={busy || (activationReason[item.id] || "").trim().length < 8} onClick={() => void run("Template activated.", () => activateSupplierEvaluationTemplate(amoCode, item.id, activationReason[item.id] || ""))}>Activate</button></div> : null}</article>)}</div></section> : null}

      {policy?.configured ? <section className="supplier-gov__section"><header><ClipboardCheck size={18} /><div><h4>Start scoped evaluation</h4><p>Scope is frozen with the template and tenant-policy revision used for this assessment.</p></div></header><form onSubmit={startEvaluation} className="supplier-gov__grid"><label>Active template<select value={templateId} onChange={(event) => setTemplateId(event.target.value)} required><option value="">Select active template</option>{templates.filter((item) => item.status === "ACTIVE").map((item) => <option key={item.id} value={item.id}>{item.code} · Rev {item.revision_no} · {item.name}</option>)}</select></label><label>Site code<input value={scope.site} onChange={(event) => setScope((current) => ({ ...current, site: event.target.value }))} required /></label><label>Category<input value={scope.category} onChange={(event) => setScope((current) => ({ ...current, category: event.target.value }))} required /></label><label>Product family<input value={scope.family} onChange={(event) => setScope((current) => ({ ...current, family: event.target.value }))} required /></label><label>Manufacturer<input value={scope.manufacturer} onChange={(event) => setScope((current) => ({ ...current, manufacturer: event.target.value }))} /></label><label>Authority<input value={scope.authority} onChange={(event) => setScope((current) => ({ ...current, authority: event.target.value }))} required /></label><label>Incoming inspection level<input value={scope.inspection} onChange={(event) => setScope((current) => ({ ...current, inspection: event.target.value }))} required /></label><label>Restrictions<textarea rows={2} value={scope.restrictions} onChange={(event) => setScope((current) => ({ ...current, restrictions: event.target.value }))} /></label><footer><button type="submit" disabled={busy || !templateId || !scope.category.trim()}>Start evaluation</button></footer></form></section> : null}

      {detail?.evaluations.length ? <section className="supplier-gov__section"><header><ClipboardCheck size={18} /><div><h4>Evaluation record</h4><p>Responses, scores, evidence and decisions are retained against the frozen revision.</p></div></header><label>Evaluation<select value={selectedEvaluationId} onChange={(event) => setSelectedEvaluationId(event.target.value)}>{detail.evaluations.map((item) => <option key={item.id} value={item.id}>{humanize(item.status)} · {item.score ?? "unscored"} · {item.id.slice(0, 8)}</option>)}</select></label>{selectedEvaluation && selectedTemplate ? <><div className="supplier-gov__evaluation-head"><span>{selectedTemplate.code} · Rev {selectedEvaluation.template_revision_no}</span><strong>{humanize(selectedEvaluation.status)}</strong><span>Version {selectedEvaluation.version}</span></div>{["DRAFT", "RETURNED"].includes(selectedEvaluation.status) ? <div className="supplier-gov__responses">{selectedTemplate.criteria.map((criterion) => { const row = responses[criterion.id] || { answer: "", score: "", evidence: "", comment: "" }; return <article key={criterion.id}><header><strong>{criterion.sequence_no}. {criterion.label}</strong><span>{criterion.evidence_required ? "Evidence required" : "Evidence optional"}{criterion.failure_is_blocking ? " · blocking" : ""}</span></header><label>Assessment response<textarea rows={2} value={row.answer} onChange={(event) => setResponses((current) => ({ ...current, [criterion.id]: { ...row, answer: event.target.value } }))} required={criterion.mandatory} /></label><label>Criterion score %<input type="number" min="0" max="100" value={row.score} onChange={(event) => setResponses((current) => ({ ...current, [criterion.id]: { ...row, score: event.target.value } }))} required={Number(criterion.weight) > 0} /></label><label>Evidence references<input value={row.evidence} onChange={(event) => setResponses((current) => ({ ...current, [criterion.id]: { ...row, evidence: event.target.value } }))} placeholder="Document IDs / references, comma separated" required={criterion.evidence_required} /></label><label>Comment<textarea rows={2} value={row.comment} onChange={(event) => setResponses((current) => ({ ...current, [criterion.id]: { ...row, comment: event.target.value } }))} /></label></article>; })}<footer><button type="button" disabled={busy} onClick={() => void saveResponses()}>Save responses</button><label>Submission note<textarea rows={2} value={submissionNote} onChange={(event) => setSubmissionNote(event.target.value)} /></label><button type="button" disabled={busy} onClick={() => void submitEvaluation()}>Submit for independent review</button></footer></div> : null}{selectedEvaluation.status === "SUBMITTED" && canQuality ? <form className="supplier-gov__grid is-review" onSubmit={reviewEvaluation}><label>Independent decision<select value={reviewDecision} onChange={(event) => setReviewDecision(event.target.value)}><option value="APPROVE">Approve</option><option value="CONDITIONALLY_APPROVE">Conditionally approve</option><option value="REJECT">Reject</option><option value="RETURN">Return for correction</option></select></label><label>Decision rationale<textarea rows={3} minLength={8} value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} required /></label>{reviewDecision === "CONDITIONALLY_APPROVE" ? <label>Conditions, one per line<textarea rows={3} value={reviewConditions} onChange={(event) => setReviewConditions(event.target.value)} required /></label> : null}<label>Canonical QMS finding ID<input value={findingId} onChange={(event) => setFindingId(event.target.value)} /></label><label>Canonical QMS CAR ID<input value={carId} onChange={(event) => setCarId(event.target.value)} /></label>{currentUserId && [selectedEvaluation.created_by_user_id, selectedEvaluation.submitted_by_user_id].includes(currentUserId) ? <p className="supplier-gov__warning">Independent review must be completed by a different authorized Quality user.</p> : <footer><button type="submit" disabled={busy || reviewReason.trim().length < 8}>Record independent decision</button></footer>}</form> : null}{["APPROVED", "CONDITIONALLY_APPROVED"].includes(selectedEvaluation.status) ? <div className="supplier-gov__activation"><button type="button" disabled={busy} onClick={() => void createScopeFromEvaluation()}>Draft approval scope from evaluated scope</button><form onSubmit={applySupplierDecision}><label>Supplier decision<select value={supplierDecision} onChange={(event) => setSupplierDecision(event.target.value)}><option value="APPROVE">Approve</option><option value="CONDITIONALLY_APPROVE">Conditionally approve</option><option value="REACTIVATE">Reactivate</option></select></label><label>Decision rationale<textarea minLength={8} rows={2} value={supplierDecisionReason} onChange={(event) => setSupplierDecisionReason(event.target.value)} required /></label><button type="submit" disabled={busy || supplierDecisionReason.trim().length < 8}>Record supplier decision</button></form></div> : null}</> : null}</section> : null}

      {canQuality ? <section className="supplier-gov__section"><header><RefreshCw size={18} /><div><h4>Re-evaluation surveillance</h4><p>Scan actual receiving rejection, active supplier-hold and evaluation-expiry signals against the tenant policy.</p></div></header><button type="button" disabled={busy || !policy?.configured} onClick={() => void run("Re-evaluation surveillance scan completed.", () => scanSupplierReevaluation(amoCode))}>Run governed re-evaluation scan</button>{detail?.re_evaluation_actions.length ? <div className="supplier-gov__records">{detail.re_evaluation_actions.map((item) => <article key={item.id}><div><strong>{humanize(item.trigger_type)}</strong><span>Due {dateLabel(item.due_on)}</span></div><span>{humanize(item.status)}</span></article>)}</div> : <p>No materialized re-evaluation actions are recorded for this supplier.</p>}</section> : null}
    </aside>
  );
}
