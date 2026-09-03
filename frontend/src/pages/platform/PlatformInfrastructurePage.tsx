import React, { useState } from "react";

import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type InfrastructureSummary = {
  status?: string;
  workers?: number;
  latest_snapshot?: {
    captured_at?: string;
    cpu_percent?: number | null;
    memory_percent?: number | null;
    db_connections_active?: number | null;
    db_connections_max?: number | null;
    queue_depth?: number | null;
    worker_count?: number | null;
    storage_used_percent?: number | null;
    storage_used_bytes?: number | null;
    storage_total_bytes?: number | null;
    network_rx_bytes_per_sec?: number | null;
    network_tx_bytes_per_sec?: number | null;
    api_error_rate?: number | null;
    api_p95_latency_ms?: number | null;
    api_requests_per_minute?: number | null;
    status?: string;
  } | null;
};

const percent = (value?: number | null): string =>
  value == null ? "N/A" : `${Number(value).toFixed(1)}%`;

const numeric = (value?: number | null, suffix = ""): string =>
  value == null ? "N/A" : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;

const bytesPerSec = (value?: number | null): string => {
  if (value == null) return "N/A";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
};

const dbUtilisation = (active?: number | null, max?: number | null): string => {
  if (active == null || !max) return "N/A";
  return `${((active / max) * 100).toFixed(1)}%`;
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
  const flags = usePlatformData(() => platformApi.featureFlags(), []);
  const windows = usePlatformData(() => platformApi.maintenanceWindows(), []);
  const commands = usePlatformData(() => platformApi.commands(), []);
  const summary = (infra.data ?? {}) as InfrastructureSummary;
  const snapshot = summary.latest_snapshot ?? {};
  const featureFlags = (flags.data?.items ?? []) as FeatureFlag[];
  const maintenanceWindows = (windows.data?.items ?? []) as MaintenanceWindow[];

  return (
    <PlatformShell
      title="System Infrastructure"
      subtitle="Feature flags, maintenance windows, worker heartbeat, storage/SMTP/API health and critical command jobs."
      actions={<button className="platform-btn primary" onClick={() => platformApi.runDiagnostics("Infrastructure probe").then(infra.reload)}>Run diagnostics</button>}
    >
      {infra.error ? <ErrorState error={infra.error} retry={infra.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Status" value={<StatusBadge value={summary.status} />} caption={snapshot.captured_at ? `As of ${new Date(snapshot.captured_at).toLocaleTimeString()}` : "Awaiting first sample"} />
        <MetricCard label="Host CPU" value={percent(snapshot.cpu_percent)} caption="System-wide utilisation" />
        <MetricCard label="Host memory" value={percent(snapshot.memory_percent)} tone="purple" caption="Resident memory in use" />
        <MetricCard label="Storage used" value={percent(snapshot.storage_used_percent)} caption="Object/upload volume" />
        <MetricCard label="API throughput" value={numeric(snapshot.api_requests_per_minute, " rpm")} caption={`p95 ${numeric(snapshot.api_p95_latency_ms, " ms")}`} />
        <MetricCard label="Workers online" value={summary.workers ?? 0} caption={`${snapshot.worker_count ?? 0} reporting heartbeats`} />
      </section>
      <section className="platform-card" style={{ marginTop: 16 }}>
        <h2>Database &amp; network status</h2>
        <div className="platform-grid">
          <MetricCard label="DB connections" value={snapshot.db_connections_active == null ? "N/A" : `${snapshot.db_connections_active}${snapshot.db_connections_max ? ` / ${snapshot.db_connections_max}` : ""}`} caption={`Pool utilisation ${dbUtilisation(snapshot.db_connections_active, snapshot.db_connections_max)}`} />
          <MetricCard label="DB utilisation" value={dbUtilisation(snapshot.db_connections_active, snapshot.db_connections_max)} tone={((snapshot.db_connections_active ?? 0) / (snapshot.db_connections_max || 1)) > 0.75 ? "amber" : undefined} caption="Active vs. max connections" />
          <MetricCard label="Durable queue" value={numeric(snapshot.queue_depth)} caption="Pending / running command jobs" />
          <MetricCard label="API error rate" value={snapshot.api_error_rate == null ? "N/A" : `${(snapshot.api_error_rate * 100).toFixed(2)}%`} tone={(snapshot.api_error_rate ?? 0) >= 0.05 ? "amber" : undefined} caption="Rolling 60m window" />
          <MetricCard label="Network in" value={bytesPerSec(snapshot.network_rx_bytes_per_sec)} caption="Host ingress" />
          <MetricCard label="Network out" value={bytesPerSec(snapshot.network_tx_bytes_per_sec)} caption="Host egress" />
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
