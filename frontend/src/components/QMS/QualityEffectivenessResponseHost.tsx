import React, { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, ClipboardCheck, PanelRightClose, PanelRightOpen, ShieldAlert } from "lucide-react";

import { getPlannerHandoffOptions } from "../../services/qmsAuditHandoff";
import {
  createEffectivenessResponse,
  decideEffectivenessResponse,
  getAssuranceCaseForResponses,
  listAssuranceCasesForResponses,
  listEffectivenessResponses,
  type EffectivenessResponseAction,
} from "../../services/qmsEffectivenessResponses";
import "../../styles/qms-effectiveness-responses.css";

type Props = { amoCode?: string };
type ActionType = EffectivenessResponseAction["action_type"];
const NON_EFFECTIVE = new Set(["INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"]);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Effectiveness response action could not be completed.";
}

const QualityEffectivenessResponseHost: React.FC<Props> = ({ amoCode = "" }) => {
  const location = useLocation();
  const workspace = new URLSearchParams(location.search).get("workspace")?.toLowerCase();
  const isAssurance = workspace === "assurance" || /\/quality\/assurance(?:\/|$)/i.test(location.pathname);
  const pathnameAmo = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1];
  const resolvedAmo = amoCode || (pathnameAmo ? decodeURIComponent(pathnameAmo) : "");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [planId, setPlanId] = useState("");
  const [actionType, setActionType] = useState<ActionType>("ADDITIONAL_ACTION");
  const [rationale, setRationale] = useState("Ineffective or inconclusive corrective action requires governed downstream response.");
  const [dueDate, setDueDate] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [targetSourceType, setTargetSourceType] = useState("");
  const [targetSourceId, setTargetSourceId] = useState("");
  const [targetRoute, setTargetRoute] = useState("");
  const [auditTitle, setAuditTitle] = useState("Effectiveness follow-up audit");
  const [auditDate, setAuditDate] = useState("");
  const [auditTime, setAuditTime] = useState("09:00");
  const [auditLocation, setAuditLocation] = useState("");
  const [auditScope, setAuditScope] = useState("");
  const [auditCriteria, setAuditCriteria] = useState("");
  const [leadAuditor, setLeadAuditor] = useState("");
  const [decisionReason, setDecisionReason] = useState("Downstream effectiveness response completed with attributable evidence.");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const casesQuery = useQuery({
    queryKey: ["qms-effectiveness-response-cases", resolvedAmo],
    queryFn: ({ signal }) => listAssuranceCasesForResponses(resolvedAmo, signal),
    enabled: Boolean(open && isAssurance && resolvedAmo),
  });
  const cases = casesQuery.data?.items || [];
  const selectedCaseId = caseId || cases[0]?.id || "";
  const caseQuery = useQuery({
    queryKey: ["qms-effectiveness-response-case", resolvedAmo, selectedCaseId],
    queryFn: ({ signal }) => getAssuranceCaseForResponses(resolvedAmo, selectedCaseId, signal),
    enabled: Boolean(open && selectedCaseId),
  });
  const plans = useMemo(
    () => (caseQuery.data?.effectiveness_plans || []).filter((plan) => NON_EFFECTIVE.has(String(plan.conclusion || ""))),
    [caseQuery.data?.effectiveness_plans],
  );
  const selectedPlanId = planId || plans[0]?.id || "";
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId);

  const responsesQuery = useQuery({
    queryKey: ["qms-effectiveness-responses", resolvedAmo, selectedCaseId],
    queryFn: ({ signal }) => listEffectivenessResponses(resolvedAmo, selectedCaseId, signal),
    enabled: Boolean(open && selectedCaseId),
  });
  const plannerOptionsQuery = useQuery({
    queryKey: ["qms-effectiveness-response-planner-options", resolvedAmo],
    queryFn: ({ signal }) => getPlannerHandoffOptions(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo && actionType === "FOLLOW_UP_AUDIT"),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-effectiveness-response-case", resolvedAmo, selectedCaseId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-effectiveness-responses", resolvedAmo, selectedCaseId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-assurance"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state"] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: () => createEffectivenessResponse(resolvedAmo, selectedCaseId, selectedPlanId, {
      action_type: actionType,
      rationale,
      target_source_type: targetSourceType || selectedPlan?.source_type || undefined,
      target_source_id: targetSourceId || selectedPlan?.source_id || undefined,
      target_route: targetRoute || selectedPlan?.source_route || undefined,
      due_date: dueDate || undefined,
      owner_user_id: ownerId || undefined,
      schedule: actionType === "FOLLOW_UP_AUDIT" ? {
        title: auditTitle,
        next_due_date: auditDate,
        start_time: auditTime,
        duration_days: 1,
        timezone_name: plannerOptionsQuery.data?.timezone_name || "Africa/Nairobi",
        location: auditLocation || undefined,
        scope: auditScope || undefined,
        criteria: auditCriteria || undefined,
        lead_auditor_user_id: leadAuditor || undefined,
        frequency: "ONE_TIME",
        allow_conflicts: false,
      } : undefined,
    }),
    onSuccess: async (row) => {
      setError("");
      setSuccess(`${row.action_type} response opened${row.schedule_id ? " and linked to the authoritative Planner" : ""}.`);
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  const decisionMutation = useMutation({
    mutationFn: ({ responseId, decision }: { responseId: string; decision: "COMPLETE" | "CANCEL" }) => decideEffectivenessResponse(resolvedAmo, selectedCaseId, responseId, decision, decisionReason),
    onSuccess: async (row) => {
      setError("");
      setSuccess(`${row.action_type} marked ${row.status}.`);
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  if (!isAssurance || !resolvedAmo) return null;
  const openResponses = (responsesQuery.data?.items || []).filter((row) => row.status === "OPEN");
  const createReady = Boolean(
    selectedCaseId && selectedPlanId && rationale.trim().length >= 8
      && (actionType !== "FOLLOW_UP_AUDIT" || (auditTitle.trim().length >= 3 && auditDate)),
  );
  const pending = createMutation.isPending || decisionMutation.isPending;

  return <>
    <button className="qms-effectiveness-response-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-effectiveness-response-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Effectiveness responses
    </button>
    {open ? <aside id="qms-effectiveness-response-panel" className="qms-effectiveness-response-panel" aria-label="Ineffective effectiveness response actions">
      <header><div><span>Effectiveness engineering</span><strong>Downstream response actions</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close effectiveness responses"><PanelRightClose size={18} /></button></header>
      <div className="qms-effectiveness-response-body">
        <p>An ineffective, partially effective or inconclusive review returns the case to action. These obligations stay open—and block assurance follow-up completion—until explicitly completed or cancelled.</p>
        {error ? <div className="qms-effectiveness-response-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-effectiveness-response-success"><CheckCircle2 size={16} /> {success}</div> : null}

        <label>Assurance case<select value={selectedCaseId} onChange={(event) => { setCaseId(event.target.value); setPlanId(""); setSuccess(""); }}><option value="">Select case</option>{cases.map((row) => <option key={row.id} value={row.id}>{row.case_ref} · {row.title}</option>)}</select></label>
        <label>Non-effective review<select value={selectedPlanId} onChange={(event) => setPlanId(event.target.value)}><option value="">Select concluded effectiveness plan</option>{plans.map((row) => <option key={row.id} value={row.id}>{row.conclusion} · {row.expected_outcome || row.id}</option>)}</select></label>
        {selectedPlan ? <div className="qms-effectiveness-response-source"><strong>{selectedPlan.conclusion}</strong><span>{selectedPlan.source_type || "Assurance source"} · {selectedPlan.source_id || "unresolved source"}</span>{selectedPlan.source_route ? <a href={selectedPlan.source_route}>Open authoritative source</a> : null}</div> : null}

        <label>Response type<select value={actionType} onChange={(event) => setActionType(event.target.value as ActionType)}><option value="ADDITIONAL_ACTION">Additional corrective action</option><option value="FOLLOW_UP_AUDIT">Follow-up audit</option><option value="REOPEN_CAR">CAR reopen obligation</option><option value="MANAGEMENT_ESCALATION">Management escalation</option><option value="RISK_REASSESSMENT">Risk reassessment</option></select></label>
        <label>Rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <div className="qms-effectiveness-response-grid"><label>Due date<input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label><label>Owner<select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}><option value="">Unassigned</option>{plannerOptionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label></div>

        {actionType !== "FOLLOW_UP_AUDIT" ? <section className="qms-effectiveness-response-card"><header><ClipboardCheck size={17} /><strong>Authoritative target</strong></header><div className="qms-effectiveness-response-grid"><label>Source type<input value={targetSourceType} onChange={(event) => setTargetSourceType(event.target.value)} placeholder={selectedPlan?.source_type || "e.g. CAR / RISK"} /></label><label>Source ID<input value={targetSourceId} onChange={(event) => setTargetSourceId(event.target.value)} placeholder={selectedPlan?.source_id || "Source identifier"} /></label></div><label>Target route<input value={targetRoute} onChange={(event) => setTargetRoute(event.target.value)} placeholder={selectedPlan?.source_route || "Owning-module route"} /></label></section> : null}

        {actionType === "FOLLOW_UP_AUDIT" ? <section className="qms-effectiveness-response-card"><header><CalendarPlus size={17} /><strong>Authoritative Planner handoff</strong></header><label>Audit title<input value={auditTitle} onChange={(event) => setAuditTitle(event.target.value)} /></label><div className="qms-effectiveness-response-grid"><label>Date<input type="date" value={auditDate} onChange={(event) => setAuditDate(event.target.value)} /></label><label>Start time<input type="time" value={auditTime} onChange={(event) => setAuditTime(event.target.value)} /></label></div><label>Lead auditor<select value={leadAuditor} onChange={(event) => setLeadAuditor(event.target.value)}><option value="">Unassigned</option>{plannerOptionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label><label>Location<input value={auditLocation} onChange={(event) => setAuditLocation(event.target.value)} /></label><label>Scope<textarea value={auditScope} onChange={(event) => setAuditScope(event.target.value)} /></label><label>Criteria<textarea value={auditCriteria} onChange={(event) => setAuditCriteria(event.target.value)} /></label></section> : null}

        <button type="button" className="qms-effectiveness-response-submit" disabled={!createReady || pending} onClick={() => createMutation.mutate()}>{actionType === "FOLLOW_UP_AUDIT" ? <CalendarPlus size={16} /> : <ClipboardCheck size={16} />} Open governed response</button>

        <section className="qms-effectiveness-response-card"><header><ClipboardCheck size={17} /><strong>Open downstream obligations</strong></header>{openResponses.length ? <>{openResponses.map((row) => <article key={row.id}><div><strong>{row.action_type}</strong><span>{row.due_date ? `Due ${row.due_date}` : "No due date"}{row.target_source_type ? ` · ${row.target_source_type}` : ""}</span></div><p>{row.rationale}</p>{row.target_route ? <a href={row.target_route}>Open target workflow</a> : null}<div className="qms-effectiveness-response-actions"><button type="button" onClick={() => decisionMutation.mutate({ responseId: row.id, decision: "COMPLETE" })} disabled={pending}>Complete</button><button type="button" onClick={() => decisionMutation.mutate({ responseId: row.id, decision: "CANCEL" })} disabled={pending}>Cancel</button></div></article>)}<label>Completion/cancellation reason<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} /></label></> : <p>No open downstream response obligations are recorded for this case.</p>}</section>
      </div>
    </aside> : null}
  </>;
};

export default QualityEffectivenessResponseHost;
