import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { platformConsoleApi, type PlatformConsoleBootstrap } from "../../services/platformConsole";
import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import "../../styles/platform-dashboard.css";
import "../../styles/platform-dashboard-tuning.css";
import { DataTable, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const compactNumber = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const integerNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

function money(cents?: number, currency = "USD") {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format((cents ?? 0) / 100);
  } catch {
    return `$${integerNumber.format((cents ?? 0) / 100)}`;
  }
}

function percentage(value?: number) {
  return `${Math.round((value ?? 0) * 10_000) / 100}%`;
}

function readableDate(value?: string | null) {
  if (!value) return "No snapshot yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relativeTime(value?: string | null) {
  if (!value) return "Not run";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return readableDate(value);
  const seconds = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function latencyState(value?: number | null) {
  if (value === undefined || value === null) return "neutral";
  if (value <= 500) return "good";
  if (value <= 1_000) return "watch";
  return "slow";
}

type DashboardSnapshot = PlatformConsoleBootstrap & {
  platform_status?: string;
  active_tenants?: number;
  inactive_tenants?: number;
  locked_tenants?: number;
  trialing_tenants?: number;
  platform_mrr?: number;
  platform_arr?: number;
  currency?: string;
  total_users?: number;
  api_requests_last_60m?: number;
  api_error_rate_last_60m?: number;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
  active_support_tickets?: number;
  open_support_tickets?: number;
  critical_security_alerts?: number;
  overdue_invoices?: number;
  queue_depth?: number;
  configured_providers?: number;
  provider_count?: number;
  pending_fiscalizations?: number;
  email_status?: string;
  email_latency_ms?: number | null;
  last_health_probe_at?: string | null;
  data_mode?: string;
};

type PlatformAlert = {
  id: string;
  severity?: string;
  title?: string;
  category?: string;
  created_at?: string;
};

type HealthRowProps = {
  label: string;
  value: React.ReactNode;
  detail: string;
  state?: "good" | "watch" | "slow" | "neutral";
};

function HealthRow({ label, value, detail, state = "neutral" }: HealthRowProps) {
  return (
    <div className="platform-health-row" data-state={state}>
      <span className="platform-health-row__indicator" />
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <b>{value}</b>
    </div>
  );
}

export default function PlatformDashboardPage() {
  const snapshot = usePlatformData<DashboardSnapshot>(
    () => platformConsoleApi.bootstrap() as Promise<DashboardSnapshot>,
    [],
    { pollMs: 15_000 },
  );
  const jobs = usePlatformData(() => platformApi.recentJobs(), [], { pollMs: 20_000 });
  const alerts = usePlatformData(() => platformApi.recentAlerts(), [], { pollMs: 20_000 });
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  const data = snapshot.data ?? {};
  const recentJobs = (jobs.data?.items ?? []) as PlatformCommandJob[];
  const recentAlerts = (alerts.data?.items ?? []) as PlatformAlert[];
  const apiErrorRate = Number(data.api_error_rate_last_60m ?? 0);
  const apiSuccessRate = Math.max(0, 1 - apiErrorRate);
  const platformStatus = String(data.platform_status ?? "UNKNOWN").toUpperCase();
  const openSupport = Number(data.open_support_tickets ?? data.active_support_tickets ?? 0);
  const providerCount = Number(data.provider_count ?? 0);
  const configuredProviders = Number(data.configured_providers ?? 0);

  const attentionCount = useMemo(
    () => Number(data.critical_security_alerts ?? 0)
      + openSupport
      + Number(data.overdue_invoices ?? 0)
      + Number(data.pending_fiscalizations ?? 0),
    [data.critical_security_alerts, data.overdue_invoices, data.pending_fiscalizations, openSupport],
  );

  const runProbe = async () => {
    setProbing(true);
    setProbeError(null);
    try {
      await platformApi.runDiagnostics();
      snapshot.reload();
      jobs.reload();
      alerts.reload();
    } catch (error) {
      setProbeError(error instanceof Error ? error.message : String(error));
    } finally {
      setProbing(false);
    }
  };

  const statusTitle = platformStatus === "HEALTHY"
    ? "Platform operating normally"
    : platformStatus === "UNKNOWN"
      ? "Health snapshot required"
      : `Platform status: ${platformStatus}`;

  return (
    <PlatformShell
      title="Platform Control"
      subtitle="Live operating view for tenant health, revenue, throughput, providers, support, security and privileged platform work."
      actions={(
        <button className="platform-btn primary" disabled={probing} onClick={runProbe}>
          {probing ? "Running probe…" : "Run health probe"}
        </button>
      )}
    >
      <div className="platform-dashboard">
        {snapshot.error ? <ErrorState error={snapshot.error} retry={snapshot.reload} /> : null}
        {probeError ? <ErrorState error={probeError} retry={runProbe} /> : null}

        <section className="platform-dashboard-status" data-status={platformStatus.toLowerCase()}>
          <div className="platform-dashboard-status__main">
            <span className="platform-dashboard-status__pulse" />
            <div>
              <span className="platform-eyebrow">Live control plane</span>
              <h2>{statusTitle}</h2>
              <p>Real platform data only. Missing values indicate that the corresponding backend rollup or health snapshot has not been produced.</p>
            </div>
          </div>
          <div className="platform-dashboard-status__meta">
            <StatusBadge value={data.platform_status} />
            <span><small>Last probe</small><strong>{relativeTime(data.last_health_probe_at)}</strong></span>
            <span><small>Snapshot</small><strong>{readableDate(data.generated_at)}</strong></span>
            <span><small>Data scope</small><strong>{data.data_mode ?? "REAL"}</strong></span>
          </div>
        </section>

        <section className="platform-dashboard-metrics" aria-label="Platform headline metrics">
          <MetricCard label="Active tenants" value={integerNumber.format(Number(data.active_tenants ?? 0))} caption={`${data.locked_tenants ?? 0} locked · ${data.trialing_tenants ?? 0} trialing · ${data.inactive_tenants ?? 0} inactive`} tone="blue" mark="TEN" />
          <MetricCard label="Platform MRR" value={money(data.platform_mrr, data.currency)} caption={`ARR ${money(data.platform_arr, data.currency)}`} tone="green" mark="REV" />
          <MetricCard label="Global users" value={compactNumber.format(Number(data.total_users ?? 0))} caption="Across active tenant accounts" tone="purple" mark="USR" />
          <MetricCard label="Requests · 60m" value={compactNumber.format(Number(data.api_requests_last_60m ?? 0))} caption={`${percentage(apiErrorRate)} error rate`} tone={apiErrorRate > 0.05 ? "red" : "blue"} mark="API" />
          <MetricCard label="P95 / P99 latency" value={`${integerNumber.format(Number(data.p95_latency_ms ?? 0))} / ${integerNumber.format(Number(data.p99_latency_ms ?? 0))}`} caption="Milliseconds across measured routes" tone={Number(data.p95_latency_ms ?? 0) > 1_000 ? "red" : "amber"} mark="LAT" />
          <MetricCard label="Attention queue" value={integerNumber.format(attentionCount)} caption={`${openSupport} support · ${data.critical_security_alerts ?? 0} security · ${data.overdue_invoices ?? 0} overdue`} tone={attentionCount > 0 ? "red" : "green"} mark="ACT" />
        </section>

        <section className="platform-dashboard-core">
          <article className="platform-dashboard-panel platform-dashboard-panel--operations">
            <header className="platform-dashboard-panel__header">
              <div><span>Runtime</span><h2>Operations health</h2></div>
              <Link to="/platform/analytics">Open analytics <span>→</span></Link>
            </header>
            <div className="platform-health-list">
              <HealthRow label="API success rate" value={percentage(apiSuccessRate)} detail={`${compactNumber.format(Number(data.api_requests_last_60m ?? 0))} requests observed during the last 60 minutes`} state={apiErrorRate <= 0.01 ? "good" : apiErrorRate <= 0.05 ? "watch" : "slow"} />
              <HealthRow label="P95 response latency" value={data.p95_latency_ms === null || data.p95_latency_ms === undefined ? "—" : `${integerNumber.format(data.p95_latency_ms)} ms`} detail="Typical high-percentile response time" state={latencyState(data.p95_latency_ms)} />
              <HealthRow label="P99 response latency" value={data.p99_latency_ms === null || data.p99_latency_ms === undefined ? "—" : `${integerNumber.format(data.p99_latency_ms)} ms`} detail="Slowest measured one percent of requests" state={latencyState(data.p99_latency_ms)} />
              <HealthRow label="Durable job queue" value={integerNumber.format(Number(data.queue_depth ?? 0))} detail="Queued platform and integration work awaiting execution" state={Number(data.queue_depth ?? 0) === 0 ? "good" : Number(data.queue_depth ?? 0) < 10 ? "watch" : "slow"} />
            </div>
          </article>

          <article className="platform-dashboard-panel">
            <header className="platform-dashboard-panel__header">
              <div><span>Services</span><h2>Provider readiness</h2></div>
              <Link to="/platform/integrations">Manage <span>→</span></Link>
            </header>
            <dl className="platform-readiness-list">
              <div><dt>Email delivery</dt><dd><StatusBadge value={data.email_status ?? "NOT CONFIGURED"} /></dd></div>
              <div><dt>Email latency</dt><dd>{data.email_latency_ms === null || data.email_latency_ms === undefined ? "No test" : `${integerNumber.format(data.email_latency_ms)} ms`}</dd></div>
              <div><dt>Configured providers</dt><dd>{configuredProviders} / {providerCount || "—"}</dd></div>
              <div><dt>Pending fiscalization</dt><dd>{integerNumber.format(Number(data.pending_fiscalizations ?? 0))}</dd></div>
            </dl>
            <div className="platform-provider-progress" aria-label="Configured provider ratio">
              <span style={{ width: providerCount ? `${Math.min(100, (configuredProviders / providerCount) * 100)}%` : "0%" }} />
            </div>
          </article>

          <article className="platform-dashboard-panel">
            <header className="platform-dashboard-panel__header"><div><span>Command</span><h2>Action centre</h2></div></header>
            <nav className="platform-action-list" aria-label="Platform action centre">
              <Link to="/platform/tenants"><span>Tenant lifecycle</span><strong>{data.active_tenants ?? 0} active</strong><i>→</i></Link>
              <Link to="/platform/users"><span>User and session controls</span><strong>{data.total_users ?? 0} users</strong><i>→</i></Link>
              <Link to="/platform/integrations?tab=support"><span>Support operations</span><strong>{openSupport} open</strong><i>→</i></Link>
              <Link to="/platform/security"><span>Security attention</span><strong>{data.critical_security_alerts ?? 0} critical</strong><i>→</i></Link>
              <Link to="/platform/infrastructure"><span>Workers and diagnostics</span><strong>{data.queue_depth ?? 0} queued</strong><i>→</i></Link>
            </nav>
          </article>
        </section>

        <section className="platform-dashboard-lower">
          <article className="platform-dashboard-panel platform-dashboard-panel--jobs">
            <header className="platform-dashboard-panel__header">
              <div><span>Privileged operations</span><h2>Latest command jobs</h2></div>
              <button className="platform-btn compact" onClick={jobs.reload}>Refresh</button>
            </header>
            {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : recentJobs.length ? (
              <DataTable>
                <thead><tr><th>Command</th><th>Status</th><th>Risk</th><th>Created</th><th>Finished</th></tr></thead>
                <tbody>
                  {recentJobs.slice(0, 8).map((job) => (
                    <tr key={job.id}>
                      <td><strong>{job.command_name}</strong>{job.reason ? <small className="platform-table-subtext">{job.reason}</small> : null}</td>
                      <td><StatusBadge value={job.status} /></td>
                      <td><StatusBadge value={job.risk_level} /></td>
                      <td>{readableDate(job.created_at)}</td>
                      <td>{job.finished_at ? readableDate(job.finished_at) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            ) : (
              <div className="platform-dashboard-empty"><span>✓</span><div><strong>No command jobs recorded</strong><small>Privileged operations will appear here with their status, risk and timestamps.</small></div></div>
            )}
          </article>

          <article className="platform-dashboard-panel platform-dashboard-panel--alerts">
            <header className="platform-dashboard-panel__header">
              <div><span>Attention</span><h2>Recent alerts</h2></div>
              <Link to="/platform/security">View all <span>→</span></Link>
            </header>
            {alerts.error ? <ErrorState error={alerts.error} retry={alerts.reload} /> : recentAlerts.length ? (
              <div className="platform-alert-list">
                {recentAlerts.slice(0, 6).map((alert) => (
                  <Link to="/platform/security" key={alert.id}>
                    <StatusBadge value={alert.severity} />
                    <span><strong>{alert.title ?? "Platform alert"}</strong><small>{alert.category ?? "Platform"} · {readableDate(alert.created_at)}</small></span>
                    <i>→</i>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="platform-dashboard-empty platform-dashboard-empty--healthy"><span>✓</span><div><strong>No active platform alerts</strong><small>Security, health, billing and integration alerts will appear here.</small></div></div>
            )}
          </article>
        </section>
      </div>
    </PlatformShell>
  );
}
