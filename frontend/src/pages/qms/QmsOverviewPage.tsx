import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import { getCachedUser } from "../../services/auth";
import { getQmsOperationalDashboard } from "../../services/qmsDashboard";
import type { QmsOperationalDashboardResponse } from "../../types/qms";
import QmsActionQueue from "./components/QmsActionQueue";
import QmsDiagnosticsDrawer from "./components/QmsDiagnosticsDrawer";
import QmsMyWork from "./components/QmsMyWork";
import QmsPerformanceSummary from "./components/QmsPerformanceSummary";
import QmsUpcomingObligations from "./components/QmsUpcomingObligations";
import {
  buildQmsOverviewRoutes,
  deriveQmsOverviewHealth,
  qmsTimestampLabel,
} from "./qmsOverviewModel";
import "../../styles/qms-overview.css";

type LoadState = "idle" | "loading" | "ready" | "error";

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

const QmsOverviewPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
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

  const health = useMemo(() => {
    if (dashboard) return deriveQmsOverviewHealth(dashboard);
    if (state === "error") {
      return {
        tone: "danger" as const,
        label: "Overview unavailable",
        summary: "The operational Quality dashboard could not be loaded.",
        urgentCount: 0,
      };
    }
    return {
      tone: "neutral" as const,
      label: "Loading overview",
      summary: "Retrieving ranked Quality work and obligations.",
      urgentCount: 0,
    };
  }, [dashboard, state]);

  const currentUser = getCachedUser();
  const diagnosticsAuthorized = Boolean(
    currentUser?.is_amo_admin ||
    currentUser?.role === "QUALITY_MANAGER" ||
    currentUser?.role === "QUALITY_INSPECTOR",
  );

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-overview-page">
        <PageHeader
          compact
          eyebrow="Quality Management System"
          title="Quality overview"
          subtitle="What needs attention, what is assigned to you, what is approaching, and whether quality performance is moving in the right direction."
          breadcrumbs={[{ label: "Quality" }, { label: "Overview" }]}
          meta={<span className={`qms-overview-health qms-tone--${health.tone}`}>{health.label}</span>}
          actions={
            <button
              className="qms-overview-refresh"
              type="button"
              onClick={() => void load()}
              disabled={state === "loading"}
            >
              <RefreshCw size={15} className={state === "loading" ? "is-spinning" : ""} aria-hidden="true" />
              Refresh
            </button>
          }
        />

        {error ? (
          <div className="qms-overview-alert qms-overview-alert--error" role="alert">
            <AlertTriangle size={19} aria-hidden="true" />
            <div>
              <strong>{dashboard ? "Quality data refresh failed" : "Quality overview unavailable"}</strong>
              <p>{error}</p>
            </div>
            <button type="button" onClick={() => void load()}>Retry</button>
          </div>
        ) : null}

        {state === "loading" && !dashboard ? (
          <div className="qms-overview-loading" role="status" aria-live="polite">
            <RefreshCw size={18} className="is-spinning" aria-hidden="true" />
            Loading ranked Quality work and obligations…
          </div>
        ) : null}

        {dashboard ? (
          <main className="qms-overview-content">
            <section className={`qms-overview-status qms-overview-status--${health.tone}`} aria-label="Current QMS control status">
              <div className="qms-overview-status__icon" aria-hidden="true"><ShieldCheck size={21} /></div>
              <div className="qms-overview-status__message">
                <span>Current control status</span>
                <strong>{health.summary}</strong>
              </div>
              <div className="qms-overview-status__freshness">
                <span>Data generated</span>
                <strong>{qmsTimestampLabel(dashboard.data_freshness?.generated_at || dashboard.as_of)}</strong>
              </div>
            </section>

            {dashboard.source_health.status !== "healthy" ? (
              <div className="qms-overview-alert qms-overview-alert--warning" role="status">
                <AlertTriangle size={18} aria-hidden="true" />
                <div>
                  <strong>Some Quality sources are incomplete</strong>
                  <p>The dashboard is showing available data. Do not treat an empty section as confirmation that no work exists.</p>
                </div>
              </div>
            ) : null}

            <QmsActionQueue
              amoCode={amoCode}
              items={dashboard.action_queue}
              fallbackRoute={routes.myWork}
            />

            <div className="qms-overview-two-column">
              <QmsMyWork
                amoCode={amoCode}
                items={dashboard.my_work}
                fallbackRoute={routes.myWork}
              />
              <QmsUpcomingObligations
                amoCode={amoCode}
                items={dashboard.upcoming_obligations}
                fallbackRoute={routes.calendar}
              />
            </div>

            <QmsPerformanceSummary
              amoCode={amoCode}
              items={dashboard.performance_kpis}
              fallbackRoute={routes.reports}
            />

            <QmsDiagnosticsDrawer dashboard={dashboard} authorized={diagnosticsAuthorized} />
          </main>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
