import "./rostering-setup-workspace.css";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  History,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";

import {
  createShiftTemplate,
  listRosterPeriods,
  listRosterRules,
  listShiftTemplates,
  updateShiftTemplate,
} from "../../../services/rostering";
import {
  getRosterSetupReadiness,
  listRosterAutomationRuns,
  previewRosterAutomation,
  runRosterAutomation,
  updateRosterAutomationPolicy,
} from "../../../services/rosteringAutomation";
import {
  createWorkPattern,
  getCurrentWorkforcePermissions,
  listWorkPatternAssignments,
  listWorkPatterns,
} from "../../../services/workforce";
import type { ShiftTemplateKind, ShiftTemplateRead } from "../../../types/rostering";
import type {
  RosterAutomationPreview,
  RosterAutomationFrequency,
  RosterGenerationPolicy,
} from "../../../types/rosteringAutomation";
import type { PatternDayStatus, WorkPatternDayInput } from "../../../types/workforce";
import { errorMessage, newIdempotencyKey } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

type Section = "overview" | "calendar" | "automation" | "shifts" | "patterns" | "policy" | "advanced";

const SECTIONS: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "Setup overview" },
  { id: "calendar", label: "Planning calendar" },
  { id: "automation", label: "Automation" },
  { id: "shifts", label: "Shift library" },
  { id: "patterns", label: "Work patterns" },
  { id: "policy", label: "Compliance & approval" },
  { id: "advanced", label: "History & diagnostics" },
];

