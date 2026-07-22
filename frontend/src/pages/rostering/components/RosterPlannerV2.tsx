import { useCallback, useMemo, useState, type CSSProperties, type DragEvent, type KeyboardEvent } from "react";
import { addDays, format, parseISO } from "date-fns";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Filter,
  GripVertical,
  LockKeyhole,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UsersRound,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import {
  approveRosterVersion,
  createRosterAssignment,
  deleteRosterAssignment,
  publishRosterVersion,
  submitRosterVersion,
  updateRosterAssignment,
  validateRosterVersion,
} from "../../../services/rostering";
import { isOfflineQueuedError } from "../../../services/offlineHttp";
import type { RosterPersonRead } from "../../../services/rosterPeople";
import type { RosterAssignmentRead, RosterValidationFindingRead, ShiftTemplateRead } from "../../../types/rostering";
import { errorMessage, formatDay, isoDate, newIdempotencyKey } from "../rosterUi";
import { formatInZone, moveIntervalToZonedDay, templateWindowInZone } from "../timezone";
import { EmptyState, RosterError, RosterLoading, StatusPill } from "./RosterShell";
import { useRosterPlannerDataV2 } from "../hooks/useRosterPlannerDataV2";

type DragPayload = { type: "person"; userId: string } | { type: "assignment"; assignmentId: string };

function setDrag(event: DragEvent<HTMLElement>, payload: DragPayload) {
  event.dataTransfer.effectAllowed = payload.type === "assignment" ? "move" : "copy";
  event.dataTransfer.setData("application/x-amo-roster", JSON.stringify(payload));
}

function getDrag(event: DragEvent<HTMLElement>): DragPayload | null {
  try {
    const value = JSON.parse(event.dataTransfer.getData("application/x-amo-roster")) as DragPayload;
    return value?.type === "person" || value?.type === "assignment" ? value : null;
  } catch {
    return null;
  }
}

function PersonCard({ person }: { person: RosterPersonRead }) {
  return (
    <button type="button" className="wr-person" draggable onDragStart={(event) => setDrag(event, { type: "person", userId: person.user_id })}>
      <GripVertical size={14} aria-hidden="true" />
      <span className="wr-person__identity"><strong>{person.full_name}</strong><small>{person.staff_code} · {person.position_title || person.role.replace(/_/g, " ")}</small></span>
      <span className="wr-person__signals"><i className={person.has_active_contract ? "is-good" : "is-danger"} /><i className={person.active_authorisation_count ? "is-good" : "is-warning"} /></span>
    </button>
  );
}

function AssignmentCard({ assignment, timezoneName, selected, onSelect, onMove }: {
  assignment: RosterAssignmentRead;
  timezoneName: string;
  selected: boolean;
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
      </button>
    </motion.div>
  );
}

function FindingRail({ findings, onFocus }: { findings: RosterValidationFindingRead[]; onFocus: (assignmentId: string) => void }) {
  const open = findings.filter((finding) => !finding.resolved);
  return (
    <aside className="wr-issue-rail">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Validation rail</span><h2>Issues to resolve</h2></div><div className="wr-inline-counts"><span className="wr-pill wr-pill--blocker">{open.filter((row) => row.severity === "BLOCKER").length} blockers</span><span className="wr-pill wr-pill--warning">{open.filter((row) => row.severity === "WARNING").length} warnings</span></div></div>
      {open.length === 0 ? <div className="wr-success-note"><CheckCircle2 size={17} /> No unresolved findings.</div> : <div className="wr-issue-list">{open.map((finding) => <button key={finding.id} type="button" className={`wr-issue wr-issue--${finding.severity.toLowerCase()}`} onClick={() => finding.assignment_id && onFocus(finding.assignment_id)}><AlertTriangle size={15} /><span><strong>{finding.code.replace(/_/g, " ")}</strong><small>{finding.message}</small></span>{finding.assignment_id ? <ArrowRight size={14} /> : null}</button>)}</div>}
    </aside>
  );
}

