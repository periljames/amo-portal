import "./workforce-hr-workspace.css";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { subDays } from "date-fns";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  FileClock,
  RefreshCw,
  Save,
  Search,
  UserRoundCheck,
  X,
  XCircle,
} from "lucide-react";

import {
  approveTimesheet,
  createAttendanceEvent,
  deleteWorkPatternAssignment,
  downloadLeaveRequestsExport,
  downloadAttendanceExport,
  downloadPayrollExport,
  hrApproveLeave,
  listLeaveRequests,
  listTimesheets,
  listWorkPatternAssignments,
  rejectLeaveRequest,
  supervisorApproveLeave,
  updateWorkPatternAssignment,
} from "../../../services/workforce";
import {
  assignWorkforceHrPattern,
  decideWorkforceHrOvertime,
  getWorkforceHrDashboard,
  listWorkforceHrOvertime,
  listWorkforceHrPatterns,
  listWorkforceHrPeople,
} from "../../../services/workforceHr";
import type { HrAttendanceException, HrOvertimeRequest, HrPersonReadiness } from "../../../types/workforceHr";
import type {
  LeaveRequestRead,
  TimesheetRead,
  WorkPatternAssignmentRead,
} from "../../../types/workforce";
import { errorMessage, isoDate, newIdempotencyKey } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

type Section = "overview" | "leave" | "time" | "patterns";
type DecisionTarget =
  | { kind: "leave-supervisor" | "leave-hr" | "leave-reject"; record: LeaveRequestRead }
  | { kind: "timesheet-supervisor" | "timesheet-hr"; record: TimesheetRead }
  | { kind: "overtime-supervisor" | "overtime-hr" | "overtime-reject"; record: HrOvertimeRequest };

const SECTIONS: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "leave", label: "Leave" },
  { id: "time", label: "Attendance & time" },
  { id: "patterns", label: "Work patterns" },
];

