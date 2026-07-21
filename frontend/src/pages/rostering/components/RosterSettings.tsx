import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck,
  BriefcaseBusiness,
  CalendarRange,
  CheckCircle2,
  Clock3,
  Download,
  FileClock,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  UserCog,
  XCircle,
} from "lucide-react";

import {
  createRosterPeriod,
  createRosterRule,
  createRosterVersion,
  createShiftTemplate,
  getRosterContracts,
  listRosterPeriods,
  listRosterRules,
  listShiftTemplates,
} from "../../../services/rostering";
import {
  approveTimesheet,
  createEmploymentContract,
  createLeaveType,
  createWorkPattern,
  downloadPayrollExport,
  getCurrentWorkforcePermissions,
  hrApproveLeave,
  listEmploymentContracts,
  listLeaveRequests,
  listLeaveTypes,
  listTimesheets,
  listWorkPatterns,
  listWorkforcePeople,
  supervisorApproveLeave,
  rejectLeaveRequest,
  updatePlannerPreferences,
  type WorkforcePersonRead,
} from "../../../services/workforce";
import type { RosterContractResponse, RosterPeriodRead, RosterRuleRead, ShiftTemplateRead } from "../../../types/rostering";
import type { EmploymentContractRead, LeaveRequestRead, LeaveTypeRead, TimesheetRead, WorkPatternRead } from "../../../types/workforce";
import { errorMessage, isoDate, newIdempotencyKey } from "../rosterUi";
import { EmptyState, RosterError, RosterLoading, StatusPill } from "./RosterShell";

type Tab = "periods" | "shifts" | "patterns" | "contracts" | "leave" | "rules" | "approvals" | "preferences";

const TABS: Array<{ id: Tab; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "periods", label: "Periods", icon: CalendarRange },
  { id: "shifts", label: "Shifts", icon: Clock3 },
  { id: "patterns", label: "Patterns", icon: Settings2 },
  { id: "contracts", label: "Contracts", icon: BriefcaseBusiness },
  { id: "leave", label: "Leave", icon: UserCog },
  { id: "rules", label: "Rules", icon: ShieldCheck },
  { id: "approvals", label: "Approvals", icon: CheckCircle2 },
  { id: "preferences", label: "Preferences", icon: Settings2 },
];

