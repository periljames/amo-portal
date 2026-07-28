import "./workforce-hr-workspace.css";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BriefcaseBusiness,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  FileClock,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
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
  getWorkforceHrDashboard,
  listWorkforceHrPatterns,
} from "../../../services/workforceHr";
import type { HrActionItem, HrPersonReadiness } from "../../../types/workforceHr";
import type { LeaveRequestRead, TimesheetRead, WorkPatternRead } from "../../../types/workforce";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

type HrSection = "overview" | "people" | "leave" | "time" | "patterns";
type DecisionTarget =
  | { kind: "leave-supervisor" | "leave-hr" | "leave-reject"; record: LeaveRequestRead }
  | { kind: "timesheet-supervisor" | "timesheet-hr"; record: TimesheetRead };

const SECTIONS: Array<{ id: HrSection; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "people", label: "People & contracts" },
  { id: "leave", label: "Leave" },
  { id: "time", label: "Attendance & time" },
  { id: "patterns", label: "Work patterns" },
];

export function WorkforceHrWorkspace() {
  const { amoCode = "" } = useParams();
  const queryClient = useQueryClient();
  const [section, setSection] = useState<HrSection>("overview");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<DecisionTarget | null>(null);
  const [decisionComment, setDecisionComment] = useState("");

  const dashboardQuery = useQuery({
    queryKey: ["workforce", "hr", "dashboard"],
    queryFn: () => getWorkforceHrDashboard(500),
    staleTime: 60_000,
  });
  const leaveQuery = useQuery({
    queryKey: ["workforce", "hr", "leave"],
    queryFn: () => listLeaveRequests({ page_size: 200 }),
    enabled: section === "leave",
    staleTime: 30_000,
  });
  const timesheetsQuery = useQuery({
    queryKey: ["workforce", "hr", "timesheets"],
    queryFn: () => listTimesheets({ page_size: 200 }),
    enabled: section === "time",
    staleTime: 30_000,
  });
  const patternsQuery = useQuery({
    queryKey: ["workforce", "hr", "patterns"],
    queryFn: () => listWorkforceHrPatterns(false),
    enabled: section === "patterns",
    staleTime: 5 * 60_000,
  });

  const dashboard = dashboardQuery.data;
  const people = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return dashboard?.people || [];
    return (dashboard?.people || []).filter((person) =>
      [person.full_name, person.staff_code, person.position_title, person.department_code, person.primary_base_code]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [dashboard?.people, search]);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["workforce"] });
    await queryClient.invalidateQueries({ queryKey: ["rostering", "setup"] });
  };

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const submitDecision = async () => {
    if (!decision || decisionComment.trim().length < 5) return;
    const { kind, record } = decision;
    await runAction(`decision:${record.id}`, async () => {
      if (kind === "leave-supervisor") await supervisorApproveLeave(record.id, decisionComment.trim());
      if (kind === "leave-hr") await hrApproveLeave(record.id, decisionComment.trim());
      if (kind === "leave-reject") await rejectLeaveRequest(record.id, decisionComment.trim());
      if (kind === "timesheet-supervisor") await approveTimesheet(record.id, "SUPERVISOR", decisionComment.trim());
      if (kind === "timesheet-hr") await approveTimesheet(record.id, "HR", decisionComment.trim());
      setDecision(null);
      setDecisionComment("");
    });
  };

  if (dashboardQuery.isPending && !dashboard) return <RosterLoading label="Opening Workforce and HR…" />;
  if (dashboardQuery.error && !dashboard) return <div className="wr-inline-error">{errorMessage(dashboardQuery.error)}</div>;
  if (!dashboard) return null;

  return (
    <div className="hr-workspace">
      <nav className="hr-workspace__nav" aria-label="Workforce and HR sections">
        {SECTIONS.map((item) => <button key={item.id} type="button" className={section === item.id ? "is-active" : ""} onClick={() => setSection(item.id)}>{item.label}</button>)}
      </nav>
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}

      {section === "overview" ? <HrOverview dashboard={dashboard} amoCode={amoCode} onOpen={setSection} onRefresh={() => void refresh()} /> : null}
      {section === "people" ? <PeoplePanel people={people} search={search} onSearch={setSearch} amoCode={amoCode} /> : null}
      {section === "leave" ? <LeavePanel dashboard={dashboard} requests={leaveQuery.data?.items || []} loading={leaveQuery.isPending} onDecision={setDecision} /> : null}
      {section === "time" ? <TimePanel dashboard={dashboard} timesheets={timesheetsQuery.data?.items || []} loading={timesheetsQuery.isPending} onDecision={setDecision} onPayroll={() => void downloadPayrollExport({})} /> : null}
      {section === "patterns" ? (
        <PatternsPanel
          dashboard={dashboard}
          amoCode={amoCode}
          patterns={patternsQuery.data || []}
          loading={patternsQuery.isPending}
          busy={busy}
          runAction={runAction}
        />
      ) : null}

      {decision ? (
        <div className="hr-decision" role="dialog" aria-modal="true" aria-label="Record controlled decision">
          <div className="hr-decision__head"><div><span className="wr-eyebrow">Controlled decision</span><h3>{decisionLabel(decision.kind)}</h3></div><button type="button" className="wr-icon-button" onClick={() => setDecision(null)}><X size={16} /></button></div>
          <p>{"user_full_name" in decision.record ? decision.record.user_full_name : "Employee record"}</p>
          <label><span>Reason or decision note</span><textarea value={decisionComment} onChange={(event) => setDecisionComment(event.target.value)} rows={4} placeholder="Record the evidence-based reason for this decision" /></label>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setDecision(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || decisionComment.trim().length < 5} onClick={() => void submitDecision()}><CheckCircle2 size={15} /> Record decision</button></div>
        </div>
      ) : null}
    </div>
  );
}

