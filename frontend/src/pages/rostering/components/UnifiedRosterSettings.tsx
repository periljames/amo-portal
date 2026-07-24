import {
  useMemo,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  BriefcaseBusiness,
  CalendarRange,
  CheckCircle2,
  Clock3,
  Download,
  FileClock,
  Link2,
  Plus,
  Settings2,
  ShieldCheck,
  UserCog,
  UsersRound,
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
  listAllRosterPeople,
  type RosterPersonRead,
} from "../../../services/rosterPeople";
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
  rejectLeaveRequest,
  supervisorApproveLeave,
  updatePlannerPreferences,
} from "../../../services/workforce";
import type {
  RosterContractResponse,
  RosterPeriodRead,
  RosterRuleRead,
  ShiftTemplateRead,
} from "../../../types/rostering";
import type {
  EmploymentContractRead,
  LeaveRequestRead,
  LeaveTypeRead,
  PatternDayStatus,
  PlannerPreferenceRead,
  TimesheetRead,
  WorkPatternDayInput,
  WorkPatternRead,
} from "../../../types/workforce";
import { errorMessage, isoDate, newIdempotencyKey } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";
import { RosterGovernancePanel } from "./RosterGovernancePanel";

type Tab =
  | "integration"
  | "periods"
  | "shifts"
  | "patterns"
  | "contracts"
  | "leave"
  | "rules"
  | "governance"
  | "approvals"
  | "preferences";

type TabSpec = {
  id: Tab;
  label: string;
  icon: ComponentType<{ size?: number }>;
};

type RunAction = (
  key: string,
  action: () => Promise<unknown>,
) => Promise<void>;

type QuerySnapshot = {
  error: unknown;
  data: unknown;
  isFetching: boolean;
  isPending: boolean;
};

const TABS: TabSpec[] = [
  { id: "integration", label: "Integration", icon: Link2 },
  { id: "periods", label: "Periods", icon: CalendarRange },
  { id: "shifts", label: "Shifts", icon: Clock3 },
  { id: "patterns", label: "Patterns", icon: Settings2 },
  { id: "contracts", label: "Contracts", icon: BriefcaseBusiness },
  { id: "leave", label: "Leave", icon: UserCog },
  { id: "rules", label: "Rules", icon: ShieldCheck },
  { id: "governance", label: "Roster approval", icon: BadgeCheck },
  { id: "approvals", label: "Approvals", icon: CheckCircle2 },
  { id: "preferences", label: "Preferences", icon: Settings2 },
];

function SectionFailure({ title, error }: { title: string; error: unknown }) {
  if (!error) return null;
  return (
    <div className="wr-inline-error" role="alert">
      <strong>{title}:</strong> {errorMessage(error)}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label>
      <span>{label}</span>
      {children}
    </label>
  );
}

function useSettingsQuery<T>(name: string, queryFn: () => Promise<T>) {
  return useQuery({
    queryKey: ["rostering", "settings", name],
    queryFn,
    staleTime: 30_000,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
  });
}

