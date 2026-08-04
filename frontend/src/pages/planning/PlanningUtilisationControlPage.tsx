import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  getFleetPlanningOverview,
  recomputeDueList,
  type FleetPlanningOverview,
} from "../../services/maintenanceProgram";
import {
  decideUsageCorrection,
  fetchReconciliationSummary,
  listUsageCorrections,
  runReconciliationScan,
  type ReconciliationSummary,
  type UsageCorrection,
} from "../../services/technicalRecords";
import {
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";

const tabs: Array<{ label: string; path: string; feature: ModuleFeature }> = [
  { label: "Dashboard", path: "dashboard", feature: "planning.dashboard" },
  { label: "Utilisation", path: "utilisation-monitoring", feature: "planning.utilisation-monitoring" },
  { label: "Forecast", path: "forecast-due-list", feature: "planning.forecast-due-list" },
  { label: "AMP", path: "amp", feature: "planning.amp" },
  { label: "Task Library", path: "task-library", feature: "planning.task-library" },
  { label: "AD/SB/EO", path: "ad-sb-eo-control", feature: "planning.ad-sb-eo-control" },
  { label: "Work Packages", path: "work-packages", feature: "planning.work-packages" },
  { label: "Work Orders", path: "work-orders", feature: "planning.work-orders" },
  { label: "Deferments", path: "deferments", feature: "planning.deferments" },
  { label: "NR Review", path: "non-routine-review", feature: "planning.non-routine-review" },
  { label: "Watchlists", path: "watchlists", feature: "planning.watchlists" },
  { label: "Publication Review", path: "publication-review", feature: "planning.publication-review" },
  { label: "Compliance", path: "compliance-actions", feature: "planning.compliance-actions" },
];

const emptyOverview: FleetPlanningOverview = {
  generated_at: "",
  horizon_days: 90,
  summary: {
    fleet_aircraft: 0,
    utilisation_current: 0,
    utilisation_stale: 0,
    utilisation_missing: 0,
    overdue: 0,
    due_soon: 0,
    planned: 0,
    unbaselined: 0,
    due_within_horizon: 0,
  },
  utilisation: [],
  due_items: [],
};

const emptySummary: ReconciliationSummary = {
  generated_at: "",
  open_total: 0,
  by_type: {},
  affected_aircraft: 0,
};

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: value.includes("T") ? "2-digit" : undefined,
        minute: value.includes("T") ? "2-digit" : undefined,
      }).format(parsed);
}

