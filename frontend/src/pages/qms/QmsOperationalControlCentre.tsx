import React, { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarPlus,
  CheckCircle2,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Target,
} from "lucide-react";
import { Link } from "react-router-dom";

import { getCachedUser } from "../../services/auth";
import { getQmsOperationalDashboard } from "../../services/qmsDashboard";
import QmsActionQueue from "./components/QmsActionQueue";
import QmsDiagnosticsDrawer from "./components/QmsDiagnosticsDrawer";
import QmsMyWork from "./components/QmsMyWork";
import QmsPerformanceSummary from "./components/QmsPerformanceSummary";
import QmsUpcomingObligations from "./components/QmsUpcomingObligations";
import { buildQmsOverviewRoutes, deriveQmsOverviewHealth, qmsTimestampLabel } from "./qmsOverviewModel";
import "../../styles/qms-operational-control-centre.css";

function countQueue(items: Array<{ count: number }>): number {
  return items.reduce((total, item) => total + Math.max(0, Number(item.count) || 0), 0);
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
  const health = deriveQmsOverviewHealth(dashboard);
  const queueCount = countQueue(dashboard?.action_queue || []);
  const sourceHealthy = dashboard?.source_health.status === "healthy";

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-operational-dashboard-v2", amoCode] });
  };

  return (
    <main className="qms-control-centre" aria-label="Quality operational control centre">
      <header className="qms-control-centre__header">
        <div className="qms-control-centre__identity">
          <span className="qms-control-centre__eyebrow"><ShieldCheck size={15} aria-hidden="true" /> Quality operations</span>
          <div>
            <h1>Control Centre</h1>
            <p>Prioritised work, obligations and performance. Open the governed source workflow to investigate or act.</p>
          </div>
        </div>
        <div className="qms-control-centre__header-actions">
          <span className={`qms-control-centre__posture qms-tone--${health.tone}`}>
            <span className="qms-control-centre__posture-dot" aria-hidden="true" />
            <strong>{health.label}</strong>
            <small>{dashboard ? qmsTimestampLabel(dashboard.as_of) : "Refreshing live sources"}</small>
          </span>
          <button type="button" className="qms-control-centre__button" onClick={() => void refresh()} disabled={dashboardQuery.isFetching}>
            <RefreshCw size={15} className={dashboardQuery.isFetching ? "is-spinning" : ""} aria-hidden="true" /> Refresh
          </button>
          <Link className="qms-control-centre__button is-primary" to={routes.auditSchedule}>
            <CalendarPlus size={15} aria-hidden="true" /> Open audit plan
          </Link>
        </div>
      </header>

      <nav className="qms-control-centre__nav" aria-label="Quality control centre workspaces">
        <Link className="is-active" to={routes.root}><Activity size={15} /> Operations</Link>
        <Link to={`${routes.root}?hub=controls`}><Target size={15} /> Controls</Link>
        <Link to={`${routes.root}?hub=evidence`}><GitBranch size={15} /> Evidence</Link>
        <Link to={`${routes.root}?hub=intelligence`}><BrainCircuit size={15} /> Intelligence</Link>
      </nav>

      {dashboardQuery.isLoading && !dashboard ? (
        <section className="qms-control-centre__loading" role="status">
          <RefreshCw size={18} className="is-spinning" aria-hidden="true" /> Building the operational picture…
        </section>
      ) : null}

      {dashboardQuery.error ? (
        <section className="qms-control-centre__alert" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <div><strong>Operational dashboard unavailable</strong><p>{dashboardQuery.error instanceof Error ? dashboardQuery.error.message : "The current QMS operational picture could not be loaded."}</p></div>
          <button type="button" onClick={() => void dashboardQuery.refetch()}>Retry</button>
        </section>
      ) : null}

      {dashboard ? (
        <>
          <section className="qms-control-centre__summary" aria-label="Quality operating summary">
            <article className={`qms-control-centre__summary-lead qms-tone--${health.tone}`}>
              <span>Operating posture</span>
              <strong>{health.label}</strong>
              <p>{health.summary}</p>
            </article>
            <Link to={routes.myWork}>
              <span>Assigned to me</span>
              <strong>{dashboard.my_work.length.toLocaleString()}</strong>
              <small>approval, review and verification items</small>
            </Link>
            <Link to={routes.calendar}>
              <span>Next 30 days</span>
              <strong>{dashboard.upcoming_obligations.length.toLocaleString()}</strong>
              <small>scheduled obligations returned</small>
            </Link>
            <Link to={routes.myWork}>
              <span>Ranked exposure</span>
              <strong>{queueCount.toLocaleString()}</strong>
              <small>{dashboard.action_queue.length.toLocaleString()} action categories</small>
            </Link>
            <button type="button" className="qms-control-centre__source-card" onClick={() => document.getElementById("qms-control-centre-diagnostics")?.scrollIntoView({ behavior: "smooth", block: "nearest" })}>
              <span>Source coverage</span>
              <strong>{sourceHealthy ? "Healthy" : dashboard.source_health.status.replaceAll("_", " ")}</strong>
              <small>{dashboard.source_health.error_count ? `${dashboard.source_health.error_count} source issue${dashboard.source_health.error_count === 1 ? "" : "s"}` : "No source errors returned"}</small>
            </button>
          </section>

          <div className="qms-control-centre__primary-grid">
            <QmsActionQueue amoCode={amoCode} items={dashboard.action_queue} fallbackRoute={routes.myWork} />
            <QmsMyWork amoCode={amoCode} items={dashboard.my_work} fallbackRoute={routes.myWork} />
          </div>

          <details className="qms-control-centre__disclosure">
            <summary>
              <span><strong>Forward view and performance</strong><small>Open when planning workload or investigating trends.</small></span>
              <ArrowRight size={16} aria-hidden="true" />
            </summary>
            <div className="qms-control-centre__secondary-grid">
              <QmsUpcomingObligations amoCode={amoCode} items={dashboard.upcoming_obligations} fallbackRoute={routes.calendar} />
              <QmsPerformanceSummary amoCode={amoCode} items={dashboard.performance_kpis} fallbackRoute={routes.reports} />
            </div>
          </details>

          <section className="qms-control-centre__review-lane" aria-label="Assurance review guidance">
            <div>
              <span>Human-governed assurance</span>
              <strong>Use the workspace navigation above to review controls, evidence and recommendations.</strong>
              <p>AI may rank and explain exposure, but acceptance, approval, verification and closure remain explicit human actions in the governed source record.</p>
            </div>
          </section>

          {!dashboard.action_queue.length && !dashboard.my_work.length ? (
            <div className="qms-control-centre__quiet" role="status"><CheckCircle2 size={18} /><span>No ranked exception or assigned work was returned. Scheduled surveillance remains visible in the forward view.</span></div>
          ) : null}

          <div id="qms-control-centre-diagnostics">
            <QmsDiagnosticsDrawer dashboard={dashboard} authorized={diagnosticsAuthorized} />
          </div>
        </>
      ) : null}
    </main>
  );
};

export default QmsOperationalControlCentre;