export function WorkforceOperationsWorkspace() {
  const queryClient = useQueryClient();
  const [section, setSection] = useState<Section>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [decision, setDecision] = useState<DecisionTarget | null>(null);
  const [comment, setComment] = useState("");

  const dashboardQuery = useQuery({
    queryKey: ["workforce", "hr", "operations-dashboard"],
    queryFn: () => getWorkforceHrDashboard(25),
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });
  const leaveQuery = useQuery({
    queryKey: ["workforce", "hr", "leave-queue"],
    queryFn: () => listLeaveRequests({ page_size: 200 }),
    enabled: section === "leave",
    staleTime: 30_000,
  });
  const timesheetQuery = useQuery({
    queryKey: ["workforce", "hr", "timesheet-queue"],
    queryFn: () => listTimesheets({ page_size: 200 }),
    enabled: section === "time",
    staleTime: 30_000,
  });
  const overtimeQuery = useQuery({
    queryKey: ["workforce", "hr", "overtime-queue"],
    queryFn: () => listWorkforceHrOvertime(true),
    enabled: section === "time",
    staleTime: 30_000,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] });
    await queryClient.invalidateQueries({ queryKey: ["rostering"] });
  };

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setFailure(null);
    setMessage(null);
    try {
      await action();
      await refresh();
      setMessage("The controlled Workforce record was updated.");
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const submitDecision = async () => {
    if (!decision || comment.trim().length < 5) return;
    const { kind, record } = decision;
    await runAction(`decision:${record.id}`, async () => {
      if (kind === "leave-supervisor") await supervisorApproveLeave(record.id, comment.trim());
      if (kind === "leave-hr") await hrApproveLeave(record.id, comment.trim());
      if (kind === "leave-reject") await rejectLeaveRequest(record.id, comment.trim());
      if (kind === "timesheet-supervisor") await approveTimesheet(record.id, "SUPERVISOR", comment.trim());
      if (kind === "timesheet-hr") await approveTimesheet(record.id, "HR", comment.trim());
      if (kind.startsWith("overtime-")) {
        const stage = kind === "overtime-hr" || record.status === "SUPERVISOR_APPROVED" ? "HR" : "SUPERVISOR";
        await decideWorkforceHrOvertime(record.id, {
          stage,
          decision: kind === "overtime-reject" ? "REJECTED" : "APPROVED",
          comment: comment.trim(),
        });
      }
      setDecision(null);
      setComment("");
    });
  };

  if (dashboardQuery.isPending) return <RosterLoading label="Opening Workforce operations…" />;
  if (dashboardQuery.error || !dashboardQuery.data) {
    return <div className="wr-inline-error">{errorMessage(dashboardQuery.error || new Error("Workforce operations unavailable"))}</div>;
  }

  const dashboard = dashboardQuery.data;
  return (
    <div className="hr-workspace">
      <nav className="hr-workspace__nav" aria-label="Workforce operational sections">
        {SECTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={section === item.id ? "is-active" : ""}
            onClick={() => setSection(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {failure ? <div className="wr-inline-error" role="alert">{failure}</div> : null}
      {message ? <div className="workforce-directory__notice" role="status">{message}</div> : null}

      {section === "overview" ? (
        <Overview dashboard={dashboard} onOpen={setSection} onRefresh={() => void refresh()} />
      ) : null}
      {section === "leave" ? (
        <LeaveQueue
          dashboard={dashboard}
          requests={leaveQuery.data?.items || []}
          loading={leaveQuery.isPending}
          onDecision={setDecision}
        />
      ) : null}
      {section === "time" ? (
        <TimeQueue
          dashboard={dashboard}
          timesheets={timesheetQuery.data?.items || []}
          overtime={overtimeQuery.data || dashboard.pending_overtime}
          loading={timesheetQuery.isPending || overtimeQuery.isPending}
          onDecision={setDecision}
          runAction={runAction}
        />
      ) : null}
      {section === "patterns" ? (
        <PatternQueue canManage={dashboard.can_assign_patterns} busy={busy} runAction={runAction} />
      ) : null}

      {decision ? (
        <div className="hr-decision" role="dialog" aria-modal="true" aria-label="Record controlled decision">
          <header className="hr-decision__head">
            <div><span className="wr-eyebrow">Controlled decision</span><h3>{decisionLabel(decision.kind)}</h3></div>
            <button type="button" className="wr-icon-button" aria-label="Close decision" onClick={() => setDecision(null)}><X size={16} /></button>
          </header>
          <label><span>Reason or decision note</span><textarea rows={4} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
          <div className="wr-actions wr-actions--end">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => setDecision(null)}>Cancel</button>
            <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || comment.trim().length < 5} onClick={() => void submitDecision()}><CheckCircle2 size={15} /> Record decision</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Overview({ dashboard, onOpen, onRefresh }: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  onOpen: (section: Section) => void;
  onRefresh: () => void;
}) {
  const queueData = [
    { name: "Leave", value: dashboard.pending_leave_count, color: "#f59e0b", section: "leave" as Section },
    { name: "Timesheets", value: dashboard.pending_timesheet_count, color: "#2563eb", section: "time" as Section },
    { name: "Overtime", value: dashboard.pending_overtime_count, color: "#8b5cf6", section: "time" as Section },
    { name: "Attendance", value: dashboard.attendance_exception_count, color: "#dc2626", section: "time" as Section },
    { name: "Pattern gaps", value: dashboard.employees_without_pattern_count, color: "#0f8f8f", section: "patterns" as Section },
  ];
  const queueTotal = queueData.reduce((sum, item) => sum + item.value, 0);
  return (
    <div className="hr-stack">
      <section className="hr-metrics">
        {dashboard.metrics.map((metric) => <article key={metric.key} className={`is-${metric.tone}`}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
      </section>
      <div className="hr-operations-overview">
        <section className="wr-panel hr-queue-chart">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Work distribution</span><h2>Open operational work</h2><p>Live queue composition, refreshed every 15 seconds.</p></div><button type="button" className="wr-icon-button" aria-label="Refresh operations" onClick={onRefresh}><RefreshCw size={16} /></button></div>
          <div className="hr-queue-chart__visual" aria-label={`${queueTotal} total open Workforce items`}>
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={queueTotal ? queueData : [{ name: "Clear", value: 1, color: "#dbe4ee" }]} dataKey="value" nameKey="name" innerRadius={62} outerRadius={92} paddingAngle={2}>
                  {(queueTotal ? queueData : [{ name: "Clear", value: 1, color: "#dbe4ee" }]).map((item) => <Cell key={item.name} fill={item.color} />)}
                </Pie>
                <Tooltip formatter={(value) => [`${Number(value)} items`, "Open"]} />
              </PieChart>
            </ResponsiveContainer>
            <div><strong>{queueTotal}</strong><span>open items</span></div>
          </div>
          <div className="hr-queue-legend">
            {queueData.map((item) => <button type="button" key={item.name} onClick={() => onOpen(item.section)}><i style={{ backgroundColor: item.color }} /><span>{item.name}</span><strong>{item.value}</strong></button>)}
          </div>
        </section>
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Action board</span><h2>What needs attention</h2></div></div>
          <div className="hr-readiness-list">
            <button type="button" onClick={() => onOpen("leave")}><CalendarDays size={18} /><span><strong>{dashboard.pending_leave_count}</strong> leave requests pending</span><StatusPill value={dashboard.pending_leave_count ? "ACTION_REQUIRED" : "CLEAR"} /></button>
            <button type="button" onClick={() => onOpen("time")}><FileClock size={18} /><span><strong>{dashboard.pending_timesheet_count}</strong> timesheets pending</span><StatusPill value={dashboard.pending_timesheet_count ? "ACTION_REQUIRED" : "CLEAR"} /></button>
            <button type="button" onClick={() => onOpen("time")}><UserRoundCheck size={18} /><span><strong>{dashboard.pending_overtime_count}</strong> overtime requests pending</span><StatusPill value={dashboard.pending_overtime_count ? "ACTION_REQUIRED" : "CLEAR"} /></button>
            <button type="button" onClick={() => onOpen("patterns")}><AlertTriangle size={18} /><span><strong>{dashboard.employees_without_pattern_count}</strong> employees without an active pattern</span><StatusPill value={dashboard.employees_without_pattern_count ? "BLOCKED" : "READY"} /></button>
          </div>
        </section>
      </div>
    </div>
  );
}

function LeaveQueue({ dashboard, requests, loading, onDecision }: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  requests: LeaveRequestRead[];
  loading: boolean;
  onDecision: (target: DecisionTarget) => void;
}) {
  const [view, setView] = useState<"pending" | "all">("pending");
  const pending = requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  const shown = view === "pending" ? pending : requests;
  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div><span className="wr-eyebrow">Leave workflow</span><h2>{view === "pending" ? "Pending leave decisions" : "Leave request history"}</h2><p>Submitted employee requests update this queue automatically.</p></div>
        <div className="wr-actions">
          <div className="hr-view-toggle" role="group" aria-label="Leave queue filter"><button type="button" className={view === "pending" ? "is-active" : ""} onClick={() => setView("pending")}>Pending</button><button type="button" className={view === "all" ? "is-active" : ""} onClick={() => setView("all")}>All</button></div>
          <button type="button" className="wr-button wr-button--secondary wr-button--small" onClick={() => void downloadLeaveRequestsExport({})}><Download size={14} /> Export CSV</button>
        </div>
      </div>
      {loading ? <RosterLoading label="Loading leave workflow…" /> : null}
      <div className="hr-approval-list">
        {shown.map((request) => (
          <article key={request.id}>
            <div><strong>{request.user_full_name || request.user_staff_code}</strong><span>{request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}</span></div>
            <StatusPill value={request.status} />
            <div className="wr-actions">
              {request.status === "SUBMITTED" && dashboard.can_review_leave ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "leave-supervisor", record: request })}>Supervisor review</button> : null}
              {request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_leave ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "leave-hr", record: request })}>HR approve</button> : null}
              {["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status) && dashboard.can_review_leave ? <button type="button" className="wr-icon-button is-danger" aria-label="Reject leave" onClick={() => onDecision({ kind: "leave-reject", record: request })}><XCircle size={15} /></button> : null}
            </div>
          </article>
        ))}
      </div>
      {!loading && !shown.length ? <EmptyState title={view === "pending" ? "No pending leave" : "No leave history"} description="Submitted leave requests will appear here." /> : null}
    </section>
  );
}