function decisionLabel(kind: DecisionTarget["kind"]): string {
  if (kind === "leave-supervisor") return "Supervisor leave approval";
  if (kind === "leave-hr") return "HR leave approval";
  if (kind === "leave-reject") return "Reject leave request";
  if (kind === "timesheet-supervisor") return "Supervisor timesheet approval";
  return "HR timesheet approval";
}

function HrOverview({ dashboard, amoCode, onOpen, onRefresh }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; amoCode: string; onOpen: (section: HrSection) => void; onRefresh: () => void }) {
  return (
    <div className="hr-stack">
      <section className="hr-metrics">
        {dashboard.metrics.map((metric) => <article key={metric.key} className={`is-${metric.tone}`}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
      </section>
      <div className="hr-overview-grid">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">HR action queue</span><h2>What needs attention</h2></div><button type="button" className="wr-icon-button" onClick={onRefresh}><RefreshCw size={16} /></button></div>
          <ActionQueue items={dashboard.action_queue.slice(0, 12)} amoCode={amoCode} onOpen={onOpen} />
        </section>
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Workforce readiness</span><h2>Operational eligibility</h2></div></div>
          <div className="hr-readiness-list">
            <button type="button" onClick={() => onOpen("people")}><BriefcaseBusiness size={18} /><span><strong>{dashboard.contracts_expiring_soon_count}</strong> contracts expire within 60 days</span><ArrowRight size={15} /></button>
            <button type="button" onClick={() => onOpen("patterns")}><CalendarDays size={18} /><span><strong>{dashboard.employees_without_pattern_count}</strong> employees lack work patterns</span><ArrowRight size={15} /></button>
            <button type="button" onClick={() => onOpen("people")}><AlertTriangle size={18} /><span><strong>{dashboard.employees_without_base_count}</strong> employees lack a primary base</span><ArrowRight size={15} /></button>
            <button type="button" onClick={() => onOpen("time")}><Clock3 size={18} /><span><strong>{dashboard.attendance_exception_count}</strong> attendance variances need review</span><ArrowRight size={15} /></button>
          </div>
        </section>
      </div>
      <section className="wr-panel hr-ownership">
        <ShieldCheck size={20} />
        <div><strong>Canonical Workforce ownership</strong><p>Contracts, leave, attendance, timesheets, overtime, payroll readiness and employee work-pattern assignments are managed here. Rostering consumes these records and cannot silently manufacture replacements.</p></div>
        <Link className="wr-button wr-button--secondary" to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=overview`}>Open roster setup <ArrowRight size={14} /></Link>
      </section>
    </div>
  );
}

function ActionQueue({ items, amoCode, onOpen }: { items: HrActionItem[]; amoCode: string; onOpen: (section: HrSection) => void }) {
  if (!items.length) return <EmptyState title="No urgent HR actions" description="Contract, pattern, base, leave and time records are currently clear." />;
  const action = (item: HrActionItem) => {
    if (item.category === "WORK_PATTERN") return <button type="button" className="hr-action-link" onClick={() => onOpen("patterns")}>{item.action_label || "Assign pattern"} <ArrowRight size={13} /></button>;
    if (item.category === "LEAVE") return <button type="button" className="hr-action-link" onClick={() => onOpen("leave")}>{item.action_label || "Review leave"} <ArrowRight size={13} /></button>;
    if (item.category === "TIMESHEET") return <button type="button" className="hr-action-link" onClick={() => onOpen("time")}>{item.action_label || "Review time"} <ArrowRight size={13} /></button>;
    return item.user_id ? <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/users/${encodeURIComponent(item.user_id)}`}>{item.action_label || "Open"} <ArrowRight size={13} /></Link> : null;
  };
  return <div className="hr-action-list">{items.map((item) => <article key={item.id} className={`is-${item.severity.toLowerCase()}`}><span className="hr-action-list__icon">{item.severity === "BLOCKER" ? <AlertTriangle size={17} /> : <BadgeCheck size={17} />}</span><div><strong>{item.title}</strong><p>{item.user_name ? `${item.user_name} · ` : ""}{item.detail}</p></div><StatusPill value={item.category} />{action(item)}</article>)}</div>;
}

function PeoplePanel({ people, search, onSearch, amoCode }: { people: HrPersonReadiness[]; search: string; onSearch: (value: string) => void; amoCode: string }) {
  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">People and contracts</span><h2>Employee readiness register</h2><p>One row per effective employment record, with base and work-pattern readiness shown together.</p></div><label className="hr-search"><Search size={15} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search staff, role, base or department" /></label></div>
      <div className="hr-people-table">
        <header><span>Employee</span><span>Contract</span><span>Base</span><span>Work pattern</span><span>Readiness</span><span /></header>
        {people.map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.position_title || person.department_code || "No position"}</span></div><div><strong>{person.employment_status || "No contract"}</strong><span>{person.contract_type || "—"}{person.contract_effective_to ? ` · ends ${person.contract_effective_to}` : ""}</span></div><span>{person.primary_base_code || "Missing"}</span><div><strong>{person.work_pattern_code || "Unassigned"}</strong><span>{person.work_pattern_name || "Automatic rotation unavailable"}</span></div><div><StatusPill value={person.readiness_state} />{person.readiness_reasons.map((reason) => <small key={reason}>{reason}</small>)}</div><Link className="wr-icon-button" to={`/maintenance/${encodeURIComponent(amoCode)}/admin/users/${encodeURIComponent(person.user_id)}`} aria-label={`Open ${person.full_name}`}><ArrowRight size={15} /></Link></article>)}
      </div>
      {!people.length ? <EmptyState title="No matching employees" description="Change the search or confirm effective employment contracts exist." /> : null}
    </section>
  );
}

