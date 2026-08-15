import "./rostering-setup-workspace.css";

import { lazy, Suspense, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  History,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  createRosterDemandRequirement,
  listRosterDemandRequirements,
  listRosterPeriods,
  listRosterRules,
  retireRosterDemandRequirement,
} from "../../../services/rostering";
import {
  getRosterSetupReadiness,
  listRosterAutomationRuns,
  previewRosterAutomation,
  runRosterAutomation,
  updateRosterAutomationPolicy,
} from "../../../services/rosteringAutomation";
import { listAllRosterPeople } from "../../../services/rosterPeople";
import type {
  RosterAutomationPreview,
  RosterAutomationFrequency,
  RosterGenerationPolicy,
} from "../../../types/rosteringAutomation";
import { errorMessage, newIdempotencyKey } from "../rosterUi";
import { zonedWallTimeToIso } from "../timezone";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";
import { RosterPeriodQuickActions } from "./RosterPeriodQuickActions";
import { WorkPatternStudio } from "./WorkPatternStudio";

const RosterGovernancePanel = lazy(() =>
  import("./RosterGovernancePanel").then((module) => ({ default: module.RosterGovernancePanel })),
);
const RosterRuleQuickEditor = lazy(() =>
  import("./RosterRuleQuickEditor").then((module) => ({ default: module.RosterRuleQuickEditor })),
);
const ControlledRosterSettingsPanel = lazy(() =>
  import("./ControlledRosterSettingsPanel").then((module) => ({ default: module.ControlledRosterSettingsPanel })),
);
const RosterCodeRegistryPanel = lazy(() =>
  import("./RosterCodeRegistryPanel").then((module) => ({ default: module.RosterCodeRegistryPanel })),
);

type Section = "start" | "patterns" | "control" | "advanced";
type ControlView = "coverage" | "governance";

const SECTIONS: Array<{ id: Section; label: string }> = [
  { id: "start", label: "Get started" },
  { id: "patterns", label: "Shifts & patterns" },
  { id: "control", label: "Coverage & approvals" },
  { id: "advanced", label: "Advanced" },
];

function normalizeSection(value: string | null): Section {
  if (value === "shifts" || value === "patterns") return "patterns";
  if (value === "coverage" || value === "policy" || value === "control") return "control";
  if (value === "automation" || value === "advanced") return "advanced";
  return "start";
}