const SHIFT_KINDS: ShiftTemplateKind[] = ["DAY", "NIGHT", "STANDBY", "TRAINING", "OFF", "LEAVE", "OTHER"];

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
  const initial = new URLSearchParams(window.location.search).get("section") as Section | null;
  const [section, setSection] = useState<Section>(SECTIONS.some((item) => item.id === initial) ? initial! : "overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const readinessQuery = useQuery({
    queryKey: ["rostering", "setup", "readiness"],
    queryFn: getRosterSetupReadiness,
    staleTime: 60_000,
  });
  const permissionsQuery = useQuery({
    queryKey: ["rostering", "settings", "permissions"],
    queryFn: getCurrentWorkforcePermissions,
    staleTime: 15 * 60_000,
  });
  const periodsQuery = useQuery({
    queryKey: ["rostering", "settings", "periods"],
    queryFn: () => listRosterPeriods(),
    enabled: section === "calendar",
    staleTime: 60_000,
  });
  const shiftsQuery = useQuery({
    queryKey: ["rostering", "settings", "shifts"],
    queryFn: () => listShiftTemplates(true),
    enabled: section === "shifts" || section === "patterns",
    staleTime: 15 * 60_000,
  });
  const patternsQuery = useQuery({
    queryKey: ["rostering", "settings", "patterns"],
    queryFn: () => listWorkPatterns(true),
    enabled: section === "patterns",
    staleTime: 5 * 60_000,
  });
  const patternAssignmentsQuery = useQuery({
    queryKey: ["rostering", "settings", "pattern-assignments"],
    queryFn: () => listWorkPatternAssignments(),
    enabled: section === "patterns",
    staleTime: 60_000,
  });
  const rulesQuery = useQuery({
    queryKey: ["rostering", "settings", "rules"],
    queryFn: () => listRosterRules(true),
    enabled: section === "policy",
    staleTime: 15 * 60_000,
  });
  const runsQuery = useQuery({
    queryKey: ["rostering", "automation", "runs"],
    queryFn: () => listRosterAutomationRuns(40),
    enabled: section === "advanced",
    staleTime: 30_000,
  });

  const permissions = permissionsQuery.data?.permissions || [];
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

      {section === "overview" ? (
        <SetupOverview readiness={readiness} root={root} onOpen={navigateSection} onRefresh={refresh} />
      ) : null}
      {section === "calendar" ? (
        <PlanningCalendar
          periods={periodsQuery.data || []}
          loading={periodsQuery.isPending}
          error={periodsQuery.error}
          previewEnabled={canGenerate}
          busy={busy}
          runAction={runAction}
          onOpenAutomation={() => navigateSection("automation")}
        />
      ) : null}
      {section === "automation" ? (
        <AutomationPanel
          policy={readiness.policy}
          canManage={can("roster.manage_patterns")}
          busy={busy}
          runAction={runAction}
        />
      ) : null}
      {section === "shifts" ? (
        <ShiftLibrary
          shifts={shiftsQuery.data || []}
          loading={shiftsQuery.isPending}
          error={shiftsQuery.error}
          canManage={can("roster.manage_shift_templates")}
          busy={busy}
          runAction={runAction}
        />
      ) : null}
      {section === "patterns" ? (
        <PatternBuilder
          shifts={shiftsQuery.data || []}
          patterns={patternsQuery.data || []}
          assignments={patternAssignmentsQuery.data || []}
          loading={shiftsQuery.isPending || patternsQuery.isPending || patternAssignmentsQuery.isPending}
          canManage={can("roster.manage_patterns")}
          busy={busy}
          runAction={runAction}
          workforcePath={`${root}/workforce`}
          timezoneName={readiness.policy.timezone_name}
        />
      ) : null}
      {section === "policy" ? (
        <PolicyPanel
          rules={rulesQuery.data || []}
          loading={rulesQuery.isPending}
          authorityCount={readiness.active_approval_authority_count}
          canManageRules={can("roster.manage_rules")}
          root={root}
        />
      ) : null}
      {section === "advanced" ? (
        <AdvancedPanel runs={runsQuery.data || []} loading={runsQuery.isPending} onRefresh={() => void runsQuery.refetch()} />
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
  return (
    <div className="rs-setup__stack">
      <section className="wr-panel rs-readiness">
        <div className="wr-section-heading">
          <div>
            <span className="wr-eyebrow">Setup readiness</span>
            <h2>{readiness.can_plan ? "Ready to plan" : "Action required before planning"}</h2>
          </div>
          <button type="button" className="wr-icon-button" onClick={() => void onRefresh()} aria-label="Refresh setup readiness">
            <RefreshCw size={17} />
          </button>
        </div>
        <div className="rs-readiness__summary">
          <div className="rs-readiness__score"><strong>{readiness.ready_count}</strong><span>of {readiness.total_count} ready</span></div>
          <div className="rs-readiness__bar" aria-label={`${percent}% setup ready`}><span style={{ width: `${percent}%` }} /></div>
          <p>
            {readiness.can_plan
              ? "The planner can be used now. Resolve warnings before relying on automatic generation."
              : "Complete the blocked items below. Rostering will not invent HR, base or policy records."}
          </p>
        </div>
      </section>

      <section className="rs-setup-card-grid">
        {readiness.items.map((item) => {
          const target = (item.action_path || "overview") as Section;
          return (
            <article key={item.key} className={`rs-setup-card is-${stateTone(item.state)}`}>
              <div className="rs-setup-card__head">
                <span className="rs-setup-card__icon">
                  {item.state === "READY" ? <CheckCircle2 size={19} /> : item.state === "BLOCKED" ? <AlertTriangle size={19} /> : <Settings2 size={19} />}
                </span>
                <StatusPill value={item.state} />
              </div>
              <h3>{item.label}</h3>
              <p>{item.detail}</p>
              <button type="button" className="wr-text-link" onClick={() => onOpen(SECTIONS.some((entry) => entry.id === target) ? target : "overview")}>
                {item.action_label || "Open"} <ArrowRight size={14} />
              </button>
            </article>
          );
        })}
      </section>

      <section className="wr-panel rs-boundaries">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Clear ownership</span><h2>Where records are managed</h2></div></div>
        <div className="rs-boundaries__grid">
          <article><UsersRound size={19} /><div><strong>Workforce & HR</strong><p>Contracts, leave, time approval, payroll readiness and employee pattern assignments.</p></div><Link to={`${root}/workforce`}>Open Workforce <ArrowRight size={14} /></Link></article>
          <article><CalendarClock size={19} /><div><strong>Rostering</strong><p>Planning periods, shift templates, draft rotations, compliance validation and controlled publication.</p></div><Link to={`${root}/calendar`}>Open Planner <ArrowRight size={14} /></Link></article>
          <article><ShieldCheck size={19} /><div><strong>Operating Structure</strong><p>Canonical bases and effective-dated personnel deployments remain tenant-wide records.</p></div><Link to={`/maintenance/${encodeURIComponent(root.split("/")[2] || "")}/admin/amo-assets?section=operating-structure`}>Open structure <ArrowRight size={14} /></Link></article>
        </div>
      </section>
    </div>
  );
}

function PlanningCalendar({
  periods,
  loading,
  error,
  previewEnabled,
  busy,
  runAction,
  onOpenAutomation,
}: {
  periods: Awaited<ReturnType<typeof listRosterPeriods>>;
  loading: boolean;
  error: unknown;
  previewEnabled: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  onOpenAutomation: () => void;
}) {
  const [preview, setPreview] = useState<RosterAutomationPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const recent = useMemo(() => [...periods].sort((a, b) => b.starts_on.localeCompare(a.starts_on)).slice(0, 12), [periods]);

  const openPreview = async () => {
    setPreviewError(null);
    try {
      setPreview(await previewRosterAutomation({ create_missing_period: true }));
    } catch (cause) {
      setPreviewError(errorMessage(cause));
    }
  };

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div><span className="wr-eyebrow">Planning calendar</span><h2>Roster periods</h2><p>One list, one next action. Period lifecycle changes are kept separate from ordinary date details.</p></div>
        <div className="wr-actions">
          <button type="button" className="wr-button wr-button--secondary" onClick={onOpenAutomation}><CalendarClock size={16} /> Calendar policy</button>
          {previewEnabled ? <button type="button" className="wr-button wr-button--primary" onClick={() => void openPreview()}><CalendarPlus size={16} /> Prepare next period</button> : null}
        </div>
      </div>
      {error ? <div className="wr-inline-error">{errorMessage(error)}</div> : null}
      {previewError ? <div className="wr-inline-error">{previewError}</div> : null}
      {loading ? <RosterLoading label="Loading planning calendar…" /> : null}
      {!loading && recent.length === 0 ? <EmptyState title="No roster periods" description="Prepare the next controlled period after configuring the calendar policy." /> : null}
      <div className="rs-period-list">
        {recent.map((period) => {
          const latest = [...period.versions].sort((a, b) => b.version_no - a.version_no)[0];
          return (
            <article key={period.id}>
              <div><strong>{period.period_code} · {period.name}</strong><span>{period.starts_on} → {period.ends_on} · {period.timezone_name}</span></div>
              <StatusPill value={period.status} />
              <span>{period.versions.length} version{period.versions.length === 1 ? "" : "s"}</span>
              <span>{latest ? `Latest: v${latest.version_no} ${latest.status}` : "No draft yet"}</span>
            </article>
          );
        })}
      </div>

      {preview ? (
        <div className="rs-preview" role="dialog" aria-modal="true" aria-label="Automatic period preview">
          <div className="rs-preview__head"><div><span className="wr-eyebrow">Preview</span><h3>{preview.period_code} · {preview.period_name}</h3></div><button type="button" className="wr-icon-button" onClick={() => setPreview(null)}><X size={16} /></button></div>
          <div className="rs-preview__facts">
            <span><strong>{preview.target_from}</strong> starts</span>
            <span><strong>{preview.target_to}</strong> ends</span>
            <span><strong>{preview.eligible_employee_count}</strong> eligible people</span>
            <span><strong>{preview.estimated_assignment_count}</strong> estimated duties</span>
          </div>
          {preview.items.map((item) => <div key={item.code} className={`rs-preview__issue is-${item.severity.toLowerCase()}`}><strong>{item.code.replace(/_/g, " ")}</strong><span>{item.message}</span></div>)}
          <div className="wr-actions wr-actions--end">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => setPreview(null)}>Cancel</button>
            <button
              type="button"
              className="wr-button wr-button--primary"
              disabled={Boolean(busy) || preview.blocking_issue_count > 0}
              onClick={() => void runAction("automation-run", async () => {
                await runRosterAutomation({
                  target_from: preview.target_from,
                  target_to: preview.target_to,
                  create_missing_period: true,
                  create_initial_draft: true,
                  generate_from_patterns: true,
                  confirm_preview: true,
                  idempotency_key: newIdempotencyKey("roster-automation"),
                });
                setPreview(null);
              })}
            ><Play size={15} /> Create draft and rotation</button>
          </div>
          <small>Automation creates a draft only. It never approves or publishes a roster.</small>
        </div>
      ) : null}
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

function ShiftLibrary({
  shifts,
  loading,
  error,
  canManage,
  busy,
  runAction,
}: {
  shifts: ShiftTemplateRead[];
  loading: boolean;
  error: unknown;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const empty = { code: "", label: "", kind: "DAY" as ShiftTemplateKind, start: "08:00", end: "17:00", description: "" };
  const [editing, setEditing] = useState<ShiftTemplateRead | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(empty);

  const beginEdit = (shift: ShiftTemplateRead) => {
    setEditing(shift);
    setCreating(false);
    setDraft({ code: shift.code, label: shift.label, kind: shift.kind, start: shift.default_start_time || "08:00", end: shift.default_end_time || "17:00", description: shift.description || "" });
  };
  const beginCreate = () => { setEditing(null); setCreating(true); setDraft(empty); };
  const close = () => { setEditing(null); setCreating(false); };
  const save = () => runAction("shift", async () => {
    const nonDuty = ["OFF", "LEAVE"].includes(draft.kind);
    const payload = {
      code: draft.code.trim().toUpperCase(),
      label: draft.label.trim(),
      kind: draft.kind,
      default_start_time: nonDuty ? null : draft.start,
      default_end_time: nonDuty ? null : draft.end,
      duration_minutes: null,
      counts_as_duty: !nonDuty,
      is_active: editing?.is_active ?? true,
      display_order: editing?.display_order ?? (shifts.length + 1) * 10,
      description: draft.description.trim() || null,
      color_token: editing?.color_token || `shift-${draft.kind.toLowerCase()}`,
      icon_name: editing?.icon_name || null,
    };
    if (editing) await updateShiftTemplate(editing.id, payload);
    else await createShiftTemplate(payload);
    close();
  });

  return (
    <section className="wr-panel">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Reusable building blocks</span><h2>Shift library</h2><p>Create, review, clone and retire shifts without exposing a permanent creation form.</p></div>{canManage ? <button type="button" className="wr-button wr-button--primary" onClick={beginCreate}><Plus size={16} /> New shift</button> : null}</div>
      {error ? <div className="wr-inline-error">{errorMessage(error)}</div> : null}
      {loading ? <RosterLoading label="Loading shift library…" /> : null}
      <div className="rs-shift-table">
        {shifts.map((shift) => (
          <article key={shift.id} className={!shift.is_active ? "is-inactive" : ""}>
            <div><strong>{shift.code}</strong><StatusPill value={shift.kind} /></div>
            <div><strong>{shift.label}</strong><span>{shift.default_start_time || "—"} → {shift.default_end_time || "—"}</span></div>
            <span>{shift.counts_as_duty ? "Counts as duty" : "Protected non-duty"}</span>
            <StatusPill value={shift.is_active ? "ACTIVE" : "INACTIVE"} />
            {canManage ? <div className="wr-actions"><button type="button" className="wr-button wr-button--small" onClick={() => beginEdit(shift)}>Open</button><button type="button" className="wr-button wr-button--small" onClick={() => { setEditing(null); setCreating(true); setDraft({ code: `${shift.code}-COPY`, label: `${shift.label} copy`, kind: shift.kind, start: shift.default_start_time || "08:00", end: shift.default_end_time || "17:00", description: shift.description || "" }); }}><Layers3 size={14} /> Clone</button></div> : null}
          </article>
        ))}
      </div>
      {!loading && !shifts.length ? <EmptyState title="No shifts" description="Create the first shift template before building work patterns." /> : null}

      {creating || editing ? (
        <div className="rs-drawer" role="dialog" aria-modal="true" aria-label={editing ? `Edit ${editing.label}` : "Create shift"}>
          <div className="rs-drawer__head"><div><span className="wr-eyebrow">Shift details</span><h3>{editing ? editing.label : "New shift"}</h3></div><button type="button" className="wr-icon-button" onClick={close}><X size={16} /></button></div>
          <div className="rs-form-grid">
            <label><span>Code</span><input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} /></label>
            <label><span>Name</span><input value={draft.label} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
            <label><span>Type</span><select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as ShiftTemplateKind })}>{SHIFT_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            <label><span>Starts</span><input type="time" value={draft.start} disabled={["OFF", "LEAVE"].includes(draft.kind)} onChange={(event) => setDraft({ ...draft, start: event.target.value })} /></label>
            <label><span>Ends</span><input type="time" value={draft.end} disabled={["OFF", "LEAVE"].includes(draft.kind)} onChange={(event) => setDraft({ ...draft, end: event.target.value })} /></label>
            <label className="rs-form-grid__wide"><span>Description</span><input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          </div>
          {editing ? <label className="rs-toggle-row"><input type="checkbox" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} /><span>Active</span></label> : null}
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={close}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !draft.code.trim() || !draft.label.trim()} onClick={() => void save()}><Save size={15} /> Save shift</button></div>
        </div>
      ) : null}
    </section>
  );
}