function LeavePanel({ dashboard, requests, loading, onDecision }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; requests: LeaveRequestRead[]; loading: boolean; onDecision: (value: DecisionTarget) => void }) {
  const pending = requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Leave workflow</span><h2>Leave requests and approvals</h2><p>Leave remains Workforce-owned and automatically becomes a protected Rostering commitment after approval.</p></div><span className="wr-header-badge"><CalendarDays size={15} /> {pending.length} pending</span></div>
      {loading ? <RosterLoading label="Loading leave workflow…" /> : null}
      <div className="hr-approval-list">{pending.map((request) => <article key={request.id}><div><strong>{request.user_full_name || request.user_staff_code}</strong><span>{request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}</span>{request.published_roster_conflicts.length ? <small className="is-danger">Published roster conflict requires a controlled amendment.</small> : null}</div><StatusPill value={request.status} /><div className="wr-actions">{request.status === "SUBMITTED" && dashboard.can_review_leave ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "leave-supervisor", record: request })}>Supervisor review</button> : null}{request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_leave ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "leave-hr", record: request })}>HR approve</button> : null}{dashboard.can_review_leave || dashboard.can_approve_leave ? <button type="button" className="wr-icon-button is-danger" onClick={() => onDecision({ kind: "leave-reject", record: request })} aria-label="Reject leave"><XCircle size={15} /></button> : null}</div></article>)}</div>
      {!loading && !pending.length ? <EmptyState title="No pending leave" description="Submitted and supervisor-approved requests will appear here." /> : null}
    </section>
  );
}

function TimePanel({ dashboard, timesheets, loading, onDecision, onPayroll }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; timesheets: TimesheetRead[]; loading: boolean; onDecision: (value: DecisionTarget) => void; onPayroll: () => void }) {
  const pending = timesheets.filter((sheet) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status));
  return (
    <div className="hr-stack">
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Time control</span><h2>Timesheet approvals</h2><p>Attendance and productive work are reconciled before HR approval and payroll export.</p></div>{dashboard.can_export_payroll ? <button type="button" className="wr-button wr-button--secondary" onClick={onPayroll}><Download size={15} /> Payroll export</button> : null}</div>
        {loading ? <RosterLoading label="Loading time approvals…" /> : null}
        <div className="hr-approval-list">{pending.map((sheet) => <article key={sheet.id}><div><strong>{sheet.user_full_name || sheet.user_id}</strong><span>{sheet.period_start} → {sheet.period_end} · {Math.round(sheet.attendance_minutes / 60)}h attendance</span></div><StatusPill value={sheet.status} /><div className="wr-actions">{sheet.status === "SUBMITTED" && dashboard.can_approve_timesheet_supervisor ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "timesheet-supervisor", record: sheet })}>Supervisor review</button> : null}{sheet.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_timesheet_hr ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "timesheet-hr", record: sheet })}>HR approve</button> : null}</div></article>)}</div>
        {!loading && !pending.length ? <EmptyState title="No timesheet approvals" description="Submitted timesheets will appear here." /> : null}
      </section>
      <section className="hr-mini-grid"><article><Clock3 size={19} /><strong>{dashboard.attendance_exception_count}</strong><span>attendance exceptions</span></article><article><FileClock size={19} /><strong>{dashboard.pending_timesheet_count}</strong><span>pending timesheets</span></article><article><UserRoundCheck size={19} /><strong>{dashboard.pending_overtime_count}</strong><span>overtime requests</span></article></section>
    </div>
  );
}

