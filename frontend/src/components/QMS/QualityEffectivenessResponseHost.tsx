import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, ClipboardCheck, ShieldAlert } from "lucide-react";

import { getPlannerHandoffOptions } from "../../services/qmsAuditHandoff";
import {
  createEffectivenessResponse,
  decideEffectivenessResponse,
  listEffectivenessResponses,
  type EffectivenessResponseAction,
} from "../../services/qmsEffectivenessResponses";
import "../../styles/qms-effectiveness-responses.css";
import type { QmsEffectivenessPlan } from "../../services/qmsAssuranceCases";

type Props = { amoCode: string; caseId: string; effectivenessPlans: QmsEffectivenessPlan[]; canManage: boolean; onChanged: () => Promise<void> };
type ActionType = EffectivenessResponseAction["action_type"];
const NON_EFFECTIVE = new Set(["INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"]);


function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Effectiveness response action could not be completed.";
}

const QualityEffectivenessResponseHost: React.FC<Props> = ({ amoCode: resolvedAmo, caseId: selectedCaseId, effectivenessPlans, canManage, onChanged }) => {
  const queryClient = useQueryClient();
  const [planId, setPlanId] = useState("");
  const [actionType, setActionType] = useState<ActionType>("ADDITIONAL_ACTION");
  const [rationale, setRationale] = useState("");
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
  const [decisionReason, setDecisionReason] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const plans = useMemo(
    () => effectivenessPlans.filter((plan) => plan.status === "CONCLUDED" && NON_EFFECTIVE.has(String(plan.conclusion || ""))),
    [effectivenessPlans],
  );
  const selectedPlanId = planId || plans[0]?.id || "";
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId);

  const responsesQuery = useQuery({
    queryKey: ["qms-effectiveness-responses", resolvedAmo, selectedCaseId],
    queryFn: ({ signal }) => listEffectivenessResponses(resolvedAmo, selectedCaseId, signal),
    enabled: Boolean(resolvedAmo && selectedCaseId),
  });
  const plannerOptionsQuery = useQuery({
    queryKey: ["qms-effectiveness-response-planner-options", resolvedAmo],
    queryFn: ({ signal }) => getPlannerHandoffOptions(resolvedAmo, signal),
    enabled: Boolean(resolvedAmo && selectedCaseId && canManage),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-effectiveness-responses", resolvedAmo, selectedCaseId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-assurance"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-car-control-loop"] }),
    ]);
    await onChanged();
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
      if (row.action_type === "REOPEN_CAR" && row.consequence) {
        const reset = (row.consequence.reset_milestones || [])
          .map((milestone) => milestone.milestone_key.replaceAll("_", " ").toLowerCase())
          .join(", ");
        setSuccess(
          `CAR ${row.consequence.car_number || row.consequence.car_id} reopened ${row.consequence.prior_status ? `from ${row.consequence.prior_status} ` : ""}to ${row.consequence.status}; CAPA is ${row.consequence.capa_status || "active"} and requires fresh effectiveness evidence${reset ? `. Reopened milestones: ${reset}.` : "."}`,
        );
      } else {
        setSuccess(`${row.action_type} marked ${row.status}.`);
      }
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  if (!resolvedAmo || !selectedCaseId) return null;
  if (!plans.length && !responsesQuery.data?.items.length && !responsesQuery.error) return null;
  const openResponses = (responsesQuery.data?.items || []).filter((row) => row.status === "OPEN");
  const createReady = Boolean(
    canManage && selectedCaseId && selectedPlanId && rationale.trim().length >= 8
      && (actionType !== "FOLLOW_UP_AUDIT" || (auditTitle.trim().length >= 3 && auditDate)),
  );
  const pending = createMutation.isPending || decisionMutation.isPending;

  return <section id="effectiveness-follow-up" className="qms-effectiveness-response-panel" aria-label="Effectiveness follow-up actions">
      <header><div><h3>Follow-up after an unsuccessful review</h3><p>Record the response to the selected case ineffective, partially effective or inconclusive conclusion.</p></div></header>
      <div className="qms-effectiveness-response-body">
        <p>An ineffective, partially effective or inconclusive review returns the case to action. These obligations stay open—and block assurance follow-up completion—until explicitly completed or cancelled.</p>
        {error ? <div className="qms-effectiveness-response-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-effectiveness-response-success"><CheckCircle2 size={16} /> {success}</div> : null}

        {canManage && plans.length ? <fieldset disabled={pending}>
        <label>Non-effective review<select value={selectedPlanId} onChange={(event) => setPlanId(event.target.value)}><option value="">Select concluded effectiveness plan</option>{plans.map((row) => <option key={row.id} value={row.id}>{row.conclusion} · {row.expected_outcome || row.id}</option>)}</select></label>
        {selectedPlan ? <div className="qms-effectiveness-response-source"><strong>{selectedPlan.conclusion}</strong><span>{selectedPlan.source_type || "Assurance source"} · {selectedPlan.source_id || "unresolved source"}</span>{selectedPlan.source_route ? <a href={selectedPlan.source_route}>Open authoritative source</a> : null}</div> : null}

        <label>Response type<select value={actionType} onChange={(event) => setActionType(event.target.value as ActionType)}><option value="ADDITIONAL_ACTION">Additional corrective action</option><option value="FOLLOW_UP_AUDIT">Follow-up audit</option><option value="REOPEN_CAR">CAR reopen obligation</option><option value="MANAGEMENT_ESCALATION">Management escalation</option><option value="RISK_REASSESSMENT">Risk reassessment</option></select></label>
        <label>Rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <div className="qms-effectiveness-response-grid"><label>Due date<input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label><label>Owner<select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}><option value="">Unassigned</option>{plannerOptionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label></div>

        {actionType !== "FOLLOW_UP_AUDIT" ? <section className="qms-effectiveness-response-card"><header><ClipboardCheck size={17} /><strong>Authoritative target</strong></header><div className="qms-effectiveness-response-grid"><label>Source type<input value={targetSourceType} onChange={(event) => setTargetSourceType(event.target.value)} placeholder={selectedPlan?.source_type || "e.g. CAR / RISK"} /></label><label>Source ID<input value={targetSourceId} onChange={(event) => setTargetSourceId(event.target.value)} placeholder={selectedPlan?.source_id || "Source identifier"} /></label></div><label>Target route<input value={targetRoute} onChange={(event) => setTargetRoute(event.target.value)} placeholder={selectedPlan?.source_route || "Owning-module route"} /></label></section> : null}

        {actionType === "FOLLOW_UP_AUDIT" ? <section className="qms-effectiveness-response-card"><header><CalendarPlus size={17} /><strong>Authoritative Planner handoff</strong></header><label>Audit title<input value={auditTitle} onChange={(event) => setAuditTitle(event.target.value)} /></label><div className="qms-effectiveness-response-grid"><label>Date<input type="date" value={auditDate} onChange={(event) => setAuditDate(event.target.value)} /></label><label>Start time<input type="time" value={auditTime} onChange={(event) => setAuditTime(event.target.value)} /></label></div><label>Lead auditor<select value={leadAuditor} onChange={(event) => setLeadAuditor(event.target.value)}><option value="">Unassigned</option>{plannerOptionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label><label>Location<input value={auditLocation} onChange={(event) => setAuditLocation(event.target.value)} /></label><label>Scope<textarea value={auditScope} onChange={(event) => setAuditScope(event.target.value)} /></label><label>Criteria<textarea value={auditCriteria} onChange={(event) => setAuditCriteria(event.target.value)} /></label></section> : null}

        <button type="button" className="qms-effectiveness-response-submit" disabled={!createReady || pending} onClick={() => createMutation.mutate()}>{actionType === "FOLLOW_UP_AUDIT" ? <CalendarPlus size={16} /> : <ClipboardCheck size={16} />} Open governed response</button>

        </fieldset> : <p>{!canManage ? "Changes require CAR management permission and an active case." : "Follow-up actions become available after an ineffective, partially effective or inconclusive review."}</p>}
        {responsesQuery.error || plannerOptionsQuery.error ? <p role="alert">{errorMessage(responsesQuery.error || plannerOptionsQuery.error)}</p> : null}
        <section className="qms-effectiveness-response-card"><header><ClipboardCheck size={17} /><strong>Open downstream obligations</strong></header>{openResponses.length ? <>{openResponses.map((row) => <article key={row.id}><div><strong>{row.action_type}</strong><span>{row.due_date ? `Due ${row.due_date}` : "No due date"}{row.target_source_type ? ` · ${row.target_source_type}` : ""}</span></div><p>{row.rationale}</p>{row.target_route ? <a href={row.target_route}>Open target workflow</a> : null}<div className="qms-effectiveness-response-actions"><button type="button" onClick={() => decisionMutation.mutate({ responseId: row.id, decision: "COMPLETE" })} disabled={!canManage || pending || decisionReason.trim().length < 8}>Complete</button><button type="button" onClick={() => decisionMutation.mutate({ responseId: row.id, decision: "CANCEL" })} disabled={!canManage || pending || decisionReason.trim().length < 8}>Cancel</button></div></article>)}<label>Completion/cancellation reason<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} /><small>Enter at least 8 characters. The decision and reason are retained in the governed response history.</small></label></> : <p>No open downstream response obligations are recorded for this case.</p>}</section>
      </div>
    </section>;
};

export default QualityEffectivenessResponseHost;
