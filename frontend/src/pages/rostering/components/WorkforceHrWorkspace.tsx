import "./workforce-hr-workspace.css";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { listBaseStations } from "../../../services/foundations";
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
  createEmploymentContract,
  downloadPayrollExport,
  hrApproveLeave,
  listLeaveRequests,
  listTimesheets,
  rejectLeaveRequest,
  supervisorApproveLeave,
  updateEmploymentContract,
} from "../../../services/workforce";
import {
  assignWorkforceHrPattern,
  decideWorkforceHrOvertime,
  getWorkforceHrDashboard,
  listWorkforceHrOvertime,
  listWorkforceHrPeople,
  listWorkforceHrPatterns,
} from "../../../services/workforceHr";
import type { BaseStationRead } from "../../../types/foundations";
import type { HrActionItem, HrOvertimeRequest, HrPersonReadiness } from "../../../types/workforceHr";
import type { ContractType, EmploymentStatus, LeaveRequestRead, TimesheetRead, WorkPatternRead } from "../../../types/workforce";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

type HrSection = "overview" | "people" | "leave" | "time" | "patterns";
type DecisionTarget =
  | { kind: "leave-supervisor" | "leave-hr" | "leave-reject"; record: LeaveRequestRead }
  | { kind: "timesheet-supervisor" | "timesheet-hr"; record: TimesheetRead }
  | { kind: "overtime-supervisor" | "overtime-hr" | "overtime-reject"; record: HrOvertimeRequest };

