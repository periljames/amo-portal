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
  const usableKpis = (dashboard?.performance_kpis || []).filter((item) => item.data_status === "available");
  const availableKpis = usableKpis.length;
  const deterioratingKpis = usableKpis.filter((item) => item.direction === "deteriorating").length;
  const sourceStatus = dashboard?.source_health.status || "unavailable";
  const sourceLabel = sourceStatus === "healthy" ? "Healthy" : sourceStatus === "partial" ? "Partial" : "Unavailable";
  const hasAttention = Boolean(dashboard?.action_queue.length || dashboard?.upcoming_obligations.length);
  const hasAssignedWork = Boolean(dashboard?.my_work.length);
  const hasSummary = Boolean(hasAssignedWork || dashboard?.action_queue.length || regulatorySignals.length || dashboard?.upcoming_obligations.length);
  const hasControlHealthIssue = sourceStatus !== "healthy" || unassignedCount > 0 || deterioratingKpis > 0;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-operational-dashboard-v2", amoCode] });
  };

  return (
    <main className="qms-assurance-room" aria-label="Quality Assurance Control Room">
      <header className="qms-assurance-room__header">
        <div>
          <span className="qms-assurance-room__eyebrow"><ShieldCheck size={15} aria-hidden="true" /> Quality assurance</span>
          <h1>Control Room</h1>
          <p>Current Quality work, exceptions and upcoming obligations.</p>
        </div>
        <div className="qms-assurance-room__header-actions">
          <span className={`qms-assurance-room__source qms-source--${sourceStatus}`}>
            <DatabaseZap size={14} aria-hidden="true" />
            <span><strong>{sourceLabel}</strong><small>{dashboard ? qmsTimestampLabel(dashboard.as_of) : "Refreshing"}</small></span>
          </span>
          <button type="button" className="qms-assurance-room__button" onClick={() => void refresh()} disabled={dashboardQuery.isFetching}>
            <RefreshCw size={15} className={dashboardQuery.isFetching ? "is-spinning" : ""} aria-hidden="true" /> Refresh
          </button>
          <Link className="qms-assurance-room__button is-primary" to={routes.calendar}>
            <CalendarClock size={15} aria-hidden="true" /> Planner
          </Link>
        </div>
      </header>

      {dashboardQuery.isLoading && !dashboard ? (
        <section className="qms-assurance-room__loading" role="status">
          <RefreshCw size={18} className="is-spinning" aria-hidden="true" /> Loading current Quality work…
        </section>
      ) : null}

      {dashboardQuery.error ? (
        <section className="qms-assurance-room__alert" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <div><strong>Control Room unavailable</strong><p>{dashboardQuery.error instanceof Error ? dashboardQuery.error.message : "The current Quality work queue could not be loaded."}</p></div>
          <button type="button" onClick={() => void dashboardQuery.refetch()}>Retry</button>
        </section>
      ) : null}

      {dashboard ? (
        <>
          {hasSummary ? (
            <section className="qms-assurance-room__summary" aria-label="Quality action summary">
              {hasAssignedWork ? (
                <Link to={routes.myWork}>
                  <span>My decisions & work</span>
                  <strong>{dashboard.my_work.length.toLocaleString()}</strong>
                  <small>assigned items</small>
                </Link>
              ) : null}
              {dashboard.action_queue.length ? (
                <article>
                  <span>Priority signals</span>
                  <strong>{dashboard.action_queue.length.toLocaleString()}</strong>
                  <small>{queueCount.toLocaleString()} underlying exception{queueCount === 1 ? "" : "s"}</small>
                </article>
              ) : null}
              {regulatorySignals.length ? (
                <article className="is-attention">
                  <span>Regulatory consequence</span>
                  <strong>{regulatorySignals.length.toLocaleString()}</strong>
                  <small>{regulatoryExposureCount.toLocaleString()} affected record{regulatoryExposureCount === 1 ? "" : "s"}</small>
                </article>
              ) : null}
              {dashboard.upcoming_obligations.length ? (
                <Link to={routes.calendar}>
                  <span>Next 30 days</span>
                  <strong>{dashboard.upcoming_obligations.length.toLocaleString()}</strong>
                  <small>scheduled obligations</small>
                </Link>
              ) : null}
            </section>
          ) : null}

          {hasAttention ? (
            <>
              <section className="qms-assurance-room__section-heading">
                <div><Sparkles size={16} aria-hidden="true" /><span><strong>Attention now</strong></span></div>
              </section>
              <div className="qms-assurance-room__primary-grid">
                {dashboard.action_queue.length ? <QmsActionQueue amoCode={amoCode} items={dashboard.action_queue} fallbackRoute={routes.myWork} /> : null}
                {dashboard.upcoming_obligations.length ? (
                  <QmsUpcomingObligations
                    amoCode={amoCode}
                    items={dashboard.upcoming_obligations}
                    fallbackRoute={routes.calendar}
                    referenceDate={new Date(dashboard.as_of)}
                  />
                ) : null}
              </div>
            </>
          ) : null}

          {hasAssignedWork || availableKpis ? (
            <div className="qms-assurance-room__secondary-grid">
              {hasAssignedWork ? <QmsMyWork amoCode={amoCode} items={dashboard.my_work} fallbackRoute={routes.myWork} /> : null}
              {availableKpis ? <QmsPerformanceSummary amoCode={amoCode} items={usableKpis} fallbackRoute={routes.reports} /> : null}
            </div>
          ) : null}

          {hasControlHealthIssue ? (
            <section className="qms-assurance-room__control-health" aria-label="Assurance control issues">
              <header>
                <div><ShieldCheck size={16} aria-hidden="true" /><span><strong>Control issues</strong></span></div>
                <Link to={routes.reports}>Open intelligence <ArrowRight size={14} aria-hidden="true" /></Link>
              </header>
              <div>
                {sourceStatus !== "healthy" ? (
                  <article className={`qms-source--${sourceStatus}`}>
                    <span>Source coverage</span>
                    <strong>{sourceLabel}</strong>
                    <small>{dashboard.source_health.error_count ? `${dashboard.source_health.error_count} source issue${dashboard.source_health.error_count === 1 ? "" : "s"}` : "Source coverage needs review"}</small>
                  </article>
                ) : null}
                {unassignedCount ? (
                  <article className="is-attention">
                    <span>Unassigned exposure</span>
                    <strong>{unassignedCount.toLocaleString()}</strong>
                    <small>items need an owner</small>
                  </article>
                ) : null}
                {deterioratingKpis ? (
                  <article className="is-attention">
                    <span>Performance drift</span>
                    <strong>{deterioratingKpis.toLocaleString()}</strong>
                    <small>usable KPI{deterioratingKpis === 1 ? "" : "s"} deteriorating</small>
                  </article>
                ) : null}
              </div>
            </section>
          ) : null}

          {!hasAttention && !hasAssignedWork && !availableKpis && !hasControlHealthIssue ? (
            <div className="qms-assurance-room__quiet" role="status"><CheckCircle2 size={18} /><span>No current Quality action requires attention.</span></div>
          ) : null}

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
