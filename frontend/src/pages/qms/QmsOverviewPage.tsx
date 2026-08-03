import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  ClipboardCheck,
  FileCheck2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
} from "lucide-react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import { getCachedUser } from "../../services/auth";
import { getQmsOperationalDashboard } from "../../services/qmsDashboard";
import type {
  QmsOperationalActionItem,
  QmsOperationalDashboardResponse,
  QmsOperationalKpi,
  QmsOperationalObligation,
  QmsOperationalWorkItem,
} from "../../types/qms";
import QmsDiagnosticsDrawer from "./components/QmsDiagnosticsDrawer";
import {
  buildQmsOverviewRoutes,
  deriveQmsOverviewHealth,
  qmsTimestampLabel,
} from "./qmsOverviewModel";
import "../../styles/qms-overview.css";

type LoadState = "idle" | "loading" | "ready" | "error";

type DashboardPanelProps = {
  title: string;
  subtitle?: string;
  className?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
};

const CHART_COLORS = [
  "var(--qms-chart-1)",
  "var(--qms-chart-2)",
  "var(--qms-chart-3)",
  "var(--qms-chart-4)",
  "var(--qms-chart-5)",
];

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

function decodeSegment(value: string | undefined): string {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function amoCodeFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "maintenance" ? decodeSegment(parts[1]) : "";
}

