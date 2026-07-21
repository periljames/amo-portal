import { useCallback, useMemo, useState } from "react";
import { addDays, format, parseISO } from "date-fns";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Filter,
  GripVertical,
  LockKeyhole,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UserRoundPlus,
  UsersRound,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import {
  approveRosterVersion,
  createRosterAssignment,
  deleteRosterAssignment,
  publishRosterVersion,
  submitRosterVersion,
  updateRosterAssignment,
  validateRosterVersion,
} from "../../../services/rostering";
import type {
  RosterAssignmentRead,
  RosterValidationFindingRead,
  ShiftTemplateRead,
} from "../../../types/rostering";
import type { WorkforcePersonRead } from "../../../services/workforce";
import { errorMessage, formatDay, hoursLabel, isoDate, newIdempotencyKey } from "../rosterUi";
import { formatInZone, moveIntervalToZonedDay, templateWindowInZone } from "../timezone";
import { EmptyState, RosterError, RosterLoading, StatusPill } from "./RosterShell";
import { useRosterPlannerData } from "../hooks/useRosterPlannerData";

type DragPayload =
  | { type: "person"; userId: string }
  | { type: "assignment"; assignmentId: string };

function assignmentTone(status: string): string {
  const value = status.toLowerCase();
  if (value === "duty") return "duty";
  if (value === "standby") return "standby";
  if (value === "training") return "training";
  if (value === "leave") return "leave";
  if (value === "off") return "off";
  return "other";
}

function writeDrag(event: React.DragEvent, payload: DragPayload) {
  event.dataTransfer.effectAllowed = payload.type === "assignment" ? "move" : "copy";
  event.dataTransfer.setData("application/x-amo-roster", JSON.stringify(payload));
}

function readDrag(event: React.DragEvent): DragPayload | null {
  try {
    const raw = event.dataTransfer.getData("application/x-amo-roster");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DragPayload;
    return parsed?.type === "person" || parsed?.type === "assignment" ? parsed : null;
  } catch {
    return null;
  }
}

function PersonCard({ person }: { person: WorkforcePersonRead }) {
  return (
    <button
      type="button"
      className="wr-person"
      draggable
      onDragStart={(event) => writeDrag(event, { type: "person", userId: person.user_id })}
      aria-label={`Drag ${person.full_name} into the roster`}
    >
      <GripVertical size={14} aria-hidden="true" />
      <span className="wr-person__identity">
        <strong>{person.full_name}</strong>
        <small>{person.staff_code} · {person.position_title || person.role.replace(/_/g, " ")}</small>
      </span>
      <span className="wr-person__signals" aria-label="Eligibility signals">
        <i className={person.has_active_contract ? "is-good" : "is-danger"} title={person.has_active_contract ? "Active contract" : "No active contract"} />
        <i className={person.active_authorisation_count > 0 ? "is-good" : "is-warning"} title={`${person.active_authorisation_count} active authorisations`} />
      </span>
    </button>
  );
}

