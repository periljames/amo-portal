import React, { useState } from "react";

import { commercialApi } from "../../services/commercialControl";
import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type InfrastructureSummary = {
  status?: string;
  workers?: number;
  latest_snapshot?: {
    cpu_percent?: number;
    memory_percent?: number;
    db_connections_active?: number;
    api_requests_per_minute?: number;
  } | null;
};

type FeatureFlag = {
  id: string;
  key: string;
  name: string;
  scope?: string;
  enabled: boolean;
};

type MaintenanceWindow = {
  id: string;
  status?: string;
  title?: string;
};

export default function PlatformInfrastructurePage() {
  const [key, setKey] = useState("new_feature_flag");
  const [reason, setReason] = useState("Critical infrastructure command requested by platform owner");
  const infra = usePlatformData(() => platformApi.infrastructureSummary(), []);
  const capacity = usePlatformData(() => commercialApi.capacity(), [], { pollMs: 15_000 });
  const flags = usePlatformData(() => platformApi.featureFlags(), []);
  const windows = usePlatformData(() => platformApi.maintenanceWindows(), []);
  const commands = usePlatformData(() => platformApi.commands(), []);
  const summary = (infra.data ?? {}) as InfrastructureSummary;
  const snapshot = summary.latest_snapshot ?? {};
  const featureFlags = (flags.data?.items ?? []) as FeatureFlag[];
  const maintenanceWindows = (windows.data?.items ?? []) as MaintenanceWindow[];
  const readiness = capacity.data;

  return (
    <PlatformShell
      title="System Infrastructure"
      subtitle="Runtime health plus explicit readiness evidence for the 1,000-concurrent-tenant target. Configuration alone is never treated as proof of capacity."
      actions={<button className="platform-btn primary" onClick={() => platformApi.runDiagnostics("Infrastructure probe").then(() => { infra.reload(); capacity.reload(); })}>Run diagnostics</button>}
    >
      {infra.error ? <ErrorState error={infra.error} retry={infra.reload} /> : null}
      {capacity.error ? <ErrorState error={capacity.error} retry={capacity.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Status" value={<StatusBadge value={summary.status} />} />
        <MetricCard label="1,000-tenant target" value={<StatusBadge value={readiness?.status ?? "UNKNOWN"} />} caption="Must be load-test verified" tone={readiness?.status === "VERIFIED" ? "green" : "amber"} mark="1K" />
        <MetricCard label="Read replica" value={<StatusBadge value={readiness?.checks.read_replica_or_split_read_dsn ? "CONFIGURED" : "NOT_CONFIGURED"} />} caption="DATABASE_READ_URL split" tone={readiness?.checks.read_replica_or_split_read_dsn ? "green" : "amber"} mark="RR" />
        <MetricCard label="DB pooler" value={<StatusBadge value={readiness?.checks.external_connection_pooler ? "EXTERNAL" : "PROCESS_LOCAL"} />} caption="PgBouncer/managed proxy recommended at scale" tone={readiness?.checks.external_connection_pooler ? "green" : "amber"} mark="DB" />
        <MetricCard label="Active SaaS workers" value={readiness?.observed.active_saas_workers ?? summary.workers ?? 0} caption="Horizontal queue consumers" tone={(readiness?.observed.active_saas_workers ?? 0) >= 2 ? "green" : "amber"} mark="WK" />
        <MetricCard label="API RPM" value={snapshot.api_requests_per_minute ?? "N/A"} />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Capacity gate</h2>
          <p>{readiness?.note ?? "Capacity evidence is loading."}</p>
          {readiness ? <DataTable><thead><tr><th>Control</th><th>Status</th></tr></thead><tbody>{Object.entries(readiness.checks).map(([check, passed]) => <tr key={check}><td>{check.replaceAll("_", " ")}</td><td><StatusBadge value={passed ? "PASS" : "REQUIRED"} /></td></tr>)}</tbody></DataTable> : <EmptyState label="No capacity evidence returned." />}
          <p><small>Observed: {readiness?.observed.real_tenants ?? 0} real tenants · {readiness?.observed.users ?? 0} users · queue depth {readiness?.observed.queue_depth ?? 0}. The repository load harness is the authority for the 1,000-tenant claim.</small></p>
        </div>
        <div className="platform-card">
          <h2>Live infrastructure</h2>
          <p>CPU: {snapshot.cpu_percent ?? "N/A"} · RAM: {snapshot.memory_percent ?? "N/A"}</p>
          <p>DB connections: {snapshot.db_connections_active ?? "N/A"}</p>
          <p>Workers: {summary.workers ?? 0}</p>
          <small>Scale horizontally behind the API/load balancer and use an external PostgreSQL connection pooler instead of multiplying a large SQLAlchemy pool per process.</small>
        </div>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Feature flags</h2>
          <div className="platform-form" style={{ gridTemplateColumns: "1fr auto", marginBottom: 12 }}><input value={key} onChange={(event) => setKey(event.target.value)} /><button className="platform-btn primary" onClick={() => platformApi.createFeatureFlag({ key, name: key, enabled: false, scope: "GLOBAL" }).then(flags.reload)}>Create flag</button></div>
          {featureFlags.length ? <DataTable><thead><tr><th>Flag</th><th>Scope</th><th>Status</th><th>Action</th></tr></thead><tbody>{featureFlags.map((flag) => <tr key={flag.id}><td>{flag.name}<br /><small>{flag.key}</small></td><td>{flag.scope ?? "GLOBAL"}</td><td><StatusBadge value={flag.enabled ? "ENABLED" : "DISABLED"} /></td><td><button className="platform-btn" onClick={() => platformApi.toggleFeatureFlag(flag.id, !flag.enabled).then(flags.reload)}>Toggle</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No feature flags yet." />}
        </div>
        <div className="platform-card">
          <h2>Critical controls</h2>
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} style={{ width: "100%", minHeight: 70 }} />
          <div className="platform-actions"><button className="platform-btn danger" onClick={() => platformApi.resetApiTokens(reason).then(commands.reload)}>Reset global API tokens</button><button className="platform-btn danger" onClick={() => platformApi.failoverDatabase(reason).then(commands.reload)}>Request DB failover</button></div>
          <h2>Maintenance windows</h2>
          {maintenanceWindows.length ? maintenanceWindows.map((window) => <p key={window.id}><StatusBadge value={window.status} /> {window.title ?? "Maintenance"}</p>) : <EmptyState label="No maintenance windows." />}
          <h2>Recent jobs</h2>
          {(commands.data?.items ?? []).slice(0, 5).map((job: PlatformCommandJob) => <p key={job.id}><StatusBadge value={job.status} /> {job.command_name}</p>)}
        </div>
      </section>
    </PlatformShell>
  );
}