function AssignmentDrawer({ assignment, templates, timezoneName, editable, onClose, onSaved, onDeleted }: {
  assignment: RosterAssignmentRead;
  templates: ShiftTemplateRead[];
  timezoneName: string;
  editable: boolean;
  onClose: () => void;
  onSaved: (row: RosterAssignmentRead) => void;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState(assignment.status);
  const [shiftTemplateId, setShiftTemplateId] = useState(assignment.shift_template_id || "");
  const [roleLabel, setRoleLabel] = useState(assignment.role_label || "");
  const [teamCode, setTeamCode] = useState(assignment.team_code || "");
  const [locationLabel, setLocationLabel] = useState(assignment.location_label || "");
  const [taskNote, setTaskNote] = useState(assignment.task_note || "");
  const [reason, setReason] = useState(assignment.change_reason || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true); setError(null);
    const patch = {
      status,
      shift_template_id: shiftTemplateId || null,
      role_label: roleLabel || null,
      team_code: teamCode || null,
      location_label: locationLabel || null,
      task_note: taskNote || null,
      change_reason: reason || "Planner edit",
      expected_state_revision: assignment.state_revision,
    };
    try {
      const row = await updateRosterAssignment(assignment.id, patch);
      onSaved(row); onClose();
    } catch (cause) {
      if (isOfflineQueuedError(cause)) {
        const template = templates.find((item) => item.id === shiftTemplateId);
        onSaved({
          ...assignment,
          ...patch,
          shift_code: template?.code || assignment.shift_code,
          shift_label: template?.label || assignment.shift_label,
          shift_kind: template?.kind || assignment.shift_kind,
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
    const deleteReason = reason.trim() || window.prompt("Reason for removing this assignment", "Planner correction");
    if (!deleteReason) return;
    setBusy(true); setError(null);
    try {
      await deleteRosterAssignment(assignment.id, { reason: deleteReason, expected_state_revision: assignment.state_revision });
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
    <motion.aside className="wr-drawer" initial={{ x: 36, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 36, opacity: 0 }}>
      <div className="wr-drawer__header"><div><span className="wr-eyebrow">Assignment</span><h2>{assignment.user_full_name || assignment.user_staff_code}</h2><p>{formatInZone(assignment.starts_at, timezoneName)} → {formatInZone(assignment.ends_at, timezoneName)}</p></div><button type="button" className="wr-icon-button" onClick={onClose}><X size={18} /></button></div>
      <div className="wr-form-grid">
        <label><span>Status</span><select value={status} disabled={!editable} onChange={(event) => setStatus(event.target.value as typeof status)}>{["DUTY", "STANDBY", "TRAINING", "OFF", "LEAVE", "TRAVEL", "UNAVAILABLE", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Shift</span><select value={shiftTemplateId} disabled={!editable} onChange={(event) => setShiftTemplateId(event.target.value)}><option value="">No template</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.code} · {template.label}</option>)}</select></label>
        <label><span>Role</span><input value={roleLabel} disabled={!editable} onChange={(event) => setRoleLabel(event.target.value)} /></label>
        <label><span>Team</span><input value={teamCode} disabled={!editable} onChange={(event) => setTeamCode(event.target.value)} /></label>
        <label className="wr-span-2"><span>Location</span><input value={locationLabel} disabled={!editable} onChange={(event) => setLocationLabel(event.target.value)} /></label>
        <label className="wr-span-2"><span>Task note</span><textarea rows={3} value={taskNote} disabled={!editable} onChange={(event) => setTaskNote(event.target.value)} /></label>
        <label className="wr-span-2"><span>Change reason</span><textarea rows={2} value={reason} disabled={!editable} onChange={(event) => setReason(event.target.value)} /></label>
      </div>
      {error ? <div className="wr-inline-error">{error}</div> : null}
      <div className="wr-drawer__footer">{editable ? <button type="button" className="wr-button wr-button--danger-ghost" onClick={remove} disabled={busy}><Trash2 size={16} /> Remove</button> : <StatusPill value={assignment.id.startsWith("offline-") ? "PENDING SYNC" : "PUBLISHED LOCK"} />}<div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" onClick={onClose}>Cancel</button>{editable ? <button type="button" className="wr-button wr-button--primary" onClick={save} disabled={busy}><Save size={16} /> Save</button> : null}</div></div>
    </motion.aside>
  );
}

export function RosterPlannerV2() {
  const data = useRosterPlannerDataV2();
  const [templateId, setTemplateId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const period = data.periods.find((row) => row.id === data.selectedPeriodId);
  const timezoneName = period?.timezone_name || "UTC";
  const editable = Boolean(data.selectedVersion?.can_edit && data.contracts?.capabilities.edit);
  const selectedTemplate = data.templates.find((row) => row.id === templateId) || data.templates.find((row) => row.kind === "DAY") || data.templates[0];
  const selected = data.assignments.find((row) => row.id === selectedId) || null;
  const people = data.people;
  const byId = useMemo(() => new Map(data.assignments.map((assignment) => [assignment.id, assignment])), [data.assignments]);

  const assignmentsFor = useCallback((userId: string, day: Date) => data.assignments.filter((assignment) => {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezoneName, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(parseISO(assignment.starts_at));
    const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
    return assignment.user_id === userId && `${values.year}-${values.month}-${values.day}` === isoDate(day);
  }), [data.assignments, timezoneName]);

  const replace = (row: RosterAssignmentRead) => data.setAssignments((current) => current.map((item) => item.id === row.id ? row : item));

  const create = async (person: RosterPersonRead, day: Date) => {
    if (!data.selectedVersion || !selectedTemplate || !editable) return;
    setBusy(`create:${person.user_id}:${isoDate(day)}`); setError(null); setNotice(null);
    const dutyWindow = templateWindowInZone(day, selectedTemplate.default_start_time || "08:00", selectedTemplate.default_end_time || "17:00", timezoneName);
    const status = selectedTemplate.kind === "STANDBY" ? "STANDBY" : selectedTemplate.kind === "TRAINING" ? "TRAINING" : selectedTemplate.kind === "OFF" ? "OFF" : selectedTemplate.kind === "LEAVE" ? "LEAVE" : "DUTY";
    const payload = { user_id: person.user_id, department_id: person.department_id, base_station_id: person.primary_base_station_id, shift_template_id: selectedTemplate.id, status, source: "MANUAL" as const, starts_at: dutyWindow.starts_at, ends_at: dutyWindow.ends_at, planned_minutes: selectedTemplate.duration_minutes ?? dutyWindow.planned_minutes, change_reason: "Planner assignment" };
    try {
      const row = await createRosterAssignment(data.selectedVersion.id, payload);
      data.setAssignments((current) => [...current, row]); setSelectedId(row.id);
    } catch (cause) {
      if (isOfflineQueuedError(cause)) {
        const now = new Date().toISOString();
        const optimistic: RosterAssignmentRead = {
          id: `offline-${cause.operation.id}`,
          amo_id: data.selectedVersion.amo_id,
          version_id: data.selectedVersion.id,
          user_id: person.user_id,
          department_id: person.department_id,
          base_station_id: person.primary_base_station_id,
          shift_template_id: selectedTemplate.id,
          status,
          source: "MANUAL",
          source_reference_id: cause.operation.idempotencyKey,
          starts_at: dutyWindow.starts_at,
          ends_at: dutyWindow.ends_at,
          planned_minutes: selectedTemplate.duration_minutes ?? dutyWindow.planned_minutes,
          role_label: null,
          team_code: null,
          location_label: null,
          task_note: null,
          change_reason: "Planner assignment",
          locked_after_publish: false,
          state_revision: 1,
          deleted_at: null,
          created_by_user_id: null,
          updated_by_user_id: null,
          created_at: now,
          updated_at: now,
          user_full_name: person.full_name,
          user_staff_code: person.staff_code,
          user_role: person.role,
          department_code: person.department_code,
          department_name: person.department_name,
          base_code: person.primary_base_code,
          base_name: null,
          shift_code: selectedTemplate.code,
          shift_label: selectedTemplate.label,
          shift_kind: selectedTemplate.kind,
          linked_task_count: 0,
          linked_task_hours: 0,
        };
        data.setAssignments((current) => [...current, optimistic]);
        setSelectedId(optimistic.id);
        setNotice(cause.message);
      } else {
        setError(errorMessage(cause));
      }
    } finally { setBusy(null); }
  };

  const move = async (assignment: RosterAssignmentRead, day: Date) => {
    if (!editable || assignment.locked_after_publish || assignment.id.startsWith("offline-")) return;
    const previous = assignment;
    const moved = moveIntervalToZonedDay(assignment.starts_at, assignment.ends_at, day, timezoneName);
    replace({ ...assignment, ...moved, state_revision: assignment.state_revision + 1 });
    setBusy(`move:${assignment.id}`); setError(null); setNotice(null);
    try { replace(await updateRosterAssignment(assignment.id, { ...moved, change_reason: "Planner drag and drop", expected_state_revision: assignment.state_revision })); }
    catch (cause) {
      if (isOfflineQueuedError(cause)) setNotice(cause.message);
      else { replace(previous); setError(errorMessage(cause)); }
    }
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
      await data.refresh();
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(null); }
  };

  if (data.loading) return <RosterLoading label="Loading roster planner…" />;
  if (data.error && data.periods.length === 0) return <RosterError message={data.error} onRetry={data.refresh} />;

  return (
    <div className="wr-planner-layout">
      <section className="wr-planner-panel">
        <div className="wr-planner-toolbar">
          <div className="wr-toolbar-group"><button type="button" className="wr-icon-button" onClick={() => data.moveWeek(-1)}><ArrowLeft size={17} /></button><button type="button" className="wr-button wr-button--secondary" onClick={() => data.setAnchor(new Date())}>This week</button><button type="button" className="wr-icon-button" onClick={() => data.moveWeek(1)}><ArrowRight size={17} /></button><strong>{format(data.week.days[0], "dd MMM")} – {format(data.week.days[6], "dd MMM yyyy")}</strong></div>
          <div className="wr-toolbar-group wr-toolbar-group--grow">
            <label className="wr-compact-field"><span>Period</span><select value={data.selectedPeriodId} onChange={(event) => data.setSelectedPeriodId(event.target.value)}><option value="">Select period</option>{data.periods.map((row) => <option key={row.id} value={row.id}>{row.period_code} · {row.name}</option>)}</select></label>
            <label className="wr-compact-field"><span>Version</span><select value={data.selectedVersionId} onChange={(event) => data.setSelectedVersionId(event.target.value)}><option value="">Select version</option>{[...data.versions].sort((a, b) => b.version_no - a.version_no).map((row) => <option key={row.id} value={row.id}>v{row.version_no} · {row.status}</option>)}</select></label>
            <label className="wr-compact-field"><span>Template</span><select value={selectedTemplate?.id || ""} onChange={(event) => setTemplateId(event.target.value)} disabled={!editable}>{data.templates.map((row) => <option key={row.id} value={row.id}>{row.code} · {row.label}</option>)}</select></label>
          </div>
          <button type="button" className="wr-icon-button" onClick={() => void data.refresh()}><RefreshCw size={17} className={data.refreshing ? "is-spinning" : ""} /></button>
        </div>
        <div className="wr-workflow-bar"><div className="wr-workflow-state"><StatusPill value={data.selectedVersion?.status || "NO VERSION"} /><span>{timezoneName}</span>{data.selectedVersion ? <span>Revision {data.selectedVersion.state_revision}</span> : null}</div><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" onClick={() => lifecycle("validate")} disabled={!data.selectedVersion || Boolean(busy)}><ShieldCheck size={16} /> Validate</button>{data.selectedVersion?.can_submit ? <button type="button" className="wr-button wr-button--primary" onClick={() => lifecycle("submit")} disabled={Boolean(busy)}><Send size={16} /> Submit</button> : null}{data.selectedVersion?.can_approve ? <button type="button" className="wr-button wr-button--primary" onClick={() => lifecycle("approve")} disabled={Boolean(busy)}><ClipboardCheck size={16} /> Approve</button> : null}{data.selectedVersion?.can_publish ? <button type="button" className="wr-button wr-button--success" onClick={() => lifecycle("publish")} disabled={Boolean(busy)}><CheckCircle2 size={16} /> Publish</button> : null}</div></div>
        {notice ? <div className="wr-inline-warning"><RefreshCw size={16} /> {notice}</div> : null}
        {error ? <div className="wr-inline-error"><AlertTriangle size={16} /> {error}</div> : null}
        {!data.selectedVersion ? <EmptyState title="No roster version selected" description="Create or select a draft version before assigning duty." /> : <div className="wr-planner-body">
          <aside className="wr-people-panel">
            <div className="wr-people-panel__controls">
              <label className="wr-search"><Search size={15} /><input value={data.peopleSearch} onChange={(event) => data.setPeopleSearch(event.target.value)} placeholder="Search name, staff code or title" /></label>
              <label className="wr-filter-select"><Filter size={14} /><select value={data.peopleDepartmentId} onChange={(event) => data.setPeopleDepartmentId(event.target.value)}><option value="">All departments</option>{data.peopleDepartments.map((department) => <option key={department.id} value={department.id}>{department.code} · {department.name}</option>)}</select></label>
            </div>
            <div className="wr-people-panel__summary"><UsersRound size={15} /> {people.length} of {data.peopleTotal} eligible people</div>
            <div className="wr-person-list">
              {people.map((person) => <PersonCard key={person.user_id} person={person} />)}
              {data.peopleHasMore ? <button type="button" className="wr-button wr-button--secondary wr-people-load-more" onClick={() => void data.loadMorePeople()} disabled={data.peopleLoadingMore}>{data.peopleLoadingMore ? <RefreshCw size={15} className="is-spinning" /> : <Plus size={15} />} Load next 100</button> : null}
            </div>
          </aside>
          <div className="wr-grid-scroll" tabIndex={0}><div className="wr-roster-grid" style={{ "--wr-days": data.week.days.length } as CSSProperties}><div className="wr-grid-corner">Personnel</div>{data.week.days.map((day) => <div key={isoDate(day)} className={`wr-day-header${isoDate(day) === isoDate(new Date()) ? " is-today" : ""}`}><strong>{formatDay(day)}</strong><small>{format(day, "yyyy")}</small></div>)}{people.map((person) => <div className="wr-grid-row" key={person.user_id}><div className="wr-grid-person"><strong>{person.full_name}</strong><small>{person.staff_code} · {person.primary_base_code || "No base"}</small></div>{data.week.days.map((day) => { const key = `${person.user_id}:${isoDate(day)}`; const rows = assignmentsFor(person.user_id, day); return <div key={key} className={`wr-drop-cell${dropTarget === key ? " is-drop-target" : ""}`} onDragOver={(event) => { if (editable) { event.preventDefault(); setDropTarget(key); } }} onDragLeave={() => setDropTarget((value) => value === key ? null : value)} onDrop={(event) => void drop(event, person.user_id, day)} onDoubleClick={() => void create(person, day)}>{rows.map((assignment) => <AssignmentCard key={assignment.id} assignment={assignment} timezoneName={timezoneName} selected={selectedId === assignment.id} onSelect={() => setSelectedId(assignment.id)} onMove={(days) => void move(assignment, addDays(day, days))} />)}{rows.length === 0 && editable ? <button type="button" className="wr-cell-add" onClick={() => void create(person, day)} disabled={busy === `create:${person.user_id}:${isoDate(day)}`}><Plus size={14} /> Assign</button> : null}</div>; })}</div>)}</div></div>
        </div>}
      </section>
      <FindingRail findings={data.findings} onFocus={setSelectedId} />
      <AnimatePresence>{selected ? <AssignmentDrawer key={selected.id} assignment={selected} templates={data.templates} timezoneName={timezoneName} editable={editable && !selected.locked_after_publish && !selected.id.startsWith("offline-")} onClose={() => setSelectedId(null)} onSaved={replace} onDeleted={(id) => data.setAssignments((current) => current.filter((row) => row.id !== id))} /> : null}</AnimatePresence>
    </div>
  );
}
