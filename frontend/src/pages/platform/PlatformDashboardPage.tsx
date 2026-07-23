import React from "react";

import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const money = (cents?: number) => `$${((cents ?? 0) / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const pct = (value?: number) => `${Math.round((value ?? 0) * 10000) / 100}%`;

type DashboardSummary = {
  platform_status?: string;
  active_tenants?: number;
  locked_tenants?: number;
  trialing_tenants?: number;
  platform_mrr?: number;
  platform_arr?: number;
  total_users?: number;
  api_requests_last_60m?: number;
  api_error_rate_last_60m?: number;
  p95_latency_ms?: number;
  p99_latency_ms?: number;
  active_support_tickets?: number;
  critical_security_alerts?: number;
};

type PlatformAlert = {
  id: string;
  severity?: string;
  title?: string;
};

export default function PlatformDashboardPage() {
  const summary = usePlatformData(() => platformApi.dashboardSummary(), []);
  const jobs = usePlatformData(() => platformApi.recentJobs(), []);
  const alerts = usePlatformData(() => platformApi.recentAlerts(), []);
  const data = (summary.data ?? {}) as DashboardSummary;
  const recentAlerts = (alerts.data?.items ?? []) as PlatformAlert[];
  const apiErrorRate = Number(data.api_error_rate_last_60m ?? 0);
  const platformStatus = String(data.platform_status ?? "UNKNOWN").toUpperCase();

  return (
    <PlatformShell
      title="Platform Control"
      subtitle="Global SaaS command centre for tenants, revenue, diagnostics, throughput, health and controlled platform operations."
      actions={<button className="platform-btn primary" onClick={() => platformApi.runDiagnostics().then(() => { summary.reload(); jobs.reload(); alerts.reload(); })}>Run health probe</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}

      <section className="platform-hero-card">
        <div>
          <span className="platform-eyebrow">Live control plane</span>
          <h2>{platformStatus === "HEALTHY" ? "All systems nominal" : platformStatus === "UNKNOWN" ? "Awaiting first health snapshot" : `Platform status: ${platformStatus}`}</h2>
          <p>Metrics below are computed from backend rollups and snapshots. Empty values mean no metric snapshot exists yet, not fake production data.</p>
        </div>
        <div className="platform-health-orb"><StatusBadge value={data.platform_status} /></div>
      </section>

      <section className="platform-grid platform-grid--six">
        <MetricCard label="Active tenants" value={data.active_tenants ?? "-"} caption={`${data.locked_tenants ?? 0} locked · ${data.trialing_tenants ?? 0} trialing`} tone="blue" />
        <MetricCard label="Platform MRR" value={money(data.platform_mrr)} caption={`ARR ${money(data.platform_arr)}`} tone="green" />
        <MetricCard label="Total users" value={data.total_users ?? "-"} caption="Global users across tenants" tone="purple" />
        <MetricCard label="API throughput" value={data.api_requests_last_60m ?? 0} caption={`${pct(apiErrorRate)} error rate`} tone={apiErrorRate > 0.05 ? "red" : "blue"} />
        <MetricCard label="P95 / P99" value={`${data.p95_latency_ms ?? "-"} / ${data.p99_latency_ms ?? "-"}`} caption="milliseconds" tone="amber" />
        <MetricCard label="Support tickets" value={data.active_support_tickets ?? 0} caption={`${data.critical_security_alerts ?? 0} critical security alerts`} tone="red" />
      </section>

      <section className="platform-two">
        <div className="platform-card platform-card--deep">
          <div className="platform-section-title"><div><h2>Latest command jobs</h2><p>Privileged actions, probes and background operations.</p></div><button className="platform-btn" onClick={jobs.reload}>Refresh</button></div>
          {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : jobs.data?.items?.length ? (
            <DataTable><thead><tr><th>Command</th><th>Status</th><th>Risk</th><th>Created</th></tr></thead><tbody>{jobs.data.items.map((job: PlatformCommandJob) => <tr key={job.id}><td><strong>{job.command_name}</strong></td><td><StatusBadge value={job.status} /></td><td>{job.risk_level}</td><td>{job.created_at ?? "-"}</td></tr>)}</tbody></DataTable>
          ) : <EmptyState label="No command jobs recorded yet." />}
        </div>
        <div className="platform-card platform-card--deep">
          <div className="platform-section-title"><div><h2>Recent alerts</h2><p>Security, health, integration and billing alerts.</p></div><button className="platform-btn" onClick={alerts.reload}>Refresh</button></div>
          {alerts.error ? <ErrorState error={alerts.error} retry={alerts.reload} /> : recentAlerts.length ? recentAlerts.map((alert) => <p className="platform-alert-row" key={alert.id}><StatusBadge value={alert.severity} /> <span>{alert.title ?? "Platform alert"}</span></p>) : <EmptyState label="No platform alerts." />}
        </div>
      </section>
    </PlatformShell>
  );
}
