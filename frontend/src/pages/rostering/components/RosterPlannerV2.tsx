import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, differenceInCalendarDays, format, parseISO } from "date-fns";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Command,
  Filter,
  GraduationCap,
  GripVertical,
  LockKeyhole,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Repeat2,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  Umbrella,
  WandSparkles,
  UsersRound,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { isOfflineQueuedError } from "../../../services/offlineHttp";
import { listRosterBaseStations } from "../../../services/rosterBases";
import {
  listPublicHolidays,
  listWorkPatternAssignments,
  listWorkPatterns,
  updateWorkPatternAssignment,
} from "../../../services/workforce";
import {
  listRosterCommitments,
  type RosterCommitmentRead,
} from "../../../services/rosterCommitments";
import { listAllRosterPeople, type RosterPersonRead } from "../../../services/rosterPeople";
import {
  approveRosterVersion,
  applyRosterCoverageRecommendation,
  bulkCreateRosterAssignments,
  createRosterAssignment,
  createRosterVersion,
  deleteRosterAssignment,
  generateRosterFromPattern,
  getRosterCoverageRecommendations,
  publishRosterVersion,
  submitRosterVersion,
  updateRosterAssignment,
  validateRosterVersion,
} from "../../../services/rostering";
import type { BaseStationRead } from "../../../types/foundations";
import type { RosterAssignmentRead, RosterBulkAssignmentItem, RosterCoverageRecommendationRead, RosterValidationFindingRead, ShiftTemplateRead } from "../../../types/rostering";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../../../types/workforce";
import { errorMessage, isoDate, newIdempotencyKey } from "../rosterUi";
import { formatInZone, moveIntervalToZonedDay, templateWindowInZone } from "../timezone";
import { useRosterPlannerDataV2, type PlannerSourceErrors } from "../hooks/useRosterPlannerDataV2";
import { AircraftAllocationEditor } from "./AircraftAllocationEditor";
import { EmptyState, RosterError, RosterLoading, StatusPill } from "./RosterShell";
import { RosterTaskAllocationEditor } from "./RosterTaskAllocationEditor";

type DragPayload =
  | { type: "person"; userId: string }
  | { type: "assignment"; assignmentId: string }
  | { type: "fill"; assignmentId: string };

type GridPoint = { userId: string; date: string };
type GridSelection = { anchor: GridPoint; focus: GridPoint };
type CellIssue = {
  key: string;
  title: string;
  message: string;
  assignmentId?: string;
};
type GenerationProgress = {
  processedPeople: number;
  totalPeople: number;
  created: number;
  skipped: number;
  conflicts: number;
};
type RotationOption = { value: string; label: string };

const OCCUPIED_STATUSES = new Set(["DUTY", "STANDBY", "TRAVEL", "OTHER"]);

function shiftAvailableForDepartment(template: ShiftTemplateRead, departmentId?: string | null): boolean {
  const scope = template.department_ids || [];
  return !scope.length || Boolean(departmentId && scope.includes(departmentId));
}

function intervalsOverlap(leftStart: string, leftEnd: string, rightStart: string, rightEnd: string): boolean {
  return new Date(leftStart).getTime() < new Date(rightEnd).getTime()
    && new Date(leftEnd).getTime() > new Date(rightStart).getTime();
}

function setDrag(event: DragEvent<HTMLElement>, payload: DragPayload) {
  event.dataTransfer.effectAllowed = payload.type === "assignment" ? "move" : "copy";
  event.dataTransfer.setData("application/x-amo-roster", JSON.stringify(payload));
}

function getDrag(event: DragEvent<HTMLElement>): DragPayload | null {
  try {
    const value = JSON.parse(event.dataTransfer.getData("application/x-amo-roster")) as DragPayload;
    return value?.type === "person" || value?.type === "assignment" || value?.type === "fill" ? value : null;
  } catch {
    return null;
  }
}

