import React from "react";

import { platformApi } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type AnalyticsSummary = {
  dau?: number;
  wau?: number;
  mau?: number;
  api?: {
    requests_per_minute?: number;
    error_rate?: number;
    p95_latency_ms?: number;
    p99_latency_ms?: number;
  };
};

type SlowRoute = {
  route: string;
  method: string;
  request_count: number;
  p95_latency_ms: number;
  server_error_count: number;
};

type TenantTraffic = {
  tenant_id: string;
  requests: number;
};

export default function PlatformAnalyticsPage() {
  const analytics = usePlatformData(() => platformApi.analyticsSummary(), []);
  const slow = usePlatformData(() => platformApi.slowRoutes(), []);
  const top = usePlatformData(() => platformApi.topTenants(), []);
  const summary = (analytics.data ?? {}) as AnalyticsSummary;
  const api = summary.api ?? {};
  const slowRoutes = (slow.data?.items ?? []) as SlowRoute[];
  const topTenants = (top.data?.items ?? []) as TenantTraffic[];

  return (
    <PlatformShell
      title="Platform Analytics"
      subtitle="DAU/WAU/MAU, route throughput, latency percentiles, noisiest tenants and slowest routes."
      actions={<button className="platform-btn primary" onClick={() => platformApi.runThroughputProbe().then(analytics.reload)}>Run throughput probe</button>}
    >
      {analytics.error ? <ErrorState error={analytics.error} retry={analytics.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="DAU" value={summary.dau ?? 0} />
        <MetricCard label="WAU" value={summary.wau ?? 0} />
        <MetricCard label="MAU" value={summary.mau ?? 0} />
        <MetricCard label="Requests/min" value={api.requests_per_minute ?? 0} />
        <MetricCard label="Error rate" value={`${Math.round((api.error_rate ?? 0) * 10000) / 100}%`} />
        <MetricCard label="P95/P99" value={`${api.p95_latency_ms ?? "-"} / ${api.p99_latency_ms ?? "-"}`} />
      </section>
      <section className="platform-two">
        <div className="platform-card">
          <h2>Slowest routes</h2>
          {slowRoutes.length ? (
            <DataTable>
              <thead><tr><th>Route</th><th>Method</th><th>Requests</th><th>P95</th><th>Errors</th></tr></thead>
              <tbody>{slowRoutes.map((route) => <tr key={`${route.method}:${route.route}`}><td>{route.route}</td><td>{route.method}</td><td>{route.request_count}</td><td>{route.p95_latency_ms}</td><td>{route.server_error_count}</td></tr>)}</tbody>
            </DataTable>
          ) : <EmptyState label="No route metrics yet. They fill from live traffic." />}
        </div>
        <div className="platform-card">
          <h2>Noisiest tenants</h2>
          {topTenants.length ? topTenants.map((tenant) => <p key={tenant.tenant_id}>{tenant.tenant_id}: <strong>{tenant.requests}</strong> requests</p>) : <EmptyState label="No tenant throughput data yet." />}
        </div>
      </section>
    </PlatformShell>
  );
}
