import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  RefreshCw,
  ShieldAlert,
  Users,
} from "lucide-react";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { getQmsDashboard } from "../../services/qmsDashboard";
import type { QmsDashboardResponse, QmsSourceError } from "../../types/qms";
import {
  buildQmsExposureSignals,
  buildQmsOverviewRoutes,
  deriveQmsOverviewHealth,
  normaliseQmsCalendarEntries,
  qmsCounter,
  qmsModuleLabel,
  qmsRelativeDateLabel,
  type QmsCalendarEntry,
  type QmsOverviewTone,
} from "./qmsOverviewModel";
import "../../styles/qms-overview.css";

type LoadState = "idle" | "loading" | "ready" | "error";

type QmsInboxItem = {
  id: string;
  message: string;
  severity?: string | null;
  created_at?: string | null;
  read_at?: string | null;
};

type QmsInboxResponse = {
  items?: QmsInboxItem[];
  view?: string;
};

type QmsCalendarResponse = {
  items?: QmsCalendarEntry[];
  source_errors?: QmsSourceError[];
  warning?: string | null;
};

type SupportingError = {
  source: string;
  message: string;
};

type ActionRow = {
  id: string;
  title: string;
  detail: string;
  route: string;
  tone: QmsOverviewTone;
  count?: number;
};

type MetricDefinition = {
  id: string;
  label: string;
  value: number;
  detail: string;
  route: string;
  tone: QmsOverviewTone;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
};

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

function severityTone(value: string | null | undefined): QmsOverviewTone {
  const severity = String(value || "").toUpperCase();
  if (["CRITICAL", "MAJOR", "ERROR", "DANGER"].includes(severity)) return "danger";
  if (["WARNING", "WARN", "MEDIUM"].includes(severity)) return "warning";
  return "neutral";
}

function safeInternalLink(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  return value.startsWith("/maintenance/") ? value : fallback;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Time unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Time unavailable";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCalendarDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function MetricCard({ metric }: { metric: MetricDefinition }): React.ReactElement {
  const Icon = metric.icon;
  return (
    <Link className={`qms-overview-metric qms-overview-tone--${metric.tone}`} to={metric.route}>
      <span className="qms-overview-metric__icon" aria-hidden="true"><Icon size={18} strokeWidth={2} /></span>
      <span className="qms-overview-metric__copy">
        <span>{metric.label}</span>
        <strong>{Intl.NumberFormat().format(metric.value)}</strong>
        <small>{metric.detail}</small>
      </span>
      <ArrowRight size={16} aria-hidden="true" />
    </Link>
  );
}

function SourceHealthNotice({ errors }: { errors: SupportingError[] }): React.ReactElement | null {
  if (!errors.length) return null;
  return (
    <details className="qms-overview-source-notice">
      <summary><AlertTriangle size={16} /> Some supporting data could not be loaded</summary>
      <div>
        {errors.map((error) => (
          <p key={`${error.source}-${error.message}`}><strong>{error.source}:</strong> {error.message}</p>
        ))}
      </div>
    </details>
  );
}