function AssignmentCard({
  assignment,
  timezoneName,
  selected,
  onSelect,
  onKeyboardMove,
}: {
  assignment: RosterAssignmentRead;
  timezoneName: string;
  selected: boolean;
  onSelect: () => void;
  onKeyboardMove: (days: number) => void;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.button
      type="button"
      layout={!reduceMotion}
      draggable={!assignment.locked_after_publish}
      onDragStart={(event) => writeDrag(event as unknown as React.DragEvent, { type: "assignment", assignmentId: assignment.id })}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (assignment.locked_after_publish) return;
        if (event.altKey && event.key === "ArrowLeft") {
          event.preventDefault();
          onKeyboardMove(-1);
        }
        if (event.altKey && event.key === "ArrowRight") {
          event.preventDefault();
          onKeyboardMove(1);
        }
      }}
      className={`wr-assignment wr-assignment--${assignmentTone(assignment.status)}${selected ? " is-selected" : ""}`}
      aria-label={`${assignment.shift_label || assignment.shift_code || assignment.status}, ${formatInZone(assignment.starts_at, timezoneName, "HH:mm")} to ${formatInZone(assignment.ends_at, timezoneName, "HH:mm")}. Alt and arrow keys move by one day.`}
    >
      <span className="wr-assignment__top">
        <strong>{assignment.shift_code || assignment.status}</strong>
        {assignment.locked_after_publish ? <LockKeyhole size={12} aria-label="Published and locked" /> : <GripVertical size={12} aria-hidden="true" />}
      </span>
      <span>{formatInZone(assignment.starts_at, timezoneName, "HH:mm")}–{formatInZone(assignment.ends_at, timezoneName, "HH:mm")}</span>
      <small>{assignment.role_label || assignment.base_code || "Duty"}</small>
      {assignment.linked_task_count > 0 ? <em>{assignment.linked_task_count} task{assignment.linked_task_count === 1 ? "" : "s"}</em> : null}
    </motion.button>
  );
}

