import React from "react";
import { useLocation } from "react-router-dom";

import { platformApi } from "../../services/platformControl";
import { readPlatformDataMode } from "../../services/platformEnvironment";
import { platformOperationsApi, type DataMode } from "../../services/platformOperations";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type AnalyticsSummary = {
  dau?: number;
  wau?: number;
  mau?: number;
  api?: { requests_per_minute?: number; error_rate?: number; p95_latency_ms?: number; p99_latency_ms?: number };
};
type SlowRoute = { route: string; method: string; request_count: number; p95_latency_ms: number; server_error_count: number };
type TenantTraffic = { tenant_id: string; requests: number };

function pct(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "—";
}

export default function PlatformAnalyticsPage() {
  const location = useLocation();
  const mode = readPlatformDataMode(location.search) as DataMode;
  const analytics = usePlatformData(() => platformApi.analyticsSummary(), []);
  const slow = usePlatformData(() => platformApi.slowRoutes(), []);
  const top = usePlatformData(() => platformApi.topTenants(), []);
  const product = usePlatformData(() => platformOperationsApi.productRollups(mode, 30), [mode]);
  const insights = usePlatformData(() => platformOperationsApi.productInsights(mode, 30, 30), [mode]);
  const summary = (analytics.data ?? {}) as AnalyticsSummary;
  const api = summary.api ?? {};
  const slowRoutes = (slow.data?.items ?? []) as SlowRoute[];
  const topTenants = (top.data?.items ?? []) as TenantTraffic[];
  const rollups = (product.data ?? {}) as Record<string, any>;
  const insight = (insights.data ?? {}) as Record<string, any>;
  const retention = insight.retention || {};
  const dormancy = insight.dormancy || {};

  const reload = () => Promise.all([
    analytics.reload(),
    slow.reload(),
    top.reload(),
    product.reload(),
    insights.reload(),
  ]);

  return (
    <PlatformShell
      title="Platform Analytics"
      subtitle={`Traffic and product adoption · ${mode}`}
      actions={<button className="platform-btn primary" onClick={() => platformApi.runThroughputProbe().then(reload)}>Run throughput probe</button>}
    >
      {analytics.error ? <ErrorState error={analytics.error} retry={analytics.reload} /> : null}
      {product.error ? <ErrorState error={product.error} retry={product.reload} /> : null}
      {insights.error ? <ErrorState error={insights.error} retry={insights.reload} /> : null}

      <section className="platform-grid">
        <MetricCard label="DAU" value={summary.dau ?? 0} />
        <MetricCard label="WAU" value={summary.wau ?? 0} />
        <MetricCard label="MAU" value={summary.mau ?? 0} />
        <MetricCard label="Requests/min" value={api.requests_per_minute ?? 0} />
        <MetricCard label="Error rate" value={`${Math.round((api.error_rate ?? 0) * 10000) / 100}%`} />
        <MetricCard label="P95/P99" value={`${api.p95_latency_ms ?? "-"} / ${api.p99_latency_ms ?? "-"}`} />
      </section>

      <section className="platform-grid">
        <MetricCard label="Product-active tenants · 30d" value={retention.current_active_tenants ?? rollups.active_tenants ?? 0} />
        <MetricCard label="Tenant retention" value={pct(retention.retention_rate)} caption="Active in both current and previous 30-day windows" />
        <MetricCard label="Activation coverage" value={pct(retention.current_activation_rate)} caption={`${retention.eligible_tenants ?? 0} eligible tenants`} />
        <MetricCard label="Dormant tenants" value={dormancy.dormant_tenants ?? 0} caption={`${dormancy.never_observed_tenants ?? 0} never observed`} tone={(dormancy.dormant_tenants ?? 0) > 0 ? "amber" : "green"} />
        <MetricCard label="Workflow completion" value={pct(rollups.workflow_funnel?.completion_rate)} />
        <MetricCard label="Analytics sink" value={<StatusBadge value={rollups.sink?.running ? "HEALTHY" : "OFFLINE"} />} caption={`${rollups.sink?.dropped ?? 0} dropped events`} />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Tenant cohorts</h2>
          <p>{retention.definition}</p>
          {(insight.cohorts || []).length ? (
            <DataTable>
              <thead><tr><th>Created</th><th>Tenants</th><th>Active · 30d</th><th>Activation</th></tr></thead>
              <tbody>{(insight.cohorts || []).map((row: any) => <tr key={row.cohort}><td>{row.cohort}</td><td>{row.tenants}</td><td>{row.active_in_window}</td><td>{pct(row.activation_rate)}</td></tr>)}</tbody>
            </DataTable>
          ) : <EmptyState label="No tenant cohort data yet." />}
        </div>
        <div className="platform-card">
          <h2>Dormancy</h2>
          <p>{dormancy.definition}</p>
          <DataTable>
            <thead><tr><th>Measure</th><th>Tenants</th></tr></thead>
            <tbody>
              <tr><td>Active recently</td><td>{dormancy.active_recently ?? 0}</td></tr>
              <tr><td>Previously observed, now dormant</td><td>{dormancy.previously_observed_dormant ?? 0}</td></tr>
              <tr><td>Never observed</td><td>{dormancy.never_observed_tenants ?? 0}</td></tr>
            </tbody>
          </DataTable>
        </div>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Module adoption</h2>
          {(rollups.modules || []).length ? (
            <DataTable>
              <thead><tr><th>Module</th><th>Active tenants</th><th>Events</th><th>Success</th><th>Failed</th></tr></thead>
              <tbody>{(rollups.modules || []).map((row: any) => <tr key={row.module}><td>{row.module}</td><td>{row.active_tenants}</td><td>{row.events}</td><td>{row.success}</td><td>{row.failed}</td></tr>)}</tbody>
            </DataTable>
          ) : <EmptyState label="No approved module events yet." />}
        </div>
        <div className="platform-card">
          <h2>Approved event inventory</h2>
          <p>{insight.event_inventory?.definition}</p>
          <p><strong>Supported:</strong> {(insight.event_inventory?.supported || []).join(", ") || "—"}</p>
          {(insight.event_inventory?.observed || []).length ? (
            <DataTable>
              <thead><tr><th>Observed event</th><th>30-day events</th></tr></thead>
              <tbody>{(insight.event_inventory.observed || []).map((row: any) => <tr key={row.event_type}><td>{row.event_type}</td><td>{row.events}</td></tr>)}</tbody>
            </DataTable>
          ) : <EmptyState label="No approved product events observed in this window." />}
        </div>
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
