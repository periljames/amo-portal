// src/pages/rostering/RosteringPages.tsx
import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { buildCanonicalRoute } from "../../app/canonicalRoutes";
import {
  getMyRoster,
  getRosterContracts,
  getRosterPlanningBoard,
  listRosterAssignments,
  listRosterPeriods,
  listShiftTemplates,
  validateRosterVersion,
} from "../../services/rostering";
import type {
  MyRosterResponse,
  RosterAssignmentRead,
  RosterContractResponse,
  RosterPeriodRead,
  RosterPlanningBoardResponse,
  RosterValidationResult,
  RosterVersionRead,
  ShiftTemplateRead,
} from "../../types/rostering";
import "../../styles/rostering.css";

function monthBounds(): { from: string; to: string } {
  const now = new Date();
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0));
  return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
}

function useAmoCode(): string {
  const params = useParams<{ amoCode?: string }>();
  return params.amoCode || "system";
}

function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

function LoadingPanel({ label = "Loading duty roster workspace" }: { label?: string }) {
  return (
    <div className="roster-loading" role="status" aria-live="polite">
      <div className="roster-loading__spinner" />
      <div>{label}</div>
    </div>
  );
}

function ErrorPanel({ message }: { message: string }) {
  return <div className="roster-error" role="alert">{message}</div>;
}

function RosterShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  const amoCode = useAmoCode();
  const nav = [
    ["Dashboard", buildCanonicalRoute.rosteringDashboard({ amoCode })],
    ["Calendar", buildCanonicalRoute.rosteringCalendar({ amoCode })],
    ["Planning Board", buildCanonicalRoute.rosteringPlanningBoard({ amoCode })],
    ["My Roster", buildCanonicalRoute.rosteringMyRoster({ amoCode })],
    ["Training Impact", buildCanonicalRoute.rosteringTrainingImpact({ amoCode })],
    ["Reports", buildCanonicalRoute.rosteringReports({ amoCode })],
    ["Settings", buildCanonicalRoute.rosteringSettings({ amoCode })],
  ] as const;
  return (
    <main className="roster-page">
      <header className="roster-hero">
        <div>
          <p className="roster-eyebrow">Duty Rostering</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <nav className="roster-nav" aria-label="Duty rostering pages">
          {nav.map(([label, href]) => <Link key={href} to={href}>{label}</Link>)}
        </nav>
      </header>
      {children}
    </main>
  );
}

function StatusPill({ value }: { value: string }) {
  return <span className={`roster-pill roster-pill--${value.toLowerCase()}`}>{value}</span>;
}