export function RosterSettings() {
  const [tab, setTab] = useState<Tab>("periods");
  const [periods, setPeriods] = useState<RosterPeriodRead[]>([]);
  const [shifts, setShifts] = useState<ShiftTemplateRead[]>([]);
  const [patterns, setPatterns] = useState<WorkPatternRead[]>([]);
  const [contracts, setContracts] = useState<EmploymentContractRead[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveTypeRead[]>([]);
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequestRead[]>([]);
  const [timesheets, setTimesheets] = useState<TimesheetRead[]>([]);
  const [rules, setRules] = useState<RosterRuleRead[]>([]);
  const [people, setPeople] = useState<WorkforcePersonRead[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [contractMap, setContractMap] = useState<RosterContractResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [periodRows, shiftRows, patternRows, contractPage, typeRows, leavePage, timesheetPage, ruleRows, personRows, permissionRows, rosterContracts] = await Promise.all([
        listRosterPeriods(),
        listShiftTemplates(true),
        listWorkPatterns(true),
        listEmploymentContracts({ page_size: 500 }),
        listLeaveTypes(true),
        listLeaveRequests({ page_size: 250 }),
        listTimesheets({ page_size: 250 }),
        listRosterRules(true),
        listWorkforcePeople({ active_only: true, roster_eligible_only: false, limit: 1000 }),
        getCurrentWorkforcePermissions(),
        getRosterContracts(),
      ]);
      setPeriods(periodRows);
      setShifts(shiftRows);
      setPatterns(patternRows);
      setContracts(contractPage.items);
      setLeaveTypes(typeRows);
      setLeaveRequests(leavePage.items);
      setTimesheets(timesheetPage.items);
      setRules(ruleRows);
      setPeople(personRows);
      setPermissions(permissionRows.permissions);
      setContractMap(rosterContracts);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const can = useCallback((permission: string) => permissions.includes(permission), [permissions]);
  const bases = useMemo(() => Array.from(new Map(people.filter((person) => person.primary_base_station_id).map((person) => [person.primary_base_station_id!, { id: person.primary_base_station_id!, code: person.primary_base_code || "BASE" }])).values()), [people]);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  if (loading && !contractMap) return <RosterLoading label="Loading roster and workforce setup…" />;
  if (error && !contractMap) return <RosterError message={error} onRetry={load} />;

  return (
    <div className="wr-settings">
      <div className="wr-settings-tabs" role="tablist" aria-label="Roster setup sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}><Icon size={16} /> {label}</button>)}
      </div>
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
      {tab === "periods" ? <PeriodsPanel periods={periods} canCreate={can("roster.create")} busy={busy} run={run} /> : null}
      {tab === "shifts" ? <ShiftsPanel shifts={shifts} canManage={can("roster.manage_shift_templates")} busy={busy} run={run} /> : null}
      {tab === "patterns" ? <PatternsPanel patterns={patterns} shifts={shifts} canManage={can("roster.manage_patterns")} busy={busy} run={run} /> : null}
      {tab === "contracts" ? <ContractsPanel contracts={contracts} people={people} bases={bases} canManage={can("workforce.manage_contracts")} busy={busy} run={run} /> : null}
      {tab === "leave" ? <LeavePanel leaveTypes={leaveTypes} canManage={can("workforce.manage_leave_types")} busy={busy} run={run} /> : null}
      {tab === "rules" ? <RulesPanel rules={rules} canManage={can("roster.manage_rules")} busy={busy} run={run} /> : null}
      {tab === "approvals" ? <ApprovalsPanel requests={leaveRequests} timesheets={timesheets} canSupervisor={can("leave.approve_supervisor")} canHr={can("leave.approve_hr")} canTimesheet={can("timesheet.approve")} canPayroll={can("payroll.export")} busy={busy} run={run} /> : null}
      {tab === "preferences" ? <PreferencesPanel permissions={permissions} contractMap={contractMap} busy={busy} run={run} /> : null}
    </div>
  );
}

function PeriodsPanel({ periods, canCreate, busy, run }: { periods: RosterPeriodRead[]; canCreate: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const now = new Date();
  const [code, setCode] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [name, setName] = useState("Monthly duty roster");
  const [startsOn, setStartsOn] = useState(isoDate(new Date(now.getFullYear(), now.getMonth(), 1)));
  const [endsOn, setEndsOn] = useState(isoDate(new Date(now.getFullYear(), now.getMonth() + 1, 0)));
  const [timezone, setTimezone] = useState("Africa/Nairobi");
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Planning control</span><h2>Roster periods and versions</h2></div></div>{canCreate ? <div className="wr-inline-create"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value)} /></label><label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>Starts</span><input type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} /></label><label><span>Ends</span><input type="date" value={endsOn} onChange={(event) => setEndsOn(event.target.value)} /></label><label><span>Time zone</span><input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label><button className="wr-button wr-button--primary" type="button" disabled={busy === "period"} onClick={() => run("period", () => createRosterPeriod({ period_code: code, name, starts_on: startsOn, ends_on: endsOn, timezone_name: timezone }))}><Plus size={16} /> Create period</button></div> : null}<div className="wr-data-list">{periods.map((period) => <article key={period.id} className="wr-data-row"><div><strong>{period.period_code} · {period.name}</strong><small>{period.starts_on} → {period.ends_on} · {period.timezone_name}</small></div><span>{period.versions.length} versions</span><StatusPill value={period.status} /><button type="button" className="wr-button wr-button--small" disabled={!canCreate || busy === `version:${period.id}`} onClick={() => run(`version:${period.id}`, () => createRosterVersion(period.id, { title: `Draft v${period.versions.length + 1}`, idempotency_key: newIdempotencyKey("version") }))}><Plus size={14} /> Draft</button></article>)}</div>{periods.length === 0 ? <EmptyState title="No periods" description="Create a period to start planning duty." /> : null}</section>;
}

