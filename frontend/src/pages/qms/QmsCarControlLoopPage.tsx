import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import { qmsListCarAssignees, type CARAssignee } from "../../services/qms";
import { canCloseCars, canManageCars } from "../../features/qms/auditSession/qmsAuditActionGates";
import QmsCarControlOperations from "./QmsCarControlOperations";
import {
  closeCarControlLoop,
  createCarDependency,
  decideCarDeadlineChange,
  evaluateCarControlLoop,
  getCarControlLoop,
  initializeCarControlLoop,
  requestCarDeadlineChange,
  updateCarControlMilestone,
  updateCarControlProfile,
  updateCarDependency,
  type CarControlLoop,
  type CarControlMilestoneStatus,
  type CarDependencyRisk,
  type CarDependencyType,
} from "../../services/qmsCarControlLoop";

const MILESTONE_STATUSES: CarControlMilestoneStatus[] = [
  "PLANNED",
  "IN_PROGRESS",
  "SUBMITTED",
  "ACCEPTED",
  "REJECTED",
  "BLOCKED",
  "COMPLETED",
  "WAIVED",
];
const DEPENDENCY_TYPES: CarDependencyType[] = ["INTERNAL", "EXTERNAL", "PROCUREMENT", "FACILITY", "RESOURCE", "SUPPLIER", "REGULATORY", "OTHER"];
const DEPENDENCY_RISKS: CarDependencyRisk[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const INITIAL_MILESTONES = [
  { key: "RCA_SUBMISSION", label: "Root cause analysis submitted" },
  { key: "CAP_APPROVAL", label: "Corrective action plan approved" },
  { key: "IMPLEMENTATION_COMPLETE", label: "Corrective actions implemented" },
  { key: "EVIDENCE_COMPLETE", label: "Closure evidence complete" },
  { key: "EFFECTIVENESS_REVIEW", label: "Effectiveness review complete" },
] as const;
type InitialMilestoneKey = (typeof INITIAL_MILESTONES)[number]["key"];
type InitialMilestoneDraft = { owner_user_id: string; due_date: string };

function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function toneClass(value: string): string {
  const normalized = value.toUpperCase();
  if (["HEALTHY", "CLOSED", "ACCEPTED", "COMPLETED", "RESOLVED", "MITIGATED", "APPROVED"].includes(normalized)) return "badge--success";
  if (["CRITICAL", "OVERDUE", "REJECTED", "BLOCKED"].includes(normalized)) return "badge--danger";
  if (["AT_RISK", "WATCH", "WARNING", "PENDING", "IN_PROGRESS", "SUBMITTED", "MITIGATING"].includes(normalized)) return "badge--warning";
  return "badge--neutral";
}

function assigneeName(assignees: CARAssignee[], userId: string | null | undefined): string {
  if (!userId) return "Unassigned";
  const match = assignees.find((item) => item.id === userId);
  return match?.full_name || match?.email || userId;
}

type MilestoneDraft = {
  owner_user_id: string;
  status: CarControlMilestoneStatus;
  notes: string;
  evidence_ref: string;
};

const QmsCarControlLoopPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; carId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const context = getContext();
  const amoCode = params.amoCode || context.amoSlug || context.amoCode || "UNKNOWN";
  const carId = params.carId || searchParams.get("control") || searchParams.get("carId") || "";
  const canManage = canManageCars();
  const canClose = canCloseCars();

  const [busy, setBusy] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [initOwner, setInitOwner] = useState("");
  const [initDue, setInitDue] = useState("");
  const [effectivenessRequired, setEffectivenessRequired] = useState(true);
  const [initialMilestones, setInitialMilestones] = useState<Record<InitialMilestoneKey, InitialMilestoneDraft>>(() => Object.fromEntries(INITIAL_MILESTONES.map((item) => [item.key, { owner_user_id: "", due_date: "" }])) as Record<InitialMilestoneKey, InitialMilestoneDraft>);
  const [milestoneDrafts, setMilestoneDrafts] = useState<Record<string, MilestoneDraft>>({});
  const [profileOwner, setProfileOwner] = useState("");
  const [profileEffectiveness, setProfileEffectiveness] = useState(true);
  const [deadlineMilestone, setDeadlineMilestone] = useState("");
  const [deadlineDate, setDeadlineDate] = useState("");
  const [deadlineReason, setDeadlineReason] = useState("");
  const [deadlineImpact, setDeadlineImpact] = useState("");
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});
  const [dependencyTitle, setDependencyTitle] = useState("");
  const [dependencyDescription, setDependencyDescription] = useState("");
  const [dependencyType, setDependencyType] = useState<CarDependencyType>("OTHER");
  const [dependencyRisk, setDependencyRisk] = useState<CarDependencyRisk>("MEDIUM");
  const [dependencyOwner, setDependencyOwner] = useState("");
  const [dependencyDue, setDependencyDue] = useState("");
  const [dependencyMilestone, setDependencyMilestone] = useState("");
  const [dependencyBlocksClosure, setDependencyBlocksClosure] = useState(false);
  const [dependencyMitigation, setDependencyMitigation] = useState("");
  const [closureEvidence, setClosureEvidence] = useState("");
  const [closureReason, setClosureReason] = useState("");

  const controlQuery = useQuery({
    queryKey: ["qms-car-control-loop", amoCode, carId],
    queryFn: ({ signal }) => getCarControlLoop(amoCode, carId, signal),
    enabled: Boolean(carId),
    staleTime: 5_000,
  });
  const assigneesQuery = useQuery({
    queryKey: ["qms-car-assignees", amoCode],
    queryFn: () => qmsListCarAssignees(),
    staleTime: 60_000,
  });

  const control = controlQuery.data;
  const assignees = useMemo(() => assigneesQuery.data ?? [], [assigneesQuery.data]);
  const assigneeOptions = useMemo(
    () => [...assignees].sort((left, right) => (left.full_name || left.email || "").localeCompare(right.full_name || right.email || "")),
    [assignees],
  );

  useEffect(() => {
    if (!control) return;
    if (!control.initialized) {
      const defaultOwner = control.car.assigned_to_user_id || "";
      setInitOwner(defaultOwner);
      setInitDue(control.car.target_closure_date || control.car.due_date || "");
      setInitialMilestones(Object.fromEntries(INITIAL_MILESTONES.map((item) => [item.key, { owner_user_id: defaultOwner, due_date: "" }])) as Record<InitialMilestoneKey, InitialMilestoneDraft>);
      return;
    }
    if (control.profile) {
      setProfileOwner(control.profile.accountable_owner_user_id || "");
      setProfileEffectiveness(control.profile.effectiveness_required);
    }
    const nextDrafts: Record<string, MilestoneDraft> = {};
    control.milestones.forEach((milestone) => {
      nextDrafts[milestone.id] = {
        owner_user_id: milestone.owner_user_id || "",
        status: milestone.status,
        notes: milestone.notes || "",
        evidence_ref: milestone.evidence_ref || "",
      };
    });
    setMilestoneDrafts(nextDrafts);
  }, [control]);

  async function runAction(label: string, action: () => Promise<CarControlLoop>, success: string): Promise<boolean> {
    setBusy(label);
    setActionError(null);
    setActionMessage(null);
    try {
      const next = await action();
      queryClient.setQueryData(["qms-car-control-loop", amoCode, carId], next);
      setActionMessage(success);
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The governed CAR action could not be completed.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  if (!carId) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
        <main className="page"><div className="card"><h1>CAR control loop</h1><p>No CAR was selected.</p></div></main>
      </DepartmentLayout>
    );
  }

  if (controlQuery.isLoading) {
    return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="page"><div className="card">Loading CAR control loop…</div></main></DepartmentLayout>;
  }

  if (controlQuery.isError || !control) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
        <main className="page">
          <div className="card">
            <h1>CAR control loop</h1>
            <p className="text-danger">{controlQuery.error instanceof Error ? controlQuery.error.message : "Unable to load the CAR control loop."}</p>
            <button className="btn" type="button" onClick={() => void controlQuery.refetch()}>Retry</button>
          </div>
        </main>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <main className="page qms-car-control-loop">
        <div className="page-header">
          <div>
            <button className="btn btn--ghost" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/cars`)}>← CAR register</button>
            <p className="eyebrow">Corrective action governance</p>
            <h1>{control.car.car_number} · {control.car.title}</h1>
            <p>{control.car.summary}</p>
          </div>
          <div className="toolbar">
            <span className={`badge ${toneClass(control.car.status)}`}>{humanize(control.car.status)}</span>
            <span className={`badge ${toneClass(control.health.state)}`}>{humanize(control.health.state)} · {control.health.risk_score}/100</span>
          </div>
        </div>

        {actionError ? <div className="alert alert--danger" role="alert">{actionError}</div> : null}
        {actionMessage ? <div className="alert alert--success" role="status">{actionMessage}</div> : null}

        <section className="card">
          <div className="card__header"><div><h2>Control position</h2><p>Deterministic status based on ownership, deadlines, milestone state and blockers.</p></div></div>
          <div className="stats-grid">
            <div><span className="muted">Health</span><strong>{humanize(control.health.state)}</strong></div>
            <div><span className="muted">Risk score</span><strong>{control.health.risk_score}/100</strong></div>
            <div><span className="muted">Final deadline</span><strong>{formatDate(control.profile?.current_due_date || control.car.target_closure_date || control.car.due_date)}</strong></div>
            <div><span className="muted">Next action</span><strong>{control.health.next_action}</strong></div>
          </div>
          {control.health.factors.length ? (
            <ul className="list-plain">
              {control.health.factors.map((factor, index) => <li key={`${factor.code}-${index}`}><span className={`badge ${toneClass(factor.severity)}`}>{humanize(factor.severity)}</span> {factor.message}</li>)}
            </ul>
          ) : <p className="muted">No active closure-risk factors are currently detected.</p>}
        </section>

        {!control.initialized ? (
          <section className="card">
            <div className="card__header"><div><h2>Initialize staged control</h2><p>Preserve the baseline deadline and establish RCA, CAP, implementation, evidence and effectiveness milestones.</p></div></div>
            {!canManage ? <p>Quality Manager or tenant administrator authority is required to initialize this CAR.</p> : (
              <div className="form-grid">
                <label>Accountable lead owner
                  <select className="input" value={initOwner} onChange={(event) => setInitOwner(event.target.value)}>
                    <option value="">Unassigned</option>
                    {assigneeOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}{person.department_name ? ` · ${person.department_name}` : ""}</option>)}
                  </select>
                </label>
                <label>Controlled final due date
                  <input className="input" type="date" value={initDue} onChange={(event) => setInitDue(event.target.value)} />
                </label>
                <div style={{ gridColumn: "1 / -1" }}>
                  <strong>Lifecycle milestone plan</strong>
                  <p className="muted">Set the accountable person and planned control date for RCA, CAP acceptance, implementation, evidence and effectiveness. Blank dates use the governed default schedule.</p>
                  <div className="table-wrap"><table className="table"><thead><tr><th>Stage</th><th>Owner</th><th>Planned due</th></tr></thead><tbody>{INITIAL_MILESTONES.map((item, index) => { const draft = initialMilestones[item.key]; return <tr key={item.key}><td><strong>{index + 1}. {item.label}</strong></td><td><select className="input" value={draft.owner_user_id} onChange={(event) => setInitialMilestones((current) => ({ ...current, [item.key]: { ...current[item.key], owner_user_id: event.target.value } }))}><option value="">Unassigned</option>{assigneeOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}{person.department_name ? ` · ${person.department_name}` : ""}</option>)}</select></td><td><input className="input" type="date" value={draft.due_date} max={initDue || undefined} onChange={(event) => setInitialMilestones((current) => ({ ...current, [item.key]: { ...current[item.key], due_date: event.target.value } }))} /></td></tr>; })}</tbody></table></div>
                </div>
                <label className="checkbox-row"><input type="checkbox" checked={effectivenessRequired} onChange={(event) => setEffectivenessRequired(event.target.checked)} /> Effectiveness review required before closure</label>
                <div><button className="btn btn--primary" type="button" disabled={!initDue || busy !== null} onClick={() => void runAction("initialize", () => initializeCarControlLoop(amoCode, carId, { accountable_owner_user_id: initOwner || null, final_due_date: initDue || undefined, effectiveness_required: effectivenessRequired, milestones: INITIAL_MILESTONES.map((item) => ({ milestone_key: item.key, owner_user_id: initialMilestones[item.key].owner_user_id || undefined, due_date: initialMilestones[item.key].due_date || undefined })) }), "Staged CAR control initialized.")}>{busy === "initialize" ? "Initializing…" : "Initialize control loop"}</button></div>
              </div>
            )}
          </section>
        ) : (
          <>
            <section className="card">
              <div className="card__header"><div><h2>Accountability & baseline</h2><p>The original deadline is immutable. Any revised deadline must pass through the governed approval history below.</p></div></div>
              <div className="stats-grid">
                <div><span className="muted">Original final due</span><strong>{formatDate(control.profile?.original_due_date)}</strong></div>
                <div><span className="muted">Current final due</span><strong>{formatDate(control.profile?.current_due_date)}</strong></div>
                <div><span className="muted">Accountable owner</span><strong>{assigneeName(assignees, control.profile?.accountable_owner_user_id)}</strong></div>
                <div><span className="muted">Effectiveness gate</span><strong>{control.profile?.effectiveness_required ? "Required" : "Not required"}</strong></div>
              </div>
              {canManage ? (
                <div className="form-grid">
                  <label>Accountable owner
                    <select className="input" value={profileOwner} onChange={(event) => setProfileOwner(event.target.value)}>
                      <option value="">Unassigned</option>
                      {assigneeOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}</option>)}
                    </select>
                  </label>
                  <label className="checkbox-row"><input type="checkbox" checked={profileEffectiveness} onChange={(event) => setProfileEffectiveness(event.target.checked)} /> Require effectiveness verification</label>
                  <div><button className="btn" type="button" disabled={busy !== null} onClick={() => void runAction("profile", () => updateCarControlProfile(amoCode, carId, { accountable_owner_user_id: profileOwner || null, effectiveness_required: profileEffectiveness }), "CAR accountability controls updated.")}>Save profile controls</button></div>
                </div>
              ) : null}
            </section>

            <QmsCarControlOperations amoCode={amoCode} carId={carId} control={control} assignees={assignees} canManage={canManage} onControlChange={(next) => queryClient.setQueryData(["qms-car-control-loop", amoCode, carId], next)} />

            <section className="card">
              <div className="card__header"><div><h2>Staged CAR lifecycle</h2><p>Each stage has a named owner, immutable original deadline, current approved deadline, governed status and evidence.</p></div></div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Stage</th><th>Owner</th><th>Original due</th><th>Current due</th><th>Status</th><th>Evidence / note</th><th /></tr></thead>
                  <tbody>
                    {control.milestones.map((milestone) => {
                      const draft = milestoneDrafts[milestone.id] || { owner_user_id: milestone.owner_user_id || "", status: milestone.status, notes: milestone.notes || "", evidence_ref: milestone.evidence_ref || "" };
                      return (
                        <tr key={milestone.id}>
                          <td><strong>{milestone.phase_order}. {milestone.title}</strong><div className="muted">{humanize(milestone.milestone_key)}</div></td>
                          <td>{canManage ? <select className="input" value={draft.owner_user_id} onChange={(event) => setMilestoneDrafts((current) => ({ ...current, [milestone.id]: { ...draft, owner_user_id: event.target.value } }))}><option value="">Unassigned</option>{assigneeOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}</option>)}</select> : assigneeName(assignees, milestone.owner_user_id)}</td>
                          <td>{formatDate(milestone.original_due_date)}</td>
                          <td>{formatDate(milestone.current_due_date)}</td>
                          <td>{canManage ? <select className="input" value={draft.status} onChange={(event) => setMilestoneDrafts((current) => ({ ...current, [milestone.id]: { ...draft, status: event.target.value as CarControlMilestoneStatus } }))}>{MILESTONE_STATUSES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select> : <span className={`badge ${toneClass(milestone.status)}`}>{humanize(milestone.status)}</span>}</td>
                          <td>{canManage ? <div className="stack"><input className="input" value={draft.evidence_ref} onChange={(event) => setMilestoneDrafts((current) => ({ ...current, [milestone.id]: { ...draft, evidence_ref: event.target.value } }))} placeholder="Evidence reference" /><input className="input" value={draft.notes} onChange={(event) => setMilestoneDrafts((current) => ({ ...current, [milestone.id]: { ...draft, notes: event.target.value } }))} placeholder="Control note" /></div> : <><div>{milestone.evidence_ref || "—"}</div><div className="muted">{milestone.notes || ""}</div></>}</td>
                          <td>{canManage ? <button className="btn btn--small" type="button" disabled={busy !== null} onClick={() => void runAction(`milestone-${milestone.id}`, () => updateCarControlMilestone(amoCode, carId, milestone.id, { owner_user_id: draft.owner_user_id || null, status: draft.status, notes: draft.notes, evidence_ref: draft.evidence_ref }), `${milestone.title} updated.`)}>Save</button> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card">
              <div className="card__header"><div><h2>Dependencies & blockers</h2><p>Record workload, procurement, facilities, supplier, regulatory and other dependencies before they silently delay closure.</p></div></div>
              {canManage ? (
                <div className="form-grid">
                  <label>Dependency title<input className="input" value={dependencyTitle} onChange={(event) => setDependencyTitle(event.target.value)} placeholder="e.g. Facility modification approval" /></label>
                  <label>Description<textarea className="input" rows={3} value={dependencyDescription} onChange={(event) => setDependencyDescription(event.target.value)} placeholder="What must be delivered, approved or completed before this CAR can progress?" /></label>
                  <label>Type<select className="input" value={dependencyType} onChange={(event) => setDependencyType(event.target.value as CarDependencyType)}>{DEPENDENCY_TYPES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label>
                  <label>Risk<select className="input" value={dependencyRisk} onChange={(event) => setDependencyRisk(event.target.value as CarDependencyRisk)}>{DEPENDENCY_RISKS.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label>
                  <label>Owner<select className="input" value={dependencyOwner} onChange={(event) => setDependencyOwner(event.target.value)}><option value="">Unassigned</option>{assigneeOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}</option>)}</select></label>
                  <label>Milestone<select className="input" value={dependencyMilestone} onChange={(event) => setDependencyMilestone(event.target.value)}><option value="">CAR-wide</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
                  <label>Due date<input className="input" type="date" value={dependencyDue} onChange={(event) => setDependencyDue(event.target.value)} /></label>
                  <label>Mitigation<input className="input" value={dependencyMitigation} onChange={(event) => setDependencyMitigation(event.target.value)} placeholder="Mitigation / recovery plan" /></label>
                  <label className="checkbox-row"><input type="checkbox" checked={dependencyBlocksClosure} onChange={(event) => setDependencyBlocksClosure(event.target.checked)} /> Blocks CAR closure</label>
                  <div><button className="btn btn--primary" type="button" disabled={dependencyTitle.trim().length < 3 || busy !== null} onClick={() => void runAction("dependency-create", () => createCarDependency(amoCode, carId, { title: dependencyTitle.trim(), description: dependencyDescription.trim() || undefined, dependency_type: dependencyType, risk_level: dependencyRisk, owner_user_id: dependencyOwner || undefined, milestone_id: dependencyMilestone || undefined, due_date: dependencyDue || undefined, blocks_closure: dependencyBlocksClosure, mitigation_plan: dependencyMitigation || undefined }), "Dependency recorded.").then((succeeded) => { if (succeeded) { setDependencyTitle(""); setDependencyDescription(""); setDependencyMitigation(""); } })}>Add dependency</button></div>
                </div>
              ) : null}
              <div className="table-wrap">
                <table className="table"><thead><tr><th>Dependency</th><th>Owner</th><th>Risk</th><th>Due</th><th>Closure gate</th><th>Status</th></tr></thead><tbody>
                  {control.dependencies.length ? control.dependencies.map((dependency) => (
                    <tr key={dependency.id}>
                      <td><strong>{dependency.title}</strong><div className="muted">{humanize(dependency.dependency_type)}{dependency.mitigation_plan ? ` · ${dependency.mitigation_plan}` : ""}</div></td>
                      <td>{assigneeName(assignees, dependency.owner_user_id)}</td>
                      <td><span className={`badge ${toneClass(dependency.risk_level)}`}>{humanize(dependency.risk_level)}</span></td>
                      <td>{formatDate(dependency.due_date)}</td>
                      <td>{dependency.blocks_closure ? "Blocking" : "Non-blocking"}</td>
                      <td>{canManage ? <select className="input" value={dependency.status} onChange={(event) => void runAction(`dependency-${dependency.id}`, () => updateCarDependency(amoCode, carId, dependency.id, { status: event.target.value as typeof dependency.status }), "Dependency status updated.")} disabled={busy !== null}><option value="OPEN">Open</option><option value="MITIGATING">Mitigating</option><option value="MITIGATED">Mitigated</option><option value="RESOLVED">Resolved</option><option value="ACCEPTED_RISK">Accepted risk</option><option value="CANCELLED">Cancelled</option></select> : humanize(dependency.status)}</td>
                    </tr>
                  )) : <tr><td colSpan={6} className="muted">No dependencies recorded.</td></tr>}
                </tbody></table>
              </div>
            </section>

            <section className="card">
              <div className="card__header"><div><h2>Controlled deadline changes</h2><p>Extensions never overwrite the baseline date. Every request records previous/requested dates, reason, impact, requester and decision.</p></div></div>
              {canManage ? (
                <div className="form-grid">
                  <label>Deadline<select className="input" value={deadlineMilestone} onChange={(event) => setDeadlineMilestone(event.target.value)}><option value="">Final CAR deadline</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
                  <label>Requested new date<input className="input" type="date" value={deadlineDate} onChange={(event) => setDeadlineDate(event.target.value)} /></label>
                  <label>Reason<input className="input" value={deadlineReason} onChange={(event) => setDeadlineReason(event.target.value)} placeholder="Why the current deadline cannot be met" /></label>
                  <label>Impact statement<input className="input" value={deadlineImpact} onChange={(event) => setDeadlineImpact(event.target.value)} placeholder="Operational / compliance impact and recovery" /></label>
                  <div><button className="btn" type="button" disabled={!deadlineDate || deadlineReason.trim().length < 8 || busy !== null} onClick={() => void runAction("deadline-request", () => requestCarDeadlineChange(amoCode, carId, { milestone_id: deadlineMilestone || undefined, requested_due_date: deadlineDate, reason: deadlineReason.trim(), impact_statement: deadlineImpact || undefined }), "Deadline change submitted for governed decision.").then((succeeded) => { if (succeeded) { setDeadlineDate(""); setDeadlineReason(""); setDeadlineImpact(""); } })}>Request deadline change</button></div>
                </div>
              ) : null}
              <div className="table-wrap"><table className="table"><thead><tr><th>Scope</th><th>Previous</th><th>Requested</th><th>Reason</th><th>Status / decision</th></tr></thead><tbody>
                {control.deadline_changes.length ? control.deadline_changes.map((change) => {
                  const milestone = control.milestones.find((item) => item.id === change.milestone_id);
                  return <tr key={change.id}><td>{milestone?.title || "Final CAR deadline"}</td><td>{formatDate(change.previous_due_date)}</td><td>{formatDate(change.requested_due_date)}</td><td>{change.reason}<div className="muted">{change.impact_statement || ""}</div></td><td><span className={`badge ${toneClass(change.status)}`}>{humanize(change.status)}</span>{canManage && change.status === "PENDING" ? <div className="stack"><input className="input" value={decisionNotes[change.id] || ""} onChange={(event) => setDecisionNotes((current) => ({ ...current, [change.id]: event.target.value }))} placeholder="Decision note" /><div className="toolbar"><button className="btn btn--small" type="button" disabled={(decisionNotes[change.id] || "").trim().length < 3 || busy !== null} onClick={() => void runAction(`approve-${change.id}`, () => decideCarDeadlineChange(amoCode, carId, change.id, { decision: "APPROVE", review_note: (decisionNotes[change.id] || "").trim() }), "Deadline change approved.")}>Approve</button><button className="btn btn--small" type="button" disabled={(decisionNotes[change.id] || "").trim().length < 3 || busy !== null} onClick={() => void runAction(`reject-${change.id}`, () => decideCarDeadlineChange(amoCode, carId, change.id, { decision: "REJECT", review_note: (decisionNotes[change.id] || "").trim() }), "Deadline change rejected.")}>Reject</button></div></div> : null}</td></tr>;
                }) : <tr><td colSpan={5} className="muted">No staged deadline changes recorded.</td></tr>}
              </tbody></table></div>
              {control.legacy_extension_history.length ? <p className="muted">Legacy CAR-level extension history is preserved in the API response ({control.legacy_extension_history.length} existing record(s)); it is not overwritten by staged controls.</p> : null}
            </section>

            <section className="card">
              <div className="card__header"><div><h2>Closure readiness</h2><p>Closure remains gated by the existing server-controlled CAR state machine, evidence requirements and training gate.</p></div><span className={`badge ${control.closure_readiness.ready ? "badge--success" : "badge--warning"}`}>{control.closure_readiness.ready ? "Ready" : "Not ready"}</span></div>
              {control.closure_readiness.blockers.length ? <ul>{control.closure_readiness.blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}>{blocker.message}</li>)}</ul> : <p>All staged closure controls are satisfied.</p>}
              {canManage ? <div className="toolbar"><button className="btn" type="button" disabled={busy !== null} onClick={() => void runAction("evaluate", () => evaluateCarControlLoop(amoCode, carId), "Risk, reminder and escalation controls evaluated.")}>Evaluate reminders & escalation</button></div> : null}
              {canManage && control.closure_readiness.ready && control.car.status !== "CLOSED" ? <div className="form-grid"><label>Closure evidence reference<input className="input" value={closureEvidence} onChange={(event) => setClosureEvidence(event.target.value)} placeholder="Optional when milestone evidence is already linked" /></label><label>Closure rationale<input className="input" value={closureReason} onChange={(event) => setClosureReason(event.target.value)} placeholder="Why Quality accepts the CAR as complete" /></label><div><button className="btn btn--primary" type="button" disabled={!canClose || closureReason.trim().length < 8 || busy !== null} title={!canClose ? "Explicit qms.car.close authority is required" : undefined} onClick={() => void runAction("close", () => closeCarControlLoop(amoCode, carId, { evidence_ref: closureEvidence || undefined, closure_reason: closureReason.trim() }), "CAR closed through the governed state machine.")}>Close CAR</button></div></div> : null}
            </section>

            <section className="card">
              <div className="card__header"><div><h2>Control event timeline</h2><p>Attributable lifecycle, deadline and automated escalation events.</p></div></div>
              <div className="table-wrap"><table className="table"><thead><tr><th>Time</th><th>Event</th><th>Severity</th><th>Reason</th><th>Actor</th></tr></thead><tbody>
                {control.events.length ? control.events.map((event) => <tr key={event.id}><td>{formatDateTime(event.created_at)}</td><td>{humanize(event.event_type)}{event.system_generated ? <div className="muted">System generated</div> : null}</td><td><span className={`badge ${toneClass(event.severity)}`}>{humanize(event.severity)}</span></td><td>{event.reason}</td><td>{assigneeName(assignees, event.actor_user_id)}</td></tr>) : <tr><td colSpan={5} className="muted">No control events recorded.</td></tr>}
              </tbody></table></div>
            </section>
          </>
        )}
      </main>
    </DepartmentLayout>
  );
};

export default QmsCarControlLoopPage;