function TimeQueue({ dashboard, timesheets, overtime, loading, onDecision, runAction }: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  timesheets: TimesheetRead[];
  overtime: HrOvertimeRequest[];
  loading: boolean;
  onDecision: (target: DecisionTarget) => void;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [correction, setCorrection] = useState<HrAttendanceException | null>(null);
  const [correctionMinutes, setCorrectionMinutes] = useState("");
  const [correctionNote, setCorrectionNote] = useState("");
  const pendingSheets = timesheets.filter((sheet) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status));
  const pendingOvertime = overtime.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  const submitCorrection = () => {
    if (!correction || !Number.isFinite(Number(correctionMinutes)) || Number(correctionMinutes) === 0 || correctionNote.trim().length < 8) return;
    void runAction(`attendance-correction:${correction.id}`, async () => {
      await createAttendanceEvent({
        user_id: correction.user_id,
        event_type: "MANUAL_ADJUSTMENT",
        occurred_at: new Date().toISOString(),
        source: "MANUAL",
        roster_assignment_id: correction.roster_assignment_id,
        idempotency_key: newIdempotencyKey("attendance-correction"),
        note: correctionNote.trim(),
        metadata_json: { minutes: Math.round(Number(correctionMinutes)), variance_id: correction.id, requires_review: false },
      });
      setCorrection(null);
      setCorrectionMinutes("");
      setCorrectionNote("");
    });
  };
  return (
    <div className="hr-stack">
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Attendance review</span><h2>Roster-to-attendance exceptions</h2><p>Investigate incomplete, missing or materially different attendance before approving pay.</p></div><span className="wr-header-badge"><Clock3 size={15} /> {dashboard.attendance_exception_count} open</span></div>
        <div className="hr-approval-list">
          {dashboard.attendance_exceptions.map((exception) => <article key={exception.id}><div><strong>{exception.user_full_name || exception.user_id}</strong><span>{exception.attendance_minutes} attended · {exception.planned_minutes} planned · {exception.variance_minutes > 0 ? "+" : ""}{exception.variance_minutes} min</span></div><StatusPill value={exception.classification} /><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary wr-button--small" onClick={() => void downloadAttendanceExport({ user_id: exception.user_id, from: isoDate(subDays(new Date(), 30)), to: isoDate(new Date()) })}><Download size={14} /> History</button>{dashboard.can_manage_attendance ? <button type="button" className="wr-button wr-button--small" onClick={() => setCorrection(exception)}>Correct</button> : null}</div></article>)}
        </div>
        {!dashboard.attendance_exceptions.length ? <EmptyState title="Attendance reconciled" description="No roster-to-attendance exceptions require review." /> : null}
      </section>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Time control</span><h2>Timesheet approvals</h2></div>{dashboard.can_export_payroll ? <button type="button" className="wr-button wr-button--secondary" onClick={() => void downloadPayrollExport({})}><Download size={15} /> Payroll export</button> : null}</div>
        {loading ? <RosterLoading label="Loading time approvals…" /> : null}
        <div className="hr-approval-list">
          {pendingSheets.map((sheet) => <article key={sheet.id}><div><strong>{sheet.user_full_name || sheet.user_id}</strong><span>{sheet.period_start} → {sheet.period_end} · {Math.round(sheet.attendance_minutes / 60)}h attendance</span></div><StatusPill value={sheet.status} /><div className="wr-actions">{sheet.status === "SUBMITTED" && dashboard.can_approve_timesheet_supervisor ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "timesheet-supervisor", record: sheet })}>Supervisor review</button> : null}{sheet.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_timesheet_hr ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "timesheet-hr", record: sheet })}>HR approve</button> : null}</div></article>)}
        </div>
        {!loading && !pendingSheets.length ? <EmptyState title="No timesheet approvals" description="Submitted timesheets will appear here." /> : null}
      </section>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Overtime control</span><h2>Overtime requests</h2></div><span className="wr-header-badge"><Clock3 size={15} /> {pendingOvertime.length} shown</span></div>
        <div className="hr-approval-list">
          {pendingOvertime.map((request) => <article key={request.id}><div><strong>{request.user_full_name || request.user_id}</strong><span>{request.starts_at.slice(0, 16).replace("T", " ")} · {Math.round(request.requested_minutes / 6) / 10}h</span><small>{request.reason}</small></div><StatusPill value={request.status} /><div className="wr-actions">{request.status === "SUBMITTED" && dashboard.can_approve_overtime_supervisor ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "overtime-supervisor", record: request })}>Supervisor approve</button> : null}{request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_overtime_hr ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "overtime-hr", record: request })}>HR approve</button> : null}<button type="button" className="wr-icon-button is-danger" aria-label="Reject overtime" onClick={() => onDecision({ kind: "overtime-reject", record: request })}><XCircle size={15} /></button></div></article>)}
        </div>
        {!loading && !pendingOvertime.length ? <EmptyState title="No overtime approvals" description="Submitted overtime requests will appear here." /> : null}
      </section>
      {correction ? <div className="hr-decision" role="dialog" aria-modal="true" aria-label="Record attendance correction"><header className="hr-decision__head"><div><span className="wr-eyebrow">Audited time correction</span><h3>{correction.user_full_name || correction.user_id}</h3><p>Enter only the signed minute adjustment. Negative minutes reduce paid time; positive minutes add it.</p></div><button type="button" className="wr-icon-button" aria-label="Close attendance correction" onClick={() => setCorrection(null)}><X size={16} /></button></header><div className="hr-assignment-grid"><label><span>Minute adjustment</span><input type="number" step="1" value={correctionMinutes} onChange={(event) => setCorrectionMinutes(event.target.value)} placeholder="e.g. -600" /></label><label><span>Variance</span><input value={`${correction.variance_minutes > 0 ? "+" : ""}${correction.variance_minutes} minutes`} readOnly /></label></div><label><span>Audited reason</span><textarea rows={4} value={correctionNote} onChange={(event) => setCorrectionNote(event.target.value)} placeholder="Explain the evidence used and why paid time must change" /></label><div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setCorrection(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={!Number(correctionMinutes) || correctionNote.trim().length < 8} onClick={submitCorrection}><Save size={15} /> Record correction</button></div></div> : null}
    </div>
  );
}

