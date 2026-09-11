import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hasQmsRolePermission } from "../../../app/routeGuards";
import { updateQmsMission, updateQmsMissionGate, recordQmsMissionDecision, type QmsMission, type QmsMissionGate, type QmsMissionGatePatch, type QmsMissionDecisionCreate } from "../../../services/qmsMissions";
import { qmsListAuditPersonnelOptions } from "../../../services/qmsCore";
import { getCachedUser } from "../../../services/auth";
import "../../../styles/qms/workspace.css";

export default function QmsMissionActions({ amoCode, mission }: { amoCode: string; mission: QmsMission }) {
  const client = useQueryClient();
  const canManage = hasQmsRolePermission("qms.change.manage");
  const mutable = ["PLANNING", "IN_PROGRESS", "GATE_REVIEW"].includes(mission.status);
  const people = useQuery({ queryKey: ["qms-mission-people", amoCode], queryFn: () => qmsListAuditPersonnelOptions(amoCode, { limit: 100 }), enabled: canManage });
  const [assignment, setAssignment] = useState({ owner_user_id: mission.owner_user_id || null, sponsor_user_id: mission.sponsor_user_id || null, target_date: mission.target_date || null });
  const [gate, setGate] = useState<QmsMissionGate | null>(null);
  const [patch, setPatch] = useState<QmsMissionGatePatch>({});
  const [decision, setDecision] = useState<QmsMissionDecisionCreate>({ decision_type: "QUALITY_SELF_EVALUATION", status: "APPROVED", rationale: "" });
  const mutation = useMutation({
    mutationFn: (action: "assignment" | "gate" | "decision") => action === "assignment" ? updateQmsMission(amoCode, mission.id, assignment) : action === "gate" && gate
      ? updateQmsMissionGate(amoCode, mission.id, gate.id, patch)
      : recordQmsMissionDecision(amoCode, mission.id, decision),
    onSuccess: async updated => {
      client.setQueryData(["qms-mission", amoCode, mission.id], updated);
      setGate(null); setDecision(value => ({ ...value, rationale: "" }));
      await client.invalidateQueries({ queryKey: ["qms-missions", amoCode] });
    },
  });
  if (!canManage) return null;
  const actor = getCachedUser()?.id;
  const canDecide = actor === (decision.decision_type === "ACCOUNTABLE_EXECUTIVE" ? mission.sponsor_user_id : mission.owner_user_id);
  return <section className="qms-personal-tasks" aria-label="Mission actions">
    <h2>Resolve readiness & record decisions</h2>
    {mutation.error ? <p role="alert">{mutation.error.message}</p> : null}
    {people.error ? <p role="alert">{people.error.message}</p> : null}
    {mutable ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("assignment"); }}>
      <label>Quality owner<select value={assignment.owner_user_id || ""} onChange={event => setAssignment({ ...assignment, owner_user_id: event.target.value || null })}><option value="">Not assigned</option>{people.data?.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      <label>Accountable Executive<select value={assignment.sponsor_user_id || ""} onChange={event => setAssignment({ ...assignment, sponsor_user_id: event.target.value || null })}><option value="">Not assigned</option>{people.data?.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      <label>Target date<input type="date" value={assignment.target_date || ""} onChange={event => setAssignment({ ...assignment, target_date: event.target.value || null })} /></label>
      <button type="submit" disabled={mutation.isPending || people.isLoading || people.isError}>Save ownership & target</button>
    </form> : null}
    {mutable ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("gate"); }}>
      <label>Readiness gate<select required value={gate?.id || ""} onChange={event => {
        const next = mission.gates?.find(item => item.id === event.target.value) || null;
        setGate(next); setPatch(next ? { status: next.status, evidence_status: next.evidence_status, source_id: next.source_id, source_type: next.source_type, source_route: next.source_route, due_date: next.due_date, blocking_reason: next.blocking_reason } : {});
      }}><option value="">Choose a gate</option>{mission.gates?.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      {gate ? <>
        <label>Status<select value={patch.status} onChange={event => setPatch({ ...patch, status: event.target.value as QmsMissionGatePatch["status"] })}>{["PENDING", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Evidence<select value={patch.evidence_status} onChange={event => setPatch({ ...patch, evidence_status: event.target.value as QmsMissionGatePatch["evidence_status"] })}>{["UNLINKED", "LINKED", "VERIFIED", "REJECTED", "EXPIRED"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Source type<input value={patch.source_type || ""} onChange={event => setPatch({ ...patch, source_type: event.target.value || null })} /></label>
        <label>Source record<input value={patch.source_id || ""} onChange={event => setPatch({ ...patch, source_id: event.target.value || null })} /></label>
        <label>Source link<input pattern="/[^/].*" value={patch.source_route || ""} onChange={event => setPatch({ ...patch, source_route: event.target.value || null })} /></label>
        <label>Due date<input type="date" value={patch.due_date || ""} onChange={event => setPatch({ ...patch, due_date: event.target.value || null })} /></label>
        <label>Blocker / next action<textarea value={patch.blocking_reason || ""} onChange={event => setPatch({ ...patch, blocking_reason: event.target.value || null })} /></label>
        <button type="submit" disabled={mutation.isPending}>Save gate</button>
      </> : null}
    </form> : null}
    <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("decision"); }}>
      <label>Decision stage<select value={decision.decision_type} onChange={event => setDecision({ ...decision, decision_type: event.target.value as QmsMissionDecisionCreate["decision_type"] })}>{["QUALITY_SELF_EVALUATION", "ACCOUNTABLE_EXECUTIVE", "AUTHORITY_SUBMISSION", "AUTHORITY_ACCEPTANCE"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Outcome<select value={decision.status} onChange={event => setDecision({ ...decision, status: event.target.value as QmsMissionDecisionCreate["status"] })}>{["APPROVED", "REJECTED", "RETURNED"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Rationale<textarea required minLength={3} value={decision.rationale} onChange={event => setDecision({ ...decision, rationale: event.target.value })} /></label>
      <button type="submit" disabled={mutation.isPending || !canDecide || decision.rationale.trim().length < 3}>Record decision</button>
      {!canDecide ? <p>The assigned {decision.decision_type === "ACCOUNTABLE_EXECUTIVE" ? "Accountable Executive" : "Quality owner"} must record this decision.</p> : null}
    </form>
  </section>;
}