function AssignmentTable({ assignments }: { assignments: RosterAssignmentRead[] }) {
  if (!assignments.length) return <div className="roster-empty">No assignments found for this view.</div>;
  return (
    <div className="roster-table-wrap">
      <table className="roster-table">
        <thead>
          <tr>
            <th>Person</th>
            <th>Status</th>
            <th>Base</th>
            <th>Shift</th>
            <th>Start</th>
            <th>End</th>
            <th>Hours</th>
          </tr>
        </thead>
        <tbody>
          {assignments.map((item) => (
            <tr key={item.id}>
              <td>{item.user_full_name || item.user_id}</td>
              <td><StatusPill value={item.status} /></td>
              <td>{item.base_code || "—"}</td>
              <td>{item.shift_code || "—"}</td>
              <td>{formatDateTime(item.starts_at)}</td>
              <td>{formatDateTime(item.ends_at)}</td>
              <td>{item.planned_minutes != null ? (item.planned_minutes / 60).toFixed(1) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pickLatestVersion(periods: RosterPeriodRead[]): RosterVersionRead | null {
  const versions = periods.flatMap((period) => period.versions || []);
  return versions.sort((a, b) => (b.published_at || b.updated_at).localeCompare(a.published_at || a.updated_at))[0] || null;
}

export function RosteringDashboardPage() {
  const [periods, setPeriods] = useState<RosterPeriodRead[]>([]);
  const [shifts, setShifts] = useState<ShiftTemplateRead[]>([]);
  const [contracts, setContracts] = useState<RosterContractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([listRosterPeriods(), listShiftTemplates(), getRosterContracts()])
      .then(([periodRows, shiftRows, contractRows]) => {
        if (!active) return;
        setPeriods(periodRows);
        setShifts(shiftRows);
        setContracts(contractRows);
      })
      .catch((err) => active && setError(err instanceof Error ? err.message : "Failed to load rostering dashboard."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const latest = useMemo(() => pickLatestVersion(periods), [periods]);
  const published = periods.flatMap((p) => p.versions).filter((v) => v.status === "PUBLISHED").length;
  const blockers = periods.flatMap((p) => p.versions).reduce((sum, version) => sum + version.blocker_count, 0);

  return (
    <RosterShell title="Roster control centre" subtitle="Create, validate, approve, publish, and monitor duty rosters using users.id as the canonical personnel key.">
      {loading ? <LoadingPanel /> : error ? <ErrorPanel message={error} /> : (
        <>
          <section className="roster-kpis">
            <article><strong>{periods.length}</strong><span>Roster periods</span></article>
            <article><strong>{published}</strong><span>Published versions</span></article>
            <article><strong>{shifts.length}</strong><span>Active shift templates</span></article>
            <article><strong>{blockers}</strong><span>Open blocker findings</span></article>
          </section>
          <section className="roster-card">
            <h2>Current lifecycle status</h2>
            {latest ? (
              <div className="roster-split">
                <div>
                  <p className="roster-muted">Latest version</p>
                  <h3>Version {latest.version_no} <StatusPill value={latest.status} /></h3>
                  <p>{latest.title || "Untitled roster version"}</p>
                </div>
                <div>
                  <p><strong>{latest.assignments_count}</strong> assignments</p>
                  <p><strong>{latest.warning_count}</strong> warnings</p>
                  <p><strong>{latest.blocker_count}</strong> blockers</p>
                </div>
              </div>
            ) : <div className="roster-empty">No roster period has been created yet.</div>}
          </section>
          <section className="roster-card">
            <h2>Module contract</h2>
            <p>Canonical personnel key: <strong>{contracts?.canonical_personnel_key || "users.id"}</strong></p>
            <div className="roster-contract-grid">
              {Object.entries(contracts?.source_modules || {}).map(([key, value]) => (
                <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value}</strong></div>
              ))}
            </div>
          </section>
        </>
      )}
    </RosterShell>
  );
}

export function RosterCalendarPage() {
  const [periods, setPeriods] = useState<RosterPeriodRead[]>([]);
  const [assignments, setAssignments] = useState<RosterAssignmentRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    listRosterPeriods()
      .then(async (rows) => {
        if (!active) return;
        setPeriods(rows);
        const latest = pickLatestVersion(rows);
        if (latest) setAssignments(await listRosterAssignments(latest.id));
      })
      .catch((err) => active && setError(err instanceof Error ? err.message : "Failed to load roster calendar."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <RosterShell title="Roster calendar" subtitle="Published and draft roster assignments displayed from the core roster records.">
      {loading ? <LoadingPanel /> : error ? <ErrorPanel message={error} /> : (
        <section className="roster-card">
          <h2>{periods[0]?.name || "Current roster"}</h2>
          <AssignmentTable assignments={assignments} />
        </section>
      )}
    </RosterShell>
  );
}

export function ManpowerPlanningBoardPage() {
  const bounds = monthBounds();
  const [board, setBoard] = useState<RosterPlanningBoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getRosterPlanningBoard(bounds.from, bounds.to)
      .then((data) => active && setBoard(data))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Failed to load planning board."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [bounds.from, bounds.to]);

  return (
    <RosterShell title="Manpower planning board" subtitle="Compare published roster capacity against base coverage, work orders, open task cards, and roster-to-task allocation links.">
      {loading ? <LoadingPanel /> : error ? <ErrorPanel message={error} /> : (
        <>
          <section className="roster-kpis">
            <article><strong>{board?.metrics.assigned_people ?? 0}</strong><span>Assigned people</span></article>
            <article><strong>{board?.metrics.available_duty_hours ?? 0}</strong><span>Available duty hours</span></article>
            <article><strong>{board?.metrics.remaining_task_hours ?? 0}</strong><span>Remaining task hours</span></article>
            <article><strong>{board?.metrics.capacity_gap_hours ?? 0}</strong><span>Capacity gap hours</span></article>
          </section>
          <section className="roster-card">
            <h2>Base capacity</h2>
            {!board?.base_capacity.length ? <div className="roster-empty">No base capacity data for this period.</div> : (
              <div className="roster-table-wrap">
                <table className="roster-table">
                  <thead><tr><th>Base</th><th>People</th><th>Certifying</th><th>Available h</th><th>Remaining capacity h</th><th>Remaining task h</th><th>Gap h</th></tr></thead>
                  <tbody>{board.base_capacity.map((base) => (
                    <tr key={base.base_station_id || base.base_code}>
                      <td><strong>{base.base_code}</strong><br /><span className="roster-muted">{base.base_name}</span></td>
                      <td>{base.assigned_people}</td>
                      <td>{base.certifying_people}</td>
                      <td>{base.available_hours}</td>
                      <td>{base.remaining_capacity_hours}</td>
                      <td>{base.remaining_task_hours}</td>
                      <td>{base.capacity_gap_hours}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
          <section className="roster-card">
            <h2>Open workload</h2>
            {!board?.tasks.length ? <div className="roster-empty">No open task-card workload found for this period.</div> : (
              <div className="roster-table-wrap">
                <table className="roster-table">
                  <thead><tr><th>Work order</th><th>Aircraft</th><th>Task</th><th>Base</th><th>Estimate</th><th>Roster linked</th><th>Remaining</th></tr></thead>
                  <tbody>{board.tasks.slice(0, 50).map((task) => (
                    <tr key={task.task_id}>
                      <td>{task.wo_number}</td>
                      <td>{task.aircraft_registration || task.aircraft_serial_number}</td>
                      <td><strong>{task.task_code || `Task ${task.task_id}`}</strong><br /><span className="roster-muted">{task.title}</span></td>
                      <td>{task.base_code || "—"}</td>
                      <td>{task.estimated_manhours ?? "—"}</td>
                      <td>{task.roster_linked_hours}</td>
                      <td>{task.remaining_manhours}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
          <section className="roster-card">
            <h2>Published roster assignments</h2>
            <AssignmentTable assignments={board?.assignments || []} />
          </section>
        </>
      )}
    </RosterShell>
  );
}

export function MyRosterPage() {
  const bounds = monthBounds();
  const [data, setData] = useState<MyRosterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getMyRoster(bounds.from, bounds.to)
      .then((value) => active && setData(value))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Failed to load your roster."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [bounds.from, bounds.to]);

  return (
    <RosterShell title="My roster" subtitle="Read-only view of your published duty assignments and training due next month.">
      {loading ? <LoadingPanel /> : error ? <ErrorPanel message={error} /> : (
        <>
          <section className="roster-card"><AssignmentTable assignments={data?.assignments || []} /></section>
          <section className="roster-card">
            <h2>Training due next month</h2>
            {!data?.training_due_next_month.length ? <div className="roster-empty">No training due next month.</div> : (
              <ul className="roster-list">
                {data.training_due_next_month.map((item, index) => <li key={index}>{String(item.course_name || item.course_id)} — due {String(item.valid_until || "")}</li>)}
              </ul>
            )}
          </section>
        </>
      )}
    </RosterShell>
  );
}

export function TrainingImpactPage() {
  return (
    <RosterShell title="Training impact" subtitle="Training records remain owned by the Training module; this view links their planning effect into the roster.">
      <section className="roster-card">
        <h2>Phase 1 behaviour</h2>
        <p>Planned training events are treated as full-day roster conflicts because the current Training module stores event dates rather than event times.</p>
        <p>Employee-level training due next month is available on the My Roster page. Organisation-wide forecasting remains sourced from QMS Training & Competence.</p>
      </section>
    </RosterShell>
  );
}

export function RosterReportsPage() {
  return (
    <RosterShell title="Roster reports" subtitle="Reports will use published roster versions, validation findings, and acknowledgement records.">
      <section className="roster-card"><div className="roster-empty">Phase 1 creates the records required for reports. Export templates can be added after UAT confirms the roster layout.</div></section>
    </RosterShell>
  );
}

export function RosterSettingsPage() {
  const [shifts, setShifts] = useState<ShiftTemplateRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    listShiftTemplates(true)
      .then((rows) => active && setShifts(rows))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Failed to load roster settings."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <RosterShell title="Roster settings" subtitle="Manage shift templates and shared roster configuration.">
      {loading ? <LoadingPanel /> : error ? <ErrorPanel message={error} /> : (
        <section className="roster-card">
          <h2>Shift templates</h2>
          <div className="roster-table-wrap">
            <table className="roster-table">
              <thead><tr><th>Code</th><th>Label</th><th>Kind</th><th>Duty</th><th>Active</th></tr></thead>
              <tbody>{shifts.map((shift) => <tr key={shift.id}><td>{shift.code}</td><td>{shift.label}</td><td>{shift.kind}</td><td>{shift.counts_as_duty ? "Yes" : "No"}</td><td>{shift.is_active ? "Yes" : "No"}</td></tr>)}</tbody>
            </table>
          </div>
        </section>
      )}
    </RosterShell>
  );
}

export function RosterVersionValidationPage({ versionId }: { versionId?: string }) {
  const [result, setResult] = useState<RosterValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(versionId));

  useEffect(() => {
    if (!versionId) return;
    let active = true;
    validateRosterVersion(versionId)
      .then((value) => active && setResult(value))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Validation failed."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [versionId]);

  return (
    <section className="roster-card">
      <h2>Validation findings</h2>
      {loading ? <LoadingPanel label="Running roster validation" /> : error ? <ErrorPanel message={error} /> : !result ? <div className="roster-empty">Select a roster version to validate.</div> : (
        <ul className="roster-list">
          {result.findings.map((finding) => <li key={finding.id}><StatusPill value={finding.severity} /> {finding.message}</li>)}
        </ul>
      )}
    </section>
  );
}