function localDate(value: string, timezoneName: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezoneName,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(parseISO(value));
  const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function inclusiveLocalEndDate(value: string, timezoneName: string): string {
  const instant = parseISO(value);
  return localDate(new Date(instant.getTime() - 1).toISOString(), timezoneName);
}

function assignmentStatusForTemplate(template: ShiftTemplateRead) {
  if (template.kind === "STANDBY") return "STANDBY" as const;
  if (template.kind === "OFF") return "OFF" as const;
  return "DUTY" as const;
}

function isWorkforceAbsence(commitment: RosterCommitmentRead): boolean {
  return commitment.source_module === "WORKFORCE"
    && /LEAVE|UNAVAILABLE|SUSPENDED|ABSEN|OFF/.test(`${commitment.kind} ${commitment.source_type}`.toUpperCase());
}

async function boundedCommitments(request: Promise<{ items: RosterCommitmentRead[] }>) {
  let timer: ReturnType<typeof globalThis.setTimeout> | undefined;
  try {
    return await Promise.race([
      request,
      new Promise<{ items: RosterCommitmentRead[] }>((_resolve, reject) => {
        timer = globalThis.setTimeout(() => reject(new Error("Source commitments did not respond within 20 seconds.")), 20_000);
      }),
    ]);
  } finally {
    if (timer) globalThis.clearTimeout(timer);
  }
}

function CommitmentSourceIcon({ sourceModule }: { sourceModule: string }) {
  if (sourceModule === "TRAINING") return <GraduationCap size={12} aria-hidden="true" />;
  if (sourceModule === "QUALITY") return <ShieldCheck size={12} aria-hidden="true" />;
  return <Umbrella size={12} aria-hidden="true" />;
}

function PersonCard({ person, assignedDays, plannedHours, issues, rotationValue, rotationOptions, rotationDisabled, rotationTitle, onRotationChange }: {
  person: RosterPersonRead;
  assignedDays: number;
  plannedHours: number;
  issues: number;
  rotationValue: string;
  rotationOptions: RotationOption[];
  rotationDisabled: boolean;
  rotationTitle: string;
  onRotationChange: (cycleDayIndex: number) => void;
}) {
  return (
    <div className="wr-person" draggable onDragStart={(event) => setDrag(event, { type: "person", userId: person.user_id })}>
      <GripVertical size={14} aria-hidden="true" />
      <span className="wr-person__identity"><strong>{person.full_name}</strong><small>{person.staff_code} · {person.position_title || person.role.replace(/_/g, " ")}</small></span>
      <label className="wr-person__rotation" title={rotationTitle} onPointerDown={(event) => event.stopPropagation()}>
        <span className="sr-only">Starting rotation day for {person.full_name}</span>
        <select
          aria-label={`Starting shift for ${person.full_name}`}
          value={rotationValue}
          disabled={rotationDisabled}
          draggable={false}
          onDragStart={(event) => event.preventDefault()}
          onChange={(event) => onRotationChange(Number(event.target.value))}
        >
          {!rotationOptions.length ? <option value="">—</option> : null}
          {rotationOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <span className="wr-person__summary"><strong>{assignedDays}d</strong><small>{plannedHours}h</small>{issues ? <em>{issues}</em> : null}</span>
      <span className="wr-person__signals" title={`${person.has_active_contract ? "Active contract" : "Contract missing"} · ${person.active_authorisation_count ? `${person.active_authorisation_count} active authorisations` : "Authorisation missing"}`}><i className={person.has_active_contract ? "is-good" : "is-danger"} /><i className={person.active_authorisation_count ? "is-good" : "is-warning"} /></span>
    </div>
  );
}

function CommitmentCard({ commitment }: { commitment: RosterCommitmentRead }) {
  return (
    <article
      className={`wr-planner-commitment wr-planner-commitment--${commitment.source_module.toLowerCase()}${commitment.blocking ? " is-blocking" : ""}`}
      title={[commitment.title, commitment.detail, commitment.location_label, commitment.status].filter(Boolean).join(" · ")}
    >
      <CommitmentSourceIcon sourceModule={commitment.source_module} />
      <span><strong>{commitment.kind.replace(/_/g, " ")}</strong><small>{commitment.title}</small></span>
      {commitment.provisional ? <em>Provisional</em> : null}
    </article>
  );
}

function AssignmentCard({ assignment, timezoneName, selected, fillEnabled, onSelect, onMove }: {
  assignment: RosterAssignmentRead;
  timezoneName: string;
  selected: boolean;
  fillEnabled: boolean;
  onSelect: () => void;
  onMove: (days: number) => void;
}) {
  const pendingSync = assignment.id.startsWith("offline-");
  const keydown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (pendingSync || assignment.locked_after_publish || !event.altKey) return;
    if (event.key === "ArrowLeft") { event.preventDefault(); onMove(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); onMove(1); }
  };
  return (
    <motion.div layout>
      <button
        type="button"
        className={`wr-assignment wr-assignment--${assignment.status.toLowerCase()}${selected ? " is-selected" : ""}${pendingSync ? " is-pending-sync" : ""}`}
        draggable={!pendingSync && !assignment.locked_after_publish}
        onDragStart={(event) => setDrag(event, { type: "assignment", assignmentId: assignment.id })}
        onClick={onSelect}
        onKeyDown={keydown}
      >
        <span className="wr-assignment__top"><strong>{assignment.shift_code || assignment.status}</strong>{pendingSync ? <RefreshCw size={12} /> : assignment.locked_after_publish ? <LockKeyhole size={12} /> : <GripVertical size={12} />}</span>
        <span>{formatInZone(assignment.starts_at, timezoneName, "HH:mm")}–{formatInZone(assignment.ends_at, timezoneName, "HH:mm")}</span>
        <small>{assignment.role_label || assignment.base_code || "Duty"}</small>
        {pendingSync ? <em>Pending sync</em> : assignment.linked_task_count ? <em>{assignment.linked_task_count} task{assignment.linked_task_count === 1 ? "" : "s"}</em> : null}
        {fillEnabled ? <span
          className="wr-fill-handle"
          draggable
          title="Drag to fill this shift across adjacent cells"
          aria-label="Drag to fill adjacent dates"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onDragStart={(event) => { event.stopPropagation(); setDrag(event, { type: "fill", assignmentId: assignment.id }); }}
        /> : null}
      </button>
    </motion.div>
  );
}

function FindingRail({
  findings,
  recommendations,
  recommendationLoading,
  editable,
  busy,
  onApplyRecommendation,
  onFocus,
  onClose,
}: {
  findings: RosterValidationFindingRead[];
  recommendations: RosterCoverageRecommendationRead[];
  recommendationLoading: boolean;
  editable: boolean;
  busy: string | null;
  onApplyRecommendation: (recommendation: RosterCoverageRecommendationRead, replacementUserId: string) => void;
  onFocus: (assignmentId: string) => void;
  onClose: () => void;
}) {
  const open = findings.filter((finding) => !finding.resolved);
  return (
    <aside className="wr-issue-rail">
      <div className="wr-recommendation-head"><div><span className="wr-eyebrow">Exceptions</span><h2>Rotation recommendations</h2></div><button type="button" className="wr-icon-button" aria-label="Close exceptions" onClick={onClose}><X size={16} /></button></div>
      {recommendationLoading ? <div className="wr-recommendation-loading"><RefreshCw size={14} className="is-spinning" /> Checking eligible substitutes…</div> : null}
      {!recommendationLoading && !recommendations.length ? <div className="wr-success-note"><CheckCircle2 size={17} /> No displaced duty detected.</div> : null}
      <div className="wr-recommendation-list">
        {recommendations.map((recommendation) => (
          <article key={recommendation.assignment_id} className="wr-recommendation">
            <div className="wr-recommendation__title"><Repeat2 size={15} /><span><strong>{recommendation.absent_user_full_name}</strong><small>{recommendation.commitment_kind.replace(/_/g, " ")} · {recommendation.commitment_title}</small></span></div>
            <button type="button" className="wr-text-link" onClick={() => onFocus(recommendation.assignment_id)}>Open affected {recommendation.shift_code || "duty"}</button>
            {recommendation.linked_task_count || recommendation.aircraft_allocation_count ? <div className="wr-inline-note"><RefreshCw size={14} /> Rotation will move {recommendation.linked_task_count ? `${recommendation.linked_task_count} open task link${recommendation.linked_task_count === 1 ? "" : "s"}` : ""}{recommendation.linked_task_count && recommendation.aircraft_allocation_count ? " and " : ""}{recommendation.aircraft_allocation_count ? `${recommendation.aircraft_allocation_count} aircraft allocation${recommendation.aircraft_allocation_count === 1 ? "" : "s"}` : ""} atomically.</div> : null}
            {recommendation.candidates.length ? <div className="wr-recommendation__candidates">{recommendation.candidates.slice(0, 3).map((candidate, index) => <button key={candidate.user_id} type="button" disabled={!editable || Boolean(busy)} onClick={() => onApplyRecommendation(recommendation, candidate.user_id)}><span><b>{index === 0 ? "Best match · " : ""}{candidate.full_name}</b><small>{candidate.staff_code} · {candidate.reasons.join(" · ")}</small></span><em>{candidate.score}</em></button>)}</div> : <div className="wr-inline-warning"><AlertTriangle size={14} /> No collision-free eligible substitute was found.</div>}
          </article>
        ))}
      </div>
      <div className="wr-issue-divider" />
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Checks</span><h2>Issues to resolve</h2></div><div className="wr-inline-counts"><span className="wr-pill wr-pill--blocker">{open.filter((row) => row.severity === "BLOCKER").length} blockers</span><span className="wr-pill wr-pill--warning">{open.filter((row) => row.severity === "WARNING").length} warnings</span></div></div>
      {open.length === 0 ? <div className="wr-success-note"><CheckCircle2 size={17} /> No unresolved findings.</div> : <div className="wr-issue-list">{open.map((finding) => <button key={finding.id} type="button" className={`wr-issue wr-issue--${finding.severity.toLowerCase()}`} onClick={() => finding.assignment_id && onFocus(finding.assignment_id)}><AlertTriangle size={15} /><span><strong>{finding.code.replace(/_/g, " ")}</strong><small>{finding.message}</small></span>{finding.assignment_id ? <ArrowRight size={14} /> : null}</button>)}</div>}
    </aside>
  );
}

function AssignmentDrawer({ assignment, templates, bases, timezoneName, editable, onClose, onSaved, onDeleted }: {
  assignment: RosterAssignmentRead;
  templates: ShiftTemplateRead[];
  bases: BaseStationRead[];
  timezoneName: string;
  editable: boolean;
  onClose: () => void;
  onSaved: (row: RosterAssignmentRead) => void;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState(assignment.status);
  const [shiftTemplateId, setShiftTemplateId] = useState(assignment.shift_template_id || "");
  const [baseStationId, setBaseStationId] = useState(assignment.base_station_id || "");
  const [roleLabel, setRoleLabel] = useState(assignment.role_label || "");
  const [teamCode, setTeamCode] = useState(assignment.team_code || "");
  const [locationLabel, setLocationLabel] = useState(assignment.location_label || "");
  const [taskNote, setTaskNote] = useState(assignment.task_note || "");
  const [reason, setReason] = useState(assignment.change_reason || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allocationOpen, setAllocationOpen] = useState(false);
  const [allocationTab, setAllocationTab] = useState<"tasks" | "aircraft">("tasks");
  const pendingSync = assignment.id.startsWith("offline-");
  const availableTemplates = templates.filter((template) => (
    template.id === assignment.shift_template_id
    || shiftAvailableForDepartment(template, assignment.department_id)
  ));

  const save = async () => {
    if (!reason.trim()) { setError("A change reason is required for an audited roster edit."); return; }
    setBusy(true); setError(null);
    const patch = {
      status,
      shift_template_id: shiftTemplateId || null,
      base_station_id: baseStationId || null,
      role_label: roleLabel || null,
      team_code: teamCode || null,
      location_label: locationLabel || null,
      task_note: taskNote || null,
      change_reason: reason.trim(),
      expected_state_revision: assignment.state_revision,
    };
    try {
      const row = await updateRosterAssignment(assignment.id, patch);
      onSaved(row); onClose();
    } catch (cause) {
      if (isOfflineQueuedError(cause)) {
        const template = templates.find((item) => item.id === shiftTemplateId);
        const base = bases.find((item) => item.id === baseStationId);
        onSaved({
          ...assignment,
          ...patch,
          shift_code: template?.code || assignment.shift_code,
          shift_label: template?.label || assignment.shift_label,
          shift_kind: template?.kind || assignment.shift_kind,
          base_code: base?.code || assignment.base_code,
          base_name: base?.name || assignment.base_name,
          state_revision: assignment.state_revision + 1,
          updated_at: new Date().toISOString(),
        });
        onClose();
      } else {
        setError(errorMessage(cause));
      }
    } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!reason.trim()) { setError("Enter a reason before removing this assignment."); return; }
    setBusy(true); setError(null);
    try {
      await deleteRosterAssignment(assignment.id, { reason: reason.trim(), expected_state_revision: assignment.state_revision });
      onDeleted(assignment.id); onClose();
    } catch (cause) {
      if (isOfflineQueuedError(cause)) {
        onDeleted(assignment.id); onClose();
      } else {
        setError(errorMessage(cause));
      }
    } finally { setBusy(false); }
  };

  return (
    <motion.aside className="wr-drawer wr-drawer--assignment" initial={{ x: 36, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 36, opacity: 0 }}>
      <div className="wr-drawer__header"><div><span className="wr-eyebrow">Assignment</span><h2>{assignment.user_full_name || assignment.user_staff_code}</h2><p>{formatInZone(assignment.starts_at, timezoneName, "EEE d MMM, HH:mm")}–{formatInZone(assignment.ends_at, timezoneName, "HH:mm")}</p></div><button type="button" className="wr-icon-button" aria-label="Close assignment" onClick={onClose}><X size={18} /></button></div>
      {pendingSync ? (
        <div className="wr-pending-card" role="status"><RefreshCw size={18} className="is-spinning" /><div><strong>Stored offline</strong><p>This assignment will sync after reconnection. Use the global sync control to retry or discard it.</p></div></div>
      ) : (
        <>
          <div className="wr-form-grid wr-form-grid--inspector">
            <label><span>Status</span><select value={status} disabled={!editable || ["TRAINING", "LEAVE", "UNAVAILABLE"].includes(status)} onChange={(event) => setStatus(event.target.value as typeof status)}>{[...new Set([status, "DUTY", "STANDBY", "OFF", "TRAVEL", "OTHER"])].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label><span>Shift</span><select value={shiftTemplateId} disabled={!editable} onChange={(event) => setShiftTemplateId(event.target.value)}><option value="">No template</option>{availableTemplates.map((template) => <option key={template.id} value={template.id}>{template.code} · {template.label}</option>)}</select></label>
            <label className="wr-span-2"><span>Duty base</span><select value={baseStationId} disabled={!editable} onChange={(event) => setBaseStationId(event.target.value)}><option value="">Use personnel base</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code} · {base.name}</option>)}</select></label>
            <label className="wr-span-2"><span>Change reason</span><input value={reason} disabled={!editable} placeholder="Required for audited changes" onChange={(event) => setReason(event.target.value)} /></label>
          </div>
          <details className="wr-drawer-details">
            <summary>More details</summary>
            <div className="wr-form-grid">
              <label><span>Role</span><input value={roleLabel} disabled={!editable} onChange={(event) => setRoleLabel(event.target.value)} /></label>
              <label><span>Team</span><input value={teamCode} disabled={!editable} onChange={(event) => setTeamCode(event.target.value)} /></label>
              <label className="wr-span-2"><span>Location</span><input value={locationLabel} disabled={!editable} onChange={(event) => setLocationLabel(event.target.value)} /></label>
              <label className="wr-span-2"><span>Task note</span><textarea rows={3} value={taskNote} disabled={!editable} onChange={(event) => setTaskNote(event.target.value)} /></label>
            </div>
          </details>
          <details className="wr-drawer-details" onToggle={(event) => setAllocationOpen(event.currentTarget.open)}>
            <summary>Work and aircraft allocation</summary>
            {allocationOpen ? <div className="wr-drawer-tabs"><div role="tablist" aria-label="Assignment allocation"><button type="button" role="tab" aria-selected={allocationTab === "tasks"} onClick={() => setAllocationTab("tasks")}>Tasks</button><button type="button" role="tab" aria-selected={allocationTab === "aircraft"} onClick={() => setAllocationTab("aircraft")}>Aircraft</button></div>{allocationTab === "tasks" ? <RosterTaskAllocationEditor assignment={assignment} editable={editable} /> : <AircraftAllocationEditor assignmentId={assignment.id} editable={editable} />}</div> : null}
          </details>
          {error ? <div className="wr-inline-error">{error}</div> : null}
        </>
      )}
      <div className="wr-drawer__footer">{editable && !pendingSync ? <button type="button" className="wr-button wr-button--danger-ghost" onClick={remove} disabled={busy}><Trash2 size={16} /> Delete</button> : <StatusPill value={pendingSync ? "PENDING SYNC" : "PUBLISHED LOCK"} />}<div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" onClick={onClose}>Close</button>{editable && !pendingSync ? <button type="button" className="wr-button wr-button--primary" onClick={save} disabled={busy || !reason.trim()}><Save size={16} /> Save changes</button> : null}</div></div>
    </motion.aside>
  );
}

