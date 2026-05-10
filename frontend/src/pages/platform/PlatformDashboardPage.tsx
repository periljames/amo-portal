import React from "react";
import { platformApi } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const money = (cents?: number) => `$${((cents || 0) / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const pct = (value?: number) => `${Math.round((value || 0) * 10000) / 100}%`;

export default function PlatformDashboardPage() {
  const summary = usePlatformData(() => platformApi.dashboardSummary(), []);
  const jobs = usePlatformData(() => platformApi.recentJobs(), []);
  const alerts = usePlatformData(() => platformApi.recentAlerts(), []);
  const s = summary.data || {};
  const apiErrorRate = Number(s.api_error_rate_last_60m || 0);
  const platformStatus = String(s.platform_status || "UNKNOWN").toUpperCase();

  return (
    <PlatformShell
      title="Platform Control"
      subtitle="Global SaaS command centre for tenants, revenue, diagnostics, throughput, health and controlled platform operations."
      actions={
        <button
          className="platform-btn primary"
          onClick={() => platformApi.runDiagnostics().then(() => { summary.reload(); jobs.reload(); alerts.reload(); })}
        >
          Run health probe
        </button>
      }
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}

      <section className="platform-hero-card">
        <div>
          <span className="platform-eyebrow">Live control plane</span>
          <h2>{platformStatus === "HEALTHY" ? "All systems nominal" : platformStatus === "UNKNOWN" ? "Awaiting first health snapshot" : `Platform status: ${platformStatus}`}</h2>
          <p>
            Metrics below are computed from backend rollups and snapshots. Empty values mean no metric snapshot exists yet, not fake production data.
          </p>
        </div>
        <div className="platform-health-orb"><StatusBadge value={s.platform_status} /></div>
      </section>

      <section className="platform-grid platform-grid--six">
        <MetricCard label="Active tenants" value={s.active_tenants ?? "-"} caption={`${s.locked_tenants ?? 0} locked · ${s.trialing_tenants ?? 0} trialing`} tone="blue" />
        <MetricCard label="Platform MRR" value={money(s.platform_mrr)} caption={`ARR ${money(s.platform_arr)}`} tone="green" />
        <MetricCard label="Total users" value={s.total_users ?? "-"} caption="Global users across tenants" tone="purple" />
        <MetricCard label="API throughput" value={s.api_requests_last_60m ?? 0} caption={`${pct(apiErrorRate)} error rate`} tone={apiErrorRate > 0.05 ? "red" : "blue"} />
        <MetricCard label="P95 / P99" value={`${s.p95_latency_ms ?? "-"} / ${s.p99_latency_ms ?? "-"}`} caption="milliseconds" tone="amber" />
        <MetricCard label="Support tickets" value={s.active_support_tickets ?? 0} caption={`${s.critical_security_alerts ?? 0} critical security alerts`} tone="red" />
      </section>

      <section className="platform-two">
        <div className="platform-card platform-card--deep">
          <div className="platform-section-title">
            <div><h2>Latest command jobs</h2><p>Privileged actions, probes and background operations.</p></div>
            <button className="platform-btn" onClick={jobs.reload}>Refresh</button>
          </div>
          {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : jobs.data?.items?.length ? (
            <DataTable>
              <thead><tr><th>Command</th><th>Status</th><th>Risk</th><th>Created</th></tr></thead>
              <tbody>{jobs.data.items.map((j:any)=><tr key={j.id}><td><strong>{j.command_name}</strong></td><td><StatusBadge value={j.status}/></td><td>{j.risk_level}</td><td>{j.created_at || "-"}</td></tr>)}</tbody>
            </DataTable>
          ) : <EmptyState label="No command jobs recorded yet." />}
        </div>
        <div className="platform-card platform-card--deep">
          <div className="platform-section-title">
            <div><h2>Recent alerts</h2><p>Security, health, integration and billing alerts.</p></div>
            <button className="platform-btn" onClick={alerts.reload}>Refresh</button>
          </div>
          {alerts.error ? <ErrorState error={alerts.error} retry={alerts.reload} /> : alerts.data?.items?.length ? alerts.data.items.map((a:any)=><p className="platform-alert-row" key={a.id}><StatusBadge value={a.severity}/> <span>{a.title}</span></p>) : <EmptyState label="No platform alerts." />}
        </div>
      </section>
    </PlatformShell>
  );
}
