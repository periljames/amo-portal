import React, { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Command,
  RefreshCw,
  ShieldCheck,
  Target,
  UserRound,
  UsersRound,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import Drawer from "../../components/shared/Drawer";
import { getContext } from "../../services/auth";
import {
  cockpitDrilldownHref,
  getAssuranceCockpit,
  getUnscheduledProgrammeRequirements,
  type AssuranceCockpitDrilldown,
  type AssuranceViewContext,
} from "../../services/assuranceCockpit";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import "./assurance-cockpit.css";

type MetricCard = {
  id: string;
  label: string;
  value: string;
  helper: string;
  tone: "neutral" | "good" | "warn" | "danger" | "info";
  drilldown?: AssuranceCockpitDrilldown;
};

const PIPELINE_ORDER = ["PLANNED", "IN_PROGRESS", "CAP_OPEN", "CLOSED"];

function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatPercent(value: number | undefined): string {
  return `${Number(value || 0).toFixed(1)}%`;
}

function labelize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMonth(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", timeZone: "UTC" });
}

function formatDate(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

function readinessCopy(band: string): string {
  if (band === "STRONG") return "Assurance controls are operating within the current monitoring thresholds.";
  if (band === "WATCH") return "Some assurance pressure requires active monitoring.";
  if (band === "AT_RISK") return "Multiple assurance conditions require intervention.";
  return "Immediate management attention is required.";
}

const QualityAuditAssuranceDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const currentYear = new Date().getFullYear();
  const rawView = searchParams.get("view");
  const view: AssuranceViewContext = rawView === "mine" ? "mine" : "global";
  const rawPeriod = Number(searchParams.get("period") || currentYear);
  const period = Number.isFinite(rawPeriod) && rawPeriod >= 2000 && rawPeriod <= 2200 ? rawPeriod : currentYear;
  const drawer = searchParams.get("drawer");
  const unscheduledDrawerOpen = drawer === "unscheduled-requirements";

  const cockpitQuery = useQuery({
    queryKey: ["qms-assurance-cockpit", amoCode, view, period],
    queryFn: () => getAssuranceCockpit(amoCode, { view, period }),
    staleTime: 30_000,
  });

  const unscheduledQuery = useQuery({
    queryKey: ["qms-assurance-unscheduled", amoCode, view, period],
    queryFn: () => getUnscheduledProgrammeRequirements(amoCode, { view, period, limit: 50 }),
    enabled: unscheduledDrawerOpen,
    staleTime: 15_000,
  });

  const data = cockpitQuery.data;
  const metrics = data?.metrics ?? {};

  const setContext = (nextView: AssuranceViewContext) => {
    const next = new URLSearchParams(searchParams);
    next.set("view", nextView);
    next.set("period", String(period));
    next.delete("drawer");
    setSearchParams(next, { replace: false });
  };

  const setPeriod = (nextPeriod: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("period", String(nextPeriod));
    next.set("view", view);
    next.delete("drawer");
    setSearchParams(next, { replace: false });
  };

  const openDrawer = (drawerId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("drawer", drawerId);
    setSearchParams(next, { replace: false });
  };

  const closeDrawer = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("drawer");
    setSearchParams(next, { replace: true });
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-assurance-cockpit", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-assurance-unscheduled", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-calendar"] }),
    ]);
  };

  const go = (drilldown?: AssuranceCockpitDrilldown) => {
    if (!drilldown) return;
    if (drilldown.drawer) {
      openDrawer(drilldown.drawer);
      return;
    }
    const href = cockpitDrilldownHref(drilldown);
    if (href) navigate(href);
  };

  const metricCards = useMemo<MetricCard[]>(() => {
    if (!data) return [];
    const openFindings = Number(metrics.open_findings || 0);
    const overdueCars = Number(metrics.overdue_cars || 0);
    const unscheduled = Number(metrics.programme_requirements_unscheduled || 0);
    return [
      {
        id: "programme_coverage_pct",
        label: "Programme coverage",
        value: formatPercent(metrics.programme_coverage_pct),
        helper: `${formatNumber(metrics.programme_requirements_scheduled)} of ${formatNumber(metrics.programme_requirements_total)} requirements scheduled`,
        tone: unscheduled ? "warn" : "good",
        drilldown: data.drilldowns.programme_coverage_pct,
      },
      {
        id: "programme_requirements_unscheduled",
        label: "Unscheduled",
        value: formatNumber(unscheduled),
        helper: unscheduled ? "Programme requirements awaiting Planner commitment" : "No programme scheduling gaps",
        tone: unscheduled ? "warn" : "good",
        drilldown: data.drilldowns.programme_requirements_unscheduled,
      },
      {
        id: "audit_completion_pct",
        label: "Audit completion",
        value: formatPercent(metrics.audit_completion_pct),
        helper: `${formatNumber(metrics.closed_audits)} closed · ${formatNumber(metrics.open_audits)} open`,
        tone: Number(metrics.open_audits || 0) ? "info" : "good",
        drilldown: data.drilldowns.audit_completion_pct,
      },
      {
        id: "open_findings",
        label: "Open findings",
        value: formatNumber(openFindings),
        helper: openFindings ? "Current unresolved assurance findings" : "Finding queue clear",
        tone: openFindings ? "warn" : "good",
        drilldown: data.drilldowns.open_findings,
      },
      {
        id: "overdue_cars",
        label: "Overdue CARs",
        value: formatNumber(overdueCars),
        helper: `${formatNumber(metrics.open_cars)} open corrective actions`,
        tone: overdueCars ? "danger" : Number(metrics.open_cars || 0) ? "info" : "good",
        drilldown: data.drilldowns.overdue_cars,
      },
      {
        id: "controls_due",
        label: "Controls due",
        value: formatNumber(metrics.controls_due),
        helper: `${formatNumber(metrics.active_controls)} active assurance controls`,
        tone: Number(metrics.controls_due || 0) ? "warn" : "good",
        drilldown: { path: `/maintenance/${amoCode}/quality`, query: { hub: "controls" } },
      },
    ];
  }, [amoCode, data, metrics]);

  const pipeline = useMemo(() => {
    const lookup = new Map((data?.audit_pipeline || []).map((row) => [row.status, Number(row.count || 0)]));
    return PIPELINE_ORDER.map((status) => ({ status, count: lookup.get(status) || 0 }));
  }, [data?.audit_pipeline]);

  const findingTrend = useMemo(
    () => (data?.finding_trend || []).map((row) => ({ ...row, label: formatMonth(row.month) })),
    [data?.finding_trend],
  );

  const closureAgeing = useMemo(
    () => (data?.closure_ageing || []).map((row) => ({
      ...row,
      label: row.bucket === "not_due" ? "Not due" : row.bucket === "over_90" ? ">90d" : row.bucket.replace("_", "–") + "d",
    })),
    [data?.closure_ageing],
  );

  const toolbar = (
    <div className="assurance-cockpit__toolbar">
      <label className="assurance-cockpit__period">
        <span>Period</span>
        <select value={period} onChange={(event) => setPeriod(Number(event.target.value))}>
          {[currentYear - 2, currentYear - 1, currentYear, currentYear + 1].map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
      </label>
      <div className="assurance-context-toggle" role="group" aria-label="Assurance data scope">
        <button type="button" className={view === "global" ? "is-active" : undefined} onClick={() => setContext("global")}><UsersRound size={15} /> Global</button>
        <button type="button" className={view === "mine" ? "is-active" : undefined} onClick={() => setContext("mine")}><UserRound size={15} /> My Work</button>
      </div>
      <button type="button" className="assurance-command-trigger" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}>
        <Command size={15} /> Search <kbd>Ctrl K</kbd>
      </button>
      <button type="button" className="assurance-refresh" onClick={() => void refresh()} disabled={cockpitQuery.isFetching}>
        <RefreshCw size={15} className={cockpitQuery.isFetching ? "is-spinning" : undefined} /> Refresh
      </button>
    </div>
  );

  return (
    <QualityAuditsSectionLayout
      title="Audit Assurance"
      subtitle="Live assurance health, delivery, exposure and corrective-action control."
      toolbar={toolbar}
    >
      <main className="assurance-cockpit" data-view-context={view}>
        {cockpitQuery.isLoading ? <div className="assurance-cockpit__loading">Building the live assurance picture…</div> : null}
        {cockpitQuery.error ? (
          <div className="assurance-cockpit__error" role="alert">
            <AlertTriangle size={18} />
            <div><strong>Unable to load the Assurance cockpit</strong><span>{cockpitQuery.error instanceof Error ? cockpitQuery.error.message : "The live assurance projection is unavailable."}</span></div>
          </div>
        ) : null}

        {data ? (
          <>
            <section className={`assurance-health assurance-health--${data.readiness.band.toLowerCase()}`}>
              <div className="assurance-health__identity">
                <span className="assurance-health__eyebrow"><ShieldCheck size={15} /> {view === "mine" ? "My assurance position" : "AMO assurance position"}</span>
                <div className="assurance-health__headline">
                  <strong>{data.readiness.score}%</strong>
                  <div><h2>{labelize(data.readiness.band)}</h2><p>{readinessCopy(data.readiness.band)}</p></div>
                </div>
                <small>{data.readiness.disclaimer}</small>
              </div>
              <div className="assurance-health__signals">
                <div><span>Priority actions</span><strong>{formatNumber(data.priority_queue.length)}</strong></div>
                <div><span>Overdue CARs</span><strong>{formatNumber(metrics.overdue_cars)}</strong></div>
                <div><span>Open regulator findings</span><strong>{formatNumber(metrics.open_regulator_findings)}</strong></div>
                <div><span>Updated</span><strong>{new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</strong></div>
              </div>
            </section>

            <section className="assurance-kpi-grid" aria-label="Assurance headline metrics">
              {metricCards.map((card) => (
                <button key={card.id} type="button" className={`assurance-kpi assurance-kpi--${card.tone}`} onClick={() => go(card.drilldown)}>
                  <span className="assurance-kpi__label">{card.label}</span>
                  <strong>{card.value}</strong>
                  <small>{card.helper}</small>
                  <span className="assurance-kpi__open">Open <ArrowRight size={13} /></span>
                </button>
              ))}
            </section>

            <section className="assurance-cockpit__grid assurance-cockpit__grid--primary">
              <article className="assurance-panel assurance-panel--trend">
                <header><div><span>Finding intelligence</span><h3>Findings trend</h3><p>Finding creation by severity for the selected period.</p></div><button type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/register?tab=findings&period=${period}&view=${view}`)}>Open register <ArrowRight size={13} /></button></header>
                {findingTrend.length ? (
                  <div className="assurance-chart assurance-chart--large">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={findingTrend} margin={{ top: 12, right: 12, left: -20, bottom: 0 }}>
                        <CartesianGrid vertical={false} stroke="var(--qms-line-soft, #e2e8f0)" />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={11} />
                        <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={11} />
                        <Tooltip />
                        <Area type="monotone" dataKey="level_1" name="Level 1" stackId="findings" stroke="var(--assurance-critical, #dc2626)" fill="var(--assurance-critical-soft, #fee2e2)" />
                        <Area type="monotone" dataKey="level_2" name="Level 2" stackId="findings" stroke="var(--assurance-major, #d97706)" fill="var(--assurance-major-soft, #fef3c7)" />
                        <Area type="monotone" dataKey="level_3" name="Level 3" stackId="findings" stroke="var(--accent-primary, #2563eb)" fill="var(--assurance-minor-soft, #dbeafe)" />
                        <Area type="monotone" dataKey="observations" name="Observations" stackId="findings" stroke="var(--assurance-observation, #059669)" fill="var(--assurance-observation-soft, #d1fae5)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : <div className="assurance-empty"><CheckCircle2 size={22} /><strong>No finding trend for {period}</strong><span>No findings have been recorded in the selected scope and period.</span></div>}
              </article>

              <article className="assurance-panel assurance-panel--actions">
                <header><div><span>Action centre</span><h3>{view === "mine" ? "My priority queue" : "Management attention"}</h3><p>Ranked from live assurance conditions.</p></div></header>
                <div className="assurance-action-list">
                  {data.priority_queue.length ? data.priority_queue.slice(0, 7).map((item) => (
                    <button key={item.id} type="button" onClick={() => {
                      if (item.id === "programme-unscheduled") openDrawer("unscheduled-requirements");
                      else navigate(item.path);
                    }}>
                      <span className={`assurance-priority assurance-priority--${item.severity.toLowerCase()}`}>{item.severity}</span>
                      <span className="assurance-action-list__copy"><strong>{item.label}</strong><small>{item.why}</small></span>
                      <b>{item.count}</b><ArrowRight size={14} />
                    </button>
                  )) : (
                    <div className="assurance-inbox-zero"><CheckCircle2 size={24} /><strong>{view === "mine" ? "You're clear" : "Priority queue clear"}</strong><span>No current conditions require action in this scope.</span></div>
                  )}
                </div>
              </article>
            </section>

            <section className="assurance-cockpit__grid assurance-cockpit__grid--secondary">
              <article className="assurance-panel">
                <header><div><span>Exposure</span><h3>Risk by control category</h3><p>Open finding concentration by available control classification.</p></div></header>
                {data.control_exposure.length ? (
                  <div className="assurance-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.control_exposure} layout="vertical" margin={{ top: 6, right: 16, left: 12, bottom: 0 }}>
                        <CartesianGrid horizontal={false} stroke="var(--qms-line-soft, #e2e8f0)" />
                        <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} fontSize={10} />
                        <YAxis type="category" dataKey="category" width={116} tickLine={false} axisLine={false} fontSize={10} />
                        <Tooltip />
                        <Bar dataKey="count" name="Open findings" fill="var(--accent-primary, #2563eb)" radius={[0, 5, 5, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : <div className="assurance-empty assurance-empty--compact"><Target size={20} /><strong>No categorized exposure</strong><span>Open findings are clear or no control category is available.</span></div>}
              </article>

              <article className="assurance-panel">
                <header><div><span>Closeout discipline</span><h3>CAR ageing</h3><p>Open corrective actions by due-state and overdue age.</p></div><button type="button" onClick={() => go(data.drilldowns.open_cars)}>Open CARs <ArrowRight size={13} /></button></header>
                <div className="assurance-ageing">
                  {closureAgeing.map((item) => <button key={item.bucket} type="button" onClick={() => go(item.bucket === "not_due" ? data.drilldowns.open_cars : data.drilldowns.overdue_cars)}><strong>{item.count}</strong><span>{item.label}</span></button>)}
                </div>
              </article>

              <article className="assurance-panel">
                <header><div><span>Delivery</span><h3>Audit pipeline</h3><p>Current audit occurrence state in the selected scope.</p></div></header>
                <div className="assurance-pipeline">
                  {pipeline.map((item, index) => (
                    <button key={item.status} type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits?status=${item.status}&period=${period}&view=${view}`)}>
                      <span>{index + 1}</span><strong>{item.count}</strong><small>{labelize(item.status)}</small>
                    </button>
                  ))}
                </div>
              </article>
            </section>

            <section className="assurance-readiness-panel">
              <header><div><span>Readiness dimensions</span><h3>What is driving the assurance position?</h3></div><small>{view === "mine" ? "Personal scope where an attributable owner/participant exists; otherwise tenant-wide indicators remain governed by source availability." : "Tenant-wide live source projection."}</small></header>
              <div className="assurance-readiness-grid">
                {data.readiness.dimensions.map((dimension) => (
                  <div key={dimension.id}><span>{dimension.label}</span><div><i style={{ width: `${dimension.score}%` }} /></div><strong>{dimension.score}%</strong></div>
                ))}
              </div>
            </section>

            {data.warnings.length ? <details className="assurance-source-warnings"><summary>{data.warnings.length} source warning{data.warnings.length === 1 ? "" : "s"}</summary><ul>{data.warnings.slice(0, 12).map((warning, index) => <li key={`${warning.source}-${index}`}><strong>{warning.source}</strong> — {warning.message}</li>)}</ul></details> : null}
          </>
        ) : null}
      </main>

      <Drawer title="Unscheduled programme requirements" isOpen={unscheduledDrawerOpen} onClose={closeDrawer} panelClassName="assurance-unscheduled-drawer">
        <div className="assurance-unscheduled-drawer__body">
          <p>Commit governed programme requirements to the authoritative Planner without losing your place in the Assurance cockpit.</p>
          {unscheduledQuery.isLoading ? <div className="assurance-cockpit__loading">Loading programme gaps…</div> : null}
          {unscheduledQuery.error ? <div className="assurance-cockpit__error"><AlertTriangle size={17} /><span>Unable to load unscheduled requirements.</span></div> : null}
          <div className="assurance-unscheduled-list">
            {(unscheduledQuery.data?.items || []).map((item) => (
              <article key={item.id}>
                <div className="assurance-unscheduled-list__top"><span>{item.audit_type.replaceAll("_", " ")}</span>{item.mandatory_surveillance ? <b>Mandatory</b> : null}</div>
                <h4>{item.title}</h4>
                <p>{item.programme_ref} · {item.programme_title}</p>
                <dl>
                  <div><dt>Target</dt><dd>{formatDate(item.target_start)}{item.target_end ? ` – ${formatDate(item.target_end)}` : ""}</dd></div>
                  <div><dt>Duration</dt><dd>{item.default_duration_days} day{item.default_duration_days === 1 ? "" : "s"}</dd></div>
                  <div><dt>Location</dt><dd>{item.default_location || "Not set"}</dd></div>
                  <div><dt>Lead</dt><dd>{item.lead_auditor_user_id ? "Assigned" : "Unassigned"}</dd></div>
                </dl>
                <div className="assurance-unscheduled-list__actions">
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/calendar/week?focusRequirementId=${encodeURIComponent(item.id)}`)}><CalendarClock size={14} /> Schedule in Planner</button>
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/program?focusId=${encodeURIComponent(item.programme_id)}`)}>Open programme <ArrowRight size={13} /></button>
                </div>
              </article>
            ))}
          </div>
          {!unscheduledQuery.isLoading && !unscheduledQuery.error && (unscheduledQuery.data?.items.length || 0) === 0 ? <div className="assurance-inbox-zero"><CheckCircle2 size={24} /><strong>No unscheduled requirements</strong><span>The selected programme scope is fully committed to the Planner.</span></div> : null}
        </div>
      </Drawer>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditAssuranceDashboardPage;