function SourceWarning({ source, message, retry }: { source: keyof PlannerSourceErrors; message: string; retry: () => Promise<void> }) {
  return <div className="wr-inline-warning"><AlertTriangle size={16} /><span><strong>{source.replace(/_/g, " ")} degraded:</strong> {message}</span><button type="button" className="wr-button wr-button--small" onClick={() => void retry()}><RefreshCw size={14} /> Retry</button></div>;
}

function OperationProgress({ operation, generation }: { operation: string; generation?: GenerationProgress | null }) {
  const label = operation === "prefill-patterns"
    ? generation
      ? `Generating roster · ${generation.processedPeople}/${generation.totalPeople} people`
      : "Preparing effective work patterns…"
    : operation === "create-version"
      ? "Creating the monthly draft…"
      : operation === "grid-fill"
        ? "Applying the selected shift range…"
        : operation === "validate"
          ? "Checking coverage and compliance…"
          : operation === "submit"
            ? "Submitting the roster for approval…"
            : operation === "approve"
              ? "Recording approval…"
              : operation === "publish"
                ? "Publishing the roster…"
                : "Saving roster changes…";
  const percentage = generation?.totalPeople
    ? Math.min(100, Math.round((generation.processedPeople / generation.totalPeople) * 100))
    : null;
  return <div className="wr-operation-progress" role="status" aria-live="polite"><RefreshCw size={14} className="is-spinning" /><span>{label}</span>{generation ? <strong>{generation.created} duties · {generation.skipped} skipped{generation.conflicts ? ` · ${generation.conflicts} conflicts` : ""}</strong> : null}<div className={percentage === null ? "" : "is-determinate"} aria-hidden="true"><i style={percentage === null ? undefined : { width: `${percentage}%` }} /></div></div>;
}

function ReviewDialog({ status, assignmentCount, plannedHours, blockers, warnings, approvals, busy, canSubmit, canApprove, canPublish, onAction, onClose }: {
  status: string;
  assignmentCount: number;
  plannedHours: number;
  blockers: number;
  warnings: number;
  approvals: string | null;
  busy: string | null;
  canSubmit: boolean;
  canApprove: boolean;
  canPublish: boolean;
  onAction: (action: "validate" | "submit" | "approve" | "publish") => void;
  onClose: () => void;
}) {
  return <div className="wr-review-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="wr-review-dialog" role="dialog" aria-modal="true" aria-labelledby="wr-review-title"><header><div><span className="wr-eyebrow">Final review</span><h2 id="wr-review-title">Review roster</h2></div><button type="button" className="wr-icon-button" aria-label="Close review" onClick={onClose}><X size={17} /></button></header><div className="wr-review-summary"><article><strong>{assignmentCount}</strong><span>Assignments</span></article><article><strong>{plannedHours}</strong><span>Planned hours</span></article><article className={blockers ? "is-danger" : "is-good"}><strong>{blockers}</strong><span>Blockers</span></article><article className={warnings ? "is-warning" : "is-good"}><strong>{warnings}</strong><span>Warnings</span></article></div><div className="wr-review-state"><StatusPill value={status} />{approvals ? <span>{approvals} approvals</span> : null}</div>{blockers ? <div className="wr-inline-error"><AlertTriangle size={15} /> Resolve all blockers before submission.</div> : <div className="wr-success-note"><CheckCircle2 size={16} /> No submission blockers detected.</div>}<footer><button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => onAction("validate")}><ShieldCheck size={16} /> Run checks</button><div className="wr-actions">{canSubmit ? <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || blockers > 0} onClick={() => onAction("submit")}><Send size={16} /> Submit for approval</button> : null}{canApprove ? <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || blockers > 0} onClick={() => onAction("approve")}><ClipboardCheck size={16} /> Approve</button> : null}{canPublish ? <button type="button" className="wr-button wr-button--success" disabled={Boolean(busy) || blockers > 0} onClick={() => onAction("publish")}><CheckCircle2 size={16} /> Publish roster</button> : null}</div></footer></section></div>;
}

function CellIssuePopover({ issue, onOpen, onDismiss }: { issue: CellIssue; onOpen: () => void; onDismiss: () => void }) {
  return <div className="wr-cell-issue" role="alert" onClick={(event) => event.stopPropagation()}><div><AlertTriangle size={14} /><span><strong>{issue.title}</strong><small>{issue.message}</small></span></div><footer>{issue.assignmentId ? <button type="button" onClick={onOpen}>Open existing</button> : null}<button type="button" onClick={onDismiss}>Dismiss</button></footer></div>;
}