function PatternQueue({ canManage, busy, runAction }: {
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [view, setView] = useState<"missing" | "assigned">("missing");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<HrPersonReadiness | null>(null);
  const [managePerson, setManagePerson] = useState<HrPersonReadiness | null>(null);
  const [editingAssignment, setEditingAssignment] = useState<WorkPatternAssignmentRead | null>(null);
  const [patternId, setPatternId] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(isoDate(new Date()));
  const [effectiveTo, setEffectiveTo] = useState("");
  const [cycleAnchor, setCycleAnchor] = useState(isoDate(new Date()));
  const [assignmentReason, setAssignmentReason] = useState("");

  const peopleQuery = useQuery({
    queryKey: ["workforce", "hr", "missing-pattern", page, search],
    queryFn: () => listWorkforceHrPeople({ page, page_size: 25, search: search || undefined, pattern_state: "MISSING", sort_by: "name", sort_dir: "asc" }),
    enabled: view === "missing",
    staleTime: 30_000,
  });
  const assignedPeopleQuery = useQuery({
    queryKey: ["workforce", "hr", "assigned-pattern", page, search],
    queryFn: () => listWorkforceHrPeople({ page, page_size: 25, search: search || undefined, pattern_state: "ASSIGNED", sort_by: "name", sort_dir: "asc" }),
    enabled: view === "assigned",
    staleTime: 30_000,
  });
  const assignmentQuery = useQuery({
    queryKey: ["workforce", "hr", "pattern-assignments", managePerson?.user_id],
    queryFn: () => listWorkPatternAssignments({ user_id: managePerson?.user_id }),
    enabled: Boolean(managePerson),
    staleTime: 30_000,
  });
  const patternsQuery = useQuery({ queryKey: ["workforce", "hr", "active-patterns"], queryFn: () => listWorkforceHrPatterns(false), staleTime: 5 * 60_000 });
  const patterns = patternsQuery.data || [];
  const selectedPatternId = patternId || patterns[0]?.id || "";

  const assign = () => {
    if (!selected || !selectedPatternId || !effectiveFrom) return;
    void runAction(`pattern:${selected.user_id}`, async () => {
      await assignWorkforceHrPattern({ user_id: selected.user_id, work_pattern_id: selectedPatternId, effective_from: effectiveFrom, effective_to: effectiveTo || null, cycle_anchor_date: effectiveFrom });
      setSelected(null);
      setPatternId("");
      setEffectiveTo("");
      await peopleQuery.refetch();
    });
  };

  const beginAssignmentEdit = (assignment: WorkPatternAssignmentRead) => {
    setEditingAssignment(assignment);
    setPatternId(assignment.work_pattern_id);
    setEffectiveFrom(assignment.effective_from);
    setEffectiveTo(assignment.effective_to || "");
    setCycleAnchor(assignment.cycle_anchor_date);
    setAssignmentReason("");
  };
  const saveExisting = () => {
    if (!editingAssignment) return;
    void runAction(`pattern-edit:${editingAssignment.id}`, async () => {
      await updateWorkPatternAssignment(editingAssignment.id, { work_pattern_id: patternId, effective_from: effectiveFrom, effective_to: effectiveTo || null, cycle_anchor_date: cycleAnchor, reason: assignmentReason.trim() });
      setEditingAssignment(null);
      await Promise.all([assignmentQuery.refetch(), assignedPeopleQuery.refetch()]);
    });
  };
  const removeExisting = () => {
    if (!editingAssignment) return;
    void runAction(`pattern-delete:${editingAssignment.id}`, async () => {
      await deleteWorkPatternAssignment(editingAssignment.id, assignmentReason.trim());
      setEditingAssignment(null);
      await Promise.all([assignmentQuery.refetch(), assignedPeopleQuery.refetch()]);
    });
  };

  const activePeopleQuery = view === "missing" ? peopleQuery : assignedPeopleQuery;
  const people = activePeopleQuery.data?.items || [];

  return (
    <div className="hr-stack">
      <nav className="hr-pattern-tabs" aria-label="Work-pattern assignments"><button type="button" className={view === "missing" ? "is-active" : ""} onClick={() => { setView("missing"); setPage(1); }}>Needs a pattern</button><button type="button" className={view === "assigned" ? "is-active" : ""} onClick={() => { setView("assigned"); setPage(1); }}>Manage assignments</button></nav>
      <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Effective pattern assignments</span><h2>{view === "missing" ? "Employees without an active work pattern" : "Assigned employee rotations"}</h2><p>Employee assignments live only in Workforce. This queue is server-paginated and keeps the roster setup free of duplicate records.</p></div><label className="hr-search"><Search size={15} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={view === "missing" ? "Search employees missing a pattern" : "Search assigned employees"} /></label></div>
      {activePeopleQuery.isPending ? <RosterLoading label="Loading pattern assignments…" /> : null}
      <div className="hr-pattern-list">{people.map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.department_name || person.department_code || "No department"}</span></div><div><strong>{view === "assigned" ? person.work_pattern_code || "Assigned" : person.primary_base_code || "No primary base"}</strong><span>{view === "assigned" ? person.work_pattern_name || "Active rotation" : person.position_title || person.account_role || "No position"}</span></div><StatusPill value={view === "assigned" ? person.pattern_state : person.readiness_state} /><button type="button" className="wr-button wr-button--small" disabled={!canManage} onClick={() => view === "missing" ? setSelected(person) : setManagePerson(person)}>{view === "missing" ? "Assign" : "Manage"}</button></article>)}</div>
      {!activePeopleQuery.isPending && !people.length ? <EmptyState title={view === "missing" ? "No matching pattern gaps" : "No matching assignments"} description={view === "missing" ? "All matching employees have an active pattern." : "No assigned employee matches this search."} /> : null}
      <div className="wr-actions wr-actions--between"><span className="hr-person-source">{activePeopleQuery.data?.total || 0} {view === "missing" ? "employees need a pattern" : "assigned employees"}</span><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {activePeopleQuery.data?.page || page} of {activePeopleQuery.data?.pages || 1}</span><button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={!activePeopleQuery.data?.pages || page >= activePeopleQuery.data.pages} onClick={() => setPage(page + 1)}>Next</button></div></div>
      {selected ? <div className="hr-decision" role="dialog" aria-modal="true" aria-label={`Assign work pattern to ${selected.full_name}`}><header className="hr-decision__head"><div><span className="wr-eyebrow">Effective assignment</span><h3>{selected.full_name}</h3></div><button type="button" className="wr-icon-button" aria-label="Close assignment" onClick={() => setSelected(null)}><X size={16} /></button></header><div className="hr-assignment-grid"><label><span>Approved pattern</span><select value={selectedPatternId} onChange={(event) => setPatternId(event.target.value)}>{patterns.map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.code} · {pattern.name}</option>)}</select></label><label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label><span>Effective to</span><input type="date" min={effectiveFrom} value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></label></div>{!patterns.length ? <div className="hr-warning"><AlertTriangle size={16} /> No active pattern exists.</div> : null}<div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setSelected(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !selectedPatternId || !effectiveFrom} onClick={assign}><Save size={15} /> Save assignment</button></div></div> : null}
      {managePerson && !editingAssignment ? <div className="hr-decision" role="dialog" aria-modal="true" aria-label={`Manage work-pattern assignments for ${managePerson.full_name}`}><header className="hr-decision__head"><div><span className="wr-eyebrow">Canonical Workforce record</span><h3>{managePerson.full_name}</h3><p>Select an effective-dated assignment to edit or remove.</p></div><button type="button" className="wr-icon-button" aria-label="Close assignment manager" onClick={() => { setManagePerson(null); setEditingAssignment(null); }}><X size={16} /></button></header>{assignmentQuery.isPending ? <RosterLoading label="Loading employee rotations…" /> : <div className="hr-pattern-list">{(assignmentQuery.data || []).map((assignment) => <article key={assignment.id}><div><strong>{assignment.pattern_code || assignment.pattern_name || "Work pattern"}</strong><span>{assignment.effective_from} → {assignment.effective_to || "Open ended"}</span></div><StatusPill value={assignment.effective_to && assignment.effective_to < isoDate(new Date()) ? "ENDED" : "EFFECTIVE"} /><button type="button" className="wr-button wr-button--small" onClick={() => beginAssignmentEdit(assignment)}>Edit</button></article>)}</div>}{!assignmentQuery.isPending && !(assignmentQuery.data || []).length ? <EmptyState title="No assignment records" description="This employee no longer has an effective pattern assignment." /> : null}</div> : null}
      {editingAssignment ? <div className="hr-decision" role="dialog" aria-modal="true" aria-label="Edit work-pattern assignment"><header className="hr-decision__head"><div><span className="wr-eyebrow">Audited assignment change</span><h3>{editingAssignment.user_full_name || managePerson?.full_name}</h3></div><button type="button" className="wr-icon-button" aria-label="Close assignment editor" onClick={() => setEditingAssignment(null)}><X size={16} /></button></header><div className="hr-assignment-grid"><label><span>Approved pattern</span><select value={patternId} onChange={(event) => setPatternId(event.target.value)}>{patterns.map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.code} · {pattern.name}</option>)}</select></label><label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label><span>Effective to</span><input type="date" min={effectiveFrom} value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></label><label><span>Cycle anchor</span><input type="date" value={cycleAnchor} onChange={(event) => setCycleAnchor(event.target.value)} /></label></div><label><span>Audited reason</span><textarea rows={3} value={assignmentReason} onChange={(event) => setAssignmentReason(event.target.value)} placeholder="Explain the effective-date or rotation change" /></label><div className="wr-actions wr-actions--between"><button type="button" className="wr-button wr-button--danger-ghost" disabled={Boolean(busy) || assignmentReason.trim().length < 5} onClick={removeExisting}>Remove assignment</button><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" onClick={() => setEditingAssignment(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || assignmentReason.trim().length < 5 || !patternId || !effectiveFrom || !cycleAnchor} onClick={saveExisting}><Save size={15} /> Save changes</button></div></div></div> : null}
    </section>
    </div>
  );
}

function decisionLabel(kind: DecisionTarget["kind"]): string {
  if (kind === "leave-supervisor") return "Supervisor leave approval";
  if (kind === "leave-hr") return "HR leave approval";
  if (kind === "leave-reject") return "Reject leave request";
  if (kind === "timesheet-supervisor") return "Supervisor timesheet approval";
  if (kind === "timesheet-hr") return "HR timesheet approval";
  if (kind === "overtime-supervisor") return "Supervisor overtime approval";
  if (kind === "overtime-hr") return "HR overtime approval";
  return "Reject overtime request";
}
