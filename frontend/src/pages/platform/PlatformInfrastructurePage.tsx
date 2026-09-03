import React, { useEffect, useRef, useState } from "react";

import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import {
  platformDiagnostics,
  type DbCheckResult,
  type LiveMetrics,
  type SpeedTestResult,
} from "../../services/platformDiagnostics";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { Sparkline } from "./components/Sparkline";
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
    api_error_rate?: number | null;
    api_p95_latency_ms?: number | null;
    api_requests_per_minute?: number | null;
    status?: string;
  } | null;
};

type FeatureFlag = { id: string; key: string; name: string; scope?: string; enabled: boolean };
type MaintenanceWindow = { id: string; status?: string; title?: string };

const percent = (value?: number | null): string => (value == null ? "N/A" : `${Number(value).toFixed(1)}%`);
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

const bytesHuman = (value?: number | null): string => {
  if (value == null) return "N/A";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
};

const HISTORY_POINTS = 60;

type LiveHistory = { cpu: number[]; mem: number[]; db: number[]; rx: number[]; tx: number[] };

function useLiveMetrics(intervalMs = 1000) {
  const [latest, setLatest] = useState<LiveMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [history, setHistory] = useState<LiveHistory>({ cpu: [], mem: [], db: [], rx: [], tx: [] });
  const pausedRef = useRef(false);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    let active = true;
    let timer = 0;
    const tick = async () => {
      if (!pausedRef.current && document.visibilityState === "visible") {
        try {
          const metrics = await platformDiagnostics.live();
          if (!active) return;
          setLatest(metrics);
          setError(null);
          setHistory((prev) => ({
            cpu: [...prev.cpu, metrics.cpu_percent ?? 0].slice(-HISTORY_POINTS),
            mem: [...prev.mem, metrics.memory_percent ?? 0].slice(-HISTORY_POINTS),
            db: [...prev.db, metrics.db_utilisation_percent ?? 0].slice(-HISTORY_POINTS),
            rx: [...prev.rx, metrics.network_rx_bytes_per_sec ?? 0].slice(-HISTORY_POINTS),
            tx: [...prev.tx, metrics.network_tx_bytes_per_sec ?? 0].slice(-HISTORY_POINTS),
          }));
        } catch (err) {
          if (active) setError(err instanceof Error ? err.message : "Live metrics unavailable");
        }
      }
      if (active) timer = window.setTimeout(tick, intervalMs);
    };
    void tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [intervalMs]);

  return { latest, history, error, paused, setPaused };
}