export function UnifiedRosterSettings() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("integration");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const periodsQuery = useSettingsQuery("periods", () => listRosterPeriods());
  const shiftsQuery = useSettingsQuery("shifts", () => listShiftTemplates(true));
  const patternsQuery = useSettingsQuery("patterns", () => listWorkPatterns(true));
  const employmentQuery = useSettingsQuery("contracts", () =>
    listEmploymentContracts({ page_size: 200 }),
  );
  const leaveTypesQuery = useSettingsQuery("leave-types", () => listLeaveTypes(true));
  const leaveRequestsQuery = useSettingsQuery("leave-requests", () =>
    listLeaveRequests({ page_size: 200 }),
  );
  const timesheetsQuery = useSettingsQuery("timesheets", () =>
    listTimesheets({ page_size: 200 }),
  );
  const rulesQuery = useSettingsQuery("rules", () => listRosterRules(true));
  const peopleQuery = useSettingsQuery("people", () =>
    listAllRosterPeople({
      page_size: 250,
      active_only: true,
      roster_eligible_only: false,
    }),
  );
  const permissionsQuery = useSettingsQuery(
    "permissions",
    getCurrentWorkforcePermissions,
  );
  const contractsQuery = useSettingsQuery("route-contracts", getRosterContracts);

  const queries: QuerySnapshot[] = [
    periodsQuery,
    shiftsQuery,
    patternsQuery,
    employmentQuery,
    leaveTypesQuery,
    leaveRequestsQuery,
    timesheetsQuery,
    rulesQuery,
    peopleQuery,
    permissionsQuery,
    contractsQuery,
  ];

  const initialLoading = queries.every((query) => query.isPending && !query.data);
  const permissions = permissionsQuery.data?.permissions || [];
  const can = (permission: string) => permissions.includes(permission);
  const people = useMemo(() => peopleQuery.data?.items || [], [peopleQuery.data?.items]);
  const periods = periodsQuery.data || [];
  const shifts = shiftsQuery.data || [];
  const timezoneName = periods[0]?.timezone_name || "UTC";
  const bases = useMemo(() => {
    const map = new Map<string, { id: string; code: string }>();
    people.forEach((person) => {
      if (!person.primary_base_station_id) return;
      map.set(person.primary_base_station_id, {
        id: person.primary_base_station_id,
        code: person.primary_base_code || "BASE",
      });
    });
    return [...map.values()];
  }, [people]);

  const run: RunAction = async (key, action) => {
    setBusy(key);
    setActionError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["rostering"] });
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  if (initialLoading) {
    return <RosterLoading label="Loading tenant rostering setup…" />;
  }

  return (
    <div className="wr-settings">
      <div className="wr-settings-tabs" role="tablist" aria-label="Roster setup sections">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "is-active" : ""}
            onClick={() => setTab(id)}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>

      {actionError ? (
        <div className="wr-inline-error" role="alert">
          {actionError}
        </div>
      ) : null}

      {tab === "integration" ? (
        <IntegrationPanel
          people={people}
          contractMap={contractsQuery.data || null}
          queries={queries}
        />
      ) : null}
      {tab === "periods" ? (
        <PeriodsPanel
          periods={periods}
          error={periodsQuery.error}
          canCreate={can("roster.create")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "shifts" ? (
        <ShiftsPanel
          shifts={shifts}
          error={shiftsQuery.error}
          canManage={can("roster.manage_shift_templates")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "patterns" ? (
        <PatternsPanel
          patterns={patternsQuery.data || []}
          shifts={shifts}
          error={patternsQuery.error || shiftsQuery.error}
          timezoneName={timezoneName}
          canManage={can("roster.manage_patterns")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "contracts" ? (
        <ContractsPanel
          contracts={employmentQuery.data?.items || []}
          people={people}
          bases={bases}
          error={employmentQuery.error || peopleQuery.error}
          canManage={can("workforce.manage_contracts")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "leave" ? (
        <LeavePanel
          leaveTypes={leaveTypesQuery.data || []}
          error={leaveTypesQuery.error}
          canManage={can("leave.manage_balances")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "rules" ? (
        <RulesPanel
          rules={rulesQuery.data || []}
          error={rulesQuery.error}
          canManage={can("roster.manage_rules")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "governance" ? (
    <RosterGovernancePanel
    people={people}
    periods={periods}
    bases={bases}
    canManageRules={can("roster.manage_rules")}
    canManageAuthorities={can("roster.manage_approval_authorities")}
    />
    ) : null}
      {tab === "approvals" ? (
        <ApprovalsPanel
          requests={leaveRequestsQuery.data?.items || []}
          timesheets={timesheetsQuery.data?.items || []}
          error={leaveRequestsQuery.error || timesheetsQuery.error}
          canSupervisor={can("leave.review")}
          canHr={can("leave.approve")}
          canTimesheet={can("timesheet.approve")}
          canPayroll={can("payroll.export")}
          busy={busy}
          run={run}
        />
      ) : null}
      {tab === "preferences" ? (
        <PreferencesPanel
          contractMap={contractsQuery.data || null}
          error={contractsQuery.error || permissionsQuery.error}
          busy={busy}
          run={run}
        />
      ) : null}
    </div>
  );
}

function IntegrationPanel({
  people,
  contractMap,
  queries,
}: {
  people: RosterPersonRead[];
  contractMap: RosterContractResponse | null;
  queries: QuerySnapshot[];
}) {
  const failures = queries.filter((query) => query.error).length;
  const loading = queries.filter((query) => query.isFetching).length;

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Canonical data contract</span>
          <h2>Tenant workforce integration</h2>
        </div>
        <StatusPill
          value={failures ? "DEGRADED" : loading ? "SYNCING" : "CONNECTED"}
        />
      </div>

      <div className="wr-card-grid">
        <article className="wr-setup-card">
          <div>
            <UsersRound size={18} />
            <strong>{people.length}</strong>
          </div>
          <h3>Active tenant users loaded</h3>
          <p>
            Canonical key: <code>{contractMap?.canonical_personnel_key || "accounts.users.id"}</code>
          </p>
          <small>
            Inactive and system accounts are excluded. Planner eligibility additionally
            requires an active employment contract.
          </small>
        </article>

        <article className="wr-setup-card">
          <div>
            <BadgeCheck size={18} />
            <strong>{contractMap?.phase || "workforce-integrated"}</strong>
          </div>
          <h3>Source ownership</h3>
          <p>
            Leave remains in Workforce, training in Training, audits in Quality and duty
            in Rostering.
          </p>
          <small>
            The planner projects source records instead of creating duplicate employee
            states.
          </small>
        </article>

        <article className="wr-setup-card">
          <div>
            <ShieldCheck size={18} />
            <strong>{failures}</strong>
          </div>
          <h3>Unavailable data sources</h3>
          <p>
            {failures
              ? "One or more sections are temporarily unavailable; usable sections remain open."
              : "All setup data sources responded."}
          </p>
          <small>The setup page no longer fails as one all-or-nothing request.</small>
        </article>
      </div>

      {contractMap ? (
        <div className="wr-data-list">
          {Object.entries(contractMap.source_modules).map(([name, source]) => (
            <article className="wr-data-row" key={name}>
              <div>
                <strong>{name.replace(/_/g, " ")}</strong>
                <small>{source}</small>
              </div>
              <StatusPill value="SOURCE OF TRUTH" />
            </article>
          ))}
        </div>
      ) : (
        <SectionFailure
          title="Integration contract"
          error={queries.find((query) => query.error)?.error}
        />
      )}
    </section>
  );
}

function PeriodsPanel({
  periods,
  error,
  canCreate,
  busy,
  run,
}: {
  periods: RosterPeriodRead[];
  error: unknown;
  canCreate: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const now = new Date();
  const [code, setCode] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );
  const [name, setName] = useState("Monthly duty roster");
  const [startsOn, setStartsOn] = useState(
    isoDate(new Date(now.getFullYear(), now.getMonth(), 1)),
  );
  const [endsOn, setEndsOn] = useState(
    isoDate(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  );
  const [timezoneOverride, setTimezoneOverride] = useState("");
  const timezoneName = timezoneOverride || periods[0]?.timezone_name || "UTC";

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Planning control</span>
          <h2>Roster periods and versions</h2>
        </div>
      </div>
      <SectionFailure title="Periods" error={error} />

      {canCreate ? (
        <div className="wr-inline-create">
          <Field label="Code">
            <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Starts">
            <input type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} />
          </Field>
          <Field label="Ends">
            <input type="date" value={endsOn} onChange={(event) => setEndsOn(event.target.value)} />
          </Field>
          <Field label="Time zone">
            <input value={timezoneName} onChange={(event) => setTimezoneOverride(event.target.value)} />
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!code || !name || busy === "period"}
            onClick={() => {
              void run("period", () =>
                createRosterPeriod({
                  period_code: code,
                  name,
                  starts_on: startsOn,
                  ends_on: endsOn,
                  timezone_name: timezoneName,
                }),
              );
            }}
          >
            <Plus size={16} /> Create period
          </button>
        </div>
      ) : null}

      <div className="wr-data-list">
        {periods.map((period) => (
          <article key={period.id} className="wr-data-row">
            <div>
              <strong>{period.period_code} · {period.name}</strong>
              <small>{period.starts_on} → {period.ends_on} · {period.timezone_name}</small>
            </div>
            <span>{period.versions.length} versions</span>
            <StatusPill value={period.status} />
            <button
              type="button"
              className="wr-button wr-button--small"
              disabled={!canCreate || busy === `version:${period.id}`}
              onClick={() => {
                void run(`version:${period.id}`, () =>
                  createRosterVersion(period.id, {
                    title: `Draft v${period.versions.length + 1}`,
                    idempotency_key: newIdempotencyKey("version"),
                  }),
                );
              }}
            >
              <Plus size={14} /> Draft
            </button>
          </article>
        ))}
      </div>

      {!error && periods.length === 0 ? (
        <EmptyState title="No periods" description="Create a period to start planning duty." />
      ) : null}
    </section>
  );
}

function ShiftsPanel({
  shifts,
  error,
  canManage,
  busy,
  run,
}: {
  shifts: ShiftTemplateRead[];
  error: unknown;
  canManage: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<ShiftTemplateRead["kind"]>("DAY");
  const [start, setStart] = useState("08:00");
  const [end, setEnd] = useState("17:00");
  const countsAsDuty = !["OFF", "LEAVE"].includes(kind);

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Reusable building blocks</span>
          <h2>Shift templates</h2>
        </div>
      </div>
      <SectionFailure title="Shift templates" error={error} />

      {canManage ? (
        <div className="wr-inline-create">
          <Field label="Code">
            <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Field label="Label">
            <input value={label} onChange={(event) => setLabel(event.target.value)} />
          </Field>
          <Field label="Kind">
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as ShiftTemplateRead["kind"])}
            >
              {["DAY", "NIGHT", "STANDBY", "TRAINING", "OFF", "LEAVE", "OTHER"].map(
                (value) => <option key={value}>{value}</option>,
              )}
            </select>
          </Field>
          <Field label="Starts">
            <input type="time" value={start} onChange={(event) => setStart(event.target.value)} />
          </Field>
          <Field label="Ends">
            <input type="time" value={end} onChange={(event) => setEnd(event.target.value)} />
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!code || !label || busy === "shift"}
            onClick={() => {
              void run("shift", () =>
                createShiftTemplate({
                  code,
                  label,
                  kind,
                  default_start_time: ["OFF", "LEAVE"].includes(kind) ? null : start,
                  default_end_time: ["OFF", "LEAVE"].includes(kind) ? null : end,
                  duration_minutes: null,
                  counts_as_duty: countsAsDuty,
                  is_active: true,
                  display_order: shifts.length * 10 + 10,
                  description: null,
                  color_token: `shift-${kind.toLowerCase()}`,
                  icon_name: null,
                }),
              );
            }}
          >
            <Plus size={16} /> Add shift
          </button>
        </div>
      ) : null}

      <div className="wr-card-grid">
        {shifts.map((shift) => (
          <article className="wr-setup-card" key={shift.id}>
            <div>
              <strong>{shift.code}</strong>
              <StatusPill value={shift.kind} />
            </div>
            <h3>{shift.label}</h3>
            <p>{shift.default_start_time || "—"} → {shift.default_end_time || "—"}</p>
            <small>
              {shift.counts_as_duty
                ? "Counts toward occupied duty time"
                : "Protected non-duty state"}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}

function buildPatternDays(
  cycle: number,
  dutyDays: number,
  shiftId: string,
  selectedShift?: ShiftTemplateRead,
): WorkPatternDayInput[] {
  const activeDutyDays = Math.min(Math.max(dutyDays, 0), cycle);
  const status: PatternDayStatus = selectedShift?.kind === "TRAINING"
    ? "TRAINING"
    : selectedShift?.kind === "STANDBY"
      ? "STANDBY"
      : "DUTY";

  return Array.from({ length: cycle }, (_, index): WorkPatternDayInput => {
    const isDutyDay = index < activeDutyDays;
    return {
      cycle_day_index: index,
      shift_template_id: isDutyDay ? shiftId : null,
      status: isDutyDay ? status : "OFF",
      start_time_local: isDutyDay ? selectedShift?.default_start_time || "08:00" : null,
      end_time_local: isDutyDay ? selectedShift?.default_end_time || "17:00" : null,
      spans_next_day: Boolean(
        isDutyDay
        && selectedShift?.default_start_time
        && selectedShift?.default_end_time
        && selectedShift.default_end_time <= selectedShift.default_start_time
      ),
      planned_minutes: isDutyDay ? selectedShift?.duration_minutes || 0 : 0,
    };
  });
}

function PatternsPanel({
  patterns,
  shifts,
  error,
  timezoneName,
  canManage,
  busy,
  run,
}: {
  patterns: WorkPatternRead[];
  shifts: ShiftTemplateRead[];
  error: unknown;
  timezoneName: string;
  canManage: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const dutyShifts = useMemo(
      () => shifts.filter((shift) => shift.counts_as_duty && shift.is_active),
      [shifts],
    );
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [cycle, setCycle] = useState(7);
  const [shiftId, setShiftId] = useState("");
  const [dutyDays, setDutyDays] = useState(5);

  const effectiveShiftId = shiftId || dutyShifts[0]?.id || "";
  const selectedShift = shifts.find((shift) => shift.id === effectiveShiftId);

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Rotation engine</span>
          <h2>Work patterns</h2>
        </div>
      </div>
      <SectionFailure title="Work patterns" error={error} />

      {canManage ? (
        <div className="wr-inline-create">
          <Field label="Code">
            <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Cycle days">
            <input
              type="number"
              min={1}
              max={56}
              value={cycle}
              onChange={(event) => setCycle(Math.min(Math.max(Number(event.target.value), 1), 56))}
            />
          </Field>
          <Field label="Duty days">
            <input
              type="number"
              min={0}
              max={cycle}
              value={dutyDays}
              onChange={(event) => setDutyDays(Number(event.target.value))}
            />
          </Field>
          <Field label="Duty shift">
            <select value={effectiveShiftId} onChange={(event) => setShiftId(event.target.value)}>
              <option value="">Select shift</option>
              {dutyShifts.map((shift) => (
                <option key={shift.id} value={shift.id}>
                  {shift.code} · {shift.label}
                </option>
              ))}
            </select>
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!code || !name || !effectiveShiftId || busy === "pattern"}
            onClick={() => {
              void run("pattern", () =>
                createWorkPattern({
                  code,
                  name,
                  description: null,
                  cycle_length_days: cycle,
                  is_active: true,
                  timezone_name: timezoneName,
                  days: buildPatternDays(cycle, dutyDays, effectiveShiftId, selectedShift),
                }),
              );
            }}
          >
            <Plus size={16} /> Create pattern
          </button>
        </div>
      ) : null}

      <div className="wr-card-grid">
        {patterns.map((pattern) => (
          <article className="wr-setup-card" key={pattern.id}>
            <div>
              <strong>{pattern.code}</strong>
              <StatusPill value={pattern.is_active ? "ACTIVE" : "INACTIVE"} />
            </div>
            <h3>{pattern.name}</h3>
            <p>
              {pattern.cycle_length_days}-day cycle · {pattern.assigned_employee_count} assigned · {pattern.timezone_name}
            </p>
            <div className="wr-pattern-strip">
              {pattern.days.map((day) => (
                <span
                  key={day.id}
                  className={`is-${day.status.toLowerCase()}`}
                  title={`Day ${day.cycle_day_index + 1}: ${day.status}`}
                />
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ContractsPanel({
  contracts,
  people,
  bases,
  error,
  canManage,
  busy,
  run,
}: {
  contracts: EmploymentContractRead[];
  people: RosterPersonRead[];
  bases: Array<{ id: string; code: string }>;
  error: unknown;
  canManage: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const [userId, setUserId] = useState("");
  const [baseId, setBaseId] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(isoDate(new Date()));

  const effectiveUserId = userId || people[0]?.user_id || "";
  const effectiveBaseId = baseId || bases[0]?.id || "";

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">HR source of truth</span>
          <h2>Employment contracts</h2>
        </div>
      </div>
      <SectionFailure title="Employment contracts" error={error} />

      {canManage ? (
        <div className="wr-inline-create">
          <Field label="Person">
            <select value={effectiveUserId} onChange={(event) => setUserId(event.target.value)}>
              <option value="">Select active user</option>
              {people.map((person) => (
                <option key={person.user_id} value={person.user_id}>
                  {person.staff_code} · {person.full_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Primary base">
            <select value={effectiveBaseId} onChange={(event) => setBaseId(event.target.value)}>
              <option value="">Select base</option>
              {bases.map((base) => (
                <option key={base.id} value={base.id}>{base.code}</option>
              ))}
            </select>
          </Field>
          <Field label="Effective from">
            <input
              type="date"
              value={effectiveFrom}
              onChange={(event) => setEffectiveFrom(event.target.value)}
            />
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!effectiveUserId || !effectiveBaseId || busy === "contract"}
            onClick={() => {
              void run("contract", () =>
                createEmploymentContract({
                  user_id: effectiveUserId,
                  contract_type: "PERMANENT",
                  employment_status: "ACTIVE",
                  effective_from: effectiveFrom,
                  effective_to: null,
                  standard_weekly_minutes: 2400,
                  standard_daily_minutes: 480,
                  fte_percentage: 100,
                  primary_base_station_id: effectiveBaseId,
                  secondary_base_station_id: null,
                  supervisor_user_id: null,
                  cost_centre: null,
                  payroll_number: null,
                  overtime_eligible: true,
                  night_shift_eligible: true,
                  standby_eligible: true,
                }),
              );
            }}
          >
            <Plus size={16} /> Add contract
          </button>
        </div>
      ) : null}

      <div className="wr-data-list">
        {contracts.map((contract) => (
          <article key={contract.id} className="wr-data-row">
            <div>
              <strong>{contract.user_full_name || contract.user_staff_code}</strong>
              <small>{contract.contract_type} · {contract.primary_base_code || "No base"}</small>
            </div>
            <span>{Math.round(contract.standard_weekly_minutes / 60)}h/week</span>
            <StatusPill value={contract.employment_status} />
            <span>
              {contract.effective_from}
              {contract.effective_to ? ` → ${contract.effective_to}` : ""}
            </span>
          </article>
        ))}
      </div>

      {!error && contracts.length === 0 ? (
        <EmptyState
          title="No employment contracts"
          description="Planner eligibility requires an active contract."
        />
      ) : null}
    </section>
  );
}

function LeavePanel({
  leaveTypes,
  error,
  canManage,
  busy,
  run,
}: {
  leaveTypes: LeaveTypeRead[];
  error: unknown;
  canManage: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Absence policy</span>
          <h2>Leave types</h2>
        </div>
      </div>
      <SectionFailure title="Leave policy" error={error} />

      {canManage ? (
        <div className="wr-inline-create">
          <Field label="Code">
            <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!code || !name || busy === "leave-type"}
            onClick={() => {
              void run("leave-type", () =>
                createLeaveType({
                  code,
                  name,
                  availability_type: "ANNUAL_LEAVE",
                  description: null,
                  paid: true,
                  deducts_balance: true,
                  requires_attachment: false,
                  supervisor_approval_required: true,
                  hr_approval_required: true,
                  allow_negative_balance: false,
                  is_active: true,
                  display_order: leaveTypes.length * 10 + 10,
                }),
              );
            }}
          >
            <Plus size={16} /> Add leave type
          </button>
        </div>
      ) : null}

      <div className="wr-card-grid">
        {leaveTypes.map((type) => (
          <article className="wr-setup-card" key={type.id}>
            <div>
              <strong>{type.code}</strong>
              <StatusPill value={type.is_active ? "ACTIVE" : "INACTIVE"} />
            </div>
            <h3>{type.name}</h3>
            <p>{type.paid ? "Paid" : "Unpaid"} · {type.deducts_balance ? "Deducts balance" : "No balance deduction"}</p>
            <small>
              {type.supervisor_approval_required ? "Supervisor" : "No supervisor"} · {type.hr_approval_required ? "HR approval" : "No HR approval"}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}

function RulesPanel({
  rules,
  error,
  canManage,
  busy,
  run,
}: {
  rules: RosterRuleRead[];
  error: unknown;
  canManage: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<RosterRuleRead["rule_type"]>("CUSTOM");
  const [severity, setSeverity] = useState<RosterRuleRead["severity"]>("WARNING");
  const ruleTypes: RosterRuleRead["rule_type"][] = [
    "MIN_REST_HOURS",
    "MAX_DUTY_HOURS_DAY",
    "MAX_DUTY_HOURS_ROLLING",
    "MAX_CONSECUTIVE_DAYS",
    "MIN_COVERAGE",
    "REQUIRED_CERTIFYING_COVERAGE",
    "TRAINING_VALIDITY",
    "AVAILABILITY_CONFLICT",
    "CUSTOM",
  ];

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Validation policy</span>
          <h2>Roster rules</h2>
        </div>
      </div>
      <SectionFailure title="Roster rules" error={error} />

      {canManage ? (
        <div className="wr-inline-create">
          <Field label="Code">
            <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Field label="Name">
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Rule type">
            <select
              value={type}
              onChange={(event) => setType(event.target.value as RosterRuleRead["rule_type"])}
            >
              {ruleTypes.map((value) => <option key={value}>{value}</option>)}
            </select>
          </Field>
          <Field label="Severity">
            <select
              value={severity}
              onChange={(event) => setSeverity(event.target.value as RosterRuleRead["severity"])}
            >
              <option>INFO</option>
              <option>WARNING</option>
              <option>BLOCKER</option>
            </select>
          </Field>
          <button
            className="wr-button wr-button--primary"
            type="button"
            disabled={!code || !name || busy === "rule"}
            onClick={() => {
              void run("rule", () =>
                createRosterRule({
                  code,
                  name,
                  description: null,
                  rule_type: type,
                  scope: "AMO",
                  severity,
                  parameters_json: {},
                  department_id: null,
                  base_station_id: null,
                  shift_template_id: null,
                  user_id: null,
                  effective_from: null,
                  effective_to: null,
                  allow_override: severity !== "BLOCKER",
                  is_active: true,
                  display_order: rules.length * 10 + 10,
                }),
              );
            }}
          >
            <Plus size={16} /> Add rule
          </button>
        </div>
      ) : null}

      <div className="wr-data-list">
        {rules.map((rule) => (
          <article key={rule.id} className="wr-data-row">
            <div>
              <strong>{rule.code}</strong>
              <small>{rule.name} · {rule.rule_type.replace(/_/g, " ")}</small>
            </div>
            <StatusPill value={rule.scope} />
            <StatusPill value={rule.severity} />
            <span>{rule.allow_override ? "Override allowed" : "Mandatory"}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function ApprovalsPanel({
  requests,
  timesheets,
  error,
  canSupervisor,
  canHr,
  canTimesheet,
  canPayroll,
  busy,
  run,
}: {
  requests: LeaveRequestRead[];
  timesheets: TimesheetRead[];
  error: unknown;
  canSupervisor: boolean;
  canHr: boolean;
  canTimesheet: boolean;
  canPayroll: boolean;
  busy: string | null;
  run: RunAction;
}) {
  const pendingLeave = requests.filter((request) =>
    ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status),
  );
  const pendingSheets = timesheets.filter((sheet) =>
    ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(sheet.status),
  );

  return (
    <div className="wr-two-column wr-two-column--wide">
      <section className="wr-panel">
        <div className="wr-section-heading">
          <div>
            <span className="wr-eyebrow">Leave workflow</span>
            <h2>Approval queue</h2>
          </div>
          <BadgeCheck size={20} />
        </div>
        <SectionFailure title="Leave approvals" error={error} />

        {pendingLeave.length === 0 ? (
          <EmptyState title="No leave approvals" description="Submitted requests will appear here." />
        ) : (
          <div className="wr-data-list">
            {pendingLeave.map((request) => (
              <article key={request.id} className="wr-approval-row">
                <div>
                  <strong>{request.user_full_name || request.user_staff_code}</strong>
                  <small>
                    {request.leave_type_name} · {request.starts_at.slice(0, 10)} → {request.ends_at.slice(0, 10)}
                  </small>
                  {request.published_roster_conflicts.length ? (
                    <span className="wr-pill wr-pill--blocker">Published roster conflict</span>
                  ) : null}
                </div>
                <StatusPill value={request.status} />
                <div className="wr-actions">
                  {request.status === "SUBMITTED" && canSupervisor ? (
                    <button
                      className="wr-button wr-button--small"
                      type="button"
                      disabled={busy === `sup:${request.id}`}
                      onClick={() => {
                        void run(`sup:${request.id}`, () =>
                          supervisorApproveLeave(request.id, "Approved in workforce control"),
                        );
                      }}
                    >
                      <CheckCircle2 size={14} /> Supervisor
                    </button>
                  ) : null}
                  {request.status === "SUPERVISOR_APPROVED" && canHr ? (
                    <button
                      className="wr-button wr-button--small wr-button--success"
                      type="button"
                      disabled={busy === `hr:${request.id}`}
                      onClick={() => {
                        void run(`hr:${request.id}`, () =>
                          hrApproveLeave(request.id, "Approved in workforce control"),
                        );
                      }}
                    >
                      <CheckCircle2 size={14} /> HR approve
                    </button>
                  ) : null}
                  {canSupervisor || canHr ? (
                    <button
                      className="wr-icon-button is-danger"
                      type="button"
                      aria-label="Reject leave"
                      disabled={busy === `reject:${request.id}`}
                      onClick={() => {
                        void run(`reject:${request.id}`, () =>
                          rejectLeaveRequest(request.id, "Rejected in workforce control"),
                        );
                      }}
                    >
                      <XCircle size={16} />
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div>
            <span className="wr-eyebrow">Timesheet workflow</span>
            <h2>Pay-period approvals</h2>
          </div>
          <FileClock size={20} />
        </div>

        {canPayroll ? (
          <button
            type="button"
            className="wr-button wr-button--secondary wr-button--full"
            onClick={() => void downloadPayrollExport({})}
          >
            <Download size={16} /> Download payroll export
          </button>
        ) : null}

        {pendingSheets.length === 0 ? (
          <EmptyState title="No timesheet approvals" description="Submitted timesheets will appear here." />
        ) : (
          <div className="wr-data-list">
            {pendingSheets.map((sheet) => (
              <article key={sheet.id} className="wr-approval-row">
                <div>
                  <strong>{sheet.user_full_name || sheet.user_id}</strong>
                  <small>
                    {sheet.period_start} → {sheet.period_end} · {Math.round(sheet.attendance_minutes / 60)}h attendance
                  </small>
                </div>
                <StatusPill value={sheet.status} />
                <div className="wr-actions">
                  {canTimesheet && sheet.status === "SUBMITTED" ? (
                    <button
                      className="wr-button wr-button--small"
                      type="button"
                      disabled={busy === `sheet-sup:${sheet.id}`}
                      onClick={() => {
                        void run(`sheet-sup:${sheet.id}`, () =>
                          approveTimesheet(sheet.id, "SUPERVISOR", "Approved in workforce control"),
                        );
                      }}
                    >
                      Supervisor
                    </button>
                  ) : null}
                  {canTimesheet && sheet.status === "SUPERVISOR_APPROVED" ? (
                    <button
                      className="wr-button wr-button--small wr-button--success"
                      type="button"
                      disabled={busy === `sheet-hr:${sheet.id}`}
                      onClick={() => {
                        void run(`sheet-hr:${sheet.id}`, () =>
                          approveTimesheet(sheet.id, "HR", "Approved in workforce control"),
                        );
                      }}
                    >
                      HR approve
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function PreferencesPanel({
  contractMap,
  error,
  busy,
  run,
}: {
  contractMap: RosterContractResponse | null;
  error: unknown;
  busy: string | null;
  run: RunAction;
}) {
  const [density, setDensity] = useState<PlannerPreferenceRead["density"]>("compact");
  const [groupBy, setGroupBy] = useState("department");
  const [zoom, setZoom] = useState("day");

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Personal workspace</span>
          <h2>Planner preferences</h2>
        </div>
      </div>
      <SectionFailure title="Planner preferences" error={error} />

      <div className="wr-inline-create">
        <Field label="Density">
          <select
            value={density}
            onChange={(event) =>
              setDensity(event.target.value as PlannerPreferenceRead["density"])
            }
          >
            <option value="compact">Compact</option>
            <option value="comfortable">Comfortable</option>
          </select>
        </Field>
        <Field label="Group by">
          <select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}>
            <option value="department">Department</option>
            <option value="base">Base</option>
            <option value="none">None</option>
          </select>
        </Field>
        <Field label="Default zoom">
          <select value={zoom} onChange={(event) => setZoom(event.target.value)}>
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </Field>
        <button
          className="wr-button wr-button--primary"
          type="button"
          disabled={busy === "preferences"}
          onClick={() => {
            void run("preferences", () =>
              updatePlannerPreferences({ density, group_by: groupBy, zoom }),
            );
          }}
        >
          <Settings2 size={16} /> Save preferences
        </button>
      </div>

      <div className="wr-card-grid">
        <article className="wr-setup-card">
          <div>
            <ShieldCheck size={18} />
            <StatusPill value={contractMap?.phase || "INTEGRATED"} />
          </div>
          <h3>Server capability contract</h3>
          <p>
            {Object.entries(contractMap?.capabilities || {})
              .filter(([, enabled]) => enabled)
              .map(([name]) => name.replace(/_/g, " "))
              .join(" · ") || "Capabilities unavailable"}
          </p>
          <small>
            Controls are rendered from server permissions, not from duplicated frontend
            role assumptions.
          </small>
        </article>
      </div>
    </section>
  );
}