function FindingRail({ findings, onFocus }: { findings: RosterValidationFindingRead[]; onFocus: (assignmentId: string) => void }) {
  const open = findings.filter((row) => !row.resolved);
  const blockers = open.filter((row) => row.severity === "BLOCKER");
  const warnings = open.filter((row) => row.severity === "WARNING");
  return (
    <aside className="wr-issue-rail" aria-label="Roster validation findings">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Validation rail</span>
          <h2>Issues to resolve</h2>
        </div>
        <div className="wr-inline-counts">
          <span className="wr-pill wr-pill--blocker">{blockers.length} blockers</span>
          <span className="wr-pill wr-pill--warning">{warnings.length} warnings</span>
        </div>
      </div>
      {open.length === 0 ? (
        <div className="wr-success-note"><CheckCircle2 size={18} /> No unresolved findings in this version.</div>
      ) : (
        <div className="wr-issue-list">
          {open.slice(0, 80).map((finding) => (
            <button
              key={finding.id}
              type="button"
              className={`wr-issue wr-issue--${finding.severity.toLowerCase()}`}
              onClick={() => finding.assignment_id && onFocus(finding.assignment_id)}
            >
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                <strong>{finding.code.replace(/_/g, " ")}</strong>
                <small>{finding.message}</small>
              </span>
              {finding.assignment_id ? <ArrowRight size={14} aria-hidden="true" /> : null}
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

function AssignmentEditor({
  assignment,
  templates,
  timezoneName,
  canEdit,
  onClose,
  onSaved,
  onDeleted,
}: {
  assignment: RosterAssignmentRead;
  templates: ShiftTemplateRead[];
  timezoneName: string;
  canEdit: boolean;
  onClose: () => void;
  onSaved: (row: RosterAssignmentRead) => void;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState(assignment.status);
  const [templateId, setTemplateId] = useState(assignment.shift_template_id || "");
  const [roleLabel, setRoleLabel] = useState(assignment.role_label || "");
  const [teamCode, setTeamCode] = useState(assignment.team_code || "");
  const [locationLabel, setLocationLabel] = useState(assignment.location_label || "");
  const [taskNote, setTaskNote] = useState(assignment.task_note || "");
  const [changeReason, setChangeReason] = useState(assignment.change_reason || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const row = await updateRosterAssignment(assignment.id, {
        status,
        shift_template_id: templateId || null,
        role_label: roleLabel || null,
        team_code: teamCode || null,
        location_label: locationLabel || null,
        task_note: taskNote || null,
        change_reason: changeReason || "Planner edit",
        expected_state_revision: assignment.state_revision,
      });
      onSaved(row);
      onClose();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Remove this draft assignment? The audit trail will retain the deletion reason.")) return;
    const reason = changeReason.trim() || window.prompt("Reason for removing this assignment", "Planner correction") || "Planner correction";
    setSaving(true);
    setError(null);
    try {
      await deleteRosterAssignment(assignment.id, { reason, expected_state_revision: assignment.state_revision });
      onDeleted(assignment.id);
      onClose();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.aside
      className="wr-drawer"
      initial={{ x: 32, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 32, opacity: 0 }}
      transition={{ duration: 0.16 }}
      aria-label="Assignment editor"
    >
      <div className="wr-drawer__header">
        <div>
          <span className="wr-eyebrow">Assignment</span>
          <h2>{assignment.user_full_name || assignment.user_staff_code || "Rostered person"}</h2>
          <p>{formatInZone(assignment.starts_at, timezoneName)} to {formatInZone(assignment.ends_at, timezoneName)}</p>
        </div>
        <button type="button" className="wr-icon-button" onClick={onClose} aria-label="Close assignment editor"><X size={18} /></button>
      </div>
      <div className="wr-form-grid">
        <label>
          <span>Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)} disabled={!canEdit}>
            {(["DUTY", "STANDBY", "TRAINING", "OFF", "LEAVE", "TRAVEL", "UNAVAILABLE", "OTHER"] as const).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>
          <span>Shift template</span>
          <select value={templateId} onChange={(event) => setTemplateId(event.target.value)} disabled={!canEdit}>
            <option value="">No template</option>
            {templates.map((template) => <option key={template.id} value={template.id}>{template.code} · {template.label}</option>)}
          </select>
        </label>
        <label>
          <span>Role on shift</span>
          <input value={roleLabel} onChange={(event) => setRoleLabel(event.target.value)} placeholder="e.g. CRS coverage" disabled={!canEdit} />
        </label>
        <label>
          <span>Team</span>
          <input value={teamCode} onChange={(event) => setTeamCode(event.target.value)} placeholder="e.g. Line A" disabled={!canEdit} />
        </label>
        <label className="wr-span-2">
          <span>Location</span>
          <input value={locationLabel} onChange={(event) => setLocationLabel(event.target.value)} placeholder="Hangar, bay or station" disabled={!canEdit} />
        </label>
        <label className="wr-span-2">
          <span>Task note</span>
          <textarea value={taskNote} onChange={(event) => setTaskNote(event.target.value)} rows={3} disabled={!canEdit} />
        </label>
        <label className="wr-span-2">
          <span>Change reason</span>
          <textarea value={changeReason} onChange={(event) => setChangeReason(event.target.value)} rows={2} placeholder="Required for controlled edits" disabled={!canEdit} />
        </label>
      </div>
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
      <div className="wr-drawer__footer">
        {canEdit ? <button type="button" className="wr-button wr-button--danger-ghost" onClick={remove} disabled={saving}><Trash2 size={16} /> Remove</button> : <StatusPill value="PUBLISHED LOCK" />}
        <div className="wr-actions">
          <button type="button" className="wr-button wr-button--secondary" onClick={onClose}>Cancel</button>
          {canEdit ? <button type="button" className="wr-button wr-button--primary" onClick={save} disabled={saving}><Save size={16} /> {saving ? "Saving…" : "Save"}</button> : null}
        </div>
      </div>
    </motion.aside>
  );
}

export function RosterPlanner() {
  const data = useRosterPlannerData();
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("ALL");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const selectedPeriod = data.periods.find((row) => row.id === data.selectedPeriodId);
  const timezoneName = selectedPeriod?.timezone_name || "UTC";
  const canEdit = !!data.selectedVersion?.can_edit && data.contracts?.capabilities.edit === true;
  const templates = data.templates;
  const activeTemplate = templates.find((row) => row.id === selectedTemplateId)
    || templates.find((row) => row.kind === "DAY")
    || templates[0];

  const departments = useMemo(() => Array.from(new Set(data.people.map((person) => person.department_code).filter(Boolean) as string[])).sort(), [data.people]);
  const people = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.people.filter((person) => {
      if (department !== "ALL" && person.department_code !== department) return false;
      if (!term) return true;
      return `${person.full_name} ${person.staff_code} ${person.position_title || ""} ${person.department_name || ""}`.toLowerCase().includes(term);
    });
  }, [data.people, department, search]);

  const assignmentById = useMemo(() => new Map(data.assignments.map((row) => [row.id, row])), [data.assignments]);
  const selectedAssignment = selectedAssignmentId ? assignmentById.get(selectedAssignmentId) || null : null;

  const assignmentsFor = useCallback((userId: string, day: Date) => data.assignments.filter((row) => {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezoneName, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(parseISO(row.starts_at));
    const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
    return row.user_id === userId && `${values.year}-${values.month}-${values.day}` === isoDate(day);
  }), [data.assignments, timezoneName]);

  const replaceAssignment = (row: RosterAssignmentRead) => {
    data.setAssignments((current) => current.map((item) => item.id === row.id ? row : item));
  };

  const createForPerson = async (person: WorkforcePersonRead, day: Date) => {
    if (!data.selectedVersion || !activeTemplate || !canEdit) return;
    setBusy(`create:${person.user_id}:${isoDate(day)}`);
    setActionError(null);
    try {
      const window = templateWindowInZone(
        day,
        activeTemplate.default_start_time || "08:00",
        activeTemplate.default_end_time || "17:00",
        timezoneName,
      );
      const row = await createRosterAssignment(data.selectedVersion.id, {
        user_id: person.user_id,
        department_id: person.department_id,
        base_station_id: person.primary_base_station_id,
        shift_template_id: activeTemplate.id,
        status: activeTemplate.kind === "STANDBY" ? "STANDBY" : activeTemplate.kind === "TRAINING" ? "TRAINING" : activeTemplate.kind === "OFF" ? "OFF" : activeTemplate.kind === "LEAVE" ? "LEAVE" : "DUTY",
        source: "MANUAL",
        starts_at: window.starts_at,
        ends_at: window.ends_at,
        planned_minutes: activeTemplate.duration_minutes ?? window.planned_minutes,
        change_reason: "Planner assignment",
      });
      data.setAssignments((current) => [...current, row]);
      setSelectedAssignmentId(row.id);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const moveAssignment = async (assignment: RosterAssignmentRead, day: Date) => {
    if (!canEdit || assignment.locked_after_publish) return;
    const previous = assignment;
    const moved = moveIntervalToZonedDay(assignment.starts_at, assignment.ends_at, day, timezoneName);
    const optimistic = { ...assignment, ...moved, state_revision: assignment.state_revision + 1 };
    replaceAssignment(optimistic);
    setBusy(`move:${assignment.id}`);
    setActionError(null);
    try {
      const row = await updateRosterAssignment(assignment.id, {
        ...moved,
        change_reason: "Planner drag and drop",
        expected_state_revision: assignment.state_revision,
      });
      replaceAssignment(row);
    } catch (reason) {
      replaceAssignment(previous);
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const drop = async (event: React.DragEvent, userId: string, day: Date) => {
    event.preventDefault();
    setDropTarget(null);
    const payload = readDrag(event);
    if (!payload) return;
    if (payload.type === "person") {
      const person = data.people.find((row) => row.user_id === payload.userId);
      if (person && person.user_id === userId) await createForPerson(person, day);
      return;
    }
    const assignment = assignmentById.get(payload.assignmentId);
    if (!assignment || assignment.user_id !== userId) {
      setActionError("Assignments may be moved across days, but changing the assigned person requires an explicit edit.");
      return;
    }
    await moveAssignment(assignment, day);
  };

  const lifecycleAction = async (action: "validate" | "submit" | "approve" | "publish") => {
    const version = data.selectedVersion;
    if (!version) return;
    setBusy(action);
    setActionError(null);
    try {
      if (action === "validate") await validateRosterVersion(version.id);
      if (action === "submit") await submitRosterVersion(version.id, { expected_state_revision: version.state_revision, comment: "Submitted from planner" });
      if (action === "approve") await approveRosterVersion(version.id, { expected_state_revision: version.state_revision, comment: "Approved from planner" });
      if (action === "publish") await publishRosterVersion(version.id, { expected_state_revision: version.state_revision, idempotency_key: newIdempotencyKey("publish"), comment: "Published from planner" });
      await data.refresh();
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  if (data.loading) return <RosterLoading label="Loading roster planner…" />;
  if (data.error && data.periods.length === 0) return <RosterError message={data.error} onRetry={data.refresh} />;

  return (
    <div className="wr-planner-layout">
      <section className="wr-planner-panel">
        <div className="wr-planner-toolbar">
          <div className="wr-toolbar-group">
            <button type="button" className="wr-icon-button" onClick={() => data.moveWeek(-1)} aria-label="Previous week"><ArrowLeft size={17} /></button>
            <button type="button" className="wr-button wr-button--secondary" onClick={() => data.setAnchor(new Date())}>This week</button>
            <button type="button" className="wr-icon-button" onClick={() => data.moveWeek(1)} aria-label="Next week"><ArrowRight size={17} /></button>
            <strong>{format(data.week.days[0], "dd MMM")} – {format(data.week.days[6], "dd MMM yyyy")}</strong>
          </div>
          <div className="wr-toolbar-group wr-toolbar-group--grow">
            <label className="wr-compact-field">
              <span>Period</span>
              <select value={data.selectedPeriodId} onChange={(event) => data.setSelectedPeriodId(event.target.value)}>
                <option value="">Select period</option>
                {data.periods.map((period) => <option key={period.id} value={period.id}>{period.period_code} · {period.name}</option>)}
              </select>
            </label>
            <label className="wr-compact-field">
              <span>Version</span>
              <select value={data.selectedVersionId} onChange={(event) => data.setSelectedVersionId(event.target.value)}>
                <option value="">Select version</option>
                {[...data.versions].sort((a, b) => b.version_no - a.version_no).map((version) => <option key={version.id} value={version.id}>v{version.version_no} · {version.status}</option>)}
              </select>
            </label>
            <label className="wr-compact-field">
              <span>Template</span>
              <select value={activeTemplate?.id || ""} onChange={(event) => setSelectedTemplateId(event.target.value)} disabled={!canEdit}>
                {templates.map((template) => <option key={template.id} value={template.id}>{template.code} · {template.label}</option>)}
              </select>
            </label>
          </div>
          <button type="button" className="wr-icon-button" onClick={data.refresh} disabled={data.refreshing} aria-label="Refresh planner"><RefreshCw size={17} className={data.refreshing ? "is-spinning" : ""} /></button>
        </div>

        <div className="wr-workflow-bar">
          <div className="wr-workflow-state">
            <StatusPill value={data.selectedVersion?.status || "NO VERSION"} />
            <span>{timezoneName}</span>
            {data.selectedVersion ? <span>Revision {data.selectedVersion.state_revision}</span> : null}
          </div>
          <div className="wr-actions">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => lifecycleAction("validate")} disabled={!data.selectedVersion || !!busy}><ShieldCheck size={16} /> Validate</button>
            {data.selectedVersion?.can_submit ? <button type="button" className="wr-button wr-button--primary" onClick={() => lifecycleAction("submit")} disabled={!!busy}><Send size={16} /> Submit</button> : null}
            {data.selectedVersion?.can_approve ? <button type="button" className="wr-button wr-button--primary" onClick={() => lifecycleAction("approve")} disabled={!!busy}><ClipboardCheck size={16} /> Approve</button> : null}
            {data.selectedVersion?.can_publish ? <button type="button" className="wr-button wr-button--success" onClick={() => lifecycleAction("publish")} disabled={!!busy}><CheckCircle2 size={16} /> Publish</button> : null}
          </div>
        </div>

        {actionError ? <div className="wr-inline-error" role="alert"><AlertTriangle size={16} /> {actionError}</div> : null}
        {!data.selectedVersion ? (
          <EmptyState title="No roster version selected" description="Create or select a draft version before assigning duty." />
        ) : (
          <div className="wr-planner-body">
            <aside className="wr-people-panel">
              <div className="wr-people-panel__controls">
                <label className="wr-search">
                  <Search size={15} aria-hidden="true" />
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search personnel" />
                </label>
                <label className="wr-filter-select">
                  <Filter size={14} aria-hidden="true" />
                  <select value={department} onChange={(event) => setDepartment(event.target.value)}>
                    <option value="ALL">All departments</option>
                    {departments.map((value) => <option key={value}>{value}</option>)}
                  </select>
                </label>
              </div>
              <div className="wr-people-panel__summary"><UsersRound size={15} /> {people.length} eligible people</div>
              <div className="wr-person-list">
                {people.map((person) => <PersonCard key={person.user_id} person={person} />)}
              </div>
            </aside>

            <div className="wr-grid-scroll" role="region" aria-label="Weekly duty roster grid" tabIndex={0}>
              <div className="wr-roster-grid" style={{ "--wr-days": data.week.days.length } as React.CSSProperties}>
                <div className="wr-grid-corner">Personnel</div>
                {data.week.days.map((day) => <div key={isoDate(day)} className={`wr-day-header${isoDate(day) === isoDate(new Date()) ? " is-today" : ""}`}><strong>{formatDay(day)}</strong><small>{format(day, "yyyy")}</small></div>)}
                {people.map((person) => (
                  <div className="wr-grid-row" key={person.user_id}>
                    <div className="wr-grid-person">
                      <strong>{person.full_name}</strong>
                      <small>{person.staff_code} · {person.primary_base_code || "No base"}</small>
                    </div>
                    {data.week.days.map((day) => {
                      const key = `${person.user_id}:${isoDate(day)}`;
                      const rows = assignmentsFor(person.user_id, day);
                      return (
                        <div
                          key={key}
                          className={`wr-drop-cell${dropTarget === key ? " is-drop-target" : ""}`}
                          onDragOver={(event) => { if (canEdit) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTarget(key); } }}
                          onDragLeave={() => setDropTarget((current) => current === key ? null : current)}
                          onDrop={(event) => drop(event, person.user_id, day)}
                          onDoubleClick={() => createForPerson(person, day)}
                          aria-label={`${person.full_name}, ${formatDay(day)}. Double click or drop to assign ${activeTemplate?.label || "duty"}.`}
                        >
                          <AnimatePresence initial={false}>
                            {rows.map((assignment) => (
                              <AssignmentCard
                                key={assignment.id}
                                assignment={assignment}
                                timezoneName={timezoneName}
                                selected={selectedAssignmentId === assignment.id}
                                onSelect={() => setSelectedAssignmentId(assignment.id)}
                                onKeyboardMove={(days) => moveAssignment(assignment, addDays(day, days))}
                              />
                            ))}
                          </AnimatePresence>
                          {rows.length === 0 && canEdit ? <button type="button" className="wr-cell-add" onClick={() => createForPerson(person, day)} disabled={busy === `create:${person.user_id}:${isoDate(day)}`}><Plus size={14} /> Assign</button> : null}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      <FindingRail findings={data.findings} onFocus={setSelectedAssignmentId} />

      <AnimatePresence>
        {selectedAssignment ? (
          <AssignmentEditor
            key={selectedAssignment.id}
            assignment={selectedAssignment}
            templates={templates}
            timezoneName={timezoneName}
            canEdit={canEdit && !selectedAssignment.locked_after_publish}
            onClose={() => setSelectedAssignmentId(null)}
            onSaved={replaceAssignment}
            onDeleted={(id) => data.setAssignments((current) => current.filter((row) => row.id !== id))}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}