const LiveCard: React.FC<{
  label: string;
  value: React.ReactNode;
  caption?: React.ReactNode;
  data: number[];
  max?: number;
  color?: string;
}> = ({ label, value, caption, data, max, color }) => (
  <section className="platform-card platform-live-card">
    <div className="platform-live-card__head">
      <span className="label">{label}</span>
      <span className="platform-live-card__value">{value}</span>
    </div>
    <Sparkline data={data} max={max} color={color} />
    {caption ? <div className="caption">{caption}</div> : null}
  </section>
);

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

  const { latest, history, error: liveError, paused, setPaused } = useLiveMetrics(1000);

  const [dbChecking, setDbChecking] = useState(false);
  const [dbResult, setDbResult] = useState<DbCheckResult | null>(null);
  const [dbError, setDbError] = useState<string | null>(null);

  const [speedRunning, setSpeedRunning] = useState(false);
  const [speedStage, setSpeedStage] = useState<string>("");
  const [speedResult, setSpeedResult] = useState<SpeedTestResult | null>(null);
  const [speedError, setSpeedError] = useState<string | null>(null);

  const runDbCheck = async () => {
    setDbChecking(true);
    setDbError(null);
    try {
      setDbResult(await platformDiagnostics.dbCheck(10));
    } catch (err) {
      setDbError(err instanceof Error ? err.message : "Database check failed");
    } finally {
      setDbChecking(false);
    }
  };

  const runSpeedTest = async () => {
    setSpeedRunning(true);
    setSpeedError(null);
    setSpeedResult(null);
    try {
      const result = await platformDiagnostics.speedTest({ onProgress: setSpeedStage });
      setSpeedResult(result);
    } catch (err) {
      setSpeedError(err instanceof Error ? err.message : "Speed test failed");
    } finally {
      setSpeedRunning(false);
      setSpeedStage("");
    }
  };

  return (
    <PlatformShell
      title="System Infrastructure"
      subtitle="Live host, database and network health"
      actions={
        <button className="platform-btn primary" onClick={() => platformApi.runDiagnostics("Infrastructure probe").then(infra.reload)}>
          Run diagnostics
        </button>
      }
    >
      {infra.error ? <ErrorState error={infra.error} retry={infra.reload} /> : null}

      {/* ---- Real-time monitor (updates every second) ---- */}
      <section className="platform-section-head">
        <h2>Live monitor</h2>
        <div className="platform-actions">
          <span className={`platform-live-chip ${paused ? "offline" : "live"}`}><i />{paused ? "Paused" : "Live"}</span>
          <button className="platform-btn compact" onClick={() => setPaused((value) => !value)}>{paused ? "Resume" : "Pause"}</button>
        </div>
      </section>
      {liveError ? <div className="platform-inline-note">Live sampling: {liveError}</div> : null}
      <section className="platform-grid platform-grid--live">
        <LiveCard label="Host CPU" value={percent(latest?.cpu_percent)} data={history.cpu} max={100} color="#3b82f6" />
        <LiveCard label="Host memory" value={percent(latest?.memory_percent)} data={history.mem} max={100} color="#a855f7" />
        <LiveCard
          label="Database"
          value={percent(latest?.db_utilisation_percent)}
          caption={`${latest?.db_connections_active ?? "–"} / ${latest?.db_connections_max ?? "–"} connections`}
          data={history.db}
          max={100}
          color="#0ea5e9"
        />
        <LiveCard label="Download" value={bytesPerSec(latest?.network_rx_bytes_per_sec)} data={history.rx} color="#22c55e" />
        <LiveCard label="Upload" value={bytesPerSec(latest?.network_tx_bytes_per_sec)} data={history.tx} color="#f59e0b" />
        <LiveCard label="Durable queue" value={numeric(latest?.queue_depth)} caption="Pending / running command jobs" data={history.db.map(() => latest?.queue_depth ?? 0)} />
      </section>

      {/* ---- On-demand diagnostics: DB check + network speed test ---- */}
      <section className="platform-two platform-two--spaced">
        <div className="platform-card">
          <div className="platform-section-head compact">
            <h2>Database check</h2>
            <button className="platform-btn primary" onClick={runDbCheck} disabled={dbChecking}>
              {dbChecking ? "Running…" : "Run check"}
            </button>
          </div>
          {dbError ? <div className="platform-inline-note bad">{dbError}</div> : null}
          {dbResult ? (
            <div className="platform-grid platform-grid--tight">
              <MetricCard label="Avg latency" value={numeric(dbResult.avg_ms, " ms")} tone={(dbResult.avg_ms ?? 0) > 25 ? "amber" : "green"} caption={`min ${numeric(dbResult.min_ms, " ms")} · max ${numeric(dbResult.max_ms, " ms")}`} />
              <MetricCard label="Connections" value={`${dbResult.connections_active ?? "–"} / ${dbResult.connections_max ?? "–"}`} caption={`Utilisation ${numeric(dbResult.utilisation_percent, "%")}`} />
              <MetricCard label="Database size" value={bytesHuman(dbResult.database_size_bytes)} caption={dbResult.server_version ? `PostgreSQL ${dbResult.server_version}` : undefined} />
              <MetricCard label="Result" value={<StatusBadge value={dbResult.ok ? "HEALTHY" : "ERROR"} />} caption={`${dbResult.samples} samples`} />
            </div>
          ) : (
            <EmptyState label="Run a check to measure latency and pool use." />
          )}
        </div>

        <div className="platform-card">
          <div className="platform-section-head compact">
            <h2>Speed test</h2>
            <button className="platform-btn primary" onClick={runSpeedTest} disabled={speedRunning}>
              {speedRunning ? "Testing…" : "Run speed test"}
            </button>
          </div>
          {speedRunning ? <div className="platform-inline-note">{speedStage || "Preparing…"}</div> : null}
          {speedError ? <div className="platform-inline-note bad">{speedError}</div> : null}
          {speedResult ? (
            <div className="platform-grid platform-grid--tight">
              <MetricCard label="Download" value={numeric(speedResult.download_mbps, " Mbps")} tone="green" caption={bytesHuman(speedResult.download_bytes)} />
              <MetricCard label="Upload" value={numeric(speedResult.upload_mbps, " Mbps")} tone="blue" caption={bytesHuman(speedResult.upload_bytes)} />
              <MetricCard label="Latency" value={numeric(speedResult.latency_ms, " ms")} caption={`jitter ${numeric(speedResult.jitter_ms, " ms")}`} />
            </div>
          ) : (
            !speedRunning && <EmptyState label="Run a test to measure latency and throughput." />
          )}
        </div>
      </section>

      {/* ---- Persisted snapshot summary + API health ---- */}
      <section className="platform-section-head">
        <h2>API health</h2>
        {snapshot.captured_at ? <span className="platform-muted">{new Date(snapshot.captured_at).toLocaleTimeString()}</span> : null}
      </section>
      <section className="platform-grid">
        <MetricCard label="Status" value={<StatusBadge value={summary.status} />} />
        <MetricCard label="API throughput" value={numeric(snapshot.api_requests_per_minute, " rpm")} caption={`p95 ${numeric(snapshot.api_p95_latency_ms, " ms")}`} />
        <MetricCard label="API error rate" value={snapshot.api_error_rate == null ? "N/A" : `${(snapshot.api_error_rate * 100).toFixed(2)}%`} tone={(snapshot.api_error_rate ?? 0) >= 0.05 ? "amber" : undefined} caption="Rolling 60m window" />
        <MetricCard label="Workers online" value={summary.workers ?? 0} caption="Reporting heartbeats" />
      </section>

      {/* ---- Controls ---- */}
      <section className="platform-two platform-two--spaced">
        <div className="platform-card">
          <h2>Feature flags</h2>
          <div className="platform-form" style={{ gridTemplateColumns: "1fr auto", marginBottom: 12 }}>
            <input value={key} onChange={(event) => setKey(event.target.value)} />
            <button className="platform-btn primary" onClick={() => platformApi.createFeatureFlag({ key, name: key, enabled: false, scope: "GLOBAL" }).then(flags.reload)}>Create flag</button>
          </div>
          {featureFlags.length ? (
            <DataTable>
              <thead><tr><th>Flag</th><th>Scope</th><th>Status</th><th>Action</th></tr></thead>
              <tbody>
                {featureFlags.map((flag) => (
                  <tr key={flag.id}>
                    <td>{flag.name}<br /><small>{flag.key}</small></td>
                    <td>{flag.scope ?? "GLOBAL"}</td>
                    <td><StatusBadge value={flag.enabled ? "ENABLED" : "DISABLED"} /></td>
                    <td><button className="platform-btn" onClick={() => platformApi.toggleFeatureFlag(flag.id, !flag.enabled).then(flags.reload)}>Toggle</button></td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          ) : <EmptyState label="No feature flags yet." />}
        </div>
        <div className="platform-card">
          <h2>Critical controls</h2>
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} style={{ width: "100%", minHeight: 70 }} />
          <div className="platform-actions">
            <button className="platform-btn danger" onClick={() => platformApi.resetApiTokens(reason).then(commands.reload)}>Reset global API tokens</button>
            <button className="platform-btn danger" onClick={() => platformApi.failoverDatabase(reason).then(commands.reload)}>Request DB failover</button>
          </div>
          <h2>Maintenance windows</h2>
          {maintenanceWindows.length ? maintenanceWindows.map((window) => <p key={window.id}><StatusBadge value={window.status} /> {window.title ?? "Maintenance"}</p>) : <EmptyState label="No maintenance windows." />}
          <h2>Recent jobs</h2>
          {(commands.data?.items ?? []).slice(0, 5).map((job: PlatformCommandJob) => <p key={job.id}><StatusBadge value={job.status} /> {job.command_name}</p>)}
        </div>
      </section>
    </PlatformShell>
  );
}
