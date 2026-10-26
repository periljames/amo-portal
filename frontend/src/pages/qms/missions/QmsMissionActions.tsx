import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hasQmsRolePermission } from "../../../app/routeGuards";
import { listMissionReadinessEvidence, listMissionAuthorityEvidence, updateQmsMission, updateQmsMissionGate, recordQmsMissionDecision, type QmsMission, type QmsMissionGate, type QmsMissionGatePatch, type QmsMissionDecisionCreate } from "../../../services/qmsMissions";
import QmsChangeDelivery from "./QmsChangeDelivery";
import { clearMissionDraft, useMissionDraft } from "./useMissionDraft";
import { qmsListAuditPersonnelOptions } from "../../../services/qmsCore";
import { getCachedUser } from "../../../services/auth";
import "../../../styles/qms/workspace.css";

export default function QmsMissionActions({ amoCode, mission }: { amoCode: string; mission: QmsMission }) {
  const client = useQueryClient();
  const canManage = hasQmsRolePermission("qms.change.manage");
  const governed = mission.scope.change_workflow_version === 2;
  const mutable = ["PLANNING", "IN_PROGRESS", "GATE_REVIEW"].includes(mission.status);
  const people = useQuery({ queryKey: ["qms-mission-people", amoCode], queryFn: () => qmsListAuditPersonnelOptions(amoCode, { limit: 1000, auditorsOnly: false }), enabled: canManage });
  const [assignment, setAssignment] = useMissionDraft(amoCode, mission, "assignment", { owner_user_id: mission.owner_user_id || null, sponsor_user_id: mission.sponsor_user_id || null, target_date: mission.target_date || null });
  const [gate, setGate] = useMissionDraft<QmsMissionGate | null>(amoCode, mission, "gate", null);
  const [patch, setPatch] = useMissionDraft<QmsMissionGatePatch>(amoCode, mission, "gate-patch", {});
  const stages: Partial<Record<QmsMission["status"], QmsMissionDecisionCreate["decision_type"]>> = { GATE_REVIEW: "QUALITY_SELF_EVALUATION", READY_FOR_APPROVAL: "ACCOUNTABLE_EXECUTIVE", APPROVED: "AUTHORITY_SUBMISSION", SUBMITTED_TO_AUTHORITY: "AUTHORITY_ACCEPTANCE" };
  const action = mission.next_action === undefined ? stages[mission.status] : mission.next_action;
  const nextStage = action && !["IMPLEMENTATION", "EFFECTIVENESS_REVIEW"].includes(action) ? action as QmsMissionDecisionCreate["decision_type"] : undefined;
  const [decision, setDecision] = useMissionDraft<QmsMissionDecisionCreate>(amoCode, mission, "decision", { decision_type: nextStage || "QUALITY_SELF_EVALUATION", status: "APPROVED", rationale: "" });
  const [evidenceSearch, setEvidenceSearch] = useMissionDraft(amoCode, mission, "readiness-search", "");
  const [evidenceQuery, setEvidenceQuery] = useState("");
  useEffect(() => { const timer = window.setTimeout(() => setEvidenceQuery(evidenceSearch.trim()), 250); return () => window.clearTimeout(timer); }, [evidenceSearch]);
  const authorityStage = ["AUTHORITY_SUBMISSION", "AUTHORITY_ACCEPTANCE"].includes(decision.decision_type);
  const evidence = useQuery({ queryKey: ["qms-mission-authority-evidence", amoCode, mission.id, evidenceQuery], queryFn: () => listMissionAuthorityEvidence(amoCode, mission.id, evidenceQuery), enabled: canManage && authorityStage && Boolean(nextStage) });
  const readinessEvidence = useQuery({ queryKey: ["qms-mission-readiness-evidence", amoCode, mission.id, evidenceQuery], queryFn: () => listMissionReadinessEvidence(amoCode, mission.id, evidenceQuery), enabled: canManage && governed && Boolean(gate) });
  const mutation = useMutation({
    mutationFn: (action: "assignment" | "gate" | "decision") => action === "assignment" ? updateQmsMission(amoCode, mission.id, { ...assignment, expected_updated_at: mission.updated_at }) : action === "gate" && gate
      ? updateQmsMissionGate(amoCode, mission.id, gate.id, { ...patch, expected_updated_at: mission.updated_at })
      : recordQmsMissionDecision(amoCode, mission.id, { ...decision, expected_updated_at: mission.updated_at }),
    onSuccess: async updated => {
      clearMissionDraft(amoCode, mission);
      client.setQueryData(["qms-mission", amoCode, mission.id], updated);
      setGate(null); setDecision(value => ({ ...value, rationale: "" }));
      await client.invalidateQueries({ queryKey: ["qms-missions", amoCode.trim().toLowerCase()] });
    },
  });
  const personnelOptions = Array.isArray(people.data) ? people.data : [];
  const personnelContractInvalid = Boolean(people.data && !Array.isArray(people.data));
  if (!canManage) return null;
  const actor = getCachedUser()?.id;
  const canDecide = actor === (decision.decision_type === "ACCOUNTABLE_EXECUTIVE" ? mission.sponsor_user_id : mission.owner_user_id);
  return <section className="qms-personal-tasks" aria-label="Mission actions">
    <h2>Resolve readiness & record decisions</h2>
    {governed ? <QmsChangeDelivery amoCode={amoCode} mission={mission}/> : null}
    {mutation.error ? <p role="alert">{mutation.error.message}</p> : null}
    {people.error ? <p role="alert">{people.error.message}</p> : null}
    {personnelContractInvalid ? <p role="alert">Personnel options could not be validated. Assignment is unavailable until a valid personnel list is loaded.</p> : null}
    {mutable ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("assignment"); }}>
      <label>Quality owner<select value={assignment.owner_user_id || ""} onChange={event => setAssignment({ ...assignment, owner_user_id: event.target.value || null })}><option value="">Not assigned</option>{personnelOptions.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      <label>Accountable Executive<select value={assignment.sponsor_user_id || ""} onChange={event => setAssignment({ ...assignment, sponsor_user_id: event.target.value || null })}><option value="">Not assigned</option>{personnelOptions.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      <label>Target date<input type="date" value={assignment.target_date || ""} onChange={event => setAssignment({ ...assignment, target_date: event.target.value || null })} /></label>
      <button type="submit" disabled={mutation.isPending || people.isLoading || people.isError || personnelContractInvalid}>Save ownership & target</button>
    </form> : null}
    {mutable ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("gate"); }}>
      <label>Readiness gate<select required value={gate?.id || ""} onChange={event => {
        const next = mission.gates?.find(item => item.id === event.target.value) || null;
        setGate(next); setPatch(next ? { status: next.status, evidence_status: next.evidence_status, source_id: next.source_id, source_type: next.source_type, source_route: next.source_route, source_snapshot: next.source_snapshot, due_date: next.due_date, blocking_reason: next.blocking_reason } : {});
      }}><option value="">Choose a gate</option>{mission.gates?.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      {gate ? <>
        <label>Status<select value={patch.status} onChange={event => setPatch({ ...patch, status: event.target.value as QmsMissionGatePatch["status"] })}>{["PENDING", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Evidence<select value={patch.evidence_status} onChange={event => setPatch({ ...patch, evidence_status: event.target.value as QmsMissionGatePatch["evidence_status"] })}>{["UNLINKED", "LINKED", "VERIFIED", "REJECTED", "EXPIRED"].map(value => <option key={value}>{value}</option>)}</select></label>
        {governed ? <>
          <label>Find readiness evidence<input type="search" value={evidenceSearch} onChange={event => setEvidenceSearch(event.target.value)}/></label>
          <label>Retained readiness evidence<select required={patch.status === "PASS"} value={patch.source_id || ""} onChange={event => setPatch({ ...patch, source_type: "DOCUMENT_EVIDENCE", source_id: event.target.value || null })}><option value="">Select retained evidence</option>{readinessEvidence.data?.items.map(item => <option key={item.asset_id} value={item.asset_id}>{item.filename}</option>)}</select></label>
          <label>Readiness review findings<textarea required={patch.status === "PASS"} minLength={10} maxLength={4000} value={String(patch.source_snapshot?.review_note || "")} onChange={event => setPatch({ ...patch, source_snapshot: { review_note: event.target.value } })}/></label>
          {readinessEvidence.error ? <p role="alert">{readinessEvidence.error.message}</p> : null}
        </> : <><label>Source type<input value={patch.source_type || ""} onChange={event => setPatch({ ...patch, source_type: event.target.value || null })} /></label>
        <label>Source record<input value={patch.source_id || ""} onChange={event => setPatch({ ...patch, source_id: event.target.value || null })} /></label>
        <label>Source link<input pattern="/[^/].*" value={patch.source_route || ""} onChange={event => setPatch({ ...patch, source_route: event.target.value || null })} /></label>
        </>}
        <label>Due date<input type="date" value={patch.due_date || ""} onChange={event => setPatch({ ...patch, due_date: event.target.value || null })} /></label>
        <label>Blocker / next action<textarea value={patch.blocking_reason || ""} onChange={event => setPatch({ ...patch, blocking_reason: event.target.value || null })} /></label>
        {patch.status === "PASS" && (patch.evidence_status !== "VERIFIED" || !patch.source_id?.trim()) ? <p role="status">Link and verify the source evidence before passing this gate.</p> : null}
        <button type="submit" disabled={mutation.isPending || (patch.status === "PASS" && (patch.evidence_status !== "VERIFIED" || !patch.source_id?.trim() || (governed && String(patch.source_snapshot?.review_note || "").trim().length < 10))) || (["FAIL", "BLOCKED"].includes(patch.status || "") && !patch.blocking_reason?.trim())}>Save gate</button>
      </> : null}
    </form> : null}
    {nextStage ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("decision"); }}>
      <label>Decision stage<input readOnly value={decision.decision_type.replaceAll("_", " ")} /></label>
      <label>Outcome<select value={decision.status} onChange={event => setDecision({ ...decision, status: event.target.value as QmsMissionDecisionCreate["status"] })}>{["APPROVED", "REJECTED", "RETURNED"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Rationale<textarea required minLength={3} value={decision.rationale} onChange={event => setDecision({ ...decision, rationale: event.target.value })} /></label>
      {governed && decision.decision_type === "AUTHORITY_SUBMISSION" ? <label>Written notification date<input type="date" max={new Date().toISOString().slice(0, 10)} required={decision.status === "APPROVED"} value={decision.notified_on || ""} onChange={event => setDecision({ ...decision, notified_on: event.target.value || undefined })}/></label> : null}
      {authorityStage ? <>
        <label>Find Authority correspondence<input type="search" value={evidenceSearch} onChange={event => { setEvidenceSearch(event.target.value); setDecision({ ...decision, evidence_asset_id: undefined }); }}/></label>
        <label>Retained Authority evidence<select required={decision.status === "APPROVED"} value={decision.evidence_asset_id || ""} onChange={event => setDecision({ ...decision, evidence_asset_id: event.target.value || undefined })}><option value="">Select retained correspondence</option>{evidence.data?.items.map(item => <option key={item.asset_id} value={item.asset_id}>{item.filename}</option>)}</select></label>
        {evidence.error ? <p role="alert">{evidence.error.message}</p> : null}
        {!evidence.isLoading && !evidence.data?.items.length ? <p>Retain the correspondence as Authority evidence in Document Control, then select it here.</p> : null}
      </> : null}
      <button type="submit" disabled={mutation.isPending || !canDecide || decision.rationale.trim().length < 3 || (authorityStage && decision.status === "APPROVED" && (!decision.evidence_asset_id || (governed && decision.decision_type === "AUTHORITY_SUBMISSION" && !decision.notified_on)))}>Record decision</button>
      {!canDecide ? <p>The assigned {decision.decision_type === "ACCOUNTABLE_EXECUTIVE" ? "Accountable Executive" : "Quality owner"} must record this decision.</p> : null}
    </form> : !["IMPLEMENTATION", "EFFECTIVENESS_REVIEW"].includes(action || "") ? <p>{["COMPLETE", "CANCELLED"].includes(mission.status) ? "Decision chain closed." : "Complete and verify the readiness gates before recording an approval."}</p> : null}
  </section>;
}