function PatternBuilder({
  shifts,
  patterns,
  assignments,
  loading,
  canManage,
  busy,
  runAction,
  workforcePath,
  timezoneName,
}: {
  shifts: ShiftTemplateRead[];
  patterns: Awaited<ReturnType<typeof listWorkPatterns>>;
  assignments: Awaited<ReturnType<typeof listWorkPatternAssignments>>;
  loading: boolean;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  workforcePath: string;
  timezoneName: string;
}) {
  const activeShifts = shifts.filter((shift) => shift.is_active);
  const [building, setBuilding] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [cycleLength, setCycleLength] = useState(7);
  const [dayShifts, setDayShifts] = useState<Array<string | null>>(Array.from({ length: 7 }, () => null));
  const resize = (length: number) => {
    const next = [...dayShifts];
    while (next.length < length) next.push(null);
    setDayShifts(next.slice(0, length));
    setCycleLength(length);
  };
  const days: WorkPatternDayInput[] = dayShifts.map((shiftId, index) => {
    const shift = activeShifts.find((item) => item.id === shiftId);
    const status: PatternDayStatus = !shift ? "OFF" : shift.kind === "STANDBY" ? "STANDBY" : shift.kind === "TRAINING" ? "TRAINING" : shift.kind === "OFF" ? "OFF" : "DUTY";
    const spans = Boolean(shift?.default_start_time && shift?.default_end_time && shift.default_end_time <= shift.default_start_time);
    return { cycle_day_index: index, shift_template_id: shift?.id || null, status, start_time_local: shift?.default_start_time || null, end_time_local: shift?.default_end_time || null, spans_next_day: spans, planned_minutes: shift?.duration_minutes || 0 };
  });
  const save = () => runAction("pattern", async () => {
    await createWorkPattern({ code: code.trim().toUpperCase(), name: name.trim(), description: null, cycle_length_days: cycleLength, is_active: true, timezone_name: timezoneName, days });
    setBuilding(false); setCode(""); setName(""); resize(7);
  });

  return (
    <div className="rs-setup__stack">
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Rotation builder</span><h2>Visual work patterns</h2><p>Build real mixed cycles such as day, day, night, night, off, off—rather than reducing every rotation to one shift.</p></div>{canManage ? <button type="button" className="wr-button wr-button--primary" onClick={() => setBuilding(true)}><Plus size={16} /> New pattern</button> : null}</div>
        {loading ? <RosterLoading label="Loading work patterns…" /> : null}
        <div className="rs-pattern-grid">
          {patterns.map((pattern) => (
            <article key={pattern.id}>
              <div><strong>{pattern.code} · {pattern.name}</strong><StatusPill value={pattern.is_active ? "ACTIVE" : "INACTIVE"} /></div>
              <p>{pattern.cycle_length_days}-day cycle · {pattern.assigned_employee_count} assigned</p>
              <div className="rs-cycle-strip">{pattern.days.map((day) => <span key={day.id} className={`is-${day.status.toLowerCase()}`} title={`Day ${day.cycle_day_index + 1}: ${day.shift_code || day.status}`}>{day.shift_code || day.status.slice(0, 3)}</span>)}</div>
            </article>
          ))}
        </div>
        {!loading && !patterns.length ? <EmptyState title="No work patterns" description="Create a visual rotation, then assign it to employees from Workforce & HR." /> : null}
      </section>

      <section className="wr-panel rs-pattern-assignment-summary">
        <div><UsersRound size={20} /><span><strong>{assignments.length}</strong> effective pattern assignment record{assignments.length === 1 ? "" : "s"}</span></div>
        <p>Employee assignment, contract dates and supervisors are HR-owned records. They are not recreated inside Rostering.</p>
        <Link className="wr-button wr-button--secondary" to={workforcePath}>Open Workforce & HR <ArrowRight size={14} /></Link>
      </section>

      {building ? (
        <div className="rs-drawer rs-drawer--wide" role="dialog" aria-modal="true" aria-label="Build work pattern">
          <div className="rs-drawer__head"><div><span className="wr-eyebrow">Visual pattern builder</span><h3>New work pattern</h3></div><button type="button" className="wr-icon-button" onClick={() => setBuilding(false)}><X size={16} /></button></div>
          <div className="rs-form-grid"><label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value)} /></label><label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>Cycle days</span><input type="number" min="1" max="56" value={cycleLength} onChange={(event) => resize(Math.min(56, Math.max(1, Number(event.target.value))))} /></label></div>
          <div className="rs-cycle-builder">{dayShifts.map((shiftId, index) => <label key={index}><span>Day {index + 1}</span><select value={shiftId || ""} onChange={(event) => { const next = [...dayShifts]; next[index] = event.target.value || null; setDayShifts(next); }}><option value="">OFF</option>{activeShifts.map((shift) => <option key={shift.id} value={shift.id}>{shift.code} · {shift.label}</option>)}</select></label>)}</div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setBuilding(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || !code.trim() || !name.trim()} onClick={() => void save()}><Save size={15} /> Save pattern</button></div>
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
  root,
}: {
  rules: Awaited<ReturnType<typeof listRosterRules>>;
  loading: boolean;
  authorityCount: number;
  canManageRules: boolean;
  root: string;
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
      <section className="wr-panel rs-approval-summary"><div><CheckCircle2 size={20} /><span><strong>{authorityCount}</strong> active approval authority record{authorityCount === 1 ? "" : "s"}</span></div><p>Approval authorities define who may review and approve. Pending approvals belong in Command, not Setup.</p><Link className="wr-button wr-button--secondary" to={`${root}/dashboard`}>Open Command <ArrowRight size={14} /></Link></section>
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
