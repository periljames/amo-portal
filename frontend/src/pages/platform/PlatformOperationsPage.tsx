import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getToken } from "../../services/auth";
import {
  persistPlatformDataMode,
  readPlatformDataMode,
  replaceLocationDataMode,
} from "../../services/platformEnvironment";
import {
  operationsStreamUrl,
  platformOperationsApi,
  type DataMode,
  type OpsSnapshot,
} from "../../services/platformOperations";
import { MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";

const sections = [
  "NOC",
  "Infrastructure",
  "Database",
  "Network",
  "Storage",
  "SLOs",
  "Capacity",
  "Tenant Fleet",
  "Incidents",
  "Product",
  "Users",
  "Commercial",
  "Changes",
  "Jobs",
] as const;
type Section = (typeof sections)[number];
type FleetFilters = { q: string; health: string; sort: "health" | "name" | "traffic" | "users" };

function pct(value: unknown, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "—";
}

function number(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : "—";
}

function bytes(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let current = n;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) { current /= 1024; index += 1; }
  return `${current.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function metricValue(payload: any): string {
  const item = payload?.items?.[0] || payload?.series?.[0];
  const raw = item?.value;
  const value = Array.isArray(raw) ? raw[1] : raw;
  if (value == null) return payload?.stale ? "Stale / unavailable" : "—";
  const unit = payload?.unit;
  const suffix = unit === "percent" ? "%" : unit === "bytes_per_second" ? " B/s" : unit === "bytes" ? " B" : unit === "milliseconds" ? " ms" : "";
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function forecastValue(payload: any): string {
  const forecast = payload?.forecast;
  if (!forecast?.available) return "Insufficient history";
  if (forecast.days_to_threshold == null) return `${Number(forecast.slope_per_hour || 0).toFixed(3)}/h · no threshold ETA`;
  return `${forecast.days_to_threshold} days to ${forecast.threshold}%`;
}

async function stream(mode: DataMode, signal: AbortSignal, onSnapshot: (snapshot: OpsSnapshot) => void) {
  const token = getToken();
  const response = await fetch(operationsStreamUrl(mode), {
    credentials: "include",
    signal,
    headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!response.ok || !response.body) throw new Error(`Operations stream unavailable (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      if (data) {
        try {
          const parsed = JSON.parse(data);
          if (parsed?.snapshot) onSnapshot(parsed.snapshot as OpsSnapshot);
        } catch { /* isolate malformed frames */ }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

const Table: React.FC<{ headers: string[]; rows: React.ReactNode[][] }> = ({ headers, rows }) => (
  <div className="platform-table-wrap">
    <table className="platform-table">
      <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
      <tbody>{rows.length ? rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>) : <tr><td colSpan={headers.length}>No records in this view.</td></tr>}</tbody>
    </table>
  </div>
);

const Toolbar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="platform-toolbar-actions" style={{ flexWrap: "wrap", justifyContent: "flex-start", marginBottom: 12 }}>{children}</div>
);

export default function PlatformOperationsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mode, setMode] = useState<DataMode>(() => readPlatformDataMode(location.search) as DataMode);
  const [section, setSection] = useState<Section>("NOC");
  const [snapshot, setSnapshot] = useState<OpsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<"connecting" | "live" | "degraded">("connecting");
  const [detail, setDetail] = useState<Record<string, any>>({});
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<Record<string, any> | null>(null);
  const [selectedTenant, setSelectedTenant] = useState<Record<string, any> | null>(null);
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Record<string, any> | null>(null);
  const [fleetDraft, setFleetDraft] = useState<FleetFilters>({ q: "", health: "", sort: "health" });
  const [fleetFilters, setFleetFilters] = useState<FleetFilters>({ q: "", health: "", sort: "health" });
  const [fleetCursor, setFleetCursor] = useState<string | null>(null);
  const [fleetCursorHistory, setFleetCursorHistory] = useState<(string | null)[]>([]);
  const [userDraft, setUserDraft] = useState("");
  const [userQuery, setUserQuery] = useState("");
  const [userOffset, setUserOffset] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const selected = readPlatformDataMode(location.search) as DataMode;
    persistPlatformDataMode(selected);
    if (selected !== mode) setMode(selected);
  }, [location.search, mode]);

  const selectMode = (next: DataMode) => {
    persistPlatformDataMode(next);
    setMode(next);
    setFleetCursor(null);
    setFleetCursorHistory([]);
    setSelectedTenantIds([]);
    navigate(replaceLocationDataMode(location.pathname, location.search, next), { replace: true });
  };

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    setConnection("connecting");
    setError(null);
    void platformOperationsApi.bootstrap(mode)
      .then((next) => { if (generation.current === current) { setSnapshot(next.snapshot); setConnection("live"); } })
      .catch((reason) => { if (generation.current === current) { setError(reason instanceof Error ? reason.message : "Operations gateway unavailable"); setConnection("degraded"); } });
    void stream(mode, controller.signal, (next) => {
      if (generation.current === current) { setSnapshot(next); setError(null); setConnection("live"); }
    }).catch((reason) => {
      if (!controller.signal.aborted && generation.current === current) {
        setError(reason instanceof Error ? reason.message : "Live operations stream unavailable");
        setConnection("degraded");
      }
    });
    return () => controller.abort();
  }, [mode]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        let next: Record<string, any> = {};
        if (section === "Infrastructure") {
          const [summary, nodes, queues] = await Promise.all([
            platformOperationsApi.infrastructureSummary(), platformOperationsApi.nodes(), platformOperationsApi.queues(mode),
          ]);
          next = { summary, nodes, queues };
        } else if (section === "Database") {
          const [health, activeConnections, capacity] = await Promise.all([
            platformOperationsApi.databaseHealth(),
            platformOperationsApi.metricTimeseries("db_active_connections", "1h"),
            platformOperationsApi.database(mode),
          ]);
          next = { health, activeConnections, capacity };
        } else if (section === "Network") {
          next = (await platformOperationsApi.infrastructureSummary()).network || {};
        } else if (section === "Storage") {
          next = (await platformOperationsApi.infrastructureSummary()).storage || {};
        } else if (section === "SLOs") {
          const [windows, slow, errors] = await Promise.all([
            platformOperationsApi.sloWindows(mode), platformOperationsApi.slowRoutes(mode), platformOperationsApi.errorRoutes(mode),
          ]);
          next = { windows, slow, errors };
        } else if (section === "Capacity") {
          const [capacity, forecast] = await Promise.all([platformOperationsApi.capacity(mode), platformOperationsApi.capacityForecast("7d")]);
          next = { capacity, forecast };
        } else if (section === "Tenant Fleet") {
          const [fleet, views] = await Promise.all([
            platformOperationsApi.tenantHealth({ data_mode: mode, q: fleetFilters.q || undefined, health: fleetFilters.health || undefined, sort: fleetFilters.sort, limit: 100, cursor: fleetCursor }),
            platformOperationsApi.savedViews("tenant_fleet"),
          ]);
          next = { fleet, views };
        } else if (section === "Incidents") {
          next = await platformOperationsApi.incidentCenter();
        } else if (section === "Product") {
          next = await platformOperationsApi.productRollups(mode, 30);
        } else if (section === "Users") {
          const params = new URLSearchParams({ limit: "100", offset: String(userOffset) });
          if (userQuery) params.set("q", userQuery);
          next = await platformOperationsApi.users(params);
        } else if (section === "Changes") {
          next = await platformOperationsApi.changeMarkers();
        }
        if (active) setDetail(next);
      } catch (reason) {
        if (active) setDetailError(reason instanceof Error ? reason.message : "Unable to load this operations view");
      } finally {
        if (active) setDetailLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [section, mode, refreshNonce, fleetFilters, fleetCursor, userOffset, userQuery]);

  const overview = snapshot?.overview || {};
  const slo = snapshot?.slo || {};
  const capacity = snapshot?.capacity || {};
  const fleet = snapshot?.fleet || {};
  const commercial = snapshot?.commercial || {};
  const changes = snapshot?.changes || {};
  const jobs = snapshot?.jobs || {};
  const jobItems = jobs.items || [];
  const stale = Boolean(snapshot?.freshness?.stale);

  const subtitle = useMemo(() => {
    const generated = snapshot?.generated_at ? new Date(snapshot.generated_at).toLocaleString() : "awaiting first prepared snapshot";
    return `Prepared control-plane snapshot · ${mode} · ${generated}`;
  }, [mode, snapshot?.generated_at]);

  const refresh = () => setRefreshNonce((value) => value + 1);

  const openNode = async (nodeId: string) => {
    setSelectedNode(nodeId);
    setNodeDetail(null);
    try {
      const [node, trend] = await Promise.all([
        platformOperationsApi.node(nodeId),
        platformOperationsApi.nodeTimeseries(nodeId, "host_cpu_utilization", "1h"),
      ]);
      setNodeDetail({ node, trend });
    } catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to load node detail"); }
  };

  const openTenant = async (tenantId: string) => {
    setSelectedTenant({ loading: true, tenant_id: tenantId });
    try { setSelectedTenant(await platformOperationsApi.tenant360(tenantId, mode)); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to load Tenant 360"); setSelectedTenant(null); }
  };

  const openIncident = async (incidentId: string) => {
    try { setSelectedIncident(await platformOperationsApi.incidentDetail(incidentId)); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to load incident timeline"); }
  };

  const createIncident = async () => {
    const title = window.prompt("Incident title");
    if (!title) return;
    const severity = (window.prompt("Severity: INFO, LOW, MEDIUM, HIGH or CRITICAL", "HIGH") || "HIGH").toUpperCase();
    try { await platformOperationsApi.createIncident({ title, severity, source: "superadmin-console" }); refresh(); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to create incident"); }
  };

  const transitionIncident = async (incidentId: string, target: string) => {
    const message = window.prompt(`Reason / update for ${target}`) || "";
    try {
      await platformOperationsApi.transitionIncident(incidentId, target, message);
      setSelectedIncident(await platformOperationsApi.incidentDetail(incidentId));
      refresh();
    } catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to transition incident"); }
  };

  const runBulk = async (commandName: string, dryRun: boolean) => {
    if (!selectedTenantIds.length) return;
    const reason = window.prompt(`Reason for ${commandName} on ${selectedTenantIds.length} tenant(s)`);
    if (!reason) return;
    try {
      await platformOperationsApi.bulk({ command_name: commandName, reason, tenant_ids: selectedTenantIds, data_mode: mode, dry_run: dryRun, idempotency_key: `${commandName}-${Date.now()}` });
      setSelectedTenantIds([]);
      refresh();
    } catch (errorValue) { setDetailError(errorValue instanceof Error ? errorValue.message : "Unable to queue bulk operation"); }
  };

  const approveJob = async (jobId: string) => {
    const reason = window.prompt("Approval reason. Approval must be by a different platform superuser.");
    if (!reason) return;
    try { await platformOperationsApi.approve(jobId, reason); refresh(); }
    catch (errorValue) { setDetailError(errorValue instanceof Error ? errorValue.message : "Unable to approve job"); }
  };

  const saveCurrentFleetView = async () => {
    const name = window.prompt("Saved view name");
    if (!name) return;
    try { await platformOperationsApi.saveView({ scope: "tenant_fleet", name, filters: fleetFilters }); refresh(); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to save view"); }
  };

  const createChangeMarker = async () => {
    const kind = (window.prompt("Change kind: DEPLOYMENT, FEATURE_FLAG, MAINTENANCE, INCIDENT, CONFIGURATION or MIGRATION", "DEPLOYMENT") || "").toUpperCase();
    const title = window.prompt("Change title");
    if (!kind || !title) return;
    const reference = window.prompt("Reference (commit, PR, release or ticket)") || undefined;
    try { await platformOperationsApi.createChangeMarker({ kind, title, reference }); refresh(); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "Unable to record change marker"); }
  };

  const fleetItems = detail.fleet?.items || [];
  const fleetViews = detail.views?.items || [];
  const incidentItems = detail.items || [];
  const userItems = detail.items || [];
  const infra = detail.summary || {};
  const sloWindows = detail.windows?.windows || {};
  const burn = detail.windows?.burn || {};

  return (
    <PlatformShell title="Operations Control Center" subtitle={subtitle} actions={
      <div className="platform-toolbar-actions">
        <StatusBadge value={connection === "live" ? (stale ? "STALE" : "LIVE") : connection === "connecting" ? "CONNECTING" : "DEGRADED"} />
        <button className={`platform-btn ${mode === "REAL" ? "primary" : ""}`} onClick={() => selectMode("REAL")}>REAL</button>
        <button className={`platform-btn ${mode === "DEMO" ? "primary" : ""}`} onClick={() => selectMode("DEMO")}>DEMO</button>
        <button className="platform-btn" onClick={refresh}>Refresh view</button>
      </div>
    }>
      {error ? <section className="platform-card"><strong>Operations gateway degraded.</strong><p>{error}</p><p>Tenant application traffic is independent of this gateway. The last prepared snapshot remains visible when available.</p></section> : null}
      {detailError ? <section className="platform-card"><strong>View request failed.</strong><p>{detailError}</p></section> : null}
      {stale ? <section className="platform-card"><strong>Stale telemetry.</strong><p>Showing last-known data. Snapshot age: {number(snapshot?.freshness?.age_seconds)} seconds.</p></section> : null}

      <div className="platform-tabs" role="tablist" aria-label="Operations views">
        {sections.map((item) => <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}>{item}</button>)}
      </div>
      {detailLoading ? <section className="platform-card"><p>Loading bounded operations data…</p></section> : null}

      {section === "NOC" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Platform status" value={<StatusBadge value={overview.platform_status || slo.status || "UNKNOWN"} />} caption="Prepared state; browser count does not multiply DB refresh work" tone="green" />
          <MetricCard label="Host CPU" value={overview.cpu_percent == null ? "No Prometheus sample" : `${Number(overview.cpu_percent).toFixed(1)}%`} caption="Bare-metal/node telemetry" tone="blue" />
          <MetricCard label="Host memory" value={overview.memory_percent == null ? "No Prometheus sample" : `${Number(overview.memory_percent).toFixed(1)}%`} tone="purple" />
          <MetricCard label="SLO burn rate" value={`${Number(slo.burn_rate || 0).toFixed(2)}×`} caption={`Availability target ${pct(slo.availability_target, 3)}`} tone={Number(slo.burn_rate || 0) >= 2 ? "red" : "green"} />
          <MetricCard label="Active tenants" value={number(overview.active_tenants)} caption={`${number(fleet.critical)} critical · ${number(fleet.warning)} warning`} />
          <MetricCard label="Durable work queue" value={number(overview.queue_depth)} caption="High-risk work requires second-person approval" tone="amber" />
        </div>
        <section className="platform-card"><h2>Immediate attention</h2><Table headers={["Tenant", "Health", "Users", "Requests", "p95", "Quota"]} rows={(fleet.items || []).slice(0, 20).map((item: any) => [<button className="platform-btn" onClick={() => void openTenant(item.tenant_id)}>{item.name || item.amo_code}</button>, <StatusBadge value={item.health?.status} />, number(item.users), number(item.requests_window), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.quota_percent == null ? "—" : `${Number(item.quota_percent).toFixed(1)}%`])} /></section>
      </>}

      {section === "Infrastructure" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Nodes discovered" value={number(detail.nodes?.items?.length)} />
          <MetricCard label="CPU user" value={metricValue(infra.host?.host_cpu_user)} />
          <MetricCard label="CPU system" value={metricValue(infra.host?.host_cpu_system)} />
          <MetricCard label="Load 5m" value={metricValue(infra.host?.host_load_5m)} />
          <MetricCard label="Runnable processes" value={metricValue(infra.host?.host_procs_running)} />
          <MetricCard label="OOM kills" value={metricValue(infra.host?.host_oom_kills)} tone="amber" />
          <MetricCard label="Container restarts · 1h" value={metricValue(infra.containers?.container_restarts_1h)} tone="amber" />
          <MetricCard label="Queue depth" value={metricValue(infra.workers?.queue_depth)} />
        </div>
        <section className="platform-card"><h2>Node fleet</h2><Table headers={["Node", "CPU", "Memory", "Load 1m", "I/O wait", "Targets", "Inspect"]} rows={(detail.nodes?.items || []).map((item: any) => [item.node_id, item.host_cpu_utilization == null ? "—" : `${Number(item.host_cpu_utilization).toFixed(1)}%`, item.host_memory_utilization == null ? "—" : `${Number(item.host_memory_utilization).toFixed(1)}%`, number(item.host_load_1m), item.host_cpu_iowait == null ? "—" : `${Number(item.host_cpu_iowait).toFixed(1)}%`, (item.targets || []).map((target: any) => `${target.job}:${Number(target.up) === 1 ? "up" : "down"}`).join(", ") || "—", <button className="platform-btn" onClick={() => void openNode(item.node_id)}>Details</button>])} /></section>
        {selectedNode && <section className="platform-card"><h2>Node detail · {selectedNode}</h2><p>CPU: {metricValue(nodeDetail?.node?.metrics?.host_cpu_utilization)} · Memory: {metricValue(nodeDetail?.node?.metrics?.host_memory_utilization)} · Swap: {metricValue(nodeDetail?.node?.metrics?.host_swap_utilization)} · Ingress: {metricValue(nodeDetail?.node?.metrics?.network_ingress)} · Egress: {metricValue(nodeDetail?.node?.metrics?.network_egress)}</p><Table headers={["Time", "CPU %"]} rows={((nodeDetail?.trend?.series?.[0]?.values || []).slice(-12)).map((value: any[]) => [new Date(Number(value[0]) * 1000).toLocaleTimeString(), Number(value[1]).toFixed(2)])} /></section>}
      </>}

      {section === "Database" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Active connections" value={metricValue(detail.health?.metrics?.db_active_connections)} />
          <MetricCard label="Connection utilisation" value={metricValue(detail.health?.metrics?.db_connection_utilization)} />
          <MetricCard label="Waiting connections" value={metricValue(detail.health?.metrics?.db_waiting_connections)} tone="amber" />
          <MetricCard label="Lock waiters" value={metricValue(detail.health?.metrics?.db_lock_waiters)} tone="amber" />
          <MetricCard label="Long queries" value={metricValue(detail.health?.metrics?.db_long_queries)} tone="amber" />
          <MetricCard label="Database size" value={metricValue(detail.health?.metrics?.db_size)} />
          <MetricCard label="Replica lag" value={metricValue(detail.health?.metrics?.db_replica_lag)} />
          <MetricCard label="Transaction rate" value={metricValue(detail.health?.metrics?.db_transaction_rate)} />
        </div>
        <section className="platform-card"><h2>Active connection history · 1 hour</h2><Table headers={["Time", "Connections"]} rows={((detail.activeConnections?.series?.[0]?.values || []).slice(-20)).map((value: any[]) => [new Date(Number(value[0]) * 1000).toLocaleTimeString(), Number(value[1]).toFixed(0)])} /></section>
      </>}

      {section === "Network" && <div className="platform-metric-grid">
        <MetricCard label="Ingress" value={metricValue(detail.network_ingress)} /><MetricCard label="Egress" value={metricValue(detail.network_egress)} />
        <MetricCard label="Errors/sec" value={metricValue(detail.network_errors)} tone="amber" /><MetricCard label="Drops/sec" value={metricValue(detail.network_drops)} tone="amber" />
        <MetricCard label="TCP established" value={metricValue(detail.tcp_established)} /><MetricCard label="TCP in use" value={metricValue(detail.tcp_inuse)} /><MetricCard label="TIME_WAIT" value={metricValue(detail.tcp_timewait)} />
      </div>}

      {section === "Storage" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Filesystem utilisation" value={metricValue(detail.filesystem_utilization)} /><MetricCard label="Filesystem free" value={metricValue(detail.filesystem_free)} /><MetricCard label="Inode utilisation" value={metricValue(detail.filesystem_inode_utilization)} />
          <MetricCard label="Disk read" value={metricValue(detail.disk_read_throughput)} /><MetricCard label="Disk write" value={metricValue(detail.disk_write_throughput)} /><MetricCard label="Read latency" value={metricValue(detail.disk_read_latency)} /><MetricCard label="Write latency" value={metricValue(detail.disk_write_latency)} />
        </div>
        <section className="platform-card"><p>All storage telemetry is read from the server-owned query registry. The browser cannot submit arbitrary PromQL.</p></section>
      </>}

      {section === "SLOs" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Current availability" value={pct(slo.availability, 3)} caption={`Target ${pct(slo.availability_target, 3)}`} tone={slo.status === "CRITICAL" ? "red" : "green"} />
          <MetricCard label="p95 latency" value={slo.p95_latency_ms == null ? "—" : `${Number(slo.p95_latency_ms).toFixed(0)} ms`} /><MetricCard label="p99 latency" value={slo.p99_latency_ms == null ? "—" : `${Number(slo.p99_latency_ms).toFixed(0)} ms`} />
          <MetricCard label="Burn policy" value={<StatusBadge value={burn.status || "UNKNOWN"} />} caption={burn.fast ? "Fast burn detected" : burn.sustained ? "Sustained burn detected" : "Within burn policy"} />
          <MetricCard label="5m burn" value={`${Number(sloWindows["5m"]?.burn_rate || 0).toFixed(2)}×`} /><MetricCard label="1h burn" value={`${Number(sloWindows["1h"]?.burn_rate || 0).toFixed(2)}×`} /><MetricCard label="6h burn" value={`${Number(sloWindows["6h"]?.burn_rate || 0).toFixed(2)}×`} />
        </div>
        <section className="platform-card"><h2>Slow routes</h2><Table headers={["Route", "Status", "Requests", "Error rate", "p95", "p99"]} rows={(detail.slow?.items || slo.routes || []).map((item: any) => [item.route, <StatusBadge value={item.status} />, number(item.requests), pct(item.error_rate), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.p99_latency_ms == null ? "—" : `${Number(item.p99_latency_ms).toFixed(0)} ms`])} /></section>
      </>}

      {section === "Capacity" && <>
        <div className="platform-metric-grid"><MetricCard label="Capacity state" value={<StatusBadge value={detail.capacity?.status || capacity.status || "UNKNOWN"} />} /><MetricCard label="Estimated headroom" value={`${number(detail.capacity?.estimated_headroom_percent ?? capacity.estimated_headroom_percent)}%`} caption="Pressure indicator, not scale certification" /><MetricCard label="CPU 7-day trend" value={forecastValue(detail.forecast?.cpu)} /><MetricCard label="Memory 7-day trend" value={forecastValue(detail.forecast?.memory)} /><MetricCard label="Filesystem 7-day trend" value={forecastValue(detail.forecast?.filesystem)} /><MetricCard label="Requests/min" value={number(detail.capacity?.requests_per_minute ?? capacity.requests_per_minute)} /></div>
        <section className="platform-card"><p>{detail.forecast?.interpretation || capacity.forecast_note}</p></section>
      </>}

      {section === "Tenant Fleet" && <>
        <section className="platform-card">
          <h2>Server-filtered tenant fleet</h2>
          <Toolbar>
            <input aria-label="Tenant search" value={fleetDraft.q} onChange={(event) => setFleetDraft((current) => ({ ...current, q: event.target.value }))} placeholder="Tenant, code, country" />
            <select aria-label="Health" value={fleetDraft.health} onChange={(event) => setFleetDraft((current) => ({ ...current, health: event.target.value }))}><option value="">All health</option><option>CRITICAL</option><option>WARN</option><option>HEALTHY</option></select>
            <select aria-label="Sort" value={fleetDraft.sort} onChange={(event) => setFleetDraft((current) => ({ ...current, sort: event.target.value as FleetFilters["sort"] }))}><option value="health">Health</option><option value="traffic">Traffic</option><option value="users">Users</option><option value="name">Name</option></select>
            <button className="platform-btn primary" onClick={() => { setFleetFilters(fleetDraft); setFleetCursor(null); setFleetCursorHistory([]); }}>Apply filters</button>
            <button className="platform-btn" onClick={() => void saveCurrentFleetView()}>Save view</button>
          </Toolbar>
          {fleetViews.length ? <Toolbar>{fleetViews.map((view: any) => <button key={view.id} className="platform-btn" onClick={() => { const filters = { q: String(view.filters?.q || ""), health: String(view.filters?.health || ""), sort: (view.filters?.sort || "health") as FleetFilters["sort"] }; setFleetDraft(filters); setFleetFilters(filters); setFleetCursor(null); setFleetCursorHistory([]); }}>{view.name}</button>)}</Toolbar> : null}
          <Toolbar><button className="platform-btn" disabled={!selectedTenantIds.length} onClick={() => void runBulk("TENANT_RECHECK_ENTITLEMENT", true)}>Dry-run entitlement recheck ({selectedTenantIds.length})</button><button className="platform-btn" disabled={!selectedTenantIds.length} onClick={() => void runBulk("TENANT_SET_READ_ONLY", false)}>Queue read-only change ({selectedTenantIds.length})</button></Toolbar>
          <Table headers={["Select", "Tenant", "Mode", "Health", "Users", "Requests", "p95", "Quota", "Telemetry"]} rows={fleetItems.map((item: any) => [<input type="checkbox" checked={selectedTenantIds.includes(item.tenant_id)} onChange={(event) => setSelectedTenantIds((current) => event.target.checked ? [...current, item.tenant_id] : current.filter((id) => id !== item.tenant_id))} />, <button className="platform-btn" onClick={() => void openTenant(item.tenant_id)}>{item.name || item.amo_code}</button>, item.data_mode, <StatusBadge value={item.health?.status} />, `${number(item.active_users)} / ${number(item.users)}`, number(item.requests_window), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.quota_percent == null ? "—" : `${Number(item.quota_percent).toFixed(1)}%`, item.last_telemetry_at ? new Date(item.last_telemetry_at).toLocaleString() : "—"]) } />
          <Toolbar><button className="platform-btn" disabled={!fleetCursorHistory.length} onClick={() => { const history = [...fleetCursorHistory]; const previous = history.pop() ?? null; setFleetCursorHistory(history); setFleetCursor(previous); }}>Previous</button><button className="platform-btn" disabled={!detail.fleet?.next_cursor} onClick={() => { setFleetCursorHistory((current) => [...current, fleetCursor]); setFleetCursor(detail.fleet.next_cursor); }}>Next</button><span>{number(detail.fleet?.total)} matching tenants</span></Toolbar>
        </section>
        {selectedTenant && <section className="platform-card"><h2>Tenant 360</h2>{selectedTenant.loading ? <p>Loading tenant…</p> : <><p><strong>{selectedTenant.tenant?.name || selectedTenant.tenant?.amo_code}</strong> · {selectedTenant.tenant?.country || "—"} · <StatusBadge value={selectedTenant.tenant?.is_active ? "ACTIVE" : "INACTIVE"} /></p><div className="platform-metric-grid"><MetricCard label="Users" value={number(selectedTenant.users?.total ?? selectedTenant.user_count)} /><MetricCard label="Storage" value={bytes(selectedTenant.resources?.storage_used_bytes ?? selectedTenant.resource_usage?.storage_used_bytes)} /><MetricCard label="24h error rate" value={pct(selectedTenant.operations?.slo_24h?.error_rate)} /><MetricCard label="24h p95" value={selectedTenant.operations?.slo_24h?.p95_latency_ms == null ? "—" : `${Number(selectedTenant.operations.slo_24h.p95_latency_ms).toFixed(0)} ms`} /></div><Table headers={["Recent action", "Reason", "Time"]} rows={(selectedTenant.operations?.audit || []).slice(0, 20).map((item: any) => [item.action, item.reason || "—", item.created_at ? new Date(item.created_at).toLocaleString() : "—"])} /></>}</section>}
      </>}

      {section === "Incidents" && <>
        <section className="platform-card"><Toolbar><button className="platform-btn primary" onClick={() => void createIncident()}>Create incident</button><span>{number(detail.total)} incidents</span></Toolbar><Table headers={["Severity", "State", "Title", "Source", "Started", "Open"]} rows={incidentItems.map((item: any) => [<StatusBadge value={item.severity} />, <StatusBadge value={item.state} />, item.title, item.source, item.started_at ? new Date(item.started_at).toLocaleString() : "—", <button className="platform-btn" onClick={() => void openIncident(item.id)}>Timeline</button>])} /></section>
        {selectedIncident && <section className="platform-card"><h2>{selectedIncident.title}</h2><p>{selectedIncident.summary || "No summary recorded."}</p><Toolbar>{selectedIncident.state === "OPEN" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "ACKNOWLEDGED")}>Acknowledge</button>}{selectedIncident.state === "ACKNOWLEDGED" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "INVESTIGATING")}>Start investigation</button>}{selectedIncident.state === "INVESTIGATING" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "MITIGATED")}>Mark mitigated</button>}{selectedIncident.state === "MITIGATED" && <button className="platform-btn primary" onClick={() => void transitionIncident(selectedIncident.id, "RESOLVED")}>Resolve</button>}</Toolbar><Table headers={["State", "Message", "Actor", "Time"]} rows={(selectedIncident.timeline || []).map((item: any) => [<StatusBadge value={item.event_type} />, item.message || "—", item.actor_user_id || "system", item.created_at ? new Date(item.created_at).toLocaleString() : "—"])} /></section>}
      </>}

      {section === "Product" && <>
        <div className="platform-metric-grid"><MetricCard label="Active tenants (30d)" value={number(detail.active_tenants)} /><MetricCard label="Controlled product events" value={number(detail.events)} /><MetricCard label="Workflow completion" value={pct(detail.workflow_funnel?.completion_rate)} /><MetricCard label="Workflow failure" value={pct(detail.workflow_funnel?.failure_rate)} tone="amber" /><MetricCard label="Buffered events" value={number(detail.sink?.buffer_depth)} /><MetricCard label="Dropped events" value={number(detail.sink?.dropped)} tone={Number(detail.sink?.dropped || 0) > 0 ? "red" : "green"} /></div>
        <section className="platform-card"><h2>Module adoption</h2><p>{detail.privacy || "Aggregated product analytics only."}</p><Table headers={["Module", "Active tenants", "Events", "Success", "Failed", "Avg duration"]} rows={(detail.modules || []).map((item: any) => [item.module, number(item.active_tenants), number(item.events), number(item.success), number(item.failed), item.avg_duration_ms == null ? "—" : `${Number(item.avg_duration_ms).toFixed(0)} ms`])} /></section>
      </>}

      {section === "Users" && <section className="platform-card"><h2>Global user operations</h2><Toolbar><input aria-label="Global user search" value={userDraft} onChange={(event) => setUserDraft(event.target.value)} placeholder="Name or email" /><button className="platform-btn primary" onClick={() => { setUserQuery(userDraft.trim()); setUserOffset(0); }}>Search</button><span>{number(detail.total)} users</span></Toolbar><Table headers={["User", "Tenant", "Role", "State", "MFA/WebAuthn", "Last login", "Failed logins"]} rows={userItems.map((item: any) => [<><strong>{item.full_name || "Unnamed"}</strong><br /><small>{item.email}</small></>, item.tenant_name || item.amo_id || "Platform", item.role, <StatusBadge value={item.is_active ? "ACTIVE" : "DISABLED"} />, item.webauthn_registered ? "Registered" : "No", item.last_login_at ? new Date(item.last_login_at).toLocaleString() : "Never", number(item.failed_login_count)])} /><Toolbar><button className="platform-btn" disabled={userOffset <= 0} onClick={() => setUserOffset((value) => Math.max(0, value - 100))}>Previous</button><button className="platform-btn" disabled={userOffset + 100 >= Number(detail.total || 0)} onClick={() => setUserOffset((value) => value + 100)}>Next</button><span>Showing {userOffset + 1}–{Math.min(userOffset + 100, Number(detail.total || 0))}</span></Toolbar></section>}

      {section === "Commercial" && <div className="platform-metric-grid"><MetricCard label="MRR" value={`${commercial.currency || overview.currency || ""} ${number((Number(commercial.mrr || 0)) / 100)}`} /><MetricCard label="ARR" value={`${commercial.currency || overview.currency || ""} ${number((Number(commercial.arr || 0)) / 100)}`} /><MetricCard label="Active subscriptions" value={number(commercial.active_subscriptions)} /><MetricCard label="Trials" value={number(commercial.trial_subscriptions)} /><MetricCard label="Overdue invoices" value={number(commercial.overdue_invoices)} tone="amber" /><MetricCard label="Grace-period tenants" value={number(commercial.grace_period_tenants)} /></div>}

      {section === "Changes" && <><section className="platform-card"><Toolbar><button className="platform-btn primary" onClick={() => void createChangeMarker()}>Record change</button></Toolbar><h2>Change markers</h2><Table headers={["Kind", "Reference", "Title", "Time"]} rows={(detail.items || []).map((item: any) => [<StatusBadge value={item.kind} />, item.reference || "—", item.title, item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "—"])} /></section><section className="platform-card"><h2>Maintenance windows</h2><Table headers={["Title", "State", "Impact", "Starts", "Ends"]} rows={(changes.maintenance || []).map((item: any) => [item.title, <StatusBadge value={item.status} />, item.impact_level, item.starts_at ? new Date(item.starts_at).toLocaleString() : "—", item.ends_at ? new Date(item.ends_at).toLocaleString() : "—"])} /></section></>}

      {section === "Jobs" && <section className="platform-card"><h2>Durable operations jobs</h2><p>Side effects execute only from the lease-fenced worker. High-risk jobs require a different platform superuser to approve them.</p><Table headers={["Command", "Risk", "State", "Tenant", "Dry run", "Attempts", "Created", "Action"]} rows={jobItems.map((item: any) => [item.command_name, <StatusBadge value={item.risk_level} />, <StatusBadge value={item.status} />, item.tenant_id || "Platform", item.dry_run ? "Yes" : "No", number(item.attempt_count), item.created_at ? new Date(item.created_at).toLocaleString() : "—", item.status === "NEEDS_APPROVAL" ? <button className="platform-btn" onClick={() => void approveJob(item.id)}>Approve</button> : "—"]) } /></section>}
    </PlatformShell>
  );
}