export function RosterPlannerV2() {
  const data = useRosterPlannerDataV2();
  const [templateId, setTemplateId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [prefillOpen, setPrefillOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [gridSelection, setGridSelection] = useState<GridSelection | null>(null);
  const [cellEntry, setCellEntry] = useState<{ key: string; value: string } | null>(null);
  const [cellIssue, setCellIssue] = useState<CellIssue | null>(null);
  const [copiedShiftCode, setCopiedShiftCode] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [rotationUpdatingUserId, setRotationUpdatingUserId] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const plannerRef = useRef<HTMLDivElement>(null);
  const cellRefs = useRef(new Map<string, HTMLDivElement>());

  const period = data.periods.find((row) => row.id === data.selectedPeriodId);
  const timezoneName = period?.timezone_name || "UTC";
  const editable = Boolean(data.selectedVersion?.can_edit && data.contracts?.capabilities.edit !== false);
  const canGeneratePatterns = Boolean(editable && data.contracts?.permissions.includes("roster.manage_patterns"));
  const canApplyRecommendations = Boolean(
    editable
    && data.contracts?.permissions.includes("roster.edit")
    && data.contracts?.permissions.includes("roster.delete_draft_assignment")
    && data.contracts?.permissions.includes("roster.allocate_work"),
  );
  const plannerTemplates = data.templates.filter((row) => !["TRAINING", "LEAVE"].includes(row.kind));
  const focusedDepartmentId = gridSelection
    ? data.people.find((person) => person.user_id === gridSelection.focus.userId)?.department_id
    : null;
  const pickerTemplates = focusedDepartmentId
    ? plannerTemplates.filter((template) => shiftAvailableForDepartment(template, focusedDepartmentId))
    : plannerTemplates;
  const selectedTemplate = pickerTemplates.find((row) => row.id === templateId) || pickerTemplates.find((row) => row.kind === "DAY") || pickerTemplates[0];
  const selected = data.assignments.find((row) => row.id === selectedId) || null;
  const people = data.people;
  const byId = useMemo(() => new Map(data.assignments.map((assignment) => [assignment.id, assignment])), [data.assignments]);

  const commitmentsQuery = useQuery({
    queryKey: ["rostering", "planner", "commitments", data.month.from, data.month.to],
    queryFn: () => boundedCommitments(listRosterCommitments({ from: data.month.from, to: data.month.to })),
    staleTime: 30_000,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
    refetchInterval: 30_000,
    retry: 1,
  });
  const basesQuery = useQuery({
    queryKey: ["foundations", "base-stations", "active"],
    queryFn: () => listRosterBaseStations(false),
    staleTime: 15 * 60_000,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
    retry: 1,
  });
  const holidaysQuery = useQuery({
    queryKey: ["workforce", "public-holidays", data.month.from, data.month.to],
    queryFn: () => listPublicHolidays({ from: data.month.from, to: data.month.to }),
    staleTime: 15 * 60_000,
    retry: 1,
  });
  const rotationsQuery = useQuery({
    queryKey: ["workforce", "planner", "rotation-starts"],
    queryFn: async () => {
      const [patterns, assignments] = await Promise.all([
        listWorkPatterns(false),
        listWorkPatternAssignments(),
      ]);
      return { patterns, assignments };
    },
    enabled: Boolean(period),
    staleTime: 60_000,
    retry: 1,
  });
  const recommendationsQuery = useQuery({
    queryKey: ["rostering", "planner", "coverage-recommendations", data.selectedVersionId, data.selectedVersion?.state_revision],
    queryFn: () => getRosterCoverageRecommendations(data.selectedVersionId),
    enabled: Boolean(data.selectedVersionId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: 1,
  });

  const rotationByUser = useMemo(() => {
    const result = new Map<string, {
      assignment: WorkPatternAssignmentRead;
      pattern: WorkPatternRead;
      targetDate: string;
      value: string;
      options: RotationOption[];
    }>();
    if (!period || !rotationsQuery.data) return result;
    const patterns = new Map(rotationsQuery.data.patterns.map((pattern) => [pattern.id, pattern]));
    const templates = new Map(data.templates.map((template) => [template.id, template]));
    const candidates = [...rotationsQuery.data.assignments]
      .filter((assignment) => assignment.effective_from <= period.ends_on && (!assignment.effective_to || assignment.effective_to >= period.starts_on))
      .sort((left, right) => right.effective_from.localeCompare(left.effective_from));
    for (const assignment of candidates) {
      if (result.has(assignment.user_id)) continue;
      const pattern = patterns.get(assignment.work_pattern_id);
      if (!pattern?.days.length || pattern.cycle_length_days < 1) continue;
      const targetDate = assignment.effective_from > period.starts_on ? assignment.effective_from : period.starts_on;
      const elapsedDays = differenceInCalendarDays(parseISO(targetDate), parseISO(assignment.cycle_anchor_date));
      const currentIndex = ((elapsedDays % pattern.cycle_length_days) + pattern.cycle_length_days) % pattern.cycle_length_days;
      const duplicateLabels = new Map<string, number>();
      for (const day of pattern.days) {
        const shiftCode = day.shift_template_id ? templates.get(day.shift_template_id)?.code : null;
        const label = shiftCode || day.status.slice(0, 2);
        duplicateLabels.set(label, (duplicateLabels.get(label) || 0) + 1);
      }
      const options = [...pattern.days]
        .sort((left, right) => left.cycle_day_index - right.cycle_day_index)
        .map((day) => {
          const shiftCode = day.shift_template_id ? templates.get(day.shift_template_id)?.code : null;
          const baseLabel = shiftCode || day.status.slice(0, 2);
          return {
            value: String(day.cycle_day_index),
            label: (duplicateLabels.get(baseLabel) || 0) > 1 ? `${baseLabel}·${day.cycle_day_index + 1}` : baseLabel,
          };
        });
      result.set(assignment.user_id, { assignment, pattern, targetDate, value: String(currentIndex), options });
    }
    return result;
  }, [data.templates, period, rotationsQuery.data]);

  const commitmentsByCell = useMemo(() => {
    const map = new Map<string, RosterCommitmentRead[]>();
    for (const commitment of commitmentsQuery.data?.items || []) {
      const start = localDate(commitment.starts_at, timezoneName);
      const end = inclusiveLocalEndDate(commitment.ends_at, timezoneName);
      for (const day of data.month.days) {
        const dayKey = isoDate(day);
        if (dayKey < start || dayKey > end) continue;
        const key = `${commitment.user_id}:${dayKey}`;
        map.set(key, [...(map.get(key) || []), commitment]);
      }
    }
    return map;
  }, [commitmentsQuery.data?.items, data.month.days, timezoneName]);

  const assignmentsFor = useCallback((userId: string, day: Date) => data.assignments.filter((assignment) => assignment.user_id === userId && localDate(assignment.starts_at, timezoneName) === isoDate(day)), [data.assignments, timezoneName]);
  const holidaysByDate = useMemo(() => new Map((holidaysQuery.data || []).map((holiday) => [holiday.holiday_date, holiday])), [holidaysQuery.data]);
  const dayIndexByDate = useMemo(() => new Map(data.month.days.map((day, index) => [isoDate(day), index])), [data.month.days]);
  const personIndexById = useMemo(() => new Map(people.map((person, index) => [person.user_id, index])), [people]);
  const selectedCellKeys = useMemo(() => {
    if (!gridSelection) return new Set<string>();
    const anchorRow = personIndexById.get(gridSelection.anchor.userId);
    const focusRow = personIndexById.get(gridSelection.focus.userId);
    const anchorColumn = dayIndexByDate.get(gridSelection.anchor.date);
    const focusColumn = dayIndexByDate.get(gridSelection.focus.date);
    if (anchorRow === undefined || focusRow === undefined || anchorColumn === undefined || focusColumn === undefined) return new Set<string>();
    const keys = new Set<string>();
    for (let row = Math.min(anchorRow, focusRow); row <= Math.max(anchorRow, focusRow); row += 1) {
      for (let column = Math.min(anchorColumn, focusColumn); column <= Math.max(anchorColumn, focusColumn); column += 1) {
        keys.add(`${people[row].user_id}:${isoDate(data.month.days[column])}`);
      }
    }
    return keys;
  }, [data.month.days, dayIndexByDate, gridSelection, people, personIndexById]);
  const protectedCellCount = useMemo(() => {
    let count = 0;
    commitmentsByCell.forEach((commitments) => {
      if (commitments.some((commitment) => commitment.blocking || (commitment.provisional && isWorkforceAbsence(commitment)))) count += 1;
    });
    return count;
  }, [commitmentsByCell]);
  const personSummary = useMemo(() => {
    const map = new Map<string, { dates: Set<string>; minutes: number; issues: number }>();
    for (const person of people) map.set(person.user_id, { dates: new Set(), minutes: 0, issues: 0 });
    for (const assignment of data.assignments) {
      const summary = map.get(assignment.user_id);
      if (!summary) continue;
      summary.dates.add(localDate(assignment.starts_at, timezoneName));
      summary.minutes += assignment.planned_minutes || Math.max(0, (new Date(assignment.ends_at).getTime() - new Date(assignment.starts_at).getTime()) / 60_000);
      if ((commitmentsQuery.data?.items || []).some((commitment) => commitment.user_id === assignment.user_id && (commitment.blocking || commitment.provisional) && intervalsOverlap(assignment.starts_at, assignment.ends_at, commitment.starts_at, commitment.ends_at))) summary.issues += 1;
    }
    return map;
  }, [commitmentsQuery.data?.items, data.assignments, people, timezoneName]);
  const totalPlannedHours = useMemo(() => Math.round(data.assignments.reduce((total, assignment) => total + (assignment.planned_minutes || 0), 0) / 60), [data.assignments]);
  const pendingSyncCount = useMemo(() => data.assignments.filter((assignment) => assignment.id.startsWith("offline-")).length, [data.assignments]);

  const focusCell = useCallback((point: GridPoint, extend = false) => {
    setGridSelection((current) => extend && current ? { anchor: current.anchor, focus: point } : { anchor: point, focus: point });
    window.requestAnimationFrame(() => {
      const cell = cellRefs.current.get(`${point.userId}:${point.date}`);
      cell?.scrollIntoView({ block: "nearest", inline: "nearest" });
      cell?.focus({ preventScroll: true });
    });
  }, []);

  const moveGridFocus = useCallback((rowDelta: number, columnDelta: number, extend: boolean) => {
    if (!gridSelection || !people.length || !data.month.days.length) return;
    const currentRow = personIndexById.get(gridSelection.focus.userId) ?? 0;
    const currentColumn = dayIndexByDate.get(gridSelection.focus.date) ?? 0;
    const row = Math.max(0, Math.min(people.length - 1, currentRow + rowDelta));
    const column = Math.max(0, Math.min(data.month.days.length - 1, currentColumn + columnDelta));
    focusCell({ userId: people[row].user_id, date: isoDate(data.month.days[column]) }, extend);
  }, [data.month.days, dayIndexByDate, focusCell, gridSelection, people, personIndexById]);

  const replace = (row: RosterAssignmentRead) => data.setAssignments((current) => current.map((item) => item.id === row.id ? row : item));

  const contractIssue = (person: RosterPersonRead, startsAt: string, endsAt: string): string | null => {
    if (!person.has_active_contract) return "No employment contract overlaps this roster month.";
    const dutyStart = localDate(startsAt, timezoneName);
    const finalInstant = new Date(Math.max(new Date(endsAt).getTime() - 1, new Date(startsAt).getTime())).toISOString();
    const dutyEnd = localDate(finalInstant, timezoneName);
    if (person.contract_effective_from && dutyStart < person.contract_effective_from) {
      return `Contract starts ${person.contract_effective_from}; this duty is outside the effective period.`;
    }
    if (person.contract_effective_to && dutyEnd > person.contract_effective_to) {
      return `Contract ends ${person.contract_effective_to}; this duty is outside the effective period.`;
    }
    return null;
  };

  const preventBlockedAssignment = (
    person: RosterPersonRead,
    startsAt: string,
    endsAt: string,
    excludeAssignmentId?: string,
  ): boolean => {
    const issueKey = `${person.user_id}:${localDate(startsAt, timezoneName)}`;
    const contractMessage = contractIssue(person, startsAt, endsAt);
    if (contractMessage) {
      setCellIssue({
        key: issueKey,
        title: "Contract does not cover this duty",
        message: contractMessage,
      });
      return true;
    }
    const sourceConflict = (commitmentsQuery.data?.items || []).find((commitment) => (
      commitment.user_id === person.user_id
      && (commitment.blocking || (commitment.provisional && isWorkforceAbsence(commitment)))
      && intervalsOverlap(startsAt, endsAt, commitment.starts_at, commitment.ends_at)
    ));
    if (sourceConflict) {
      const state = sourceConflict.provisional ? "pending" : "approved";
      setCellIssue({
        key: issueKey,
        title: `${sourceConflict.kind.replace(/_/g, " ")} is ${state}`,
        message: `This time is protected by ${sourceConflict.source_module.toLowerCase()}.`,
      });
      return true;
    }
    const rosterConflict = data.assignments.find((assignment) => (
      assignment.id !== excludeAssignmentId
      && assignment.user_id === person.user_id
      && OCCUPIED_STATUSES.has(assignment.status)
      && intervalsOverlap(startsAt, endsAt, assignment.starts_at, assignment.ends_at)
    ));
    if (rosterConflict) {
      setCellIssue({
        key: issueKey,
        title: `${rosterConflict.shift_code || rosterConflict.status} already assigned`,
        message: "Open the existing duty to move, edit or delete it.",
        assignmentId: rosterConflict.id,
      });
      return true;
    }
    return false;
  };

  const submitBulkAssignments = async (assignments: RosterBulkAssignmentItem[], protectedCount: number, actionLabel: string) => {
    if (!data.selectedVersion || !editable || !assignments.length) {
      if (protectedCount) setNotice(`${protectedCount} protected or occupied cell${protectedCount === 1 ? " was" : "s were"} left unchanged.`);
      return;
    }
    setBusy("grid-fill"); setError(null); setNotice(null);
    try {
      const result = await bulkCreateRosterAssignments(data.selectedVersion.id, {
        assignments,
        idempotency_key: newIdempotencyKey("planner-grid-fill"),
        atomic: false,
      });
      data.setAssignments((current) => {
        const known = new Set(current.map((row) => row.id));
        return [...current, ...result.created.filter((row) => !known.has(row.id))];
      });
      if (result.created.length) setSelectedId(result.created[result.created.length - 1].id);
      const guarded = protectedCount + result.skipped.length + result.conflicts.length;
      setNotice(`${actionLabel}: ${result.created.length} cell${result.created.length === 1 ? "" : "s"} populated${guarded ? `; ${guarded} occupied, leave, off or otherwise protected cell${guarded === 1 ? "" : "s"} unchanged` : ""}.`);
      const validation = await Promise.allSettled([validateRosterVersion(data.selectedVersion.id)]);
      await data.refresh();
      if (validation[0].status === "rejected") setError(`Assignments were saved, but automatic checks could not finish: ${errorMessage(validation[0].reason)}`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const applyShiftCode = async (rawCode: string, keys = selectedCellKeys) => {
    const code = rawCode.trim().toUpperCase();
    const template = plannerTemplates.find((row) => row.code.trim().toUpperCase() === code);
    if (!template) {
      setError(`Unknown shift code “${rawCode.trim()}”. Use ${plannerTemplates.slice(0, 8).map((row) => row.code).join(", ") || "an active shift template"}.`);
      return;
    }
    const assignments: RosterBulkAssignmentItem[] = [];
    let protectedCount = 0;
    for (const key of keys) {
      const separator = key.lastIndexOf(":");
      const userId = key.slice(0, separator);
      const date = key.slice(separator + 1);
      const person = people.find((row) => row.user_id === userId);
      const dayIndex = dayIndexByDate.get(date);
      const day = dayIndex === undefined ? null : data.month.days[dayIndex];
      if (!person || !day) { protectedCount += 1; continue; }
      if (!shiftAvailableForDepartment(template, person.department_id)) {
        protectedCount += 1;
        if (keys.size === 1) setCellIssue({ key, title: `${template.code} is department-specific`, message: "Choose a shift code available to this person's department." });
        continue;
      }
      const existing = assignmentsFor(userId, day);
      if (existing.length) {
        protectedCount += 1;
        if (keys.size === 1) setCellIssue({ key, title: `${existing[0].shift_code || existing[0].status} already assigned`, message: "Open the existing duty to move, edit or delete it.", assignmentId: existing[0].id });
        continue;
      }
      const commitments = commitmentsByCell.get(key) || [];
      const sourceCommitment = commitments.find((commitment) => commitment.blocking || (commitment.provisional && isWorkforceAbsence(commitment)));
      if (sourceCommitment) {
        protectedCount += 1;
        if (keys.size === 1) setCellIssue({ key, title: `${sourceCommitment.kind.replace(/_/g, " ")} protected`, message: `This date is controlled by ${sourceCommitment.source_module.toLowerCase()}.` });
        continue;
      }
      const dutyWindow = templateWindowInZone(day, template.default_start_time || "08:00", template.default_end_time || "17:00", timezoneName);
      const contractMessage = contractIssue(person, dutyWindow.starts_at, dutyWindow.ends_at);
      if (contractMessage) {
        protectedCount += 1;
        if (keys.size === 1) setCellIssue({ key, title: "Contract does not cover this duty", message: contractMessage });
        continue;
      }
      assignments.push({
        client_id: key,
        user_id: person.user_id,
        department_id: person.department_id,
        base_station_id: null,
        shift_template_id: template.id,
        status: assignmentStatusForTemplate(template),
        source: "MANUAL",
        starts_at: dutyWindow.starts_at,
        ends_at: dutyWindow.ends_at,
        planned_minutes: template.duration_minutes ?? dutyWindow.planned_minutes,
        change_reason: `Planner grid entry: ${template.code}`,
      });
    }
    await submitBulkAssignments(assignments, protectedCount, `Applied ${template.code}`);
  };

  const fillFromAssignment = async (assignment: RosterAssignmentRead, targetUserId: string, targetDay: Date) => {
    if (assignment.user_id !== targetUserId) {
      setError("Fill works across adjacent dates for the same person. Use a controlled assignment edit to change personnel.");
      return;
    }
    if (["LEAVE", "TRAINING", "UNAVAILABLE"].includes(assignment.status)) {
      setError(`${assignment.status.replace(/_/g, " ")} is source-owned and cannot be copied in Rostering.`);
      return;
    }
    const sourceDate = localDate(assignment.starts_at, timezoneName);
    const sourceIndex = dayIndexByDate.get(sourceDate);
    const targetIndex = dayIndexByDate.get(isoDate(targetDay));
    if (sourceIndex === undefined || targetIndex === undefined) return;
    const from = Math.min(sourceIndex, targetIndex);
    const to = Math.max(sourceIndex, targetIndex);
    const person = people.find((row) => row.user_id === targetUserId);
    if (!person) return;
    const assignments: RosterBulkAssignmentItem[] = [];
    let protectedCount = 0;
    for (let index = from; index <= to; index += 1) {
      const day = data.month.days[index];
      const key = `${targetUserId}:${isoDate(day)}`;
      if (assignmentsFor(targetUserId, day).length) { protectedCount += 1; continue; }
      const commitments = commitmentsByCell.get(key) || [];
      if (commitments.some((commitment) => commitment.blocking || (commitment.provisional && isWorkforceAbsence(commitment)))) { protectedCount += 1; continue; }
      const moved = moveIntervalToZonedDay(assignment.starts_at, assignment.ends_at, day, timezoneName);
      if (contractIssue(person, moved.starts_at, moved.ends_at)) { protectedCount += 1; continue; }
      assignments.push({
        client_id: key,
        user_id: targetUserId,
        department_id: person.department_id,
        base_station_id: assignment.base_station_id,
        shift_template_id: assignment.shift_template_id,
        status: assignment.status,
        source: "MANUAL",
        starts_at: moved.starts_at,
        ends_at: moved.ends_at,
        planned_minutes: assignment.planned_minutes,
        role_label: assignment.role_label,
        team_code: assignment.team_code,
        location_label: assignment.location_label,
        task_note: assignment.task_note,
        change_reason: `Planner fill from ${sourceDate}`,
      });
    }
    focusCell({ userId: targetUserId, date: isoDate(targetDay) }, true);
    await submitBulkAssignments(assignments, protectedCount, `Filled ${assignment.shift_code || assignment.status}`);
  };

  const create = async (person: RosterPersonRead, day: Date) => {
    if (!data.selectedVersion || !selectedTemplate || !editable) return;
    if (!shiftAvailableForDepartment(selectedTemplate, person.department_id)) {
      setCellIssue({
        key: `${person.user_id}:${isoDate(day)}`,
        title: `${selectedTemplate.code} is department-specific`,
        message: "Choose a shift code available to this person's department.",
      });
      return;
    }
    const dutyWindow = templateWindowInZone(day, selectedTemplate.default_start_time || "08:00", selectedTemplate.default_end_time || "17:00", timezoneName);
    if (preventBlockedAssignment(person, dutyWindow.starts_at, dutyWindow.ends_at)) return;
    setBusy(`create:${person.user_id}:${isoDate(day)}`); setError(null); setNotice(null);
    const status = assignmentStatusForTemplate(selectedTemplate);
    const payload = { user_id: person.user_id, department_id: person.department_id, base_station_id: null, shift_template_id: selectedTemplate.id, status, source: "MANUAL" as const, starts_at: dutyWindow.starts_at, ends_at: dutyWindow.ends_at, planned_minutes: selectedTemplate.duration_minutes ?? dutyWindow.planned_minutes, change_reason: "Planner assignment" };
    try {
      const row = await createRosterAssignment(data.selectedVersion.id, payload);
      data.setAssignments((current) => [...current, row]); setSelectedId(row.id);
    } catch (cause) {
      if (isOfflineQueuedError(cause)) {
        const now = new Date().toISOString();
        const optimistic: RosterAssignmentRead = {
          id: `offline-${cause.operation.id}`, amo_id: data.selectedVersion.amo_id, version_id: data.selectedVersion.id,
          user_id: person.user_id, department_id: person.department_id, base_station_id: null,
          shift_template_id: selectedTemplate.id, status, source: "MANUAL", source_reference_id: cause.operation.idempotencyKey,
          starts_at: dutyWindow.starts_at, ends_at: dutyWindow.ends_at,
          planned_minutes: selectedTemplate.duration_minutes ?? dutyWindow.planned_minutes,
          role_label: null, team_code: null, location_label: null, task_note: null, change_reason: "Planner assignment",
          locked_after_publish: false, state_revision: 1, deleted_at: null, created_by_user_id: null, updated_by_user_id: null,
          created_at: now, updated_at: now, user_full_name: person.full_name, user_staff_code: person.staff_code,
          user_role: person.role, department_code: person.department_code, department_name: person.department_name,
          base_code: "Effective base pending sync", base_name: null, shift_code: selectedTemplate.code,
          shift_label: selectedTemplate.label, shift_kind: selectedTemplate.kind, linked_task_count: 0, linked_task_hours: 0,
        };
        data.setAssignments((current) => [...current, optimistic]); setSelectedId(optimistic.id); setNotice(cause.message);
      } else setError(errorMessage(cause));
    } finally { setBusy(null); }
  };

  const move = async (assignment: RosterAssignmentRead, day: Date) => {
    if (!editable || assignment.locked_after_publish || assignment.id.startsWith("offline-")) return;
    const person = people.find((row) => row.user_id === assignment.user_id);
    const moved = moveIntervalToZonedDay(assignment.starts_at, assignment.ends_at, day, timezoneName);
    if (person && preventBlockedAssignment(person, moved.starts_at, moved.ends_at, assignment.id)) return;
    const previous = assignment;
    replace({ ...assignment, ...moved, state_revision: assignment.state_revision + 1 });
    setBusy(`move:${assignment.id}`); setError(null); setNotice(null);
    try { replace(await updateRosterAssignment(assignment.id, { ...moved, change_reason: "Planner drag and drop", expected_state_revision: assignment.state_revision })); }
    catch (cause) { if (isOfflineQueuedError(cause)) setNotice(cause.message); else { replace(previous); setError(errorMessage(cause)); } }
    finally { setBusy(null); }
  };

  const drop = async (event: DragEvent<HTMLDivElement>, userId: string, day: Date) => {
    event.preventDefault(); setDropTarget(null);
    const payload = getDrag(event); if (!payload) return;
    if (payload.type === "person") {
      const person = data.people.find((row) => row.user_id === payload.userId);
      if (person && person.user_id === userId) await create(person, day);
      return;
    }
    const assignment = byId.get(payload.assignmentId);
    if (payload.type === "fill") {
      if (assignment) await fillFromAssignment(assignment, userId, day);
      return;
    }
    if (!assignment || assignment.user_id !== userId) { setError("Move across days by drag-and-drop. Reassigning the person requires a controlled edit."); return; }
    await move(assignment, day);
  };

  const lifecycle = async (action: "validate" | "submit" | "approve" | "publish") => {
    const version = data.selectedVersion; if (!version) return;
    setBusy(action); setError(null); setNotice(null);
    try {
      if (action === "validate") await validateRosterVersion(version.id);
      if (action === "submit") await submitRosterVersion(version.id, { expected_state_revision: version.state_revision, comment: "Submitted from planner" });
      if (action === "approve") await approveRosterVersion(version.id, { expected_state_revision: version.state_revision, comment: "Approved from planner" });
      if (action === "publish") await publishRosterVersion(version.id, { expected_state_revision: version.state_revision, idempotency_key: newIdempotencyKey("publish"), comment: "Published from planner" });
      await Promise.all([data.refresh(), commitmentsQuery.refetch()]);
      if (action !== "validate") setReviewOpen(false);
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(null); }
  };

  const createMonthVersion = async () => {
    if (!period || busy) return;
    setBusy("create-version"); setError(null); setNotice(null);
    try {
      const created = await createRosterVersion(period.id, {
        title: `${format(data.month.days[0], "MMMM yyyy")} roster`,
        change_summary: "Initial monthly roster draft",
        idempotency_key: newIdempotencyKey("monthly-roster"),
      });
      await data.refresh();
      data.setSelectedVersionId(created.id);
      setNotice("Draft created. Generate the month to apply effective work patterns.");
      setPrefillOpen(true);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const changeRotationStart = async (userId: string, cycleDayIndex: number) => {
    const rotation = rotationByUser.get(userId);
    if (!rotation || !Number.isInteger(cycleDayIndex) || cycleDayIndex < 0) return;
    const anchorDate = format(addDays(parseISO(rotation.targetDate), -cycleDayIndex), "yyyy-MM-dd");
    setRotationUpdatingUserId(userId); setError(null); setNotice(null);
    try {
      await updateWorkPatternAssignment(rotation.assignment.id, {
        cycle_anchor_date: anchorDate,
        reason: `Planner rotation starts on cycle day ${cycleDayIndex + 1}`,
      });
      await rotationsQuery.refetch();
      const selected = rotation.options.find((option) => option.value === String(cycleDayIndex))?.label || `day ${cycleDayIndex + 1}`;
      setNotice(`${selected} is now the starting rotation for this month; following months continue from it automatically.`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRotationUpdatingUserId(null);
    }
  };

  const prefillFromPatterns = async () => {
    if (!data.selectedVersion || !period || !canGeneratePatterns) return;
    setBusy("prefill-patterns"); setError(null); setNotice(null);
    let partial: GenerationProgress | null = null;
    try {
      const rosterPeople = await listAllRosterPeople({
        page_size: 250,
        active_only: true,
        roster_eligible_only: true,
        from: period.starts_on,
        to: period.ends_on,
      });
      const userIds = rosterPeople.items.map((person) => person.user_id);
      if (!userIds.length) throw new Error("No roster-eligible personnel have an active contract for this month.");
      const batchSize = 10;
      const operationKey = newIdempotencyKey("pattern-generation");
      partial = { processedPeople: 0, totalPeople: userIds.length, created: 0, skipped: 0, conflicts: 0 };
      setGenerationProgress(partial);
      for (let offset = 0; offset < userIds.length; offset += batchSize) {
        const batchNumber = Math.floor(offset / batchSize);
        const batchUserIds = userIds.slice(offset, offset + batchSize);
        const result = await generateRosterFromPattern(data.selectedVersion.id, {
          from_date: period.starts_on,
          to_date: period.ends_on,
          user_ids: batchUserIds,
          idempotency_key: `${operationKey}-${batchNumber + 1}`,
          skip_duplicates: true,
          expected_version_revision: batchNumber === 0 ? data.selectedVersion.state_revision : undefined,
        });
        partial = {
          processedPeople: Math.min(offset + batchUserIds.length, userIds.length),
          totalPeople: userIds.length,
          created: partial.created + result.created.length,
          skipped: partial.skipped + result.skipped.length,
          conflicts: partial.conflicts + result.conflicts.length,
        };
        setGenerationProgress(partial);
      }
      setPrefillOpen(false);
      const validation = await Promise.allSettled([validateRosterVersion(data.selectedVersion.id)]);
      setNotice(`${partial.created} duties generated for ${partial.processedPeople} people; ${partial.skipped} protected or occupied dates skipped${partial.conflicts ? `; ${partial.conflicts} exceptions need review` : ""}.`);
      await Promise.all([data.refresh(), commitmentsQuery.refetch(), recommendationsQuery.refetch()]);
      if (validation[0].status === "rejected") setError(`The month was generated, but automatic checks could not finish: ${errorMessage(validation[0].reason)}`);
      if (partial.conflicts) setInsightsOpen(true);
    } catch (cause) {
      const completed = partial?.processedPeople || 0;
      setError(`${completed ? `${completed} people were completed safely. ` : ""}${errorMessage(cause)}${completed ? " Run Fill gaps again to continue; existing duties will not be duplicated." : ""}`);
    } finally {
      setBusy(null);
      setGenerationProgress(null);
    }
  };

  const applyRecommendation = async (recommendation: RosterCoverageRecommendationRead, replacementUserId: string) => {
    if (!data.selectedVersion || !canApplyRecommendations) return;
    setBusy(`recommend:${recommendation.assignment_id}`); setError(null); setNotice(null);
    try {
      const result = await applyRosterCoverageRecommendation(data.selectedVersion.id, {
        assignment_id: recommendation.assignment_id,
        replacement_user_id: replacementUserId,
        reason: `Coverage rotation after ${recommendation.commitment_kind.replace(/_/g, " ").toLowerCase()} commitment`,
        idempotency_key: newIdempotencyKey("coverage-rotation"),
        expected_assignment_revision: recommendation.assignment_state_revision,
      });
      data.setAssignments((current) => [
        ...current.filter((row) => row.id !== result.removed_assignment_id),
        result.replacement_assignment,
      ]);
      setSelectedId(result.replacement_assignment.id);
      setNotice(`Coverage reassigned to ${result.replacement_assignment.user_full_name || result.replacement_assignment.user_staff_code}. The displaced duty was removed with an audit reason.`);
      await Promise.all([data.refresh(), recommendationsQuery.refetch()]);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const refreshAll = async () => { await Promise.allSettled([data.refresh(), commitmentsQuery.refetch(), holidaysQuery.refetch(), basesQuery.refetch(), recommendationsQuery.refetch(), rotationsQuery.refetch()]); };

  const handleCellKeyDown = (event: KeyboardEvent<HTMLDivElement>, point: GridPoint, rows: RosterAssignmentRead[]) => {
    if (cellEntry) return;
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "c") {
      const code = rows[0]?.shift_code || rows[0]?.status || selectedTemplate?.code;
      if (code) {
        event.preventDefault();
        setCopiedShiftCode(code);
        void navigator.clipboard?.writeText(code).catch(() => undefined);
        setNotice(`Copied ${code}. Select a range and press Ctrl/⌘+V to fill.`);
      }
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "v" && copiedShiftCode) {
      event.preventDefault();
      void applyShiftCode(copiedShiftCode);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && ["d", "r"].includes(key.toLowerCase())) {
      const anchor = gridSelection?.anchor;
      const anchorDayIndex = anchor ? dayIndexByDate.get(anchor.date) : undefined;
      const source = anchor && anchorDayIndex !== undefined ? assignmentsFor(anchor.userId, data.month.days[anchorDayIndex])[0] : rows[0];
      const code = source?.shift_code || source?.status;
      if (code) { event.preventDefault(); void applyShiftCode(code); }
      return;
    }
    if (key === "ArrowLeft") { event.preventDefault(); moveGridFocus(0, -1, event.shiftKey); return; }
    if (key === "ArrowRight") { event.preventDefault(); moveGridFocus(0, 1, event.shiftKey); return; }
    if (key === "ArrowUp") { event.preventDefault(); moveGridFocus(-1, 0, event.shiftKey); return; }
    if (key === "ArrowDown") { event.preventDefault(); moveGridFocus(1, 0, event.shiftKey); return; }
    if (key === "Tab") { event.preventDefault(); moveGridFocus(0, event.shiftKey ? -1 : 1, false); return; }
    if (key === "Home") { event.preventDefault(); focusCell({ ...point, date: isoDate(data.month.days[0]) }, event.shiftKey); return; }
    if (key === "End") { event.preventDefault(); focusCell({ ...point, date: isoDate(data.month.days[data.month.days.length - 1]) }, event.shiftKey); return; }
    if ((key === "Enter" || key === "F2") && editable) {
      event.preventDefault();
      setCellEntry({ key: `${point.userId}:${point.date}`, value: rows[0]?.shift_code || "" });
      return;
    }
    if (editable && !event.altKey && !event.ctrlKey && !event.metaKey && key.length === 1 && /[a-zA-Z0-9_-]/.test(key)) {
      event.preventDefault();
      setCellEntry({ key: `${point.userId}:${point.date}`, value: key.toUpperCase() });
    }
  };

  useEffect(() => {
    const planner = plannerRef.current;
    if (!planner) return;
    const measure = () => {
      const top = planner.getBoundingClientRect().top;
      planner.style.setProperty("--wr-planner-height", `${Math.max(440, window.innerHeight - top - 10)}px`);
    };
    measure();
    window.addEventListener("resize", measure);
    const observer = new ResizeObserver(measure);
    if (planner.parentElement) observer.observe(planner.parentElement);
    return () => { window.removeEventListener("resize", measure); observer.disconnect(); };
  }, [data.loading]);

  useEffect(() => {
    const handleShortcut = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = Boolean(target?.closest("input, select, textarea, [contenteditable='true']"));
      const inPlannerGrid = Boolean(target?.closest(".wr-drop-cell"));
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
        return;
      }
      if (event.key === "Escape") {
        setCellEntry(null);
        setCommandOpen(false);
        setInsightsOpen(false);
        return;
      }
      if (editing || inPlannerGrid || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "/") { event.preventDefault(); searchRef.current?.focus(); }
      if (event.key === "[") { event.preventDefault(); data.moveMonth(-1); }
      if (event.key === "]") { event.preventDefault(); data.moveMonth(1); }
      if (event.key.toLowerCase() === "c") { event.preventDefault(); setInsightsOpen((value) => !value); }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [data]);

  if (data.loading) return <RosterLoading label="Loading roster planner…" />;
  if (data.error && data.periods.length === 0) return <RosterError message={data.error} onRetry={data.refresh} />;

  const degradations = (Object.entries(data.sourceErrors) as Array<[keyof PlannerSourceErrors, string | null]>).filter(([source, message]) => Boolean(message) && source !== "periods" && source !== "workspace");
  const openFindingCount = data.findings.filter((finding) => !finding.resolved).length;
  const openBlockerCount = data.findings.filter((finding) => !finding.resolved && finding.severity === "BLOCKER").length;
  const openWarningCount = data.findings.filter((finding) => !finding.resolved && finding.severity === "WARNING").length;
  const recommendationCount = recommendationsQuery.data?.items.length || 0;

  return (
    <div ref={plannerRef} className="wr-planner-layout wr-planner-layout--sheet">
      <section className="wr-planner-panel">
        <div className="wr-planner-toolbar wr-planner-toolbar--compact">
          <div className="wr-month-nav"><button type="button" className="wr-icon-button" aria-label="Previous month" onClick={() => data.moveMonth(-1)}><ArrowLeft size={17} /></button><button type="button" className="wr-month-label" onClick={() => data.setAnchor(new Date())}>{format(data.month.days[0], "MMMM yyyy")}</button><button type="button" className="wr-icon-button" aria-label="Next month" onClick={() => data.moveMonth(1)}><ArrowRight size={17} /></button></div>
          <div className="wr-planner-context">
            {data.periods.length > 1 ? <select aria-label="Roster period" value={data.selectedPeriodId} onChange={(event) => data.setSelectedPeriodId(event.target.value)}>{data.periods.map((row) => <option key={row.id} value={row.id}>{row.period_code} · {row.name}</option>)}</select> : null}
            {data.versions.length > 1 ? <select aria-label="Roster version" value={data.selectedVersionId} onChange={(event) => data.setSelectedVersionId(event.target.value)}>{[...data.versions].sort((a, b) => b.version_no - a.version_no).map((row) => <option key={row.id} value={row.id}>v{row.version_no} · {row.status}</option>)}</select> : null}
            {data.selectedVersion ? <><StatusPill value={`${data.selectedVersion.status} v${data.selectedVersion.version_no}`} tone={data.selectedVersion.status.toLowerCase()} /><span className={`wr-sync-state${pendingSyncCount ? " is-pending" : ""}`}>{pendingSyncCount ? `${pendingSyncCount} offline` : data.refreshing ? "Refreshing" : "Saved"}</span></> : null}
          </div>
          <div className="wr-planner-primary-actions">
            {!data.selectedVersion && period ? <button type="button" className="wr-button wr-button--primary" onClick={() => void createMonthVersion()} disabled={Boolean(busy)}><Plus size={16} /> Create {format(data.month.days[0], "MMM")} roster</button> : null}
            {data.selectedVersion && canGeneratePatterns ? <button type="button" className={`wr-button ${data.assignments.length ? "wr-button--secondary" : "wr-button--primary"}`} onClick={() => setPrefillOpen(true)} disabled={!period || Boolean(busy) || Boolean(rotationUpdatingUserId)}><WandSparkles size={16} /> {data.assignments.length ? "Fill gaps" : "Generate month"}</button> : null}
            <button type="button" className="wr-button wr-button--secondary wr-coverage-toggle" onClick={() => setInsightsOpen(true)} disabled={!data.selectedVersion}><PanelRightOpen size={16} /> Exceptions <span>{recommendationCount + openFindingCount}</span></button>
            <button type="button" className="wr-button wr-button--primary" onClick={() => setReviewOpen(true)} disabled={!data.selectedVersion || !data.assignments.length}><ClipboardCheck size={16} /> Review &amp; submit</button>
            <button type="button" className="wr-icon-button" aria-label="Refresh planner" onClick={() => void refreshAll()}><RefreshCw size={17} className={data.refreshing || commitmentsQuery.isFetching ? "is-spinning" : ""} /></button>
          </div>
        </div>
        <div className="wr-planner-filterbar">
          <label className="wr-search"><Search size={15} /><input ref={searchRef} value={data.peopleSearch} onChange={(event) => data.setPeopleSearch(event.target.value)} placeholder="Search people" /></label>
          <label className="wr-filter-select"><Filter size={14} /><select aria-label="Department" value={data.peopleDepartmentId} onChange={(event) => data.setPeopleDepartmentId(event.target.value)}><option value="">All departments</option>{data.peopleDepartments.map((department) => <option key={department.id} value={department.id}>{department.code} · {department.name}</option>)}</select></label>
          <label className="wr-shift-picker"><span>Shift</span><select value={selectedTemplate?.id || ""} onChange={(event) => setTemplateId(event.target.value)} disabled={!editable || !pickerTemplates.length}>{pickerTemplates.map((row) => <option key={row.id} value={row.id}>{row.code} · {row.label}</option>)}</select></label>
          {selectedCellKeys.size > 1 ? <span className="wr-sheet-selection">{selectedCellKeys.size} cells</span> : null}
          <span className="wr-planner-filterbar__count"><UsersRound size={14} /> {people.length}/{data.peopleTotal}</span>
          {data.peopleHasMore ? <button type="button" className="wr-button wr-button--secondary" onClick={() => void data.loadMorePeople()} disabled={data.peopleLoadingMore}>{data.peopleLoadingMore ? <RefreshCw size={15} className="is-spinning" /> : <Plus size={15} />} Load more</button> : null}
          <button type="button" className="wr-icon-button" aria-label="Keyboard shortcuts" title="Keyboard shortcuts" onClick={() => setCommandOpen(true)}><Command size={17} /></button>
        </div>
        {busy ? <OperationProgress operation={busy} generation={busy === "prefill-patterns" ? generationProgress : null} /> : null}
        <div className="wr-planner-alert-stack">
          {degradations.map(([source, message]) => <SourceWarning key={source} source={source} message={message || "Unavailable"} retry={() => data.retrySource(source)} />)}
          {commitmentsQuery.error ? <SourceWarning source="findings" message={`Commitments unavailable: ${errorMessage(commitmentsQuery.error)}`} retry={async () => { await commitmentsQuery.refetch(); }} /> : null}
          {rotationsQuery.error ? <SourceWarning source="workspace" message={`Rotation starts unavailable: ${errorMessage(rotationsQuery.error)}`} retry={async () => { await rotationsQuery.refetch(); }} /> : null}
          {recommendationsQuery.error ? <SourceWarning source="findings" message={`Recommendations unavailable: ${errorMessage(recommendationsQuery.error)}`} retry={async () => { await recommendationsQuery.refetch(); }} /> : null}
          {basesQuery.error ? <div className="wr-inline-warning"><AlertTriangle size={16} /> Duty bases unavailable. <button type="button" className="wr-button wr-button--small" onClick={() => void basesQuery.refetch()}>Retry</button></div> : null}
          {notice ? <div className="wr-inline-note"><CheckCircle2 size={16} /> {notice}<button type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}><X size={13} /></button></div> : null}
          {error ? <div className="wr-inline-error"><AlertTriangle size={16} /> {error}<button type="button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={13} /></button></div> : null}
        </div>
        {!data.selectedVersion ? <EmptyState title={period ? `Create ${format(data.month.days[0], "MMMM")} roster` : "No monthly period"} description={period ? "Start a draft, then generate duties from effective work patterns." : "Create the monthly period in Setup first."} action={period ? <button type="button" className="wr-button wr-button--primary" onClick={() => void createMonthVersion()} disabled={Boolean(busy)}><Plus size={16} /> Create monthly roster</button> : null} /> : <div className="wr-planner-body wr-planner-body--month">
          <div className="wr-grid-scroll" aria-label={`${format(data.month.days[0], "MMMM yyyy")} monthly roster`}>
            <div className="wr-roster-grid wr-roster-grid--month" role="grid" aria-rowcount={people.length + 1} aria-colcount={data.month.days.length + 1} aria-multiselectable="true" style={{ "--wr-days": data.month.days.length } as CSSProperties}>
              <div className="wr-grid-row" role="row"><div className="wr-grid-corner" role="columnheader"><span><strong>Personnel</strong><small>Select a cell, then type a shift code</small></span><strong className="wr-grid-corner__start" title="Starting cycle day; continuity is inferred from the saved anchor">Start</strong></div>
                {data.month.days.map((day) => { const holiday = holidaysByDate.get(isoDate(day)); return <div key={isoDate(day)} role="columnheader" className={`wr-day-header${isoDate(day) === isoDate(new Date()) ? " is-today" : ""}${[0, 6].includes(day.getDay()) ? " is-weekend" : ""}${holiday ? " is-holiday" : ""}`} title={holiday ? `${holiday.name} · ${format(day, "EEEE, d MMMM yyyy")}` : format(day, "EEEE, d MMMM yyyy")}><small>{format(day, "EEE")}</small><strong>{format(day, "d")}</strong>{holiday ? <em>H</em> : null}</div>; })}
              </div>
              {people.map((person) => {
                const summary = personSummary.get(person.user_id);
                const rotation = rotationByUser.get(person.user_id);
                return <div className="wr-grid-row" role="row" key={person.user_id}>
                <div className="wr-grid-person" role="rowheader"><PersonCard person={person} assignedDays={summary?.dates.size || 0} plannedHours={Math.round((summary?.minutes || 0) / 60)} issues={summary?.issues || 0} rotationValue={rotation?.value || ""} rotationOptions={rotation?.options || []} rotationDisabled={!editable || !rotation || rotationUpdatingUserId === person.user_id || Boolean(busy)} rotationTitle={rotation ? `${rotation.pattern.code} · starts ${rotation.targetDate}` : rotationsQuery.isLoading ? "Loading saved rotation" : "Assign a work pattern in Workforce before selecting a rotation start"} onRotationChange={(cycleDayIndex) => void changeRotationStart(person.user_id, cycleDayIndex)} /></div>
                {data.month.days.map((day) => {
                  const key = `${person.user_id}:${isoDate(day)}`;
                  const point = { userId: person.user_id, date: isoDate(day) };
                  const rows = assignmentsFor(person.user_id, day);
                  const commitments = commitmentsByCell.get(key) || [];
                  const holiday = holidaysByDate.get(isoDate(day));
                  const blocking = commitments.some((commitment) => commitment.blocking);
                  const pendingAbsence = commitments.some((commitment) => commitment.provisional && isWorkforceAbsence(commitment));
                  const approvedAbsence = commitments.some((commitment) => commitment.blocking && isWorkforceAbsence(commitment));
                  const offTime = rows.some((assignment) => assignment.status === "OFF");
                  const protectedCell = blocking || pendingAbsence || offTime;
                  const displaced = blocking && rows.some((assignment) => OCCUPIED_STATUSES.has(assignment.status));
                  const pendingRisk = pendingAbsence && rows.some((assignment) => OCCUPIED_STATUSES.has(assignment.status));
                  const activeCell = gridSelection?.focus.userId === person.user_id && gridSelection.focus.date === point.date;
                  return <div
                    key={key}
                    ref={(node) => { if (node) cellRefs.current.set(key, node); else cellRefs.current.delete(key); }}
                    role="gridcell"
                    aria-selected={selectedCellKeys.has(key)}
                    tabIndex={activeCell || (!gridSelection && person.user_id === people[0]?.user_id && point.date === isoDate(data.month.days[0])) ? 0 : -1}
                    className={`wr-drop-cell${dropTarget === key ? " is-drop-target" : ""}${blocking ? " is-source-blocked" : ""}${pendingAbsence ? " is-pending-absence" : ""}${approvedAbsence ? " is-approved-absence" : ""}${offTime ? " is-off-time" : ""}${holiday ? " is-holiday" : ""}${selectedCellKeys.has(key) ? " is-range-selected" : ""}${activeCell ? " is-active-cell" : ""}${displaced ? " has-duty-conflict" : ""}${pendingRisk ? " has-pending-conflict" : ""}${[0, 6].includes(day.getDay()) ? " is-weekend" : ""}`}
                    onFocus={() => { if (!activeCell) focusCell(point); }}
                    onClick={(event) => focusCell(point, event.shiftKey)}
                    onKeyDown={(event) => handleCellKeyDown(event, point, rows)}
                    onDragOver={(event) => { if (editable && !blocking && !pendingAbsence && !offTime) { event.preventDefault(); setDropTarget(key); } }}
                    onDragLeave={() => setDropTarget((value) => value === key ? null : value)}
                    onDrop={(event) => void drop(event, person.user_id, day)}
                    onDoubleClick={() => { if (!protectedCell) void create(person, day); }}
                    title={pendingAbsence ? "Pending leave or unavailability — protected while approval is outstanding" : approvedAbsence ? "Approved leave or unavailability — source owned" : offTime ? "Off period — already allocated" : holiday ? `${holiday.name} · ${person.full_name}` : `${person.full_name} · ${format(day, "d MMMM yyyy")}`}
                  >
                    {holiday ? <span className="wr-cell-holiday" title={holiday.name}>H</span> : null}
                    {displaced || pendingRisk ? <span className={`wr-cell-conflict${pendingRisk && !displaced ? " is-pending" : ""}`} title={displaced ? "Coverage gap" : "Duty overlaps a pending leave request"}><AlertTriangle size={11} /></span> : null}
                    {pendingAbsence ? <span className="wr-cell-source-state"><Umbrella size={10} /> Pending</span> : null}
                    {commitments.map((commitment) => <CommitmentCard key={commitment.id} commitment={commitment} />)}
                    {rows.map((assignment) => <AssignmentCard key={assignment.id} assignment={assignment} timezoneName={timezoneName} selected={selectedId === assignment.id} fillEnabled={editable && selectedId === assignment.id && !assignment.locked_after_publish && !assignment.id.startsWith("offline-")} onSelect={() => { focusCell(point); setSelectedId(assignment.id); }} onMove={(days) => void move(assignment, addDays(day, days))} />)}
                    {cellIssue?.key === key ? <CellIssuePopover issue={cellIssue} onOpen={() => { if (cellIssue.assignmentId) setSelectedId(cellIssue.assignmentId); setCellIssue(null); }} onDismiss={() => setCellIssue(null)} /> : null}
                    {cellEntry?.key === key ? <form className="wr-cell-entry" onSubmit={(event) => { event.preventDefault(); const code = cellEntry.value; setCellEntry(null); void applyShiftCode(code, selectedCellKeys.size ? selectedCellKeys : new Set([key])); }}><input autoFocus maxLength={2} list="wr-shift-code-options" value={cellEntry.value} aria-label="Shift code" placeholder="A1" onChange={(event) => setCellEntry({ key, value: event.target.value.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() })} onKeyDown={(event) => { event.stopPropagation(); if (event.key === "Escape") { event.preventDefault(); setCellEntry(null); cellRefs.current.get(key)?.focus(); } }} /></form> : null}
                    {rows.length === 0 && commitments.length === 0 && editable && !cellEntry ? <button type="button" className="wr-cell-add" title={`Assign ${person.full_name} on ${format(day, "d MMMM")}`} aria-label={`Assign ${person.full_name} on ${format(day, "d MMMM")}`} onClick={() => void create(person, day)} disabled={busy === `create:${person.user_id}:${isoDate(day)}`}><Plus size={12} /></button> : null}
                  </div>;
                })}
              </div>;})}
            </div>
            <datalist id="wr-shift-code-options">{pickerTemplates.map((template) => <option key={template.id} value={template.code}>{template.label}</option>)}</datalist>
          </div>
        </div>}
      </section>
      {insightsOpen ? <div className="wr-issue-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setInsightsOpen(false); }}><FindingRail
        findings={data.findings}
        recommendations={recommendationsQuery.data?.items || []}
        recommendationLoading={recommendationsQuery.isPending || recommendationsQuery.isFetching}
        editable={canApplyRecommendations}
        busy={busy}
        onApplyRecommendation={(recommendation, replacementUserId) => void applyRecommendation(recommendation, replacementUserId)}
        onFocus={setSelectedId}
        onClose={() => setInsightsOpen(false)}
      /></div> : null}
      {reviewOpen && data.selectedVersion ? <ReviewDialog
        status={data.selectedVersion.status}
        assignmentCount={data.assignments.length}
        plannedHours={totalPlannedHours}
        blockers={openBlockerCount}
        warnings={openWarningCount}
        approvals={data.selectedVersion.approval_required_count ? `${data.selectedVersion.approval_approved_count}/${data.selectedVersion.approval_required_count}` : null}
        busy={busy}
        canSubmit={data.selectedVersion.can_submit}
        canApprove={data.selectedVersion.can_approve}
        canPublish={data.selectedVersion.can_publish}
        onAction={(action) => void lifecycle(action)}
        onClose={() => setReviewOpen(false)}
      /> : null}
      {commandOpen ? <div className="wr-command-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setCommandOpen(false); }}><div className="wr-command-palette" role="dialog" aria-modal="true" aria-labelledby="wr-command-title"><div className="wr-command-heading"><div><span className="wr-eyebrow">Keyboard planner</span><h2 id="wr-command-title">Quick actions</h2></div><button type="button" className="wr-icon-button" aria-label="Close commands" onClick={() => setCommandOpen(false)}><X size={16} /></button></div><button type="button" onClick={() => { data.setAnchor(new Date()); setCommandOpen(false); }}><span>Go to current month</span><kbd>T</kbd></button><button type="button" onClick={() => { data.moveMonth(-1); setCommandOpen(false); }}><span>Previous month</span><kbd>[</kbd></button><button type="button" onClick={() => { data.moveMonth(1); setCommandOpen(false); }}><span>Next month</span><kbd>]</kbd></button><button type="button" onClick={() => { setCommandOpen(false); window.setTimeout(() => searchRef.current?.focus(), 0); }}><span>Search personnel</span><kbd>/</kbd></button><button type="button" onClick={() => { setInsightsOpen(true); setCommandOpen(false); }}><span>Open coverage intelligence</span><kbd>C</kbd></button><button type="button" disabled={!data.selectedVersion || Boolean(busy)} onClick={() => { setCommandOpen(false); void lifecycle("validate"); }}><span>Validate roster</span><kbd>V</kbd></button>{canGeneratePatterns ? <button type="button" disabled={!period || Boolean(busy)} onClick={() => { setCommandOpen(false); setPrefillOpen(true); }}><span>Prefill month from patterns</span><kbd>P</kbd></button> : null}</div></div> : null}
      {prefillOpen && period && data.selectedVersion ? (
        <div className="wr-prefill-dialog" role="dialog" aria-modal="true" aria-labelledby="wr-prefill-title">
          <div className="wr-prefill-dialog__head"><div><span className="wr-eyebrow">Automation preview</span><h2 id="wr-prefill-title">Generate {format(data.month.days[0], "MMMM")} roster</h2><p>{period.starts_on}–{period.ends_on}</p></div><button type="button" className="wr-icon-button" aria-label="Close generation preview" disabled={busy === "prefill-patterns"} onClick={() => setPrefillOpen(false)}><X size={17} /></button></div>
          <div className="wr-prefill-summary"><article><strong>{data.peopleTotal}</strong><span>Personnel</span></article><article><strong>{data.assignments.length}</strong><span>Existing duties kept</span></article><article><strong>{protectedCellCount}</strong><span>Protected dates</span></article><article><strong>{recommendationCount + openFindingCount}</strong><span>Current exceptions</span></article></div>
          <ul className="wr-prefill-rules"><li><WandSparkles size={15} /> Saved start shifts continue each rotation</li><li><GraduationCap size={15} /> Leave and scheduled classes stay protected</li><li><ShieldCheck size={15} /> Occupied dates are skipped, never duplicated</li></ul>
          {generationProgress ? <div className="wr-prefill-batch-progress" role="status"><div><strong>{generationProgress.processedPeople}/{generationProgress.totalPeople} people</strong><span>{generationProgress.created} duties · {generationProgress.skipped} skipped</span></div><progress max={generationProgress.totalPeople} value={generationProgress.processedPeople} /></div> : null}
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" disabled={busy === "prefill-patterns"} onClick={() => setPrefillOpen(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || Boolean(rotationUpdatingUserId)} onClick={() => void prefillFromPatterns()}>{busy === "prefill-patterns" ? <RefreshCw size={15} className="is-spinning" /> : <WandSparkles size={15} />} {generationProgress ? "Generating…" : "Generate month"}</button></div>
        </div>
      ) : null}
      <AnimatePresence>{selected ? <AssignmentDrawer key={selected.id} assignment={selected} templates={data.templates} bases={basesQuery.data || []} timezoneName={timezoneName} editable={editable && !selected.locked_after_publish && !selected.id.startsWith("offline-")} onClose={() => setSelectedId(null)} onSaved={replace} onDeleted={(id) => data.setAssignments((current) => current.filter((row) => row.id !== id))} /> : null}</AnimatePresence>
    </div>
  );
}