function PatternsPanel({
  dashboard,
  amoCode,
  patterns,
  loading,
  busy,
  runAction,
}: {
  dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>;
  amoCode: string;
  patterns: WorkPatternRead[];
  loading: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const withoutPattern = dashboard.people.filter((person) => !person.work_pattern_code);
  const [assigning, setAssigning] = useState(false);
  const [userId, setUserId] = useState("");
  const [patternId, setPatternId] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(isoDate(new Date()));
  const [effectiveTo, setEffectiveTo] = useState("");
  const effectiveUserId = userId || withoutPattern[0]?.user_id || dashboard.people[0]?.user_id || "";
  const effectivePatternId = patternId || patterns[0]?.id || "";

  const assign = () => runAction("hr-pattern-assignment", async () => {
    await assignWorkforceHrPattern({
      user_id: effectiveUserId,
      work_pattern_id: effectivePatternId,
      effective_from: effectiveFrom,
      effective_to: effectiveTo || null,
      cycle_anchor_date: effectiveFrom,
    });
    setAssigning(false);
    setUserId("");
    setPatternId("");
    setEffectiveTo("");
  });

  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Employee rotation assignments</span><h2>Work-pattern readiness</h2><p>Pattern templates are designed in Rostering. Effective employee assignments and dates are controlled here by Workforce and HR.</p></div><div className="wr-actions"><Link className="wr-button wr-button--secondary" to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=patterns`}>Open pattern builder <ArrowRight size={14} /></Link>{dashboard.can_manage_contracts ? <button type="button" className="wr-button wr-button--primary" onClick={() => setAssigning(true)}><Plus size={15} /> Assign pattern</button> : null}</div></div>
      {loading ? <RosterLoading label="Loading approved work patterns…" /> : null}
      <div className="hr-pattern-list">{dashboard.people.map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.primary_base_code || "No base"}</span></div><div><strong>{person.work_pattern_code || "No pattern"}</strong><span>{person.work_pattern_name || "Automatic duty generation will skip this employee"}</span></div><StatusPill value={person.work_pattern_code ? "ASSIGNED" : "MISSING"} /><button type="button" className="wr-icon-button" aria-label={`Assign pattern to ${person.full_name}`} disabled={!dashboard.can_manage_contracts} onClick={() => { setUserId(person.user_id); setAssigning(true); }}><ArrowRight size={15} /></button></article>)}</div>
      {!dashboard.people.length ? <EmptyState title="No employees" description="Create effective employment contracts before assigning work patterns." /> : null}
      {withoutPattern.length ? <div className="hr-warning"><AlertTriangle size={17} /><span>{withoutPattern.length} employee{withoutPattern.length === 1 ? "" : "s"} will be omitted from automatic rotation until a pattern is assigned.</span></div> : null}

      {assigning ? (
        <div className="hr-decision" role="dialog" aria-modal="true" aria-label="Assign work pattern">
          <div className="hr-decision__head"><div><span className="wr-eyebrow">Effective assignment</span><h3>Assign employee work pattern</h3></div><button type="button" className="wr-icon-button" onClick={() => setAssigning(false)}><X size={16} /></button></div>
          <div className="hr-assignment-grid">
            <label><span>Employee</span><select value={effectiveUserId} onChange={(event) => setUserId(event.target.value)}>{dashboard.people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
            <label><span>Approved pattern</span><select value={effectivePatternId} onChange={(event) => setPatternId(event.target.value)}>{patterns.map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.code} · {pattern.name}</option>)}</select></label>
            <label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label>
            <label><span>Effective to</span><input type="date" value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></label>
          </div>
          {!patterns.length ? <div className="hr-warning"><AlertTriangle size={16} /><span>No active pattern is available. Create and approve a pattern in Rostering first.</span></div> : null}
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setAssigning(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !effectiveUserId || !effectivePatternId || !effectiveFrom} onClick={() => void assign()}><Save size={15} /> Save assignment</button></div>
        </div>
      ) : null}
    </section>
  );
}