function ShiftsPanel({ shifts, canManage, busy, run }: { shifts: ShiftTemplateRead[]; canManage: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [code, setCode] = useState(""); const [label, setLabel] = useState(""); const [kind, setKind] = useState("DAY"); const [start, setStart] = useState("08:00"); const [end, setEnd] = useState("17:00");
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Reusable building blocks</span><h2>Shift templates</h2></div></div>{canManage ? <div className="wr-inline-create"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></label><label><span>Label</span><input value={label} onChange={(event) => setLabel(event.target.value)} /></label><label><span>Kind</span><select value={kind} onChange={(event) => setKind(event.target.value)}>{["DAY", "NIGHT", "STANDBY", "TRAINING", "OFF", "LEAVE", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Starts</span><input type="time" value={start} onChange={(event) => setStart(event.target.value)} /></label><label><span>Ends</span><input type="time" value={end} onChange={(event) => setEnd(event.target.value)} /></label><button className="wr-button wr-button--primary" type="button" disabled={!code || !label || busy === "shift"} onClick={() => run("shift", () => createShiftTemplate({ code, label, kind: kind as ShiftTemplateRead["kind"], default_start_time: start, default_end_time: end, duration_minutes: null, counts_as_duty: !["OFF", "LEAVE", "TRAINING"].includes(kind), is_active: true, display_order: shifts.length * 10 + 10, description: null, color_token: `shift-${kind.toLowerCase()}`, icon_name: null }))}><Plus size={16} /> Add shift</button></div> : null}<div className="wr-card-grid">{shifts.map((shift) => <article className="wr-setup-card" key={shift.id}><div><strong>{shift.code}</strong><StatusPill value={shift.kind} /></div><h3>{shift.label}</h3><p>{shift.default_start_time || "—"} → {shift.default_end_time || "—"}</p><small>{shift.counts_as_duty ? "Counts as duty" : "Non-duty status"}</small></article>)}</div></section>;
}

function PatternsPanel({ patterns, shifts, canManage, busy, run }: { patterns: WorkPatternRead[]; shifts: ShiftTemplateRead[]; canManage: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [code, setCode] = useState(""); const [name, setName] = useState(""); const [cycle, setCycle] = useState(7); const [shiftId, setShiftId] = useState(shifts[0]?.id || ""); const [dutyDays, setDutyDays] = useState(5);
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Rotation engine</span><h2>Work patterns</h2></div></div>{canManage ? <div className="wr-inline-create"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></label><label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>Cycle days</span><input type="number" min={1} max={56} value={cycle} onChange={(event) => setCycle(Number(event.target.value))} /></label><label><span>Duty days</span><input type="number" min={0} max={cycle} value={dutyDays} onChange={(event) => setDutyDays(Number(event.target.value))} /></label><label><span>Duty shift</span><select value={shiftId} onChange={(event) => setShiftId(event.target.value)}>{shifts.map((shift) => <option key={shift.id} value={shift.id}>{shift.code}</option>)}</select></label><button className="wr-button wr-button--primary" type="button" disabled={!code || !name || !shiftId || busy === "pattern"} onClick={() => run("pattern", () => createWorkPattern({ code, name, description: null, cycle_length_days: cycle, is_active: true, timezone_name: "Africa/Nairobi", days: Array.from({ length: cycle }, (_, index) => ({ cycle_day_index: index, shift_template_id: index < dutyDays ? shiftId : null, status: index < dutyDays ? "DUTY" : "OFF", start_time_local: index < dutyDays ? "08:00" : null, end_time_local: index < dutyDays ? "17:00" : null, spans_next_day: false, planned_minutes: index < dutyDays ? 540 : 0 })) }))}><Plus size={16} /> Create pattern</button></div> : null}<div className="wr-card-grid">{patterns.map((pattern) => <article className="wr-setup-card" key={pattern.id}><div><strong>{pattern.code}</strong><StatusPill value={pattern.is_active ? "ACTIVE" : "INACTIVE"} /></div><h3>{pattern.name}</h3><p>{pattern.cycle_length_days}-day cycle · {pattern.assigned_employee_count} assigned</p><div className="wr-pattern-strip">{pattern.days.map((day) => <span key={day.id} className={`is-${day.status.toLowerCase()}`} title={`Day ${day.cycle_day_index + 1}: ${day.status}`} />)}</div></article>)}</div></section>;
}

function ContractsPanel({ contracts, people, bases, canManage, busy, run }: { contracts: EmploymentContractRead[]; people: WorkforcePersonRead[]; bases: Array<{ id: string; code: string }>; canManage: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [userId, setUserId] = useState(people[0]?.user_id || ""); const [baseId, setBaseId] = useState(bases[0]?.id || ""); const [effectiveFrom, setEffectiveFrom] = useState(isoDate(new Date()));
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">HR source of truth</span><h2>Employment contracts</h2></div></div>{canManage ? <div className="wr-inline-create"><label><span>Person</span><select value={userId} onChange={(event) => setUserId(event.target.value)}>{people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label><label><span>Primary base</span><select value={baseId} onChange={(event) => setBaseId(event.target.value)}>{bases.map((base) => <option key={base.id} value={base.id}>{base.code}</option>)}</select></label><label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><button className="wr-button wr-button--primary" type="button" disabled={!userId || !baseId || busy === "contract"} onClick={() => run("contract", () => createEmploymentContract({ user_id: userId, contract_type: "PERMANENT", employment_status: "ACTIVE", effective_from: effectiveFrom, effective_to: null, standard_weekly_minutes: 2400, standard_daily_minutes: 480, fte_percentage: 100, primary_base_station_id: baseId, secondary_base_station_id: null, supervisor_user_id: null, cost_centre: null, payroll_number: null, overtime_eligible: true, night_shift_eligible: true, standby_eligible: true }))}><Plus size={16} /> Add contract</button></div> : null}<div className="wr-data-list">{contracts.map((contract) => <article key={contract.id} className="wr-data-row"><div><strong>{contract.user_full_name || contract.user_staff_code}</strong><small>{contract.contract_type} · {contract.primary_base_code || "No base"}</small></div><span>{Math.round(contract.standard_weekly_minutes / 60)}h/week</span><StatusPill value={contract.employment_status} /><span>{contract.effective_from}{contract.effective_to ? ` → ${contract.effective_to}` : ""}</span></article>)}</div>{contracts.length === 0 ? <EmptyState title="No employment contracts" description="Roster eligibility requires an active contract." /> : null}</section>;
}

function LeavePanel({ leaveTypes, canManage, busy, run }: { leaveTypes: LeaveTypeRead[]; canManage: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [code, setCode] = useState(""); const [name, setName] = useState("");
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Absence policy</span><h2>Leave types</h2></div></div>{canManage ? <div className="wr-inline-create"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></label><label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><button className="wr-button wr-button--primary" type="button" disabled={!code || !name || busy === "leave-type"} onClick={() => run("leave-type", () => createLeaveType({ code, name, availability_type: "ANNUAL_LEAVE", description: null, paid: true, deducts_balance: true, requires_attachment: false, supervisor_approval_required: true, hr_approval_required: true, allow_negative_balance: false, is_active: true, display_order: leaveTypes.length * 10 + 10 }))}><Plus size={16} /> Add leave type</button></div> : null}<div className="wr-card-grid">{leaveTypes.map((type) => <article className="wr-setup-card" key={type.id}><div><strong>{type.code}</strong><StatusPill value={type.is_active ? "ACTIVE" : "INACTIVE"} /></div><h3>{type.name}</h3><p>{type.paid ? "Paid" : "Unpaid"} · {type.deducts_balance ? "Deducts balance" : "No balance deduction"}</p><small>{type.supervisor_approval_required ? "Supervisor" : "No supervisor"} · {type.hr_approval_required ? "HR approval" : "No HR approval"}</small></article>)}</div></section>;
}

function RulesPanel({ rules, canManage, busy, run }: { rules: RosterRuleRead[]; canManage: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [code, setCode] = useState(""); const [name, setName] = useState(""); const [type, setType] = useState("CUSTOM"); const [severity, setSeverity] = useState("WARNING");
  return <section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Validation policy</span><h2>Roster rules</h2></div></div>{canManage ? <div className="wr-inline-create"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></label><label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>Rule type</span><select value={type} onChange={(event) => setType(event.target.value)}>{["MIN_REST_HOURS", "MAX_DUTY_HOURS_DAY", "MAX_DUTY_HOURS_ROLLING", "MAX_CONSECUTIVE_DAYS", "MIN_COVERAGE", "REQUIRED_CERTIFYING_COVERAGE", "CUSTOM"].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Severity</span><select value={severity} onChange={(event) => setSeverity(event.target.value)}><option>INFO</option><option>WARNING</option><option>BLOCKER</option></select></label><button className="wr-button wr-button--primary" type="button" disabled={!code || !name || busy === "rule"} onClick={() => run("rule", () => createRosterRule({ code, name, description: null, rule_type: type as RosterRuleRead["rule_type"], scope: "AMO", severity: severity as RosterRuleRead["severity"], parameters_json: {}, department_id: null, base_station_id: null, shift_template_id: null, user_id: null, effective_from: null, effective_to: null, allow_override: severity !== "BLOCKER", is_active: true, display_order: rules.length * 10 + 10 }))}><Plus size={16} /> Add rule</button></div> : null}<div className="wr-data-list">{rules.map((rule) => <article key={rule.id} className="wr-data-row"><div><strong>{rule.code}</strong><small>{rule.name} · {rule.rule_type.replace(/_/g, " ")}</small></div><StatusPill value={rule.scope} /><StatusPill value={rule.severity} /><span>{rule.allow_override ? "Override allowed" : "Mandatory"}</span></article>)}</div></section>;
}

function ApprovalsPanel({ requests, timesheets, canSupervisor, canHr, canTimesheet, canPayroll, busy, run }: { requests: LeaveRequestRead[]; timesheets: TimesheetRead[]; canSupervisor: boolean; canHr: boolean; canTimesheet: boolean; canPayroll: boolean; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const pendingLeave = requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status)); const pendingSheets = timesheets.filter((sheet) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status));
  return <div className="wr-two-column wr-two-column--wide"><section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Leave workflow</span><h2>Approval queue</h2></div><BadgeCheck size={20} /></div>{pendingLeave.length === 0 ? <EmptyState title="No leave approvals" description="Submitted requests will appear here." /> : <div className="wr-data-list">{pendingLeave.map((request) => <article key={request.id} className="wr-approval-row"><div><strong>{request.user_full_name || request.user_staff_code}</strong><small>{request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}</small>{request.published_roster_conflicts.length ? <span className="wr-pill wr-pill--blocker">Published roster conflict</span> : null}</div><StatusPill value={request.status} /><div className="wr-actions">{request.status === "SUBMITTED" && canSupervisor ? <button className="wr-button wr-button--small" type="button" disabled={busy === `sup:${request.id}`} onClick={() => run(`sup:${request.id}`, () => supervisorApproveLeave(request.id, "Approved in workforce control"))}><CheckCircle2 size={14} /> Supervisor</button> : null}{request.status === "SUPERVISOR_APPROVED" && canHr ? <button className="wr-button wr-button--small wr-button--success" type="button" disabled={busy === `hr:${request.id}`} onClick={() => run(`hr:${request.id}`, () => hrApproveLeave(request.id, "Approved in workforce control"))}><CheckCircle2 size={14} /> HR approve</button> : null}{(canSupervisor || canHr) ? <button className="wr-icon-button is-danger" type="button" onClick={() => run(`reject:${request.id}`, () => rejectLeaveRequest(request.id, "Rejected in workforce control"))}><XCircle size={16} /></button> : null}</div></article>)}</div>}</section><section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Timesheet workflow</span><h2>Pay-period approvals</h2></div><FileClock size={20} /></div>{canPayroll ? <button type="button" className="wr-button wr-button--secondary wr-button--full" onClick={() => downloadPayrollExport({})}><Download size={16} /> Download payroll export</button> : null}{pendingSheets.length === 0 ? <EmptyState title="No timesheet approvals" description="Submitted timesheets will appear here." /> : <div className="wr-data-list">{pendingSheets.map((sheet) => <article key={sheet.id} className="wr-approval-row"><div><strong>{sheet.user_full_name || sheet.user_id}</strong><small>{sheet.period_start} → {sheet.period_end} · {Math.round(sheet.attendance_minutes / 60)}h attendance</small></div><StatusPill value={sheet.status} /><div className="wr-actions">{canTimesheet && sheet.status === "SUBMITTED" ? <button className="wr-button wr-button--small" type="button" onClick={() => run(`sheet-sup:${sheet.id}`, () => approveTimesheet(sheet.id, "SUPERVISOR", "Approved in workforce control"))}>Supervisor</button> : null}{canTimesheet && sheet.status === "SUPERVISOR_APPROVED" ? <button className="wr-button wr-button--small wr-button--success" type="button" onClick={() => run(`sheet-hr:${sheet.id}`, () => approveTimesheet(sheet.id, "HR", "Approved in workforce control"))}>HR approve</button> : null}</div></article>)}</div>}</section></div>;
}

function PreferencesPanel({ permissions, contractMap, busy, run }: { permissions: string[]; contractMap: RosterContractResponse | null; busy: string | null; run: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  const [density, setDensity] = useState("compact"); const [groupBy, setGroupBy] = useState("department"); const [zoom, setZoom] = useState("week");
  return <div className="wr-two-column"><section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Planner behaviour</span><h2>Personal preferences</h2></div></div><div className="wr-form-grid"><label><span>Density</span><select value={density} onChange={(event) => setDensity(event.target.value)}><option value="compact">Compact</option><option value="comfortable">Comfortable</option></select></label><label><span>Group by</span><select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}><option value="department">Department</option><option value="base">Base</option><option value="role">Role</option></select></label><label><span>Default zoom</span><select value={zoom} onChange={(event) => setZoom(event.target.value)}><option value="week">Week</option><option value="fortnight">Fortnight</option><option value="month">Month</option></select></label></div><button type="button" className="wr-button wr-button--primary" disabled={busy === "preferences"} onClick={() => run("preferences", () => updatePlannerPreferences({ density: density as "compact" | "comfortable", group_by: groupBy, zoom }))}><Save size={16} /> Save preferences</button></section><section className="wr-panel"><div className="wr-section-heading"><div><span className="wr-eyebrow">Access contract</span><h2>Effective capabilities</h2></div></div><div className="wr-permission-grid">{permissions.map((permission) => <span key={permission}><ShieldCheck size={13} /> {permission}</span>)}</div><div className="wr-contract-map"><strong>Canonical person key</strong><code>{contractMap?.canonical_personnel_key}</code><strong>Phase</strong><code>{contractMap?.phase}</code></div></section></div>;
}