function formatDate(value?: string | null): string {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function stateTone(value: string): string {
  if (value === "READY" || value === "COMPLETED") return "good";
  if (value === "BLOCKED" || value === "FAILED") return "danger";
  if (value === "NEEDS_ATTENTION" || value === "COMPLETED_WITH_CONFLICTS") return "warning";
  return "info";
}

export function RosteringSetupWorkspace() {
  const { amoCode = "" } = useParams();
  const root = `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
  const queryClient = useQueryClient();
  const initial = new URLSearchParams(window.location.search).get("section");
  const [section, setSection] = useState<Section>(() => normalizeSection(initial));
  const [controlView, setControlView] = useState<ControlView>(initial === "policy" ? "governance" : "coverage");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const readinessQuery = useQuery({
    queryKey: ["rostering", "setup", "readiness"],
    queryFn: getRosterSetupReadiness,
    staleTime: 60_000,
  });
  const permissionsQuery = useWorkforcePermissions();
  const periodsQuery = useQuery({
    queryKey: ["rostering", "settings", "periods"],
    queryFn: () => listRosterPeriods(),
    enabled: section === "control" && controlView === "governance",
    staleTime: 60_000,
  });
  const governancePeopleQuery = useQuery({
    queryKey: ["rostering", "settings", "governance-people"],
    queryFn: () => listAllRosterPeople({
      page_size: 250,
      active_only: true,
      roster_eligible_only: false,
    }),
    enabled: section === "control",
    staleTime: 15 * 60_000,
  });
  const rulesQuery = useQuery({
    queryKey: ["rostering", "settings", "rules"],
    queryFn: () => listRosterRules(true),
    enabled: section === "control" && controlView === "governance",
    staleTime: 15 * 60_000,
  });
  const runsQuery = useQuery({
    queryKey: ["rostering", "automation", "runs"],
    queryFn: () => listRosterAutomationRuns(40),
    enabled: section === "advanced",
    staleTime: 30_000,
  });
  const demandsQuery = useQuery({
    queryKey: ["rostering", "settings", "demand-requirements"],
    queryFn: () => listRosterDemandRequirements({ include_inactive: true }),
    enabled: section === "control" && controlView === "coverage",
    staleTime: 60_000,
  });

  const permissions = permissionsQuery.data?.permissions || [];
  const governancePeople = useMemo(
    () => governancePeopleQuery.data?.items || [],
    [governancePeopleQuery.data?.items],
  );
  const governanceBases = useMemo(() => {
    const map = new Map<string, { id: string; code: string }>();
    governancePeople.forEach((person) => {
      if (!person.primary_base_station_id) return;
      map.set(person.primary_base_station_id, {
        id: person.primary_base_station_id,
        code: person.primary_base_code || "BASE",
      });
    });
    return [...map.values()].sort((left, right) => left.code.localeCompare(right.code));
  }, [governancePeople]);
  const can = (permission: string) => permissions.includes(permission);
  const canGenerate = can("roster.create") && can("roster.manage_patterns");
  const readiness = readinessQuery.data;

  const navigateSection = (next: Section) => {
    setSection(next);
    const url = new URL(window.location.href);
    url.searchParams.set("section", next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["rostering"] });
    await queryClient.invalidateQueries({ queryKey: ["workforce"] });
  };

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setActionError(null);
    try {
      await action();
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  if (readinessQuery.isPending && !readiness) return <RosterLoading label="Checking roster setup…" />;
  if (readinessQuery.error && !readiness) {
    return <div className="wr-inline-error" role="alert">{errorMessage(readinessQuery.error)}</div>;
  }
  if (!readiness) return null;

  return (
    <div className="rs-setup">
      <nav className="rs-setup__nav" aria-label="Roster setup sections">
        {SECTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={section === item.id ? "is-active" : ""}
            onClick={() => navigateSection(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}

      {section === "start" ? <div className="rs-setup__stack"><SetupOverview readiness={readiness} root={root} onOpen={navigateSection} onRefresh={refresh} /><PlanningCalendar previewEnabled={canGenerate} busy={busy} runAction={runAction} /></div> : null}
      {section === "patterns" ? (
        <WorkPatternStudio
          canManageShifts={can("roster.manage_shift_templates")}
          canManagePatterns={can("roster.manage_patterns")}
          busy={busy}
          runAction={runAction}
          workforcePath={`${root}/workforce`}
          timezoneName={readiness.policy.timezone_name}
        />
      ) : null}
      {section === "control" ? <div className="rs-setup__stack"><nav className="rs-subnav" aria-label="Coverage and approval controls"><button type="button" className={controlView === "coverage" ? "is-active" : ""} onClick={() => setControlView("coverage")}>Coverage demand</button><button type="button" className={controlView === "governance" ? "is-active" : ""} onClick={() => setControlView("governance")}>Rules & approvals</button></nav>{controlView === "coverage" ? <CoverageDemandPanel demands={demandsQuery.data || []} loading={demandsQuery.isPending || governancePeopleQuery.isPending} error={demandsQuery.error || governancePeopleQuery.error} people={governancePeople} bases={governanceBases} timezoneName={readiness.policy.timezone_name} canManage={can("roster.allocate_work")} busy={busy} runAction={runAction} /> : <PolicyPanel rules={rulesQuery.data || []} loading={rulesQuery.isPending} authorityCount={readiness.active_approval_authority_count} canManageRules={can("roster.manage_rules")} canManageAuthorities={can("roster.manage_approval_authorities")} people={governancePeople} periods={periodsQuery.data || []} bases={governanceBases} governanceLoading={governancePeopleQuery.isPending || periodsQuery.isPending} governanceError={governancePeopleQuery.error || periodsQuery.error} />}</div> : null}
      {section === "advanced" ? (
        <AdvancedWorkspace policy={readiness.policy} permissions={permissions} busy={busy} runAction={runAction} runs={runsQuery.data || []} loading={runsQuery.isPending} onRefresh={() => void runsQuery.refetch()} />
      ) : null}
    </div>
  );
}

function SetupOverview({
  readiness,
  root,
  onOpen,
  onRefresh,
}: {
  readiness: Awaited<ReturnType<typeof getRosterSetupReadiness>>;
  root: string;
  onOpen: (section: Section) => void;
  onRefresh: () => Promise<void>;
}) {
  const percent = Math.round((readiness.ready_count / Math.max(readiness.total_count, 1)) * 100);
  const outstanding = readiness.items.filter((item) => item.state !== "READY");
  return (
    <section className="wr-panel rs-start">
      <div className="rs-start__status">
        <div><span className="wr-eyebrow">Setup status</span><h2>{readiness.can_plan ? "Ready to build a roster" : "Finish setup before planning"}</h2><p>{readiness.can_plan ? "Use the three-step path below. Advanced settings stay out of the way unless you need them." : `${outstanding.length} setup item${outstanding.length === 1 ? "" : "s"} still need attention.`}</p></div>
        <div className="rs-start__score"><strong>{percent}%</strong><span>{readiness.ready_count} of {readiness.total_count} ready</span><button type="button" className="wr-icon-button" onClick={() => void onRefresh()} aria-label="Refresh setup status"><RefreshCw size={16} /></button></div>
      </div>
      <div className="rs-start__bar" aria-label={`${percent}% setup complete`}><span style={{ width: `${percent}%` }} /></div>

      {outstanding.length ? <div className="rs-start__issues">{outstanding.slice(0, 4).map((item) => <button key={item.key} type="button" onClick={() => onOpen(normalizeSection(item.action_path || null))}><span className={`rs-setup-card__icon is-${stateTone(item.state)}`}>{item.state === "BLOCKED" ? <AlertTriangle size={17} /> : <Settings2 size={17} />}</span><span><strong>{item.label}</strong><small>{item.detail}</small></span><ArrowRight size={14} /></button>)}</div> : null}

      <div className="rs-workflow">
        <button type="button" onClick={() => onOpen("patterns")}><span>1</span><div><strong>Set shifts and patterns</strong><small>Choose a rotation recipe and adjust the cycle.</small></div><ArrowRight size={15} /></button>
        <div><span>2</span><div><strong>Create the month</strong><small>Preview pattern-generated duty before creating a draft.</small></div><CalendarPlus size={15} /></div>
        <Link to={`${root}/calendar`}><span>3</span><div><strong>Review and publish</strong><small>Resolve gaps, validate and move through approval.</small></div><ArrowRight size={15} /></Link>
      </div>
    </section>
  );
}

function PlanningCalendar({
  previewEnabled,
  busy,
  runAction,
}: {
  previewEnabled: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [preview, setPreview] = useState<RosterAutomationPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const openPreview = async () => {
    setPreviewError(null);
    try {
      setPreview(await previewRosterAutomation({ create_missing_period: true }));
    } catch (cause) {
      setPreviewError(errorMessage(cause));
    }
  };
  return (
    <section className="wr-panel rs-month-start">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Step 2 · Monthly roster</span><h2>Create the next roster</h2><p>Use the guided action for normal work. Manual period and amendment controls remain available below.</p></div>{previewEnabled ? <button type="button" className="wr-button wr-button--primary" onClick={() => void openPreview()}><CalendarPlus size={16} /> Preview next month</button> : null}</div>
      {previewError ? <div className="wr-inline-error" role="alert">{previewError}</div> : null}
      <details className="rs-progressive"><summary><span><CalendarClock size={16} /><strong>Manual period controls</strong><small>Create a specific month or amend a published version</small></span></summary><div className="rs-progressive__body"><RosterPeriodQuickActions /></div></details>
      {preview ? <div className="rs-preview" role="dialog" aria-modal="true" aria-label="Next roster preview"><div className="rs-preview__head"><div><span className="wr-eyebrow">Safe preview</span><h3>{preview.period_code} · {preview.period_name}</h3></div><button type="button" className="wr-icon-button" aria-label="Close preview" onClick={() => setPreview(null)}><X size={16} /></button></div><div className="rs-preview__facts"><span><strong>{preview.target_from}</strong> starts</span><span><strong>{preview.target_to}</strong> ends</span><span><strong>{preview.eligible_employee_count}</strong> eligible people</span><span><strong>{preview.estimated_assignment_count}</strong> estimated duties</span></div>{preview.items.map((item) => <div key={item.code} className={`rs-preview__issue is-${item.severity.toLowerCase()}`}><strong>{item.code.replace(/_/g, " ")}</strong><span>{item.message}</span></div>)}<div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setPreview(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || preview.blocking_issue_count > 0} onClick={() => void runAction("automation-run", async () => { await runRosterAutomation({ target_from: preview.target_from, target_to: preview.target_to, create_missing_period: true, create_initial_draft: true, generate_from_patterns: true, confirm_preview: true, idempotency_key: newIdempotencyKey("roster-automation") }); setPreview(null); })}><Play size={15} /> Create draft roster</button></div><small>Creates a draft only. Approval and publication always remain separate authorised actions.</small></div> : null}
    </section>
  );
}

function AutomationPanel({
  policy,
  canManage,
  busy,
  runAction,
}: {
  policy: RosterGenerationPolicy;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useState(policy);
  const [reason, setReason] = useState("");
  const schedulingDisabled = !canManage || draft.frequency === "MANUAL";
  const changeFrequency = (frequency: RosterAutomationFrequency) => {
    const weeklyCadence = frequency === "WEEKLY" || frequency === "FORTNIGHTLY";
    const runDay = weeklyCadence && draft.run_day > 7 ? 1 : !weeklyCadence && draft.run_day > 28 ? 1 : draft.run_day;
    setDraft({ ...draft, frequency, run_day: runDay });
  };

  const save = () => runAction("automation-policy", () => updateRosterAutomationPolicy({
    enabled: draft.enabled,
    frequency: draft.frequency,
    lead_periods: draft.lead_periods,
    run_day: draft.run_day,
    run_hour_local: draft.run_hour_local,
    timezone_name: draft.timezone_name,
    period_code_pattern: draft.period_code_pattern,
    period_name_pattern: draft.period_name_pattern,
    create_initial_draft: draft.create_initial_draft,
    generate_from_patterns: draft.generate_from_patterns,
    preserve_source_commitments: true,
    validate_after_generation: draft.validate_after_generation,
    notify_planners: false,
    require_preview_confirmation: draft.require_preview_confirmation,
    expected_state_revision: policy.state_revision,
    reason,
  }));

  return (
    <div className="rs-setup__stack">
      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Automatic month setup</span><h2>Create future periods automatically</h2><p>Maintain the planning horizon without creating duplicates or publishing unattended duty.</p></div>
          <label className="rs-toggle"><input type="checkbox" checked={draft.enabled} disabled={!canManage} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} /><span>{draft.enabled ? "On" : "Off"}</span></label>
        </div>
        <div className="rs-form-grid">
          <label><span>Frequency</span><select value={draft.frequency} disabled={!canManage} onChange={(event) => changeFrequency(event.target.value as RosterAutomationFrequency)}><option value="MONTHLY">Monthly</option><option value="FORTNIGHTLY">Fortnightly</option><option value="WEEKLY">Weekly</option><option value="MANUAL">Manual only</option></select></label>
          <label><span>Maintain ahead</span><select value={draft.lead_periods} disabled={schedulingDisabled} onChange={(event) => setDraft({ ...draft, lead_periods: Number(event.target.value) })}>{[1, 2, 3, 6, 12].map((value) => <option key={value} value={value}>{value} period{value === 1 ? "" : "s"}</option>)}</select></label>
          {draft.frequency === "MONTHLY" ? <label><span>Day of month</span><input type="number" min="1" max="28" value={draft.run_day} disabled={schedulingDisabled} onChange={(event) => setDraft({ ...draft, run_day: Number(event.target.value) })} /></label> : null}
          {draft.frequency === "WEEKLY" || draft.frequency === "FORTNIGHTLY" ? <label><span>Weekday</span><select value={draft.run_day} disabled={schedulingDisabled} onChange={(event) => setDraft({ ...draft, run_day: Number(event.target.value) })}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day, index) => <option key={day} value={index + 1}>{day}</option>)}</select></label> : null}
          <label><span>Run hour</span><input type="number" min="0" max="23" value={draft.run_hour_local} disabled={schedulingDisabled} onChange={(event) => setDraft({ ...draft, run_hour_local: Number(event.target.value) })} /></label>
          <label><span>Timezone</span><input value={draft.timezone_name} disabled={!canManage} onChange={(event) => setDraft({ ...draft, timezone_name: event.target.value })} /></label>
          <label><span>Period code</span><input value={draft.period_code_pattern} disabled={!canManage} onChange={(event) => setDraft({ ...draft, period_code_pattern: event.target.value })} /></label>
          <label className="rs-form-grid__wide"><span>Period name</span><input value={draft.period_name_pattern} disabled={!canManage} onChange={(event) => setDraft({ ...draft, period_name_pattern: event.target.value })} /></label>
        </div>
        <div className="rs-check-grid">
          <label><input type="checkbox" checked={draft.create_initial_draft} disabled={!canManage} onChange={(event) => setDraft({ ...draft, create_initial_draft: event.target.checked })} /> Create initial draft</label>
          <label><input type="checkbox" checked={draft.require_preview_confirmation} disabled={!canManage} onChange={(event) => setDraft({ ...draft, require_preview_confirmation: event.target.checked })} /> Require preview confirmation</label>
        </div>
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Automatic rotation</span><h2>Generate duties from work patterns</h2><p>Use effective HR pattern assignments while preserving leave, training and Quality commitments.</p></div><label className="rs-toggle"><input type="checkbox" checked={draft.generate_from_patterns} disabled={!canManage} onChange={(event) => setDraft({ ...draft, generate_from_patterns: event.target.checked })} /><span>{draft.generate_from_patterns ? "On" : "Off"}</span></label></div>
        <div className="rs-check-grid">
          <label><input type="checkbox" checked={draft.validate_after_generation} disabled={!canManage} onChange={(event) => setDraft({ ...draft, validate_after_generation: event.target.checked })} /> Validate after generation</label>
        </div>
        <div className="rs-safety-note"><ShieldCheck size={18} /><p><strong>Enforced protection:</strong> source commitments are always preserved during generation.</p></div>
        <div className="rs-safety-note"><ShieldCheck size={18} /><p><strong>Controlled boundary:</strong> automatic generation can create draft duty only. Submission, approval and publication remain separate authorised actions.</p></div>
      </section>

      {canManage ? (
        <section className="wr-panel rs-save-bar">
          <label><span>Reason for change</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain why the automation policy is changing" /></label>
          <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || reason.trim().length < 5} onClick={() => void save()}><Save size={15} /> Save automation policy</button>
          <span>Next run: {formatDate(policy.next_run_at)}</span>
        </section>
      ) : <div className="rs-readonly">You can review this policy but do not have permission to change roster automation.</div>}
    </div>
  );
}

function CoverageDemandPanel({
  demands,
  loading,
  error,
  people,
  bases,
  timezoneName,
  canManage,
  busy,
  runAction,
}: {
  demands: Awaited<ReturnType<typeof listRosterDemandRequirements>>;
  loading: boolean;
  error: unknown;
  people: Awaited<ReturnType<typeof listAllRosterPeople>>["items"];
  bases: Array<{ id: string; code: string }>;
  timezoneName: string;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const now = new Date();
  const dateValue = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const empty = {
    requirement_code: "",
    label: "",
    work_date: dateValue,
    start_time: "08:00",
    end_time: "17:00",
    required_headcount: 1,
    required_minutes: 0,
    base_station_id: "",
    department_id: "",
    role_label: "",
  };
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(empty);
  const [retiringId, setRetiringId] = useState<string | null>(null);
  const [retireReason, setRetireReason] = useState("");
  const departments = useMemo(() => {
    const rows = new Map<string, string>();
    people.forEach((person) => {
      if (person.department_id) rows.set(person.department_id, `${person.department_code || "DEPT"} · ${person.department_name || "Department"}`);
    });
    return [...rows].map(([id, label]) => ({ id, label })).sort((left, right) => left.label.localeCompare(right.label));
  }, [people]);
  const active = demands.filter((row) => row.is_active).sort((left, right) => left.starts_at.localeCompare(right.starts_at));
  const archived = demands.filter((row) => !row.is_active);
  const toIso = (workDate: string, wallTime: string) => zonedWallTimeToIso(new Date(`${workDate}T12:00:00`), wallTime, timezoneName);
  const save = () => runAction("coverage-demand", async () => {
    await createRosterDemandRequirement({
      requirement_code: draft.requirement_code.trim().toUpperCase(),
      label: draft.label.trim(),
      starts_at: toIso(draft.work_date, draft.start_time),
      ends_at: toIso(draft.work_date, draft.end_time),
      required_headcount: draft.required_headcount,
      required_minutes: draft.required_minutes,
      base_station_id: draft.base_station_id || null,
      department_id: draft.department_id || null,
      role_label: draft.role_label.trim() || null,
      authorisation_type_id: null,
      source_type: "MANUAL",
      source_id: null,
      metadata_json: { timezone_name: timezoneName },
      is_active: true,
    });
    setDraft(empty);
    setCreating(false);
  });
  const retire = () => {
    if (!retiringId) return;
    void runAction("coverage-retire", async () => {
      await retireRosterDemandRequirement(retiringId, retireReason.trim());
      setRetiringId(null);
      setRetireReason("");
    });
  };

  return (
    <div className="rs-setup__stack">
      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Coverage inputs</span><h2>Required staffing windows</h2><p>Define the headcount or labour minutes that validation must protect. These records drive coverage-gap findings and recommendations.</p></div>
          {canManage ? <button type="button" className="wr-button wr-button--primary" onClick={() => setCreating(true)}><Plus size={16} /> New requirement</button> : null}
        </div>
        {error ? <div className="wr-inline-error" role="alert">{errorMessage(error)}</div> : null}
        {loading ? <RosterLoading label="Loading coverage requirements…" /> : null}
        <div className="rs-demand-list">
          {active.map((row) => (
            <article key={row.id}>
              <div><strong>{row.requirement_code} · {row.label}</strong><span>{formatDate(row.starts_at)} → {formatDate(row.ends_at)}</span><small>{row.role_label || "Any eligible role"} · {row.required_headcount || 0} people · {row.required_minutes || 0} minutes</small></div>
              <StatusPill value="ACTIVE" />
              <span>{bases.find((base) => base.id === row.base_station_id)?.code || "All bases"}</span>
              {canManage ? <button type="button" className="wr-button wr-button--danger-ghost" onClick={() => { setRetiringId(row.id); setRetireReason(""); }}><Trash2 size={14} /> Retire</button> : null}
            </article>
          ))}
        </div>
        {!loading && !active.length ? <EmptyState title="No coverage requirements" description="Add required staffing windows so roster validation can identify genuine gaps." /> : null}
        {archived.length ? <details className="rs-archived"><summary>{archived.length} retired requirement{archived.length === 1 ? "" : "s"}</summary>{archived.map((row) => <div key={row.id}><span>{row.requirement_code} · {row.label}</span><StatusPill value="RETIRED" /></div>)}</details> : null}
        {!canManage ? <div className="rs-readonly">Coverage demand is readable. Roster work-allocation permission is required to create or retire records.</div> : null}
      </section>

      {creating ? (
        <div className="rs-drawer" role="dialog" aria-modal="true" aria-label="Create coverage requirement">
          <div className="rs-drawer__head"><div><span className="wr-eyebrow">Structured demand</span><h3>New staffing requirement</h3><p>Times are interpreted in {timezoneName}.</p></div><button type="button" className="wr-icon-button" onClick={() => setCreating(false)}><X size={16} /></button></div>
          <div className="rs-form-grid">
            <label><span>Requirement code</span><input value={draft.requirement_code} onChange={(event) => setDraft({ ...draft, requirement_code: event.target.value })} placeholder="LINE-AM" /></label>
            <label><span>Name</span><input value={draft.label} onChange={(event) => setDraft({ ...draft, label: event.target.value })} placeholder="Morning line coverage" /></label>
            <label><span>Work date</span><input type="date" value={draft.work_date} onChange={(event) => setDraft({ ...draft, work_date: event.target.value })} /></label>
            <label><span>Starts</span><input type="time" value={draft.start_time} onChange={(event) => setDraft({ ...draft, start_time: event.target.value })} /></label>
            <label><span>Ends</span><input type="time" value={draft.end_time} onChange={(event) => setDraft({ ...draft, end_time: event.target.value })} /></label>
            <label><span>Required people</span><input type="number" min="0" value={draft.required_headcount} onChange={(event) => setDraft({ ...draft, required_headcount: Math.max(0, Number(event.target.value)) })} /></label>
            <label><span>Required labour minutes</span><input type="number" min="0" value={draft.required_minutes} onChange={(event) => setDraft({ ...draft, required_minutes: Math.max(0, Number(event.target.value)) })} /></label>
            <label><span>Base</span><select value={draft.base_station_id} onChange={(event) => setDraft({ ...draft, base_station_id: event.target.value })}><option value="">All bases</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code}</option>)}</select></label>
            <label><span>Department</span><select value={draft.department_id} onChange={(event) => setDraft({ ...draft, department_id: event.target.value })}><option value="">All departments</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.label}</option>)}</select></label>
            <label className="rs-form-grid__wide"><span>Required role</span><input value={draft.role_label} onChange={(event) => setDraft({ ...draft, role_label: event.target.value })} placeholder="Optional, for example Certifying Engineer" /></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setCreating(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !draft.requirement_code.trim() || !draft.label.trim() || (!draft.required_headcount && !draft.required_minutes) || draft.end_time <= draft.start_time} onClick={() => void save()}><Save size={15} /> Save requirement</button></div>
        </div>
      ) : null}

      {retiringId ? (
        <div className="rs-preview" role="dialog" aria-modal="true" aria-label="Retire coverage requirement">
          <div className="rs-preview__head"><div><span className="wr-eyebrow">Audited removal</span><h3>Retire coverage requirement</h3></div><button type="button" className="wr-icon-button" onClick={() => setRetiringId(null)}><X size={16} /></button></div>
          <p>Retiring preserves history but removes this requirement from future validation.</p>
          <label className="rs-retire-reason"><span>Reason</span><textarea rows={3} value={retireReason} onChange={(event) => setRetireReason(event.target.value)} placeholder="Explain why this staffing requirement no longer applies" /></label>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setRetiringId(null)}>Cancel</button><button type="button" className="wr-button wr-button--danger" disabled={Boolean(busy) || retireReason.trim().length < 5} onClick={retire}><Trash2 size={15} /> Retire</button></div>
        </div>
      ) : null}

    </div>
  );
}

function PolicyPanel({
  rules,
  loading,
  authorityCount,
  canManageRules,
  canManageAuthorities,
  people,
  periods,
  bases,
  governanceLoading,
  governanceError,
}: {
  rules: Awaited<ReturnType<typeof listRosterRules>>;
  loading: boolean;
  authorityCount: number;
  canManageRules: boolean;
  canManageAuthorities: boolean;
  people: Awaited<ReturnType<typeof listAllRosterPeople>>["items"];
  periods: Awaited<ReturnType<typeof listRosterPeriods>>;
  bases: Array<{ id: string; code: string }>;
  governanceLoading: boolean;
  governanceError: unknown;
}) {
  const groups = useMemo(() => ({
    statutory: rules.filter((rule) => /KCAR|STATUT/i.test(`${rule.name} ${rule.description || ""}`)),
    mandatory: rules.filter((rule) => rule.severity === "BLOCKER" && !/KCAR|STATUT/i.test(`${rule.name} ${rule.description || ""}`)),
    warning: rules.filter((rule) => rule.severity === "WARNING"),
    advisory: rules.filter((rule) => rule.severity === "INFO"),
  }), [rules]);
  return (
    <div className="rs-setup__stack">
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Controlled policy</span><h2>Compliance rules</h2><p>Rules are grouped by operational effect. A value must not be presented as a statutory KCAR limit without a controlled source and clause.</p></div><span className="wr-header-badge"><ShieldCheck size={15} /> {rules.filter((rule) => rule.is_active).length} active</span></div>
        {loading ? <RosterLoading label="Loading controlled policy…" /> : null}
        {Object.entries(groups).map(([group, rows]) => (
          <div className="rs-policy-group" key={group}>
            <h3>{group === "statutory" ? "Statutory hard stops" : group === "mandatory" ? "Approved company hard stops" : group === "warning" ? "Operational warnings" : "Advisories"}</h3>
            {!rows.length ? <p className="rs-muted">No rules in this classification.</p> : rows.map((rule) => (
              <article key={rule.id} className={!rule.is_active ? "is-inactive" : ""}>
                <div><strong>{rule.name}</strong><span>{rule.code} · {rule.rule_type.replace(/_/g, " ")}</span></div>
                <StatusPill value={rule.severity} />
                <span>{rule.allow_override ? "Controlled override allowed" : "No override"}</span>
                <span>{rule.rule_set_id ? "Controlled rule set" : "Source review required"}</span>
              </article>
            ))}
          </div>
        ))}
        {!canManageRules ? <div className="rs-readonly">Rules are visible for review. Only authorised policy controllers can change them.</div> : null}
      </section>
      {canManageRules ? (
      <Suspense fallback={<RosterLoading label="Loading rule controls…" />}>
        <RosterRuleQuickEditor />
      </Suspense>
    ) : null}
      <section className="wr-panel rs-approval-summary"><div><CheckCircle2 size={20} /><span><strong>{authorityCount}</strong> active approval authority record{authorityCount === 1 ? "" : "s"}</span></div><p>Approval authorities define review and publishing scopes. Configure them here; submitted roster decisions remain in Command.</p></section>
      {governanceError ? <div className="wr-inline-error" role="alert">{errorMessage(governanceError)}</div> : null}
      {governanceLoading ? <RosterLoading label="Loading approval authorities…" /> : (
        <Suspense fallback={<RosterLoading label="Loading approval authority controls…" />}>
          <RosterGovernancePanel
            people={people}
            periods={periods}
            bases={bases}
            canManageRules={canManageRules}
            canManageAuthorities={canManageAuthorities}
            showApprovalWorkflow={false}
          />
        </Suspense>
      )}
    </div>
  );
}

function AdvancedWorkspace({ policy, permissions, busy, runAction, runs, loading, onRefresh }: {
  policy: RosterGenerationPolicy;
  permissions: string[];
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  runs: Awaited<ReturnType<typeof listRosterAutomationRuns>>;
  loading: boolean;
  onRefresh: () => void;
}) {
  const access = [
    ["Read", ["roster.view_own", "roster.view_department", "roster.view_all"]],
    ["Edit", ["roster.create", "roster.edit"]],
    ["Delete draft duty", ["roster.delete_draft_assignment"]],
    ["Configure", ["roster.manage_shift_templates", "roster.manage_patterns", "roster.manage_rules"]],
    ["Approve / publish", ["roster.approve", "roster.publish"]],
  ] as const;
  return (
    <div className="rs-setup__stack">
      <details className="wr-panel rs-progressive">
        <summary><span><CalendarClock size={17} /><strong>Automatic period creation</strong><small>Scheduling and unattended draft-generation policy</small></span><StatusPill value={policy.enabled ? "ON" : "OFF"} /></summary>
        <div className="rs-progressive__body"><AutomationPanel policy={policy} canManage={permissions.includes("roster.manage_patterns")} busy={busy} runAction={runAction} /></div>
      </details>
      <details className="wr-panel rs-progressive">
        <summary><span><History size={17} /><strong>Automation history</strong><small>Generation results, conflicts and failures</small></span><StatusPill value={`${runs.length} RUNS`} /></summary>
        <div className="rs-progressive__body"><AdvancedPanel runs={runs} loading={loading} onRefresh={onRefresh} /></div>
      </details>
      <details className="wr-panel rs-progressive">
        <summary><span><ShieldCheck size={17} /><strong>Document and code controls</strong><small>Controlled output metadata and legacy roster-code verification</small></span></summary>
        <div className="rs-progressive__body"><Suspense fallback={<RosterLoading label="Opening controlled settings…" />}><ControlledRosterSettingsPanel /><RosterCodeRegistryPanel /></Suspense></div>
      </details>
      <details className="wr-panel rs-progressive">
        <summary><span><Settings2 size={17} /><strong>My effective permissions</strong><small>Why a control is editable or read-only</small></span></summary>
        <div className="rs-progressive__body"><div className="rs-access-compact">{access.map(([label, codes]) => { const allowed = codes.some((code) => permissions.includes(code)); return <span key={label} className={allowed ? "is-allowed" : "is-restricted"}>{allowed ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{label}</span>; })}</div></div>
      </details>
    </div>
  );
}

function AdvancedPanel({ runs, loading, onRefresh }: { runs: Awaited<ReturnType<typeof listRosterAutomationRuns>>; loading: boolean; onRefresh: () => void }) {
  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Execution evidence</span><h2>Automation history</h2><p>Every automatic generation attempt is retained, including failures and conflicts.</p></div><button type="button" className="wr-icon-button" onClick={onRefresh}><RefreshCw size={16} /></button></div>
      {loading ? <RosterLoading label="Loading automation history…" /> : null}
      <div className="rs-run-list">{runs.map((run) => <article key={run.id}><div><History size={17} /><span><strong>{run.target_from} → {run.target_to}</strong><small>{formatDate(run.started_at)}</small></span></div><StatusPill value={run.status} /><span>{run.generated_count} generated</span><span>{run.conflict_count} conflicts</span><span>{run.validation_blocker_count} blockers</span>{run.error_message ? <p>{run.error_message}</p> : null}</article>)}</div>
      {!loading && !runs.length ? <EmptyState title="No automation runs" description="Preview and run the next controlled draft from Planning calendar." /> : null}
      <div className="rs-safety-note"><Sparkles size={18} /><p>Integration diagnostics are kept here for administrators. Normal planners see readiness and direct actions rather than API contract details.</p></div>
    </section>
  );
}