type ContractDraft = {
  contract_type: ContractType;
  employment_status: EmploymentStatus;
  effective_from: string;
  effective_to: string;
  primary_base_station_id: string;
  standard_weekly_hours: string;
  standard_daily_hours: string;
  fte_percentage: string;
  cost_centre: string;
  payroll_number: string;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
};

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
  const [peoplePage, setPeoplePage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<DecisionTarget | null>(null);
  const [decisionComment, setDecisionComment] = useState("");

  const dashboardQuery = useQuery({
    queryKey: ["workforce", "hr", "dashboard"],
    queryFn: () => getWorkforceHrDashboard(500),
    staleTime: 60_000,
  });
  const peopleQuery = useQuery({
    queryKey: ["workforce", "hr", "people", peoplePage, search.trim()],
    queryFn: () => listWorkforceHrPeople({
        page: peoplePage,
        page_size: 100,
        search: search.trim() || undefined,
    }),
    enabled: section === "people",
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
  const overtimeQuery = useQuery({
    queryKey: ["workforce", "hr", "overtime"],
    queryFn: () => listWorkforceHrOvertime(true),
    enabled: section === "time",
    staleTime: 30_000,
  });
  const patternsQuery = useQuery({
    queryKey: ["workforce", "hr", "patterns"],
    queryFn: () => listWorkforceHrPatterns(false),
    enabled: section === "patterns",
    staleTime: 5 * 60_000,
  });
  const basesQuery = useQuery({
    queryKey: ["foundations", "base-stations", "active"],
    queryFn: () => listBaseStations({ include_inactive: false }),
    enabled: section === "people" && Boolean(dashboardQuery.data?.can_manage_contracts),
    staleTime: 15 * 60_000,
  });

  const dashboard = dashboardQuery.data;
  const people = peopleQuery.data?.items || [];

  const openSection = (next: HrSection, searchValue?: string) => {
    setSection(next);
    if (searchValue !== undefined) setSearch(searchValue);
  };

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
      if (kind === "overtime-supervisor") await decideWorkforceHrOvertime(record.id, { stage: "SUPERVISOR", decision: "APPROVED", comment: decisionComment.trim() });
      if (kind === "overtime-hr") await decideWorkforceHrOvertime(record.id, { stage: "HR", decision: "APPROVED", comment: decisionComment.trim() });
      if (kind === "overtime-reject") await decideWorkforceHrOvertime(record.id, {
        stage: record.status === "SUPERVISOR_APPROVED" ? "HR" : "SUPERVISOR",
        decision: "REJECTED",
        comment: decisionComment.trim(),
      });
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

      {section === "overview" ? <HrOverview dashboard={dashboard} amoCode={amoCode} onOpen={openSection} onRefresh={() => void refresh()} /> : null}
      {section === "people" ? (
        <PeoplePanel
          people={people}
          search={search}
          onSearch={(value) => { setSearch(value); setPeoplePage(1); }}
          page={peopleQuery.data?.page || peoplePage}
          pages={peopleQuery.data?.pages || 0}
          total={peopleQuery.data?.total || 0}
          loading={peopleQuery.isPending}
          onPage={setPeoplePage}
          bases={basesQuery.data || []}
          loadingBases={basesQuery.isPending}
          canManage={dashboard.can_manage_contracts}
          busy={busy}
          runAction={runAction}
        />
      ) : null}
      {section === "leave" ? <LeavePanel dashboard={dashboard} requests={leaveQuery.data?.items || []} loading={leaveQuery.isPending} onDecision={setDecision} /> : null}
      {section === "time" ? <TimePanel dashboard={dashboard} timesheets={timesheetsQuery.data?.items || []} overtimeRequests={overtimeQuery.data || dashboard.pending_overtime} loading={timesheetsQuery.isPending || overtimeQuery.isPending} onDecision={setDecision} onPayroll={() => void downloadPayrollExport({})} /> : null}
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
  if (kind === "timesheet-hr") return "HR timesheet approval";
  if (kind === "overtime-supervisor") return "Supervisor overtime approval";
  if (kind === "overtime-hr") return "HR overtime approval";
  return "Reject overtime request";
}


function HrOverview({ dashboard, amoCode, onOpen, onRefresh }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; amoCode: string; onOpen: (section: HrSection, searchValue?: string) => void; onRefresh: () => void }) {
  return (
    <div className="hr-stack">
      <section className="hr-metrics">
        {dashboard.metrics.map((metric) => <article key={metric.key} className={`is-${metric.tone}`}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
      </section>
      <div className="hr-overview-grid">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">HR action queue</span><h2>What needs attention</h2></div><button type="button" className="wr-icon-button" onClick={onRefresh}><RefreshCw size={16} /></button></div>
          <ActionQueue items={dashboard.action_queue.slice(0, 12)} onOpen={onOpen} />
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
        <Link className="wr-button wr-button--secondary" to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=start`}>Open roster setup <ArrowRight size={14} /></Link>
      </section>
    </div>
  );
}

function ActionQueue({ items, onOpen }: { items: HrActionItem[]; onOpen: (section: HrSection, searchValue?: string) => void }) {
  if (!items.length) return <EmptyState title="No urgent HR actions" description="Contract, pattern, base, leave and time records are currently clear." />;
  const action = (item: HrActionItem) => {
    if (item.category === "WORK_PATTERN") return <button type="button" className="hr-action-link" onClick={() => onOpen("patterns")}>{item.action_label || "Assign pattern"} <ArrowRight size={13} /></button>;
    if (item.category === "LEAVE") return <button type="button" className="hr-action-link" onClick={() => onOpen("leave")}>{item.action_label || "Review leave"} <ArrowRight size={13} /></button>;
    if (["TIMESHEET", "OVERTIME", "ATTENDANCE"].includes(item.category)) return <button type="button" className="hr-action-link" onClick={() => onOpen("time")}>{item.action_label || "Review time"} <ArrowRight size={13} /></button>;
    return item.user_id ? <button type="button" className="hr-action-link" onClick={() => onOpen("people", item.user_name || "")}>{item.action_label || "Open employment record"} <ArrowRight size={13} /></button> : null;
  };
  return <div className="hr-action-list">{items.map((item) => <article key={item.id} className={`is-${item.severity.toLowerCase()}`}><span className="hr-action-list__icon">{item.severity === "BLOCKER" ? <AlertTriangle size={17} /> : <BadgeCheck size={17} />}</span><div><strong>{item.title}</strong><p>{item.user_name ? `${item.user_name} · ` : ""}{item.detail}</p></div><StatusPill value={item.category} />{action(item)}</article>)}</div>;
}

function PeoplePanel({
  people, search, onSearch, page, pages, total, loading, onPage, bases, loadingBases, canManage, busy, runAction,
}: {
  people: HrPersonReadiness[];
  search: string;
  onSearch: (value: string) => void;
  page: number;
  pages: number;
  total: number;
  loading: boolean;
  onPage: (page: number) => void;
  bases: BaseStationRead[];
  loadingBases: boolean;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [editing, setEditing] = useState<HrPersonReadiness | null>(null);
  const [draft, setDraft] = useState<ContractDraft | null>(null);

  const beginEdit = (person: HrPersonReadiness) => {
    setEditing(person);
    setDraft({
      contract_type: (person.contract_type || "PERMANENT") as ContractType,
      employment_status: (person.contract_id ? person.employment_status : "ACTIVE") as EmploymentStatus,
      effective_from: person.hire_date || person.contract_effective_from || isoDate(new Date()),
      effective_to: person.contract_effective_to || "",
      primary_base_station_id: person.primary_base_station_id || "",
      standard_weekly_hours: String((person.standard_weekly_minutes || 2400) / 60),
      standard_daily_hours: String((person.standard_daily_minutes || 480) / 60),
      fte_percentage: String(person.fte_percentage),
      cost_centre: person.cost_centre || "",
      payroll_number: person.payroll_number || "",
      overtime_eligible: person.overtime_eligible,
      night_shift_eligible: person.night_shift_eligible,
      standby_eligible: person.standby_eligible,
    });
  };
  const close = () => { setEditing(null); setDraft(null); };
  const save = () => {
    if (!editing || !draft) return;
    void runAction(`employment-contract:${editing.contract_id || editing.user_id}`, async () => {
      const payload = {
        user_id: editing.user_id,
        contract_type: draft.contract_type,
        employment_status: draft.employment_status,
        effective_from: draft.effective_from,
        effective_to: draft.effective_to || null,
        primary_base_station_id: draft.primary_base_station_id,
        standard_weekly_minutes: Math.round(Number(draft.standard_weekly_hours) * 60),
        standard_daily_minutes: Math.round(Number(draft.standard_daily_hours) * 60),
        fte_percentage: Number(draft.fte_percentage),
        cost_centre: draft.cost_centre.trim() || null,
        payroll_number: draft.payroll_number.trim() || null,
        overtime_eligible: draft.overtime_eligible,
        night_shift_eligible: draft.night_shift_eligible,
        standby_eligible: draft.standby_eligible,
      };
      if (editing.contract_id) {
        await updateEmploymentContract(editing.contract_id, { ...payload, user_id: undefined });
      } else {
        await createEmploymentContract(payload);
      }
      close();
    });
  };
  const validDraft = Boolean(
    draft?.effective_from
    && draft.primary_base_station_id
    && Number(draft.standard_weekly_hours) >= 0
    && Number(draft.standard_daily_hours) >= 0
    && Number(draft.fte_percentage) > 0
    && Number(draft.fte_percentage) <= 100
    && (!draft.effective_to || draft.effective_to >= draft.effective_from)
  );

  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">People and contracts</span><h2>Employee readiness register</h2><p>Missing contracts, bases and rotations stay visible as blockers.</p></div><label className="hr-search"><Search size={15} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search staff, email, role, base or department" /></label></div>
      <div className="hr-people-table">
        <header><span>Employee</span><span>Contract</span><span>Base</span><span>Work pattern</span><span>Readiness</span><span>Action</span></header>
        {people.map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.position_title || person.department_code || "No position"}</span></div><div><strong>{person.employment_status || "No contract"}</strong><span>{person.contract_type || "—"}{person.contract_effective_to ? ` · ends ${person.contract_effective_to}` : ""}</span></div><span>{person.primary_base_code || "Missing"}</span><div><strong>{person.work_pattern_code || "Unassigned"}</strong><span>{person.work_pattern_name || "Automatic rotation unavailable"}</span>{person.uses_default_day_pattern ? <small>System baseline · planner review required</small> : null}</div><div><StatusPill value={person.readiness_state} />{person.readiness_reasons.map((reason) => <small key={reason}>{reason}</small>)}</div>{canManage ? <button type="button" className="wr-button wr-button--small" onClick={() => beginEdit(person)}><BriefcaseBusiness size={14} /> {person.contract_id ? "Edit" : "Create contract"}</button> : <span className="hr-person-source">Read only</span>}</article>)}
      </div>
    {loading ? <RosterLoading label="Loading employee register…" /> : null}
    <div className="wr-actions wr-actions--between">
        <span className="hr-person-source">Showing {people.length} of {total} employees · page {page}{pages ? ` of ${pages}` : ""}</span>
        <div className="wr-actions">
            <button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={page <= 1 || loading} onClick={() => onPage(page - 1)}>Previous</button>
            <button type="button" className="wr-button wr-button--secondary wr-button--small" disabled={!pages || page >= pages || loading} onClick={() => onPage(page + 1)}>Next</button>
        </div>
    </div>
    {!people.length && !loading ? <EmptyState title="No active tenant users found" description="Change the search, or activate/create user accounts in tenant administration. Employment-contract gaps no longer hide users from this register." /> : null}

      {editing && draft ? (
        <div className="hr-decision hr-contract-editor" role="dialog" aria-modal="true" aria-label={`Edit employment contract for ${editing.full_name}`}>
          <div className="hr-decision__head"><div><span className="wr-eyebrow">Controlled Workforce record</span><h3>{editing.full_name}</h3></div><button type="button" className="wr-icon-button" onClick={close}><X size={16} /></button></div>
          <p>{editing.staff_code} · Changes are effective-dated and audited by the Workforce service.</p>
          <div className="hr-contract-grid">
            <label><span>Contract type</span><select value={draft.contract_type} onChange={(event) => setDraft({ ...draft, contract_type: event.target.value as ContractType })}>{["PERMANENT", "FIXED_TERM", "TEMPORARY", "CONTRACTOR", "INTERN"].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label><span>Employment status</span><select value={draft.employment_status} onChange={(event) => setDraft({ ...draft, employment_status: event.target.value as EmploymentStatus })}>{["ONBOARDING", "ACTIVE", "SUSPENDED", "TERMINATED"].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label className={editing.hire_date ? "wr-locked-field" : undefined}><span>Workforce start</span><input type="date" value={draft.effective_from} disabled={Boolean(editing.hire_date)} onChange={(event) => setDraft({ ...draft, effective_from: event.target.value })} />{editing.hire_date ? <small>Locked to imported hire date. Re-employ from User Management to change it.</small> : null}</label>
            <label><span>Effective to</span><input type="date" min={draft.effective_from} value={draft.effective_to} onChange={(event) => setDraft({ ...draft, effective_to: event.target.value })} /></label>
            <label><span>Primary base</span><select value={draft.primary_base_station_id} disabled={loadingBases} onChange={(event) => setDraft({ ...draft, primary_base_station_id: event.target.value })}><option value="">Select canonical base</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code} · {base.name}</option>)}</select></label>
            <label><span>FTE percentage</span><input type="number" min="1" max="100" step="0.1" value={draft.fte_percentage} onChange={(event) => setDraft({ ...draft, fte_percentage: event.target.value })} /></label>
            <label><span>Weekly hours</span><input type="number" min="0" step="0.25" value={draft.standard_weekly_hours} onChange={(event) => setDraft({ ...draft, standard_weekly_hours: event.target.value })} /></label>
            <label><span>Daily hours</span><input type="number" min="0" step="0.25" value={draft.standard_daily_hours} onChange={(event) => setDraft({ ...draft, standard_daily_hours: event.target.value })} /></label>
            <label><span>Payroll number</span><input value={draft.payroll_number} onChange={(event) => setDraft({ ...draft, payroll_number: event.target.value })} /></label>
            <label><span>Cost centre</span><input value={draft.cost_centre} onChange={(event) => setDraft({ ...draft, cost_centre: event.target.value })} /></label>
          </div>
          <div className="hr-contract-flags">
            <label><input type="checkbox" checked={draft.overtime_eligible} onChange={(event) => setDraft({ ...draft, overtime_eligible: event.target.checked })} /> Overtime eligible</label>
            <label><input type="checkbox" checked={draft.night_shift_eligible} onChange={(event) => setDraft({ ...draft, night_shift_eligible: event.target.checked })} /> Night duty eligible</label>
            <label><input type="checkbox" checked={draft.standby_eligible} onChange={(event) => setDraft({ ...draft, standby_eligible: event.target.checked })} /> Standby eligible</label>
          </div>
          {!loadingBases && !bases.length ? <div className="hr-warning"><AlertTriangle size={16} /><span>No active canonical base exists. Create it in Operating Structure before saving this contract.</span></div> : null}
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={close}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !validDraft} onClick={save}><Save size={15} /> {editing.contract_id ? "Save contract" : "Create contract"}</button></div>
        </div>
      ) : null}
    </section>
  );
}

function LeavePanel({ dashboard, requests, loading, onDecision }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; requests: LeaveRequestRead[]; loading: boolean; onDecision: (value: DecisionTarget) => void }) {
  const pending = requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Leave workflow</span><h2>Leave requests and approvals</h2><p>Leave remains Workforce-owned and automatically becomes a protected Rostering commitment after approval.</p></div><span className="wr-header-badge"><CalendarDays size={15} /> {pending.length} pending</span></div>
      {loading ? <RosterLoading label="Loading leave workflow…" /> : null}
      <div className="hr-approval-list">{pending.map((request) => <article key={request.id}><div><strong>{request.user_full_name || request.user_staff_code}</strong><span>{request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}</span>{request.published_roster_conflicts.length ? <small className="is-danger">Published roster conflict requires a controlled amendment.</small> : null}</div><StatusPill value={request.status} /><div className="wr-actions">{request.status === "SUBMITTED" && dashboard.can_review_leave ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "leave-supervisor", record: request })}>Supervisor review</button> : null}{request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_leave ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "leave-hr", record: request })}>HR approve</button> : null}{dashboard.can_review_leave ? <button type="button" className="wr-icon-button is-danger" onClick={() => onDecision({ kind: "leave-reject", record: request })} aria-label="Reject leave"><XCircle size={15} /></button> : null}</div></article>)}</div>
      {!loading && !pending.length ? <EmptyState title="No pending leave" description="Submitted and supervisor-approved requests will appear here." /> : null}
    </section>
  );
}

function TimePanel({ dashboard, timesheets, overtimeRequests, loading, onDecision, onPayroll }: { dashboard: Awaited<ReturnType<typeof getWorkforceHrDashboard>>; timesheets: TimesheetRead[]; overtimeRequests: HrOvertimeRequest[]; loading: boolean; onDecision: (value: DecisionTarget) => void; onPayroll: () => void }) {
  const pending = timesheets.filter((sheet) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status));
  const pendingOvertime = overtimeRequests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status));
  return (
    <div className="hr-stack">
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Time control</span><h2>Timesheet approvals</h2><p>Attendance and productive work are reconciled before HR approval and payroll export.</p></div>{dashboard.can_export_payroll ? <button type="button" className="wr-button wr-button--secondary" onClick={onPayroll}><Download size={15} /> Payroll export</button> : null}</div>
        {loading ? <RosterLoading label="Loading time approvals…" /> : null}
        <div className="hr-approval-list">{pending.map((sheet) => <article key={sheet.id}><div><strong>{sheet.user_full_name || sheet.user_id}</strong><span>{sheet.period_start} → {sheet.period_end} · {Math.round(sheet.attendance_minutes / 60)}h attendance</span></div><StatusPill value={sheet.status} /><div className="wr-actions">{sheet.status === "SUBMITTED" && dashboard.can_approve_timesheet_supervisor ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "timesheet-supervisor", record: sheet })}>Supervisor review</button> : null}{sheet.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_timesheet_hr ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "timesheet-hr", record: sheet })}>HR approve</button> : null}</div></article>)}</div>
        {!loading && !pending.length ? <EmptyState title="No timesheet approvals" description="Submitted timesheets will appear here." /> : null}
      </section>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Overtime control</span><h2>Overtime requests</h2><p>Supervisors and HR can complete the two-stage approval workflow without leaving Workforce.</p></div><span className="wr-header-badge"><UserRoundCheck size={15} /> {pendingOvertime.length} pending</span></div>
        {loading ? <RosterLoading label="Loading overtime requests…" /> : null}
        <div className="hr-approval-list">{pendingOvertime.map((request) => {
          const canReject = request.status === "SUBMITTED" ? dashboard.can_approve_overtime_supervisor : dashboard.can_approve_overtime_hr;
          return <article key={request.id}><div><strong>{request.user_full_name || request.user_id}</strong><span>{request.starts_at.slice(0, 16).replace("T", " ")} → {request.ends_at.slice(0, 16).replace("T", " ")} · {Math.round(request.requested_minutes / 60 * 10) / 10}h</span><small>{request.reason}</small></div><StatusPill value={request.status} /><div className="wr-actions">{request.status === "SUBMITTED" && dashboard.can_approve_overtime_supervisor ? <button type="button" className="wr-button wr-button--small" onClick={() => onDecision({ kind: "overtime-supervisor", record: request })}>Supervisor approve</button> : null}{request.status === "SUPERVISOR_APPROVED" && dashboard.can_approve_overtime_hr ? <button type="button" className="wr-button wr-button--small wr-button--success" onClick={() => onDecision({ kind: "overtime-hr", record: request })}>HR approve</button> : null}{canReject ? <button type="button" className="wr-icon-button is-danger" onClick={() => onDecision({ kind: "overtime-reject", record: request })} aria-label="Reject overtime"><XCircle size={15} /></button> : null}</div></article>;
        })}</div>
        {!loading && !pendingOvertime.length ? <EmptyState title="No overtime approvals" description="Submitted and supervisor-approved overtime requests will appear here." /> : null}
      </section>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Attendance reconciliation</span><h2>Attendance exceptions</h2><p>These canonical variances identify the employee, roster assignment and measured difference requiring review.</p></div><span className="wr-header-badge"><Clock3 size={15} /> {dashboard.attendance_exceptions.length} shown</span></div>
        <div className="hr-approval-list">{dashboard.attendance_exceptions.map((exception) => <article key={exception.id}><div><strong>{exception.user_full_name || exception.user_id}</strong><span>{exception.calculated_at.slice(0, 16).replace("T", " ")} · assignment {exception.roster_assignment_id}</span><small>{exception.attendance_minutes} attendance · {exception.productive_minutes} productive · {exception.planned_minutes} planned minutes</small></div><StatusPill value={exception.classification} /><strong className={exception.variance_minutes === 0 ? "" : "is-danger"}>{exception.variance_minutes > 0 ? "+" : ""}{exception.variance_minutes} min</strong></article>)}</div>
        {!dashboard.attendance_exceptions.length ? <EmptyState title="No attendance exceptions" description="Roster-to-attendance variances will appear here with employee and assignment evidence." /> : null}
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
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Employee rotation assignments</span><h2>Work-pattern readiness</h2><p>Pattern templates are designed in Rostering. Effective employee assignments and dates are controlled here by Workforce and HR.</p></div><div className="wr-actions"><Link className="wr-button wr-button--secondary" to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=patterns`}>Open pattern builder <ArrowRight size={14} /></Link>{dashboard.can_assign_patterns ? <button type="button" className="wr-button wr-button--primary" onClick={() => setAssigning(true)}><Plus size={15} /> Assign pattern</button> : null}</div></div>
      {loading ? <RosterLoading label="Loading approved work patterns…" /> : null}
      <div className="hr-pattern-list">{dashboard.people.map((person) => <article key={person.user_id}><div><strong>{person.full_name}</strong><span>{person.staff_code} · {person.primary_base_code || "No base"}</span></div><div><strong>{person.work_pattern_code || "No pattern"}</strong><span>{person.work_pattern_name || "Automatic duty generation will skip this employee"}</span></div><StatusPill value={person.work_pattern_code ? "ASSIGNED" : "MISSING"} /><button type="button" className="wr-icon-button" aria-label={`Assign pattern to ${person.full_name}`} disabled={!dashboard.can_assign_patterns} onClick={() => { setUserId(person.user_id); setAssigning(true); }}><ArrowRight size={15} /></button></article>)}</div>
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