function formatNumber(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const className = normalized.includes("missing") || normalized.includes("overdue") || normalized.includes("rejected")
    ? "badge badge--danger"
    : normalized.includes("stale") || normalized.includes("pending") || normalized.includes("attention")
      ? "badge badge--warning"
      : normalized.includes("current") || normalized.includes("applied") || normalized.includes("ready")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

const MetricGrid: React.FC<{ items: Array<{ label: string; value: number | string; tone?: string }> }> = ({ items }) => (
  <section className="planning-metric-grid">
    {items.map((item) => (
      <article key={item.label} className={`planning-metric-card ${item.tone || ""}`}>
        <span className="planning-metric-card__label">{item.label}</span>
        <strong>{item.value}</strong>
      </article>
    ))}
  </section>
);

export const PlanningUtilisationPage: React.FC = () => {
  const { amoCode } = useParams();
  const location = useLocation();
  const currentUser = getCachedUser();
  const context = getContext();
  const canRecompute = canPerformAction(currentUser, "planning.recompute-due", context.department);
  const visibleTabs = tabs.filter((tab) => canViewFeature(currentUser, tab.feature, context.department));
  const [overview, setOverview] = useState<FleetPlanningOverview>(emptyOverview);
  const [corrections, setCorrections] = useState<UsageCorrection[]>([]);
  const [summary, setSummary] = useState<ReconciliationSummary>(emptySummary);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [workingAircraft, setWorkingAircraft] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [planningOverview, correctionRows, reconciliation] = await Promise.all([
      getFleetPlanningOverview({ horizonDays: 90, limit: 5000 }),
      listUsageCorrections({ status: "PENDING" }),
      fetchReconciliationSummary(),
    ]);
    setOverview(planningOverview);
    setCorrections(correctionRows);
    setSummary(reconciliation);
  }, []);

  useEffect(() => {
    void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Utilisation controls could not be loaded."));
  }, [reload]);

  const filteredAircraft = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return overview.utilisation;
    return overview.utilisation.filter((row) =>
      `${row.registration} ${row.aircraft_serial_number} ${row.model || ""}`.toLowerCase().includes(needle),
    );
  }, [overview.utilisation, search]);

  const decide = async (correction: UsageCorrection, decision: "APPROVE" | "REJECT") => {
    const reviewNotes = decision === "APPROVE"
      ? "Reviewed and approved from Planning Utilisation Control."
      : "Rejected from Planning Utilisation Control; submit a corrected request with supporting details.";
    setBusy(true);
    setMessage(null);
    try {
      await decideUsageCorrection(correction.id, decision, reviewNotes);
      setMessage(`Correction ${correction.id} ${decision === "APPROVE" ? "approved and applied" : "rejected"}.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Correction decision failed.");
    } finally {
      setBusy(false);
    }
  };

  const scan = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await runReconciliationScan();
      setMessage(`Reconciliation checked ${result.checked_aircraft} aircraft and created ${result.created} new exception(s).`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Reconciliation scan failed.");
    } finally {
      setBusy(false);
    }
  };

  const recompute = async (aircraftSerialNumber: string, registration: string) => {
    setWorkingAircraft(aircraftSerialNumber);
    setMessage(null);
    try {
      await recomputeDueList(aircraftSerialNumber);
      setMessage(`${registration} due projection recalculated from the accepted ledger.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Due projection could not be recalculated.");
    } finally {
      setWorkingAircraft(null);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning</p>
            <h1>Utilisation Control</h1>
            <p className="page-header__subtitle">Canonical counter freshness, immutable correction approvals, and records reconciliation.</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(currentUser, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          <div className="planning-phase-one__header-actions">
            <button className="btn btn-secondary" disabled={busy} onClick={() => void reload()}>Refresh</button>
            <button className="btn btn-primary" disabled={busy} onClick={() => void scan()}>{busy ? "Working…" : "Run reconciliation"}</button>
          </div>
        </header>

        <nav className="planning-phase-one__tabs" aria-label="Planning pages">
          {visibleTabs.map((tab) => {
            const target = `/maintenance/${amoCode}/planning/${tab.path}`;
            return <Link key={target} className={location.pathname === target ? "is-active" : ""} to={target}>{tab.label}</Link>;
          })}
        </nav>

        {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}

        <MetricGrid items={[
          { label: "Current ledgers", value: overview.summary.utilisation_current },
          { label: "Stale ledgers", value: overview.summary.utilisation_stale, tone: overview.summary.utilisation_stale ? "is-warning" : "" },
          { label: "Missing ledgers", value: overview.summary.utilisation_missing, tone: overview.summary.utilisation_missing ? "is-danger" : "" },
          { label: "Pending corrections", value: corrections.length, tone: corrections.length ? "is-warning" : "" },
          { label: "Open exceptions", value: summary.open_total, tone: summary.open_total ? "is-danger" : "" },
          { label: "Affected aircraft", value: summary.affected_aircraft },
        ]} />

        <section className="planning-phase-two__split">
          <article className="card planning-panel planning-phase-two__builder">
            <div className="planning-toolbar planning-toolbar--filters">
              <div><h2>Canonical aircraft counters</h2><p>The latest accepted `aircraft_usage` entry drives planning totals and due calculations.</p></div>
              <input className="input planning-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search aircraft or model" />
            </div>
            <div className="table-wrapper">
              <table className="table table-striped planning-table planning-table--utilisation">
                <thead><tr><th>Aircraft</th><th>FH</th><th>FC</th><th>Last log</th><th>Freshness</th><th>7-day avg</th><th>Due exposure</th><th /></tr></thead>
                <tbody>{filteredAircraft.map((row) => (
                  <tr key={row.aircraft_serial_number}>
                    <td><strong>{row.registration}</strong><small>{row.model || row.aircraft_serial_number}</small></td>
                    <td>{formatNumber(row.current_hours)}</td>
                    <td>{formatNumber(row.current_cycles, 0)}</td>
                    <td>{formatDate(row.last_log_date)}<small>{row.days_since_log == null ? "No accepted entry" : `${row.days_since_log} day(s) ago`}</small></td>
                    <td><StatusChip value={row.freshness_status} /></td>
                    <td>{formatNumber(row.seven_day_daily_average_hours)} FH/day</td>
                    <td><span className={row.overdue_count ? "planning-danger-text" : ""}>{row.overdue_count} overdue</span><small>{row.due_soon_count} due soon</small></td>
                    <td><button className="btn btn-secondary" disabled={!canRecompute || workingAircraft === row.aircraft_serial_number} onClick={() => void recompute(row.aircraft_serial_number, row.registration)}>{workingAircraft === row.aircraft_serial_number ? "Calculating…" : "Recompute"}</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </article>

          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Pending corrections</h2><p>Approved requests update the ledger and recalculate every later cumulative entry.</p></div></div>
            <div className="planning-phase-two__package-list">
              {corrections.map((correction) => (
                <section key={correction.id} className="planning-phase-two__package">
                  <div className="planning-phase-two__package-head">
                    <div><strong>Correction {correction.id}</strong><span>{correction.aircraft_serial_number} · Usage {correction.usage_id}</span></div>
                    <StatusChip value={correction.status} />
                  </div>
                  <p>{correction.reason}</p>
                  <dl>
                    <div><dt>Requested</dt><dd>{formatDate(correction.requested_at)}</dd></div>
                    <div><dt>Fields</dt><dd>{Object.keys(correction.proposed_values_json).join(", ") || "—"}</dd></div>
                  </dl>
                  <div className="planning-phase-two__readiness-notes">
                    {Object.entries(correction.proposed_values_json).map(([field, value]) => <span key={field}>{humanize(field)}: {String(value ?? "—")}</span>)}
                  </div>
                  <div className="planning-inline-actions">
                    <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(correction, "REJECT")}>Reject</button>
                    <button className="btn btn-primary" disabled={busy} onClick={() => void decide(correction, "APPROVE")}>Approve and apply</button>
                  </div>
                </section>
              ))}
              {!corrections.length ? <div className="planning-empty-state"><strong>No pending corrections</strong><span>Accepted utilization entries remain immutable.</span></div> : null}
            </div>

            <div className="planning-panel__header planning-phase-two__table-spacer"><div><h2>Exception categories</h2><p>Current open Technical Records reconciliation queue.</p></div></div>
            <div className="planning-condition-list">
              {Object.entries(summary.by_type).map(([type, count]) => <div key={type}><span>{humanize(type)}</span><strong>{count}</strong></div>)}
              {!Object.keys(summary.by_type).length ? <div><span>No open categories</span><strong>0</strong></div> : null}
            </div>
          </article>
        </section>
      </div>
    </DepartmentLayout>
  );
};
