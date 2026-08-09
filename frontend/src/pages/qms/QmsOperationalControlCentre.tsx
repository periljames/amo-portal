import React, { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  DatabaseZap,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
} from "lucide-react";
import { Link } from "react-router-dom";

import { getCachedUser } from "../../services/auth";
import { getQmsOperationalDashboard } from "../../services/qmsDashboard";
import QmsActionQueue from "./components/QmsActionQueue";
import QmsDiagnosticsDrawer from "./components/QmsDiagnosticsDrawer";
import QmsMyWork from "./components/QmsMyWork";
import QmsPerformanceSummary from "./components/QmsPerformanceSummary";
import QmsUpcomingObligations from "./components/QmsUpcomingObligations";
import { buildQmsOverviewRoutes, qmsTimestampLabel } from "./qmsOverviewModel";
import "../../styles/qms-assurance-control-room.css";

function countQueue(items: Array<{ count: number }>): number {
  return items.reduce((total, item) => total + Math.max(0, Number(item.count) || 0), 0);
}

function sumKnownCounts(values: Record<string, number | null> | undefined): number {
  return Object.values(values || {}).reduce<number>((total, value) => total + Math.max(0, Number(value) || 0), 0);
}

const QmsOperationalControlCentre: React.FC<{ amoCode: string }> = ({ amoCode }) => {
  const queryClient = useQueryClient();
  const routes = useMemo(() => buildQmsOverviewRoutes(amoCode), [amoCode]);
  const currentUser = getCachedUser();
  const diagnosticsAuthorized = Boolean(
    currentUser?.is_superuser
    || currentUser?.is_amo_admin
    || currentUser?.role === "QUALITY_MANAGER"
    || currentUser?.role === "QUALITY_INSPECTOR",
  );

  const dashboardQuery = useQuery({
    queryKey: ["qms-operational-dashboard-v2", amoCode],
    queryFn: ({ signal }) => getQmsOperationalDashboard(amoCode, signal),
    staleTime: 20_000,
    refetchOnWindowFocus: true,
  });

  const dashboard = dashboardQuery.data;
  const queueCount = countQueue(dashboard?.action_queue || []);
  const regulatorySignals = (dashboard?.action_queue || []).filter((item) => Boolean(item.regulatory_consequence?.trim()));
  const regulatoryExposureCount = countQueue(regulatorySignals);
  const unassignedCount = sumKnownCounts(dashboard?.unassigned_counts);
  const availableKpis = (dashboard?.performance_kpis || []).filter((item) => item.data_status === "available").length;
  const deterioratingKpis = (dashboard?.performance_kpis || []).filter((item) => item.data_status === "available" && item.direction === "deteriorating").length;
  const sourceStatus = dashboard?.source_health.status || "unavailable";
  const sourceLabel = sourceStatus === "healthy" ? "Healthy" : sourceStatus === "partial" ? "Partial" : "Unavailable";

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-operational-dashboard-v2", amoCode] });
  };

  return (
    <main className="qms-assurance-room" aria-label="Quality Assurance Control Room">
      <header className="qms-assurance-room__header">
        <div>
          <span className="qms-assurance-room__eyebrow"><ShieldCheck size={15} aria-hidden="true" /> Quality assurance operating picture</span>
          <h1>Control Room</h1>
          <p>Prioritise emerging assurance signals, decisions and obligations without duplicating the operational records that own the evidence.</p>
        </div>
        <div className="qms-assurance-room__header-actions">
          <span className={`qms-assurance-room__source qms-source--${sourceStatus}`}>
            <DatabaseZap size={14} aria-hidden="true" />
            <span><strong>{sourceLabel}</strong><small>{dashboard ? qmsTimestampLabel(dashboard.as_of) : "Refreshing sources"}</small></span>
          </span>
          <button type="button" className="qms-assurance-room__button" onClick={() => void refresh()} disabled={dashboardQuery.isFetching}>
            <RefreshCw size={15} className={dashboardQuery.isFetching ? "is-spinning" : ""} aria-hidden="true" /> Refresh
          </button>
          <Link className="qms-assurance-room__button is-primary" to={routes.calendar}>
            <CalendarClock size={15} aria-hidden="true" /> Open planner
          </Link>
        </div>
      </header>

      {dashboardQuery.isLoading && !dashboard ? (
        <section className="qms-assurance-room__loading" role="status">
          <RefreshCw size={18} className="is-spinning" aria-hidden="true" /> Building the assurance picture…
        </section>
      ) : null}

      {dashboardQuery.error ? (
        <section className="qms-assurance-room__alert" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <div><strong>Assurance picture unavailable</strong><p>{dashboardQuery.error instanceof Error ? dashboardQuery.error.message : "The current Quality operating picture could not be loaded."}</p></div>
          <button type="button" onClick={() => void dashboardQuery.refetch()}>Retry</button>
        </section>
      ) : null}

      {dashboard ? (
        <>
          <section className="qms-assurance-room__summary" aria-label="Quality assurance summary">
            <Link to={routes.myWork}>
              <span>My decisions & work</span>
              <strong>{dashboard.my_work.length.toLocaleString()}</strong>
              <small>items currently assigned to the logged-in user</small>
            </Link>
            <article>
              <span>Priority signals</span>
              <strong>{dashboard.action_queue.length.toLocaleString()}</strong>
              <small>{queueCount.toLocaleString()} underlying exception{queueCount === 1 ? "" : "s"}</small>
            </article>
            <article className={regulatoryExposureCount ? "is-attention" : ""}>
              <span>Regulatory consequence</span>
              <strong>{regulatorySignals.length.toLocaleString()}</strong>
              <small>{regulatoryExposureCount ? `${regulatoryExposureCount.toLocaleString()} records carry an explicit consequence` : "No explicit regulatory consequence returned"}</small>
            </article>
            <Link to={routes.calendar}>
              <span>Next 30 days</span>
              <strong>{dashboard.upcoming_obligations.length.toLocaleString()}</strong>
              <small>scheduled obligations in the current feed</small>
            </Link>
          </section>

          <section className="qms-assurance-room__section-heading">
            <div><Sparkles size={16} aria-hidden="true" /><span><strong>Attention now</strong><small>Signals are ranked from authoritative source records. Open the governed source to investigate or act.</small></span></div>
          </section>

          <div className="qms-assurance-room__primary-grid">
            <QmsActionQueue amoCode={amoCode} items={dashboard.action_queue} fallbackRoute={routes.myWork} />
            <QmsUpcomingObligations amoCode={amoCode} items={dashboard.upcoming_obligations} fallbackRoute={routes.calendar} />
          </div>

          <div className="qms-assurance-room__secondary-grid">
            <QmsMyWork amoCode={amoCode} items={dashboard.my_work} fallbackRoute={routes.myWork} />
            <QmsPerformanceSummary amoCode={amoCode} items={dashboard.performance_kpis} fallbackRoute={routes.reports} />
          </div>

          <section className="qms-assurance-room__control-health" aria-label="Assurance control health">
            <header>
              <div><ShieldCheck size={16} aria-hidden="true" /><span><strong>Assurance health</strong><small>Coverage and data conditions that affect the confidence of this view.</small></span></div>
              <Link to={routes.reports}>Open intelligence <ArrowRight size={14} aria-hidden="true" /></Link>
            </header>
            <div>
              <article className={`qms-source--${sourceStatus}`}>
                <span>Source coverage</span>
                <strong>{sourceLabel}</strong>
                <small>{dashboard.source_health.error_count ? `${dashboard.source_health.error_count} source issue${dashboard.source_health.error_count === 1 ? "" : "s"}` : "No source errors returned"}</small>
              </article>
              <article className={unassignedCount ? "is-attention" : ""}>
                <span>Unassigned exposure</span>
                <strong>{unassignedCount.toLocaleString()}</strong>
                <small>{unassignedCount ? "items have no explicit owner in returned source counts" : "No unassigned source count returned"}</small>
              </article>
              <article className={deterioratingKpis ? "is-attention" : ""}>
                <span>Performance drift</span>
                <strong>{deterioratingKpis.toLocaleString()}</strong>
                <small>{availableKpis ? `${availableKpis} KPI${availableKpis === 1 ? "" : "s"} have usable data` : "No performance KPI data available"}</small>
              </article>
              <article>
                <span>Evidence freshness</span>
                <strong>{dashboard.data_freshness?.generated_at ? qmsTimestampLabel(dashboard.data_freshness.generated_at) : "Not reported"}</strong>
                <small>{dashboard.data_freshness?.counter_source || "Dashboard source timestamp"}</small>
              </article>
            </div>
          </section>

          {!dashboard.action_queue.length && !dashboard.my_work.length ? (
            <div className="qms-assurance-room__quiet" role="status"><CheckCircle2 size={18} /><span>No ranked signal or assigned work was returned. Scheduled assurance obligations and performance remain visible above.</span></div>
          ) : null}

          <section className="qms-assurance-room__governance-note">
            <UserRoundCheck size={17} aria-hidden="true" />
            <div><strong>Human-governed assurance</strong><span>Analytics may rank, compare and explain. Acceptance, authorization, root-cause approval, effectiveness verification and closure remain explicit human decisions in the governed source workflow.</span></div>
          </section>

          <details className="qms-assurance-room__diagnostics" id="qms-control-centre-diagnostics">
            <summary>Data health & diagnostics</summary>
            <QmsDiagnosticsDrawer dashboard={dashboard} authorized={diagnosticsAuthorized} />
          </details>
        </>
      ) : null}
    </main>
  );
};

export default QmsOperationalControlCentre;
