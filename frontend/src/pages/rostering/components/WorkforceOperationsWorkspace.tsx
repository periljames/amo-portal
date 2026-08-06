import "./workforce-hr-workspace.css";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  downloadPayrollExport,
  hrApproveLeave,
  listLeaveRequests,
  listTimesheets,
  rejectLeaveRequest,
  supervisorApproveLeave,
} from "../../../services/workforce";
import {
  assignWorkforceHrPattern,
  decideWorkforceHrOvertime,
  getWorkforceHrDashboard,
  listWorkforceHrOvertime,
  listWorkforceHrPatterns,
  listWorkforceHrPeople,
} from "../../../services/workforceHr";
import type { HrOvertimeRequest, HrPersonReadiness } from "../../../types/workforceHr";
import type { LeaveRequestRead, TimesheetRead } from "../../../types/workforce";
import { errorMessage, isoDate } from "../rosterUi";
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
    staleTime: 60_000,
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
        />
      ) : null}
      {section === "patterns" ? (
        <PatternQueue canManage={dashboard.can_manage_contracts} busy={busy} runAction={runAction} />
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
  return (
    <div className="hr-stack">
      <section className="hr-metrics">
        {dashboard.metrics.map((metric) => <article key={metric.key} className={`is-${metric.tone}`}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
      </section>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Operational queues</span><h2>Leave, time and pattern control</h2></div><button type="button" className="wr-icon-button" aria-label="Refresh operations" onClick={onRefresh}><RefreshCw size={16} /></button></div>
        <div className="hr-readiness-list">
          <button type="button" onClick={() => onOpen("leave")}><CalendarDays size={18} /><span><strong>{dashboard.pending_leave_count}</strong> leave requests pending</span></button>
          <button type="button" onClick={() => onOpen("time")}><FileClock size={18} /><span><strong>{dashboard.pending_timesheet_count}</strong> timesheets pending</span></button>
          <button type="button" onClick={() => onOpen("time")}><UserRoundCheck size={18} /><span><strong>{dashboard.pending_overtime_count}</strong> overtime requests pending</span></button>
          <button type="button" onClick={() => onOpen("patterns")}><AlertTriangle size={18} /><span><strong>{dashboard.employees_without_pattern_count}</strong> employees without an active pattern</span></button>
        </div>
      </section>
    </div>
  );
}

function LeaveQueue({ dashboard, requests, loading, onDecision }: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  requests: LeaveRequestRead[];
  loading: boolean;
  onDecision: (target: DecisionTarget) => void;
}) {
  const pending = requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Leave workflow</span><h2>Pending leave decisions</h2></div><span className="wr-header-badge"><CalendarDays size={15} /> {pending.length} shown</span></div>
      {loading ? <RosterLoading label="Loading leave workflow…" /> : null}
      <div className="hr-approval-list">
        {pending.map((request) => (
          <article key={request.id}>
            <div><strong>{request.user_full_name || request.user_staff_code}</strong><span>{request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}</span></div>
            <StatusPill value={request.status} />
            <div className="wr-actions">
              {request.status === "SUBMITTED" && dashboard.can_review_leave ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "leave-supervisor", record: request })}>Supervisor review</button> : null}
              {request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_leave ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "leave-hr", record: request })}>HR approve</button> : null}
              {dashboard.can_review_leave ? <button type="button" className="wr-icon-button is-danger" aria-label="Reject leave" onClick={() => onDecision({ kind: "leave-reject", record: request })}><XCircle size={15} /></button> : null}
            </div>
          </article>
        ))}
      </div>
      {!loading && !pending.length ? <EmptyState title="No pending leave" description="Submitted leave requests will appear here." /> : null}
    </section>
  );
}

function TimeQueue({ dashboard, timesheets, overtime, loading, onDecision }: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  timesheets: TimesheetRead[];
  overtime: HrOvertimeRequest[];
  loading: boolean;
  onDecision: (target: DecisionTarget) => void;
}) {
  const pendingSheets = timesheets.filter((sheet) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status));
  const pendingOvertime = overtime.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  return (
    <div className="hr-stack">
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
    </div>
  );
}

function PatternQueue({ canManage, busy, runAction }: {
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<HrPersonReadiness | null>(null);
  const [patternId, setPatternId] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(isoDate(new Date()));
  const [effectiveTo, setEffectiveTo] = useState("");

  const peopleQuery = useQuery({
    queryKey: ["workforce", "hr", "missing-pattern", page, search],
    queryFn: () => listWorkforceHrPeople({ page, page_size: 25, search: search || undefined, pattern_state: "MISSING", sort_by: "name", sort_dir: "asc" }),
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

  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Effective pattern assignments</span><h2>Employees without an active work pattern</h2><p>This queue is server-paginated and does not load the full tenant workforce.</p></div><label className="hr-search"><Search size={15} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search employees missing a pattern" /></label></div>
      {peopleQuery.isPending ? <RosterLoading label="Loading pattern readiness…" /> : null}
      <div className="hr-pattern-list">
        {(peopleQuery.data?.items || []).map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.department_name || person.department_code || "No department"}</span></div><div><strong>{person.primary_base_code || "No primary base"}</strong><span>{person.position_title || person.account_role || "No position"}</span></div><StatusPill value={person.readiness_state} /><button type="button" className="wr-button wr-button--small" disabled={!canManage} onClick={() => setSelected(person)}>Assign</button></article>)}
      </div>
      {!peopleQuery.isPending && !peopleQuery.data?.items.length ? <EmptyState title="No matching pattern gaps" description="All matching employees have an active pattern." /> : null}
      <div className="wr-actions wr-actions--between"><span className="hr-person-source">{peopleQuery.data?.total || 0} employees without an active pattern</span><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {peopleQuery.data?.page || page} of {peopleQuery.data?.pages || 1}</span><button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={!peopleQuery.data?.pages || page >= peopleQuery.data.pages} onClick={() => setPage(page + 1)}>Next</button></div></div>
      {selected ? <div className="hr-decision" role="dialog" aria-modal="true" aria-label={`Assign work pattern to ${selected.full_name}`}><header className="hr-decision__head"><div><span className="wr-eyebrow">Effective assignment</span><h3>{selected.full_name}</h3></div><button type="button" className="wr-icon-button" aria-label="Close assignment" onClick={() => setSelected(null)}><X size={16} /></button></header><div className="hr-assignment-grid"><label><span>Approved pattern</span><select value={selectedPatternId} onChange={(event) => setPatternId(event.target.value)}>{patterns.map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.code} · {pattern.name}</option>)}</select></label><label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label><span>Effective to</span><input type="date" min={effectiveFrom} value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></label></div>{!patterns.length ? <div className="hr-warning"><AlertTriangle size={16} /> No active pattern exists.</div> : null}<div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setSelected(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !selectedPatternId || !effectiveFrom} onClick={assign}><Save size={15} /> Save assignment</button></div></div> : null}
    </section>
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