function counter(dashboard: QmsOperationalDashboardResponse, ...keys: string[]): number {
  for (const key of keys) {
    const value = dashboard.counters[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return 0;
}

function formatMetric(value: number | null, unit = ""): string {
  if (value === null || !Number.isFinite(value)) return "Not available";
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
  if (!unit) return formatted;
  return unit === "%" ? `${formatted}%` : `${formatted} ${unit}`;
}

function DashboardPanel({ title, subtitle, className = "", action, children }: DashboardPanelProps): React.ReactElement {
  return (
    <section className={`qms-dashboard-panel ${className}`.trim()}>
      <header className="qms-dashboard-panel__header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {action ? <div className="qms-dashboard-panel__action">{action}</div> : null}
      </header>
      <div className="qms-dashboard-panel__body">{children}</div>
    </section>
  );
}

function EmptyChart({ message }: { message: string }): React.ReactElement {
  return (
    <div className="qms-dashboard-empty">
      <ShieldCheck size={22} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function ActionQueue({
  items,
  onNavigate,
}: {
  items: QmsOperationalActionItem[];
  onNavigate: (route: string) => void;
}): React.ReactElement {
  if (!items.length) return <EmptyChart message="No urgent Quality exposure is currently ranked." />;
  return (
    <div className="qms-dashboard-action-list">
      {items.map((item) => (
        <button key={item.id} type="button" onClick={() => onNavigate(item.route)} className={`qms-dashboard-action qms-dashboard-action--${item.tone}`}>
          <span className="qms-dashboard-action__count">{item.count}</span>
          <span className="qms-dashboard-action__copy">
            <strong>{item.label}</strong>
            <small>{item.next_action}</small>
          </span>
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function WorkList({
  items,
  onNavigate,
  empty,
}: {
  items: QmsOperationalWorkItem[];
  onNavigate: (route: string) => void;
  empty: string;
}): React.ReactElement {
  if (!items.length) return <EmptyChart message={empty} />;
  return (
    <div className="qms-dashboard-work-list">
      {items.slice(0, 7).map((item) => (
        <button key={item.id} type="button" onClick={() => onNavigate(item.route)}>
          <span className={`qms-dashboard-work-list__marker qms-severity--${String(item.severity || "neutral").toLowerCase()}`} />
          <span>
            <strong>{item.title}</strong>
            <small>{item.created_at ? qmsTimestampLabel(item.created_at) : "Quality work item"}</small>
          </span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function ObligationList({
  items,
  onNavigate,
}: {
  items: QmsOperationalObligation[];
  onNavigate: (route: string) => void;
}): React.ReactElement {
  if (!items.length) return <EmptyChart message="No dated Quality obligations are available for the next 30 days." />;
  return (
    <div className="qms-dashboard-obligations">
      {items.slice(0, 8).map((item) => (
        <button key={`${item.module || "qms"}-${item.id}`} type="button" onClick={() => onNavigate(item.link || "") } disabled={!item.link}>
          <time dateTime={item.date || undefined}>{item.date ? new Date(item.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "Unscheduled"}</time>
          <span>
            <strong>{item.title}</strong>
            <small>{item.subtitle || item.event_type || item.module || "Quality obligation"}</small>
          </span>
          <span className={`qms-dashboard-due qms-dashboard-due--${item.due_state || "scheduled"}`}>{String(item.due_state || "scheduled").replace(/_/g, " ")}</span>
        </button>
      ))}
    </div>
  );
}

function KpiTable({ items, onNavigate }: { items: QmsOperationalKpi[]; onNavigate: (route: string) => void }): React.ReactElement {
  return (
    <div className="qms-dashboard-kpis">
      {items.map((item) => (
        <button key={item.id} type="button" onClick={() => onNavigate(item.route)}>
          <span>
            <strong>{formatMetric(item.current, item.unit)}</strong>
            <small>{item.label}</small>
          </span>
          <span className={`qms-dashboard-direction qms-dashboard-direction--${item.direction}`}>{item.direction.replace(/_/g, " ")}</span>
        </button>
      ))}
    </div>
  );
}

const QmsOverviewPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const amoCode = params.amoCode || amoCodeFromPath(location.pathname) || "UNKNOWN";
  const routes = useMemo(() => buildQmsOverviewRoutes(amoCode), [amoCode]);
  const requestRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [dashboard, setDashboard] = useState<QmsOperationalDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort(new DOMException("Superseded by a newer QMS overview request", "AbortError"));
    const controller = new AbortController();
    requestRef.current = controller;
    setState("loading");
    setError(null);
    try {
      const response = await getQmsOperationalDashboard(amoCode, controller.signal);
      if (controller.signal.aborted) return;
      if (response.contract !== "qms-operational-dashboard.v2") {
        throw new Error("The Quality API returned an unsupported dashboard contract.");
      }
      setDashboard(response);
      setState("ready");
    } catch (loadError) {
      if (controller.signal.aborted) return;
      setError(friendlyError(loadError, "Unable to load the operational Quality dashboard."));
      setState("error");
    }
  }, [amoCode]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort(new DOMException("QMS overview unmounted", "AbortError"));
  }, [load]);

  const currentUser = getCachedUser();
  const diagnosticsAuthorized = Boolean(
    currentUser?.is_amo_admin ||
    currentUser?.role === "QUALITY_MANAGER" ||
    currentUser?.role === "QUALITY_INSPECTOR",
  );

  const health = useMemo(() => {
    if (dashboard) return deriveQmsOverviewHealth(dashboard);
    return state === "error"
      ? { tone: "danger" as const, label: "Overview unavailable", summary: "Quality data could not be loaded.", urgentCount: 0 }
      : { tone: "neutral" as const, label: "Loading overview", summary: "Retrieving Quality controls.", urgentCount: 0 };
  }, [dashboard, state]);

  const severityData = useMemo(() => {
    const source = dashboard?.severity_breakdown?.open_findings || {};
    return Object.entries(source)
      .map(([name, value]) => ({ name: name.replace(/_/g, " "), value: Number(value || 0) }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [dashboard]);

  const agingData = useMemo(() => {
    const source = dashboard?.aging_buckets?.overdue_cars || {};
    const labels: Record<string, string> = { "1_7": "1–7d", "8_30": "8–30d", "31_90": "31–90d", over_90: "90d+" };
    return Object.entries(source).map(([bucket, value]) => ({ bucket: labels[bucket] || bucket, value: Number(value || 0) }));
  }, [dashboard]);

  const performanceData = useMemo(() => (
    dashboard?.performance_kpis
      .filter((item) => item.current !== null)
      .map((item) => ({ name: item.label, value: Number(item.current), unit: item.unit })) || []
  ), [dashboard]);

  const riskCounters = useMemo(() => {
    if (!dashboard) return null;
    const source = dashboard.counters;
    const keys = Object.keys(source).filter((key) => key.startsWith("risk_") || key.includes("risk_rating"));
    if (!keys.length) return null;
    return {
      low: counter(dashboard, "risk_low", "risks_low", "risk_rating_low"),
      medium: counter(dashboard, "risk_medium", "risks_medium", "risk_rating_medium"),
      high: counter(dashboard, "risk_high", "risks_high", "risk_rating_high"),
      critical: counter(dashboard, "risk_critical", "risks_critical", "risk_rating_critical"),
    };
  }, [dashboard]);

  const go = useCallback((route: string) => {
    if (!route) return;
    navigate(route);
  }, [navigate]);

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-overview-page">
        <PageHeader
          compact
          eyebrow="Quality Management System"
          title="Quality dashboard"
          subtitle="Live Quality exposure, assigned work, upcoming obligations, performance and control health for this AMO only."
          breadcrumbs={[{ label: "Quality" }, { label: "Dashboard" }]}
          meta={<span className={`qms-overview-health qms-tone--${health.tone}`}>{health.label}</span>}
          actions={
            <div className="qms-dashboard-header-actions">
              <button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/quality/settings/general`)}>
                <SlidersHorizontal size={15} aria-hidden="true" /> Configure
              </button>
              <button type="button" onClick={() => void load()} disabled={state === "loading"}>
                <RefreshCw size={15} className={state === "loading" ? "is-spinning" : ""} aria-hidden="true" /> Refresh
              </button>
            </div>
          }
        />

        {error ? (
          <div className="qms-overview-alert qms-overview-alert--error" role="alert">
            <AlertTriangle size={19} aria-hidden="true" />
            <div>
              <strong>{dashboard ? "Quality data refresh failed" : "Quality dashboard unavailable"}</strong>
              <p>{error}</p>
            </div>
            <button type="button" onClick={() => void load()}>Retry</button>
          </div>
        ) : null}

        {state === "loading" && !dashboard ? (
          <div className="qms-overview-loading" role="status" aria-live="polite">
            <RefreshCw size={18} className="is-spinning" aria-hidden="true" /> Loading Quality dashboard…
          </div>
        ) : null}

        {dashboard ? (
          <main className="qms-dashboard-grid">
            <section className={`qms-dashboard-control qms-dashboard-control--${health.tone}`}>
              <ShieldCheck size={21} aria-hidden="true" />
              <div>
                <span>Current control status</span>
                <strong>{health.summary}</strong>
              </div>
              <div className="qms-dashboard-freshness">
                <span>Generated</span>
                <strong>{qmsTimestampLabel(dashboard.data_freshness?.generated_at || dashboard.as_of)}</strong>
              </div>
            </section>

            {dashboard.source_health.status !== "healthy" ? (
              <div className="qms-overview-alert qms-overview-alert--warning" role="status">
                <AlertTriangle size={18} aria-hidden="true" />
                <div>
                  <strong>Some Quality sources are incomplete</strong>
                  <p>Available data is shown. Empty panels must not be treated as proof that no work exists.</p>
                </div>
              </div>
            ) : null}

            <section className="qms-dashboard-stat-grid" aria-label="Quality overview metrics">
              <button type="button" onClick={() => go(routes.findings)}>
                <ShieldAlert size={20} aria-hidden="true" />
                <span><strong>{counter(dashboard, "open_findings", "findings_open_total")}</strong><small>Open findings</small></span>
              </button>
              <button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/quality/cars/overdue`)}>
                <ClipboardCheck size={20} aria-hidden="true" />
                <span><strong>{counter(dashboard, "overdue_cars", "cars_overdue")}</strong><small>Overdue CARs</small></span>
              </button>
              <button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/schedule`)}>
                <CalendarClock size={20} aria-hidden="true" />
                <span><strong>{counter(dashboard, "audits_due_soon")}</strong><small>Audits due in 30 days</small></span>
              </button>
              <button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/training/competence/overdue`)}>
                <UsersRound size={20} aria-hidden="true" />
                <span><strong>{counter(dashboard, "training_expired_records")}</strong><small>Expired training</small></span>
              </button>
              <button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/quality/documents/approvals`)}>
                <FileCheck2 size={20} aria-hidden="true" />
                <span><strong>{counter(dashboard, "pending_document_approvals", "documents_pending_approval")}</strong><small>Document approvals</small></span>
              </button>
            </section>

            <DashboardPanel title="Priority action queue" subtitle="Ranked by regulatory and operational exposure" className="qms-dashboard-panel--span-2" action={<button type="button" onClick={() => go(routes.myWork)}>Open all work <ArrowRight size={14} /></button>}>
              <ActionQueue items={dashboard.action_queue} onNavigate={go} />
            </DashboardPanel>

            <DashboardPanel title="Findings by severity" subtitle="Open findings only">
              {severityData.length ? (
                <div className="qms-dashboard-chart qms-dashboard-chart--pie">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={severityData} dataKey="value" nameKey="name" innerRadius="48%" outerRadius="78%" paddingAngle={2}>
                        {severityData.map((entry, index) => <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="qms-dashboard-legend">
                    {severityData.map((item, index) => <span key={item.name}><i style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} />{item.name}: {item.value}</span>)}
                  </div>
                </div>
              ) : <EmptyChart message="No severity-classified open findings are available." />}
            </DashboardPanel>

            <DashboardPanel title="Risk matrix" subtitle="Current risk register distribution" action={<button type="button" onClick={() => go(`/maintenance/${encodeURIComponent(amoCode)}/quality/risk/risk-matrix`)}>Open register <ArrowRight size={14} /></button>}>
              {riskCounters ? (
                <div className="qms-risk-matrix" role="table" aria-label="Risk matrix summary">
                  <div className="qms-risk-matrix__corner" />
                  <div>Low</div><div>Medium</div><div>High</div>
                  <strong>Low</strong><span className="is-low">{riskCounters.low}</span><span className="is-low">—</span><span className="is-medium">—</span>
                  <strong>Medium</strong><span className="is-low">—</span><span className="is-medium">{riskCounters.medium}</span><span className="is-high">—</span>
                  <strong>High</strong><span className="is-medium">—</span><span className="is-high">{riskCounters.high}</span><span className="is-critical">{riskCounters.critical}</span>
                </div>
              ) : <EmptyChart message="Risk matrix counters are not yet exposed by the dashboard source." />}
            </DashboardPanel>

            <DashboardPanel title="Overdue CAR aging" subtitle="Age of currently overdue corrective actions">
              {agingData.some((item) => item.value > 0) ? (
                <div className="qms-dashboard-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={agingData} margin={{ top: 8, right: 10, left: -24, bottom: 0 }}>
                      <CartesianGrid stroke="var(--qms-grid)" vertical={false} />
                      <XAxis dataKey="bucket" tick={{ fontSize: 11, fill: "var(--qms-muted)" }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--qms-muted)" }} />
                      <Tooltip />
                      <Bar dataKey="value" fill="var(--qms-chart-2)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <EmptyChart message="No overdue CAR aging data is available." />}
            </DashboardPanel>

            <DashboardPanel title="Performance indicators" subtitle="Current performance against available targets" className="qms-dashboard-panel--span-2">
              {performanceData.length ? (
                <div className="qms-dashboard-chart qms-dashboard-chart--wide">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={performanceData} layout="vertical" margin={{ top: 4, right: 20, left: 16, bottom: 4 }}>
                      <CartesianGrid stroke="var(--qms-grid)" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 10, fill: "var(--qms-muted)" }} />
                      <YAxis type="category" dataKey="name" width={145} tick={{ fontSize: 10, fill: "var(--qms-muted)" }} />
                      <Tooltip formatter={(value, _name, item) => [`${value}${item.payload.unit === "%" ? "%" : item.payload.unit ? ` ${item.payload.unit}` : ""}`, "Current"]} />
                      <Bar dataKey="value" fill="var(--qms-chart-1)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <EmptyChart message="Performance values are not yet available from the source records." />}
              <KpiTable items={dashboard.performance_kpis} onNavigate={go} />
            </DashboardPanel>

            <DashboardPanel title="My Quality work" subtitle="Assigned and unread work" action={<button type="button" onClick={() => go(routes.myWork)}>Open inbox <ArrowRight size={14} /></button>}>
              <WorkList items={dashboard.my_work} onNavigate={go} empty="No assigned Quality work is currently listed." />
            </DashboardPanel>

            <DashboardPanel title="Upcoming obligations" subtitle="Next 30 days" className="qms-dashboard-panel--span-2" action={<button type="button" onClick={() => go(routes.calendar)}>Open calendar <ArrowRight size={14} /></button>}>
              <ObligationList items={dashboard.upcoming_obligations} onNavigate={go} />
            </DashboardPanel>

            <QmsDiagnosticsDrawer dashboard={dashboard} authorized={diagnosticsAuthorized} />
          </main>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