const QmsOverviewPage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const routes = useMemo(() => buildQmsOverviewRoutes(amoCode), [amoCode]);
  const requestRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [dashboard, setDashboard] = useState<QmsDashboardResponse | null>(null);
  const [inboxItems, setInboxItems] = useState<QmsInboxItem[]>([]);
  const [calendarItems, setCalendarItems] = useState<QmsCalendarEntry[]>([]);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [supportingErrors, setSupportingErrors] = useState<SupportingError[]>([]);

  const load = useCallback(async () => {
    requestRef.current?.abort(new DOMException("Superseded by a newer QMS overview request", "AbortError"));
    const controller = new AbortController();
    requestRef.current = controller;
    setState((current) => (current === "ready" ? "ready" : "loading"));
    setFatalError(null);
    setSupportingErrors([]);

    const today = new Date();
    const calendarParams = new URLSearchParams({
      start: isoDate(today),
      end: isoDate(addDays(today, 30)),
      limit: "80",
      offset: "0",
      view: "list",
    });

    const [dashboardResult, inboxResult, calendarResult] = await Promise.allSettled([
      getQmsDashboard(amoCode),
      apiRequest<QmsInboxResponse>(qmsPath(amoCode, "/inbox/assigned-to-me"), {
        timeoutMs: 8_000,
        cacheTtlMs: 15_000,
        signal: controller.signal,
      }),
      apiRequest<QmsCalendarResponse>(qmsPath(amoCode, `/integrations/calendar?${calendarParams.toString()}`), {
        timeoutMs: 10_000,
        cacheTtlMs: 15_000,
        signal: controller.signal,
      }),
    ]);

    if (controller.signal.aborted) return;

    if (dashboardResult.status === "rejected") {
      setState("error");
      setFatalError(friendlyError(dashboardResult.reason, "Unable to load the QMS dashboard."));
      return;
    }

    const partialErrors: SupportingError[] = [];
    setDashboard(dashboardResult.value);

    if (inboxResult.status === "fulfilled") {
      setInboxItems(inboxResult.value.items || []);
    } else {
      setInboxItems([]);
      partialErrors.push({ source: "My Quality Work", message: friendlyError(inboxResult.reason, "Unable to load assigned work.") });
    }

    if (calendarResult.status === "fulfilled") {
      setCalendarItems(calendarResult.value.items || []);
      (calendarResult.value.source_errors || []).forEach((error) => {
        partialErrors.push({ source: error.label || "Calendar", message: error.message });
      });
    } else {
      setCalendarItems([]);
      partialErrors.push({ source: "Upcoming obligations", message: friendlyError(calendarResult.reason, "Unable to load the QMS calendar.") });
    }

    (dashboardResult.value.source_errors || []).forEach((error) => {
      partialErrors.push({ source: error.label || "Dashboard", message: error.message });
    });

    setSupportingErrors(partialErrors);
    setState("ready");
  }, [amoCode]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort(new DOMException("QMS overview unmounted", "AbortError"));
  }, [load]);

  const counters = dashboard?.counters;
  const health = useMemo(() => deriveQmsOverviewHealth(counters), [counters]);
  const exposureSignals = useMemo(() => buildQmsExposureSignals(counters, routes), [counters, routes]);
  const upcoming = useMemo(() => normaliseQmsCalendarEntries(calendarItems, new Date(), 8), [calendarItems]);

  const metrics = useMemo<MetricDefinition[]>(() => [
    {
      id: "overdue-cars",
      label: "Overdue CARs",
      value: qmsCounter(counters, "overdue_cars"),
      detail: "Target: zero overdue",
      route: routes.overdueCars,
      tone: qmsCounter(counters, "overdue_cars") > 0 ? "danger" : "positive",
      icon: ShieldAlert,
    },
    {
      id: "training-expired",
      label: "Expired training",
      value: qmsCounter(counters, "training_expired_records"),
      detail: "Latest competence records",
      route: routes.overdueTraining,
      tone: qmsCounter(counters, "training_expired_records") > 0 ? "danger" : "positive",
      icon: Users,
    },
    {
      id: "audits-due",
      label: "Audits due in 30 days",
      value: qmsCounter(counters, "audits_due_soon"),
      detail: "Programme preparation window",
      route: routes.auditSchedule,
      tone: qmsCounter(counters, "audits_due_soon") > 0 ? "warning" : "neutral",
      icon: ClipboardCheck,
    },
    {
      id: "open-findings",
      label: "Open findings",
      value: qmsCounter(counters, "open_findings"),
      detail: "Requires ownership and follow-up",
      route: routes.findings,
      tone: qmsCounter(counters, "open_findings") > 0 ? "warning" : "positive",
      icon: AlertTriangle,
    },
  ], [counters, routes]);

  const actionRows = useMemo<ActionRow[]>(() => {
    const notificationRows: ActionRow[] = inboxItems
      .filter((item) => !item.read_at)
      .slice(0, 4)
      .map((item) => ({
        id: `notification-${item.id}`,
        title: item.message,
        detail: `Assigned work · ${formatTimestamp(item.created_at)}`,
        route: routes.myWork,
        tone: severityTone(item.severity),
      }));

    const signalRows: ActionRow[] = exposureSignals.map((signal) => ({
      id: signal.id,
      title: signal.label,
      detail: signal.description,
      route: signal.route,
      tone: signal.tone,
      count: signal.count,
    }));

    return [...notificationRows, ...signalRows].slice(0, 7);
  }, [exposureSignals, inboxItems, routes.myWork]);

  const performanceRows = useMemo(() => [
    {
      label: "Active audit plans",
      value: qmsCounter(counters, "open_audits"),
      route: routes.auditSchedule,
      context: "Current programme",
    },
    {
      label: "Open CARs",
      value: qmsCounter(counters, "open_cars"),
      route: routes.cars,
      context: `${qmsCounter(counters, "cars_due_soon")} due soon`,
    },
    {
      label: "Active controlled documents",
      value: qmsCounter(counters, "active_documents"),
      route: routes.documents,
      context: `${qmsCounter(counters, "draft_documents")} draft`,
    },
    {
      label: "Active fieldwork today",
      value: qmsCounter(counters, "active_audit_fieldwork"),
      route: routes.audits,
      context: "Audit schedule source",
    },
  ], [counters, routes]);

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-overview-page">
        <PageHeader
          compact
          eyebrow="Quality Management System"
          title="Quality overview"
          subtitle="Priority work, approaching obligations, and control exposure—without repeating the full QMS menu."
          breadcrumbs={[{ label: "Quality" }, { label: "Overview" }]}
          meta={<span className={`qms-overview-health qms-overview-tone--${health.tone}`}>{health.label}</span>}
          actions={
            <button className="qms-overview-refresh" type="button" onClick={() => void load()} disabled={state === "loading"}>
              <RefreshCw size={15} className={state === "loading" ? "is-spinning" : ""} />
              Refresh
            </button>
          }
        />

        {fatalError ? (
          <div className="qms-overview-fatal" role="alert">
            <AlertTriangle size={20} />
            <div><strong>QMS overview unavailable</strong><p>{fatalError}</p></div>
            <button type="button" onClick={() => void load()}>Retry</button>
          </div>
        ) : null}

        {state === "loading" && !dashboard ? (
          <div className="qms-overview-loading" role="status" aria-live="polite">
            <RefreshCw size={18} className="is-spinning" /> Loading operational quality data…
          </div>
        ) : null}

        {dashboard ? (
          <>
            <section className={`qms-overview-status qms-overview-status--${health.tone}`} aria-label="Current QMS status">
              <div>
                <span>Current control status</span>
                <strong>{health.summary}</strong>
              </div>
              <div className="qms-overview-status__meta">
                <span>Data as of</span>
                <strong>{formatTimestamp(dashboard.as_of)}</strong>
              </div>
            </section>

            <section className="qms-overview-metrics" aria-label="Priority QMS indicators">
              {metrics.map((metric) => <MetricCard key={metric.id} metric={metric} />)}
            </section>

            <div className="qms-overview-main-grid">
              <section className="qms-overview-panel qms-overview-panel--actions">
                <header className="qms-overview-panel__header">
                  <div><span>Decision queue</span><h2>Needs action</h2></div>
                  <Link to={routes.myWork}>Open my work <ArrowRight size={14} /></Link>
                </header>
                <div className="qms-overview-action-list">
                  {actionRows.length ? actionRows.map((item) => (
                    <Link key={item.id} to={item.route} className={`qms-overview-action qms-overview-tone--${item.tone}`}>
                      <span className="qms-overview-action__marker" />
                      <span className="qms-overview-action__copy"><strong>{item.title}</strong><small>{item.detail}</small></span>
                      {typeof item.count === "number" ? <b>{Intl.NumberFormat().format(item.count)}</b> : null}
                      <ArrowRight size={15} aria-hidden="true" />
                    </Link>
                  )) : (
                    <div className="qms-overview-empty">
                      <CheckCircle2 size={20} />
                      <div><strong>No dashboard exceptions detected</strong><p>Open My Quality Work to confirm individual assignments and approvals.</p></div>
                    </div>
                  )}
                </div>
              </section>

              <section className="qms-overview-panel qms-overview-panel--calendar">
                <header className="qms-overview-panel__header">
                  <div><span>Next 30 days</span><h2>Upcoming obligations</h2></div>
                  <Link to={routes.calendar}>Full calendar <ArrowRight size={14} /></Link>
                </header>
                <div className="qms-overview-timeline">
                  {upcoming.length ? upcoming.map((item) => (
                    <Link key={item.id} to={safeInternalLink(item.link, routes.calendar)} className="qms-overview-timeline__row">
                      <time dateTime={item.date || undefined}><strong>{formatCalendarDate(item.date)}</strong><small>{qmsRelativeDateLabel(item.date)}</small></time>
                      <span><strong>{item.title}</strong><small>{qmsModuleLabel(item.module)} · {qmsModuleLabel(item.event_type)}</small></span>
                      <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                  )) : (
                    <div className="qms-overview-empty qms-overview-empty--compact">
                      <CalendarClock size={20} />
                      <div><strong>No dated obligations loaded</strong><p>Use the QMS calendar to inspect a wider period.</p></div>
                    </div>
                  )}
                </div>
              </section>
            </div>

            <section className="qms-overview-performance" aria-label="QMS operational context">
              <header>
                <div><span>Operational context</span><h2>Control pulse</h2></div>
                <Link to={routes.reports}>Reports and analytics <ArrowRight size={14} /></Link>
              </header>
              <div className="qms-overview-performance__grid">
                {performanceRows.map((row) => (
                  <Link key={row.label} to={row.route}>
                    <span>{row.label}</span>
                    <strong>{Intl.NumberFormat().format(row.value)}</strong>
                    <small>{row.context}</small>
                  </Link>
                ))}
              </div>
            </section>

            <section className="qms-overview-direct" aria-label="Common QMS actions">
              <div><FileText size={17} /><span><strong>Controlled records stay in their dedicated workflows.</strong><small>The overview does not create generic audit, CAR, finding, or document rows.</small></span></div>
              <nav>
                <Link to={routes.auditSchedule}>Plan audits</Link>
                <Link to={routes.cars}>Review CARs</Link>
                <Link to={routes.documents}>Controlled documents</Link>
              </nav>
            </section>

            <SourceHealthNotice errors={supportingErrors} />
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
