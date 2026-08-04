import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import { listWorkOrders } from "../../services/workOrders";
import { listAD, listDeferrals, listSB } from "../../services/production";
import { listNonRoutines } from "../../services/maintenance";
import {
  getFleetPlanningOverview,
  listProgramItems,
  recomputeDueList,
  type FleetDueItem,
  type FleetPlanningOverview,
  type FleetUtilisationRow,
  type PlanningStatus,
} from "../../services/maintenanceProgram";
import {
  createWatchlist,
  decidePublicationReview,
  getPlanningDashboard,
  listComplianceActions,
  listPublicationReview,
  listWatchlists,
  runWatchlist,
  updateComplianceActionStatus,
  type ComplianceAction,
  type PlanningDashboardResponse,
  type PublicationReviewRow,
  type Watchlist,
} from "../../services/planningProduction";
import {
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";

type PlanningTab = {
  label: string;
  path: string;
  feature: ModuleFeature;
};

const planningTabs: PlanningTab[] = [
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

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatInteger(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function dueLimitText(item: FleetDueItem): string {
  const limits = [
    item.next_due_date ? formatDate(item.next_due_date) : null,
    item.next_due_hours != null ? `${formatNumber(item.next_due_hours)} FH` : null,
    item.next_due_cycles != null ? `${formatInteger(item.next_due_cycles)} FC` : null,
  ].filter(Boolean);
  return limits.join(" · ") || "No baseline";
}

function remainingText(item: FleetDueItem): string {
  const values = [
    item.remaining_days != null ? `${formatInteger(item.remaining_days)} d` : null,
    item.remaining_hours != null ? `${formatNumber(item.remaining_hours)} FH` : null,
    item.remaining_cycles != null ? `${formatInteger(item.remaining_cycles)} FC` : null,
  ].filter(Boolean);
  return values.join(" · ") || "—";
}

function overdueText(item: FleetDueItem): string {
  const values = [
    item.overdue_by_days != null ? `${formatInteger(item.overdue_by_days)} d` : null,
    item.overdue_by_hours != null ? `${formatNumber(item.overdue_by_hours)} FH` : null,
    item.overdue_by_cycles != null ? `${formatInteger(item.overdue_by_cycles)} FC` : null,
  ].filter(Boolean);
  return values.join(" · ") || "—";
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const cssClass = normalized.includes("overdue") || normalized.includes("blocked") || normalized.includes("missing")
    ? "badge badge--danger"
    : normalized.includes("due") || normalized.includes("await") || normalized.includes("stale")
      ? "badge badge--warning"
      : normalized.includes("current") || normalized.includes("ready") || normalized.includes("complete")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={cssClass}>{humanize(value)}</span>;
};

const EmptyState: React.FC<{ text: string }> = ({ text }) => (
  <div className="planning-empty-state"><strong>No records</strong><span>{text}</span></div>
);

const PlanningShell: React.FC<{
  title: string;
  children: React.ReactNode;
  subtitle?: string;
  feature?: ModuleFeature;
  actions?: React.ReactNode;
}> = ({ title, subtitle, children, feature, actions }) => {
  const { amoCode } = useParams();
  const location = useLocation();
  const currentUser = getCachedUser();
  const context = getContext();
  const tabs = planningTabs.filter((tab) => canViewFeature(currentUser, tab.feature, context.department));

  if (feature && !canViewFeature(currentUser, feature, context.department)) {
    return (
      <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
        <div className="page planning-production-page planning-phase-one">
          <header className="page-header"><h1>{title}</h1></header>
          <section className="card"><strong>Role visibility</strong><p className="text-muted planning-copy-spacer">This planning surface is not available to the current role assignment.</p></section>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning</p>
            <h1>{title}</h1>
            {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(currentUser, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          {actions ? <div className="planning-phase-one__header-actions">{actions}</div> : null}
        </header>

        <nav className="planning-phase-one__tabs" aria-label="Planning pages">
          {tabs.map((tab) => {
            const target = `/maintenance/${amoCode}/planning/${tab.path}`;
            const active = location.pathname === target || location.pathname.startsWith(`${target}/`);
            return <Link key={target} className={active ? "is-active" : ""} to={target}>{tab.label}</Link>;
          })}
        </nav>
        {children}
      </div>
    </DepartmentLayout>
  );
};

const MetricGrid: React.FC<{
  items: Array<{ label: string; value: number | string; helper?: string; tone?: string; to?: string }>;
}> = ({ items }) => (
  <section className="planning-metric-grid">
    {items.map((item) => {
      const content = <><span className="planning-metric-card__label">{item.label}</span><strong>{item.value}</strong>{item.helper ? <small>{item.helper}</small> : null}</>;
      return item.to
        ? <Link key={item.label} className={`planning-metric-card ${item.tone || ""}`} to={item.to}>{content}</Link>
        : <article key={item.label} className={`planning-metric-card ${item.tone || ""}`}>{content}</article>;
    })}
  </section>
);

const SimpleTable: React.FC<{ title: string; headers: string[]; rows: React.ReactNode[][] }> = ({ title, headers, rows }) => (
  <section className="card planning-panel">
    <div className="planning-panel__header"><div><h2>{title}</h2><p>{rows.length.toLocaleString()} record(s)</p></div></div>
    {rows.length ? (
      <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>
    ) : <EmptyState text="No records are available yet." />}
  </section>
);

function useFleetOverview(query: { horizonDays: number; status?: PlanningStatus | "ALL"; search?: string }) {
  const [overview, setOverview] = useState<FleetPlanningOverview>(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const reload = useCallback(() => setRefreshToken((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      getFleetPlanningOverview({ horizonDays: query.horizonDays, status: query.status, search: query.search, limit: 5000 })
        .then((data) => {
          if (!active) return;
          setOverview(data);
          setError(null);
        })
        .catch((requestError: unknown) => {
          if (!active) return;
          setError(requestError instanceof Error ? requestError.message : "Planning data could not be loaded.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, query.search ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query.horizonDays, query.search, query.status, refreshToken]);

  return { overview, loading, error, reload };
}

const PlanningDashboardPageInner: React.FC = () => {
  const { amoCode } = useParams();
  const { overview, loading, error, reload } = useFleetOverview({ horizonDays: 90, status: "ALL" });
  const [planning, setPlanning] = useState<PlanningDashboardResponse>({
    summary: { due_soon: 0, overdue: 0, open_deferrals: 0, open_watchlist_reviews: 0, open_compliance_actions: 0 },
    priority_items: [],
  });

  useEffect(() => {
    void getPlanningDashboard().then(setPlanning).catch(() => undefined);
  }, []);

  const highestRisk = overview.due_items.slice(0, 12);
  const summary = overview.summary;

  return (
    <PlanningShell title="Planning Dashboard" feature="planning.dashboard" subtitle="One fleet view for utilisation freshness, due exposure, exceptions, and planning action." actions={<button className="btn btn-secondary" onClick={reload} disabled={loading}>{loading ? "Refreshing…" : "Refresh data"}</button>}>
      {error ? <div className="alert alert--danger">{error}</div> : null}
      <MetricGrid items={[
        { label: "Overdue requirements", value: summary.overdue, helper: "Immediate planning review", tone: summary.overdue ? "is-danger" : "", to: `/maintenance/${amoCode}/planning/forecast-due-list?status=OVERDUE` },
        { label: "Due within 90 days", value: summary.due_within_horizon, helper: "Calendar horizon and active alerts", tone: "is-warning", to: `/maintenance/${amoCode}/planning/forecast-due-list` },
        { label: "Stale utilisation", value: summary.utilisation_stale + summary.utilisation_missing, helper: `${summary.utilisation_missing} aircraft missing a ledger update`, tone: summary.utilisation_stale + summary.utilisation_missing ? "is-warning" : "", to: `/maintenance/${amoCode}/planning/utilisation-monitoring` },
        { label: "Open deferments", value: planning.summary.open_deferrals, helper: "Operational limitation control", to: `/maintenance/${amoCode}/planning/deferments` },
        { label: "Publication reviews", value: planning.summary.open_watchlist_reviews, helper: "Applicability decisions pending", to: `/maintenance/${amoCode}/planning/publication-review` },
        { label: "Unbaselined tasks", value: summary.unbaselined, helper: "Missing an approved due anchor", tone: summary.unbaselined ? "is-danger" : "", to: `/maintenance/${amoCode}/production/records/reconciliation` },
      ]} />

      <section className="planning-layout planning-layout--dashboard">
        <article className="card planning-panel planning-panel--wide">
          <div className="planning-panel__header"><div><h2>Highest-risk maintenance items</h2><p>Sorted by overdue state and nearest remaining limit.</p></div><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/forecast-due-list`}>Open full forecast</Link></div>
          {highestRisk.length ? (
            <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Aircraft</th><th>Task</th><th>ATA</th><th>Status</th><th>Next limit</th><th>Remaining / overdue</th></tr></thead><tbody>{highestRisk.map((item) => <tr key={item.api_id}><td><strong>{item.registration}</strong><small>{item.aircraft_serial_number}</small></td><td><strong>{item.task_code || "Uncoded task"}</strong><small>{item.task_title}</small></td><td>{item.ata_chapter || "—"}</td><td><StatusChip value={item.status} /></td><td>{dueLimitText(item)}</td><td>{item.status === "OVERDUE" ? <span className="planning-danger-text">Overdue {overdueText(item)}</span> : remainingText(item)}</td></tr>)}</tbody></table></div>
          ) : <EmptyState text="No aircraft maintenance requirements have been baselined yet." />}
        </article>

        <article className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Fleet data condition</h2><p>Counter freshness before planning.</p></div></div>
          <div className="planning-condition-list"><div><span>Current</span><strong>{summary.utilisation_current}</strong></div><div><span>Stale</span><strong>{summary.utilisation_stale}</strong></div><div><span>Missing</span><strong>{summary.utilisation_missing}</strong></div><div><span>Fleet aircraft</span><strong>{summary.fleet_aircraft}</strong></div></div>
          <Link className="btn btn-primary planning-full-button" to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Review utilisation</Link>
        </article>
      </section>
    </PlanningShell>
  );
};

const PlanningUtilisationPageInner: React.FC = () => {
  const [search, setSearch] = useState("");
  const { overview, loading, error, reload } = useFleetOverview({ horizonDays: 90, status: "ALL" });
  const currentUser = getCachedUser();
  const context = getContext();
  const canRecompute = canPerformAction(currentUser, "planning.recompute-due", context.department);
  const [workingAircraft, setWorkingAircraft] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return overview.utilisation;
    return overview.utilisation.filter((row) => `${row.registration} ${row.aircraft_serial_number} ${row.model || ""}`.toLowerCase().includes(needle));
  }, [overview.utilisation, search]);

  const recompute = async (row: FleetUtilisationRow) => {
    setWorkingAircraft(row.aircraft_serial_number);
    setMessage(null);
    try {
      await recomputeDueList(row.aircraft_serial_number);
      setMessage(`${row.registration} due status recalculated from the latest utilisation ledger entry.`);
      reload();
    } catch (requestError) {
      setMessage(requestError instanceof Error ? requestError.message : "Recalculation failed.");
    } finally {
      setWorkingAircraft(null);
    }
  };

  return (
    <PlanningShell title="Utilisation Monitoring" feature="planning.utilisation-monitoring" subtitle="Validate the counter ledger before maintenance forecasting and package decisions." actions={<button className="btn btn-secondary" onClick={reload} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>}>
      {error ? <div className="alert alert--danger">{error}</div> : null}
      {message ? <div className="alert alert--info">{message}</div> : null}
      <MetricGrid items={[
        { label: "Fleet aircraft", value: overview.summary.fleet_aircraft },
        { label: "Current ledgers", value: overview.summary.utilisation_current },
        { label: "Stale ledgers", value: overview.summary.utilisation_stale, tone: overview.summary.utilisation_stale ? "is-warning" : "" },
        { label: "Missing ledgers", value: overview.summary.utilisation_missing, tone: overview.summary.utilisation_missing ? "is-danger" : "" },
      ]} />

      <section className="card planning-panel">
        <div className="planning-toolbar"><div><h2>Aircraft utilisation control</h2><p>Latest accepted totals, update age, usage trend, and due exposure.</p></div><input className="input planning-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search registration, serial, or model" /></div>
        {rows.length ? (
          <div className="table-wrapper"><table className="table table-striped planning-table planning-table--utilisation"><thead><tr><th>Aircraft</th><th>Current FH</th><th>Current FC</th><th>Last log</th><th>Freshness</th><th>7-day avg</th><th>Due exposure</th><th>Next known limit</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.aircraft_serial_number}><td><strong>{row.registration}</strong><small>{row.model || "Unknown model"} · {row.aircraft_serial_number}</small></td><td>{formatNumber(row.current_hours)}</td><td>{formatInteger(row.current_cycles)}</td><td>{formatDate(row.last_log_date)}<small>{row.days_since_log == null ? "No accepted entry" : `${row.days_since_log} day(s) ago`}</small></td><td><StatusChip value={row.freshness_status} /></td><td>{formatNumber(row.seven_day_daily_average_hours)} FH/day</td><td><span className={row.overdue_count ? "planning-danger-text" : ""}>{row.overdue_count} overdue</span><small>{row.due_soon_count} due soon</small></td><td>{[row.next_due_date ? formatDate(row.next_due_date) : null, row.next_due_hours != null ? `${formatNumber(row.next_due_hours)} FH` : null, row.next_due_cycles != null ? `${formatInteger(row.next_due_cycles)} FC` : null].filter(Boolean).join(" · ") || "No baseline"}</td><td><button className="btn btn-secondary" disabled={!canRecompute || workingAircraft === row.aircraft_serial_number} onClick={() => void recompute(row)}>{workingAircraft === row.aircraft_serial_number ? "Calculating…" : "Recompute"}</button></td></tr>)}</tbody></table></div>
        ) : <EmptyState text="No aircraft matched the current search." />}
      </section>
    </PlanningShell>
  );
};

const PlanningForecastPageInner: React.FC = () => {
  const { amoCode } = useParams();
  const location = useLocation();
  const initialStatus = new URLSearchParams(location.search).get("status") as PlanningStatus | null;
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<PlanningStatus | "ALL">(initialStatus || "ALL");
  const [horizonDays, setHorizonDays] = useState(90);
  const { overview, loading, error, reload } = useFleetOverview({ horizonDays, status: statusFilter, search });
  const currentUser = getCachedUser();
  const context = getContext();
  const canPlanPackage = canPerformAction(currentUser, "planning.plan-package", context.department);

  return (
    <PlanningShell title="Forecast / Due List" feature="planning.forecast-due-list" subtitle="Full-fleet maintenance exposure with signed remaining values and explicit baseline condition." actions={<button className="btn btn-secondary" onClick={reload} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>}>
      {error ? <div className="alert alert--danger">{error}</div> : null}
      <MetricGrid items={[
        { label: "Overdue", value: overview.summary.overdue, tone: overview.summary.overdue ? "is-danger" : "" },
        { label: "Due soon", value: overview.summary.due_soon, tone: overview.summary.due_soon ? "is-warning" : "" },
        { label: `Within ${horizonDays} days`, value: overview.summary.due_within_horizon },
        { label: "Unbaselined", value: overview.summary.unbaselined, tone: overview.summary.unbaselined ? "is-danger" : "" },
      ]} />

      <section className="card planning-panel">
        <div className="planning-toolbar planning-toolbar--filters"><div><h2>Fleet due requirements</h2><p>{overview.due_items.length.toLocaleString()} matching requirement(s).</p></div><div className="planning-filter-row"><input className="input planning-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search aircraft, task, ATA, or model" /><select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as PlanningStatus | "ALL")}><option value="ALL">All statuses</option><option value="OVERDUE">Overdue</option><option value="DUE_SOON">Due soon</option><option value="PLANNED">Planned</option></select><select className="input" value={horizonDays} onChange={(event) => setHorizonDays(Number(event.target.value))}>{[30, 60, 90, 180, 365, 730].map((days) => <option key={days} value={days}>{days} day horizon</option>)}</select></div></div>
        {overview.due_items.length ? (
          <div className="table-wrapper"><table className="table table-striped planning-table planning-table--forecast"><thead><tr><th>Aircraft</th><th>Requirement</th><th>ATA</th><th>Status</th><th>Current counters</th><th>Next limit</th><th>Remaining</th><th>Overdue by</th><th>Baseline</th><th /></tr></thead><tbody>{overview.due_items.map((item) => <tr key={item.api_id}><td><strong>{item.registration}</strong><small>{item.model || "Unknown model"} · {item.aircraft_serial_number}</small></td><td><strong>{item.task_code || "Uncoded task"}</strong><small>{item.task_title}</small></td><td>{item.ata_chapter || "—"}</td><td><StatusChip value={item.status} /></td><td>{formatNumber(item.current_hours)} FH<small>{formatInteger(item.current_cycles)} FC</small></td><td>{dueLimitText(item)}</td><td>{remainingText(item)}</td><td className={item.status === "OVERDUE" ? "planning-danger-text" : ""}>{overdueText(item)}</td><td><StatusChip value={item.baseline_status} /></td><td><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/work-packages?aircraft=${encodeURIComponent(item.aircraft_serial_number)}&program_item=${item.program_item_id}`} aria-disabled={!canPlanPackage} onClick={(event) => !canPlanPackage && event.preventDefault()}>Plan</Link></td></tr>)}</tbody></table></div>
        ) : <EmptyState text="No requirements matched the selected filters." />}
      </section>
    </PlanningShell>
  );
};

const PlanningReferencePage: React.FC<{ title: string; mode: string; feature: ModuleFeature }> = ({ title, mode, feature }) => {
  const [deferrals, setDeferrals] = useState<any[]>([]);
  const [ads, setAds] = useState<any[]>([]);
  const [sbs, setSbs] = useState<any[]>([]);
  const [programItems, setProgramItems] = useState<any[]>([]);
  const [workOrders, setWorkOrders] = useState<any[]>([]);

  useEffect(() => {
    void listDeferrals().then(setDeferrals).catch(() => setDeferrals([]));
    void listAD().then(setAds).catch(() => setAds([]));
    void listSB().then(setSbs).catch(() => setSbs([]));
    void listProgramItems().then(setProgramItems).catch(() => setProgramItems([]));
    void listWorkOrders({ limit: 300 }).then(setWorkOrders).catch(() => setWorkOrders([]));
  }, []);

  const content: Record<string, React.ReactNode> = {
    amp: <SimpleTable title="Approved maintenance programme" headers={["Template", "Task", "ATA", "Interval", "Status"]} rows={programItems.map((item) => [item.template_code, item.task_code || item.task_number || item.title, item.ata_chapter || "—", `${item.interval_hours ?? "—"} FH · ${item.interval_cycles ?? "—"} FC · ${item.interval_days ?? "—"} d`, <StatusChip value={item.status} />])} />,
    "task-library": <SimpleTable title="Task library" headers={["Task", "Description", "ATA", "Template"]} rows={programItems.map((item) => [item.task_code || item.task_number || item.id, item.title, item.ata_chapter || "—", item.template_code])} />,
    "ad-sb-eo-control": <SimpleTable title="AD / SB / EO register" headers={["Type", "Reference", "Status", "Next due"]} rows={[...ads, ...sbs].map((item: any) => [item.item_type, item.reference, <StatusChip value={item.status || "Open"} />, item.next_due_date || "—"])} />,
    "work-packages": <SimpleTable title="Work packages" headers={["Package / WO", "Aircraft", "Status", "Type", "Due"]} rows={workOrders.filter((item: any) => item.work_package_ref).map((item: any) => [item.work_package_ref || item.wo_number, item.aircraft_serial_number, <StatusChip value={item.status} />, item.wo_type, item.due_date || "—"])} />,
    "work-orders": <SimpleTable title="Planning work orders" headers={["WO", "Aircraft", "Status", "Type", "Due"]} rows={workOrders.map((item: any) => [item.wo_number, item.aircraft_serial_number, <StatusChip value={item.status} />, item.wo_type, item.due_date || "—"])} />,
    deferments: <SimpleTable title="Deferments" headers={["Aircraft", "Defect", "Expiry", "Status"]} rows={deferrals.map((item: any) => [item.tail_id, item.defect_ref, item.expiry_at || "—", <StatusChip value={item.status || "Open"} />])} />,
    "non-routine-review": <SimpleTable title="Non-routine review queue" headers={["Aircraft", "WO", "Description", "Status"]} rows={listNonRoutines().map((item) => [item.tail, item.woId, item.description, <StatusChip value={item.status} />])} />,
  };

  return <PlanningShell title={title} feature={feature}>{content[mode] || <EmptyState text="No data available." />}</PlanningShell>;
};

const WatchlistsPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const context = getContext();
  const [rows, setRows] = useState<Watchlist[]>([]);
  const canManage = canPerformAction(currentUser, "planning.manage-watchlists", context.department);
  const reload = useCallback(() => {
    void listWatchlists().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => { reload(); }, [reload]);

  return (
    <PlanningShell title="Watchlists" feature="planning.watchlists" actions={<button className="btn btn-primary" disabled={!canManage} onClick={() => void createWatchlist({ name: `Airworthiness watchlist ${new Date().toLocaleDateString()}`, criteria_json: { document_type: ["AD", "SB"] } }).then(reload)}>Create watchlist</button>}>
      <SimpleTable title="Airworthiness watchlists" headers={["Name", "Status", "Runs", "Last run", "Action"]} rows={rows.map((row) => [row.name, <StatusChip value={row.status} />, row.run_count, row.last_run_at || "Never", <button className="btn btn-secondary" disabled={!canManage} onClick={() => void runWatchlist(row.id).then(reload)}>Run</button>])} />
    </PlanningShell>
  );
};

const PublicationReviewPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const context = getContext();
  const [rows, setRows] = useState<PublicationReviewRow[]>([]);
  const canDecide = canPerformAction(currentUser, "planning.decide-publication", context.department);
  const reload = useCallback(() => {
    void listPublicationReview().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => { reload(); }, [reload]);

  return (
    <PlanningShell title="Publication Review" feature="planning.publication-review">
      <SimpleTable title="Applicability review queue" headers={["Reference", "Title", "Authority", "Classification", "Age", "Action"]} rows={rows.map((row) => [row.doc_number, row.title, row.authority, <StatusChip value={row.classification} />, `${row.ageing_days} d`, <button className="btn btn-secondary" disabled={!canDecide} onClick={() => void decidePublicationReview(row.match_id, { review_status: "Reviewed", classification: "Potentially Applicable", review_notes: "Reviewed from planning queue" }).then(reload)}>Record review</button>])} />
    </PlanningShell>
  );
};

const ComplianceActionsPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const context = getContext();
  const [rows, setRows] = useState<ComplianceAction[]>([]);
  const canManage = canPerformAction(currentUser, "planning.update-compliance", context.department);
  const reload = useCallback(() => {
    void listComplianceActions().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => { reload(); }, [reload]);

  return (
    <PlanningShell title="Compliance Actions" feature="planning.compliance-actions">
      <SimpleTable title="Compliance action control" headers={["Action", "Decision", "Due", "Status", "Package / WO", "Action"]} rows={rows.map((row) => [`CA-${row.id}`, row.decision, row.due_date || "—", <StatusChip value={row.status} />, row.package_ref || row.work_order_ref || "—", <button className="btn btn-secondary" disabled={!canManage} onClick={() => void updateComplianceActionStatus(row.id, { status: "In Work", event_notes: "Moved to execution from planning control" }).then(reload)}>Set in work</button>])} />
    </PlanningShell>
  );
};

export const PlanningDashboardPage = PlanningDashboardPageInner;
export const PlanningUtilisationPage = PlanningUtilisationPageInner;
export const PlanningForecastPage = PlanningForecastPageInner;
export const PlanningAmpPage = () => <PlanningReferencePage title="AMP / Maintenance Programme" mode="amp" feature="planning.amp" />;
export const PlanningTaskLibraryPage = () => <PlanningReferencePage title="Task Library" mode="task-library" feature="planning.task-library" />;
export const PlanningAdSbPage = () => <PlanningReferencePage title="AD / SB / EO Control" mode="ad-sb-eo-control" feature="planning.ad-sb-eo-control" />;
export const PlanningWorkPackagesPage = () => <PlanningReferencePage title="Work Packages" mode="work-packages" feature="planning.work-packages" />;
export const PlanningWorkOrdersPage = () => <PlanningReferencePage title="Planning Work Orders" mode="work-orders" feature="planning.work-orders" />;
export const PlanningDefermentsPage = () => <PlanningReferencePage title="Deferments" mode="deferments" feature="planning.deferments" />;
export const PlanningNonRoutinePage = () => <PlanningReferencePage title="Non-Routine Review" mode="non-routine-review" feature="planning.non-routine-review" />;
export const WatchlistsPage = WatchlistsPageInner;
export const PublicationReviewPage = PublicationReviewPageInner;
export const ComplianceActionsPage = ComplianceActionsPageInner;
