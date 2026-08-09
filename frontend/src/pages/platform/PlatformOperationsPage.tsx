import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  persistPlatformDataMode,
  readPlatformDataMode,
  replaceLocationDataMode,
} from "../../services/platformEnvironment";
import {
  platformOperationsApi,
  type DataMode,
  type OpsSnapshot,
} from "../../services/platformOperations";
import { MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import {
  PLATFORM_CONSOLE_LIVE_EVENT,
  type PlatformConsoleEvent,
} from "./components/usePlatformRealtime";

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
type FleetSort = "health" | "name" | "traffic" | "users" | "assets" | "activity";
type FleetFilters = {
  q: string;
  health: string;
  lifecycle: string;
  billing_risk: string;
  security_risk: string;
  integration: string;
  support_state: string;
  country: string;
  plan: string;
  module: string;
  sort: FleetSort;
};
type UserSort = "updated" | "last_login" | "name" | "failed_logins";
type UserFilters = { q: string; role: string; status: string; mfa: string; sort: UserSort };

const emptyFleetFilters: FleetFilters = {
  q: "",
  health: "",
  lifecycle: "",
  billing_risk: "",
  security_risk: "",
  integration: "",
  support_state: "",
  country: "",
  plan: "",
  module: "",
  sort: "health",
};
const emptyUserFilters: UserFilters = { q: "", role: "", status: "", mfa: "", sort: "updated" };

function pct(value: unknown, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "—";
}

function number(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : "—";
}

function money(cents: unknown, currency: unknown) {
  const n = Number(cents);
  if (!Number.isFinite(n)) return "—";
  return `${String(currency || "")} ${(n / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`.trim();
}

function bytes(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let current = n;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  return `${current.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function metricValue(payload: any): string {
  const item = payload?.items?.[0] || payload?.series?.[0];
  const raw = item?.value;
  const value = Array.isArray(raw) ? raw[1] : raw;
  if (value == null) return payload?.stale ? "Stale / unavailable" : "—";
  const suffix =
    payload?.unit === "percent"
      ? "%"
      : payload?.unit === "bytes_per_second"
        ? " B/s"
        : payload?.unit === "bytes"
          ? " B"
          : payload?.unit === "milliseconds"
            ? " ms"
            : "";
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function forecastValue(payload: any): string {
  const forecast = payload?.forecast;
  if (!forecast?.available) return "Insufficient history";
  if (forecast.days_to_threshold == null) {
    return `${Number(forecast.slope_per_hour || 0).toFixed(3)}/h · no threshold ETA`;
  }
  return `${forecast.days_to_threshold} days to ${forecast.threshold}%`;
}

function displayDate(value: unknown) {
  return value ? new Date(String(value)).toLocaleString() : "—";
}

const Table: React.FC<{ headers: string[]; rows: React.ReactNode[][] }> = ({ headers, rows }) => (
  <div className="platform-table-wrap">
    <table className="platform-table">
      <thead>
        <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
      </thead>
      <tbody>
        {rows.length ? rows.map((row, index) => (
          <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
        )) : (
          <tr><td colSpan={headers.length}>No records in this view.</td></tr>
        )}
      </tbody>
    </table>
  </div>
);

const Toolbar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    className="platform-toolbar-actions"
    style={{ flexWrap: "wrap", justifyContent: "flex-start", marginBottom: 12 }}
  >
    {children}
  </div>
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
  const [fleetDraft, setFleetDraft] = useState<FleetFilters>(emptyFleetFilters);
  const [fleetFilters, setFleetFilters] = useState<FleetFilters>(emptyFleetFilters);
  const [fleetCursor, setFleetCursor] = useState<string | null>(null);
  const [fleetCursorHistory, setFleetCursorHistory] = useState<(string | null)[]>([]);
  const [userDraft, setUserDraft] = useState<UserFilters>(emptyUserFilters);
  const [userFilters, setUserFilters] = useState<UserFilters>(emptyUserFilters);
  const [userCursor, setUserCursor] = useState<string | null>(null);
  const [userCursorHistory, setUserCursorHistory] = useState<(string | null)[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
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
    setUserCursor(null);
    setUserCursorHistory([]);
    setSelectedUserIds([]);
    navigate(replaceLocationDataMode(location.pathname, location.search, next), { replace: true });
  };

  useEffect(() => {
    const current = ++generation.current;
    setConnection("connecting");
    setError(null);

    const handleLive = (rawEvent: Event) => {
      const event = (rawEvent as CustomEvent<PlatformConsoleEvent>).detail;
      const next = event?.snapshot as OpsSnapshot | undefined;
      if (!next || generation.current !== current) return;
      if (next.data_mode && next.data_mode !== mode) return;
      setSnapshot(next);
      setError(null);
      setConnection("live");
    };
    window.addEventListener(PLATFORM_CONSOLE_LIVE_EVENT, handleLive);

    void platformOperationsApi.bootstrap(mode)
      .then((next) => {
        if (generation.current === current) setSnapshot(next.snapshot);
      })
      .catch((reason) => {
        if (generation.current === current) {
          setError(reason instanceof Error ? reason.message : "Operations gateway unavailable");
          setConnection("degraded");
        }
      });

    return () => window.removeEventListener(PLATFORM_CONSOLE_LIVE_EVENT, handleLive);
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
            platformOperationsApi.infrastructureSummary(),
            platformOperationsApi.nodes(),
            platformOperationsApi.queues(mode),
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
            platformOperationsApi.sloWindows(mode),
            platformOperationsApi.slowRoutes(mode),
            platformOperationsApi.errorRoutes(mode),
          ]);
          next = { windows, slow, errors };
        } else if (section === "Capacity") {
          const [capacity, forecast] = await Promise.all([
            platformOperationsApi.capacity(mode),
            platformOperationsApi.capacityForecast("7d"),
          ]);
          next = { capacity, forecast };
        } else if (section === "Tenant Fleet") {
          const [fleet, views] = await Promise.all([
            platformOperationsApi.tenantFleet({
              data_mode: mode,
              ...fleetFilters,
              q: fleetFilters.q || undefined,
              health: fleetFilters.health || undefined,
              lifecycle: fleetFilters.lifecycle || undefined,
              billing_risk: fleetFilters.billing_risk || undefined,
              security_risk: fleetFilters.security_risk || undefined,
              integration: fleetFilters.integration || undefined,
              support_state: fleetFilters.support_state || undefined,
              country: fleetFilters.country || undefined,
              plan: fleetFilters.plan || undefined,
              module: fleetFilters.module || undefined,
              limit: 100,
              cursor: fleetCursor,
            }),
            platformOperationsApi.savedViews("tenant_fleet"),
          ]);
          next = { fleet, views };
        } else if (section === "Incidents") {
          next = await platformOperationsApi.incidentCenter();
        } else if (section === "Product") {
          next = await platformOperationsApi.productRollups(mode, 30);
        } else if (section === "Users") {
          next = await platformOperationsApi.usersV2({
            data_mode: mode,
            q: userFilters.q || undefined,
            role: userFilters.role || undefined,
            status: (userFilters.status || undefined) as "active" | "disabled" | undefined,
            mfa: userFilters.mfa === "yes" ? true : userFilters.mfa === "no" ? false : undefined,
            sort: userFilters.sort,
            limit: 100,
            cursor: userCursor,
          });
        } else if (section === "Commercial") {
          next = await platformOperationsApi.commercial(mode);
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
  }, [section, mode, refreshNonce, fleetFilters, fleetCursor, userFilters, userCursor]);

  const overview = snapshot?.overview || {};
  const slo = snapshot?.slo || {};
  const capacity = snapshot?.capacity || {};
  const preparedFleet = snapshot?.fleet || {};
  const changes = snapshot?.changes || {};
  const jobs = snapshot?.jobs || {};
  const jobItems = jobs.items || [];
  const stale = Boolean(snapshot?.freshness?.stale);
  const subtitle = useMemo(
    () => `Prepared control-plane snapshot · ${mode} · ${snapshot?.generated_at ? new Date(snapshot.generated_at).toLocaleString() : "awaiting first prepared snapshot"}`,
    [mode, snapshot?.generated_at],
  );
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
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to load node detail");
    }
  };

  const openTenant = async (tenantId: string) => {
    setSelectedTenant({ loading: true, tenant_id: tenantId });
    try {
      setSelectedTenant(await platformOperationsApi.tenant360(tenantId, mode));
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to load Tenant 360");
      setSelectedTenant(null);
    }
  };

  const openIncident = async (incidentId: string) => {
    try {
      setSelectedIncident(await platformOperationsApi.incidentDetail(incidentId));
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to load incident timeline");
    }
  };

  const createIncident = async () => {
    const title = window.prompt("Incident title");
    if (!title) return;
    const severity = (window.prompt("Severity: INFO, LOW, MEDIUM, HIGH or CRITICAL", "HIGH") || "HIGH").toUpperCase();
    try {
      await platformOperationsApi.createIncident({ title, severity, source: "superadmin-console" });
      refresh();
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to create incident");
    }
  };

  const transitionIncident = async (incidentId: string, target: string) => {
    const message = window.prompt(`Reason / update for ${target}`) || "";
    try {
      await platformOperationsApi.transitionIncident(incidentId, target, message);
      setSelectedIncident(await platformOperationsApi.incidentDetail(incidentId));
      refresh();
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to transition incident");
    }
  };

  const runTenantBulk = async (commandName: string, dryRun: boolean) => {
    if (!selectedTenantIds.length) return;
    const reason = window.prompt(`Reason for ${commandName} on ${selectedTenantIds.length} tenant(s)`);
    if (!reason) return;
    try {
      await platformOperationsApi.bulk({
        command_name: commandName,
        reason,
        tenant_ids: selectedTenantIds,
        data_mode: mode,
        dry_run: dryRun,
        idempotency_key: `${commandName}-${Date.now()}`,
      });
      setSelectedTenantIds([]);
      refresh();
    } catch (value) {
      setDetailError(value instanceof Error ? value.message : "Unable to queue bulk operation");
    }
  };

  const runUserBulk = async (action: "DISABLE" | "ENABLE" | "REVOKE_SESSIONS" | "REQUIRE_PASSWORD_RESET") => {
    if (!selectedUserIds.length) return;
    const reason = window.prompt(`Reason for ${action} on ${selectedUserIds.length} user(s)`);
    if (!reason) return;
    try {
      await platformOperationsApi.usersBulk({ action, reason, user_ids: selectedUserIds });
      setSelectedUserIds([]);
      refresh();
    } catch (value) {
      setDetailError(value instanceof Error ? value.message : "Unable to apply user operation");
    }
  };

  const approveJob = async (jobId: string) => {
    const reason = window.prompt("Approval reason. Approval must be by a different platform superuser.");
    if (!reason) return;
    try {
      await platformOperationsApi.approve(jobId, reason);
      refresh();
    } catch (value) {
      setDetailError(value instanceof Error ? value.message : "Unable to approve job");
    }
  };

  const saveCurrentFleetView = async () => {
    const name = window.prompt("Saved view name");
    if (!name) return;
    try {
      await platformOperationsApi.saveView({ scope: "tenant_fleet", name, filters: fleetFilters });
      refresh();
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to save view");
    }
  };

  const createChangeMarker = async () => {
    const kind = (window.prompt(
      "Change kind: DEPLOYMENT, FEATURE_FLAG, MAINTENANCE, INCIDENT, CONFIGURATION or MIGRATION",
      "DEPLOYMENT",
    ) || "").toUpperCase();
    const title = window.prompt("Change title");
    if (!kind || !title) return;
    const reference = window.prompt("Reference (commit, PR, release or ticket)") || undefined;
    try {
      await platformOperationsApi.createChangeMarker({ kind, title, reference });
      refresh();
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : "Unable to record change marker");
    }
  };

  const fleetItems = detail.fleet?.items || [];
  const fleetViews = detail.views?.items || [];
  const incidentItems = detail.items || [];
  const userItems = section === "Users" ? detail.items || [] : [];
  const infra = detail.summary || {};
  const sloWindows = detail.windows?.windows || {};
  const burn = detail.windows?.burn || {};

  return (
    <PlatformShell
      title="Operations Control Center"
      subtitle={subtitle}
      actions={(
        <div className="platform-toolbar-actions">
          <StatusBadge value={connection === "live" ? (stale ? "STALE" : "LIVE") : connection === "connecting" ? "CONNECTING" : "DEGRADED"} />
          <button className={`platform-btn ${mode === "REAL" ? "primary" : ""}`} onClick={() => selectMode("REAL")}>REAL</button>
          <button className={`platform-btn ${mode === "DEMO" ? "primary" : ""}`} onClick={() => selectMode("DEMO")}>DEMO</button>
          <button className="platform-btn" onClick={refresh}>Refresh view</button>
        </div>
      )}
    >
      {error ? <section className="platform-card"><strong>Operations gateway degraded.</strong><p>{error}</p><p>Tenant application traffic is independent of this gateway. Last-known prepared data remains visible when available.</p></section> : null}
      {detailError ? <section className="platform-card"><strong>View request failed.</strong><p>{detailError}</p></section> : null}
      {stale ? <section className="platform-card"><strong>Stale telemetry.</strong><p>Showing last-known data. Snapshot age: {number(snapshot?.freshness?.age_seconds)} seconds.</p></section> : null}

      <div className="platform-tabs" role="tablist" aria-label="Operations views">
        {sections.map((item) => <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}>{item}</button>)}
      </div>
      {detailLoading ? <section className="platform-card"><p>Loading bounded operations data…</p></section> : null}

      {section === "NOC" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Platform status" value={<StatusBadge value={overview.platform_status || slo.status || "UNKNOWN"} />} caption="Prepared state; browser count does not multiply DB refresh work" tone="green" />
          <MetricCard label="Host CPU" value={overview.cpu_percent == null ? "No Prometheus sample" : `${Number(overview.cpu_percent).toFixed(1)}%`} caption="Bare-metal/node telemetry" />
          <MetricCard label="Host memory" value={overview.memory_percent == null ? "No Prometheus sample" : `${Number(overview.memory_percent).toFixed(1)}%`} tone="purple" />
          <MetricCard label="SLO burn rate" value={`${Number(slo.burn_rate || 0).toFixed(2)}×`} caption={`Availability target ${pct(slo.availability_target, 3)}`} tone={Number(slo.burn_rate || 0) >= 2 ? "red" : "green"} />
          <MetricCard label="Active tenants" value={number(overview.active_tenants)} caption={`${number(preparedFleet.critical)} critical · ${number(preparedFleet.warning)} warning`} />
          <MetricCard label="Durable work queue" value={number(overview.queue_depth)} caption="High-risk work requires second-person approval" tone="amber" />
        </div>
        <section className="platform-card"><h2>Immediate attention</h2><Table headers={["Tenant", "Health", "Users", "Requests", "p95", "Quota"]} rows={(preparedFleet.items || []).slice(0, 20).map((item: any) => [<button className="platform-btn" onClick={() => void openTenant(item.tenant_id)}>{item.name || item.amo_code}</button>, <StatusBadge value={item.health?.status} />, number(item.users), number(item.requests_window), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.quota_percent == null ? "—" : `${Number(item.quota_percent).toFixed(1)}%`])} /></section>
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
        {selectedNode && <section className="platform-card"><h2>Node detail · {selectedNode}</h2><p>CPU: {metricValue(nodeDetail?.node?.metrics?.host_cpu_utilization)} · Memory: {metricValue(nodeDetail?.node?.metrics?.host_memory_utilization)} · Swap: {metricValue(nodeDetail?.node?.metrics?.host_swap_utilization)} · Ingress: {metricValue(nodeDetail?.node?.metrics?.network_ingress)} · Egress: {metricValue(nodeDetail?.node?.metrics?.network_egress)}</p></section>}
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
        <MetricCard label="Ingress" value={metricValue(detail.network_ingress)} />
        <MetricCard label="Egress" value={metricValue(detail.network_egress)} />
        <MetricCard label="Errors/sec" value={metricValue(detail.network_errors)} tone="amber" />
        <MetricCard label="Drops/sec" value={metricValue(detail.network_drops)} tone="amber" />
        <MetricCard label="TCP established" value={metricValue(detail.tcp_established)} />
        <MetricCard label="TCP in use" value={metricValue(detail.tcp_inuse)} />
        <MetricCard label="TIME_WAIT" value={metricValue(detail.tcp_timewait)} />
      </div>}

      {section === "Storage" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Filesystem utilisation" value={metricValue(detail.filesystem_utilization)} />
          <MetricCard label="Filesystem free" value={metricValue(detail.filesystem_free)} />
          <MetricCard label="Inode utilisation" value={metricValue(detail.filesystem_inode_utilization)} />
          <MetricCard label="Disk read" value={metricValue(detail.disk_read_throughput)} />
          <MetricCard label="Disk write" value={metricValue(detail.disk_write_throughput)} />
          <MetricCard label="Read latency" value={metricValue(detail.disk_read_latency)} />
          <MetricCard label="Write latency" value={metricValue(detail.disk_write_latency)} />
        </div>
        <section className="platform-card"><p>Storage telemetry is server-owned and allow-listed. The browser cannot submit arbitrary PromQL.</p></section>
      </>}

      {section === "SLOs" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Current availability" value={pct(slo.availability, 3)} caption={`Target ${pct(slo.availability_target, 3)}`} tone={slo.status === "CRITICAL" ? "red" : "green"} />
          <MetricCard label="p95 latency" value={slo.p95_latency_ms == null ? "—" : `${Number(slo.p95_latency_ms).toFixed(0)} ms`} />
          <MetricCard label="p99 latency" value={slo.p99_latency_ms == null ? "—" : `${Number(slo.p99_latency_ms).toFixed(0)} ms`} />
          <MetricCard label="Burn policy" value={<StatusBadge value={burn.status || "UNKNOWN"} />} caption={burn.fast ? "Fast burn detected" : burn.sustained ? "Sustained burn detected" : "Within burn policy"} />
          <MetricCard label="5m burn" value={`${Number(sloWindows["5m"]?.burn_rate || 0).toFixed(2)}×`} />
          <MetricCard label="1h burn" value={`${Number(sloWindows["1h"]?.burn_rate || 0).toFixed(2)}×`} />
          <MetricCard label="6h burn" value={`${Number(sloWindows["6h"]?.burn_rate || 0).toFixed(2)}×`} />
        </div>
        <section className="platform-card"><h2>Slow routes</h2><Table headers={["Route", "Status", "Requests", "Error rate", "p95", "p99"]} rows={(detail.slow?.items || slo.routes || []).map((item: any) => [item.route, <StatusBadge value={item.status} />, number(item.requests), pct(item.error_rate), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.p99_latency_ms == null ? "—" : `${Number(item.p99_latency_ms).toFixed(0)} ms`])} /></section>
      </>}

      {section === "Capacity" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Capacity state" value={<StatusBadge value={detail.capacity?.status || capacity.status || "UNKNOWN"} />} />
          <MetricCard label="Estimated headroom" value={`${number(detail.capacity?.estimated_headroom_percent ?? capacity.estimated_headroom_percent)}%`} caption="Pressure indicator, not scale certification" />
          <MetricCard label="CPU 7-day trend" value={forecastValue(detail.forecast?.cpu)} />
          <MetricCard label="Memory 7-day trend" value={forecastValue(detail.forecast?.memory)} />
          <MetricCard label="Filesystem 7-day trend" value={forecastValue(detail.forecast?.filesystem)} />
          <MetricCard label="Requests/min" value={number(detail.capacity?.requests_per_minute ?? capacity.requests_per_minute)} />
        </div>
        <section className="platform-card"><p>{detail.forecast?.interpretation || capacity.forecast_note}</p></section>
      </>}

      {section === "Tenant Fleet" && <>
        <section className="platform-card">
          <h2>Server-filtered tenant fleet</h2>
          <Toolbar>
            <input aria-label="Tenant search" value={fleetDraft.q} onChange={(event) => setFleetDraft((value) => ({ ...value, q: event.target.value }))} placeholder="Tenant, code, country, plan" />
            <select aria-label="Health filter" value={fleetDraft.health} onChange={(event) => setFleetDraft((value) => ({ ...value, health: event.target.value }))}><option value="">All health</option><option>CRITICAL</option><option>WARN</option><option>HEALTHY</option></select>
            <select aria-label="Lifecycle filter" value={fleetDraft.lifecycle} onChange={(event) => setFleetDraft((value) => ({ ...value, lifecycle: event.target.value }))}><option value="">All lifecycle</option><option>ACTIVE</option><option>TRIAL</option><option>INACTIVE</option></select>
            <select aria-label="Billing filter" value={fleetDraft.billing_risk} onChange={(event) => setFleetDraft((value) => ({ ...value, billing_risk: event.target.value }))}><option value="">All billing</option><option>OVERDUE</option><option>READ_ONLY</option><option>WATCH</option><option>CLEAR</option></select>
            <select aria-label="Security filter" value={fleetDraft.security_risk} onChange={(event) => setFleetDraft((value) => ({ ...value, security_risk: event.target.value }))}><option value="">All security</option><option>HIGH</option><option>CLEAR</option></select>
            <select aria-label="Integration filter" value={fleetDraft.integration} onChange={(event) => setFleetDraft((value) => ({ ...value, integration: event.target.value }))}><option value="">All integrations</option><option value="FAILED">Failure</option><option value="CLEAR">Clear</option></select>
            <select aria-label="Sort tenant fleet" value={fleetDraft.sort} onChange={(event) => setFleetDraft((value) => ({ ...value, sort: event.target.value as FleetSort }))}><option value="health">Health</option><option value="traffic">Traffic</option><option value="users">Users</option><option value="assets">Assets</option><option value="activity">Activity</option><option value="name">Name</option></select>
            <button className="platform-btn primary" onClick={() => { setFleetFilters(fleetDraft); setFleetCursor(null); setFleetCursorHistory([]); }}>Apply</button>
            <button className="platform-btn" onClick={() => { setFleetDraft(emptyFleetFilters); setFleetFilters(emptyFleetFilters); setFleetCursor(null); setFleetCursorHistory([]); }}>Clear</button>
            <button className="platform-btn" onClick={() => void saveCurrentFleetView()}>Save view</button>
          </Toolbar>
          {fleetViews.length ? <Toolbar>{fleetViews.map((view: any) => <button key={view.id} className="platform-btn" onClick={() => { const filters = { ...emptyFleetFilters, ...(view.filters || {}) } as FleetFilters; setFleetDraft(filters); setFleetFilters(filters); setFleetCursor(null); setFleetCursorHistory([]); }}>{view.name}</button>)}</Toolbar> : null}
          <Toolbar>
            <button className="platform-btn" disabled={!selectedTenantIds.length} onClick={() => void runTenantBulk("TENANT_RECHECK_ENTITLEMENT", true)}>Dry-run entitlement recheck ({selectedTenantIds.length})</button>
            <button className="platform-btn" disabled={!selectedTenantIds.length} onClick={() => void runTenantBulk("TENANT_SET_READ_ONLY", false)}>Queue read-only ({selectedTenantIds.length})</button>
          </Toolbar>
          <Table headers={["Select", "Tenant", "Lifecycle", "Health", "Users", "Assets", "Traffic", "Billing", "Security", "Integrations", "Support", "Activity"]} rows={fleetItems.map((item: any) => [<input aria-label={`Select ${item.name}`} type="checkbox" checked={selectedTenantIds.includes(item.tenant_id)} onChange={(event) => setSelectedTenantIds((current) => event.target.checked ? [...current, item.tenant_id] : current.filter((id) => id !== item.tenant_id))} />, <button className="platform-btn" onClick={() => void openTenant(item.tenant_id)}>{item.name || item.amo_code}</button>, <StatusBadge value={item.lifecycle} />, <StatusBadge value={item.health?.status} />, `${number(item.active_users)} / ${number(item.users)}`, number(item.asset_count), number(item.requests_24h), <StatusBadge value={item.billing_risk} />, <StatusBadge value={item.security_risk} />, <StatusBadge value={item.integration_failure ? "FAILED" : "CLEAR"} />, <StatusBadge value={item.support_state} />, displayDate(item.last_activity_at)])} />
          <Toolbar>
            <button className="platform-btn" disabled={!fleetCursorHistory.length} onClick={() => { const history = [...fleetCursorHistory]; const previous = history.pop() ?? null; setFleetCursorHistory(history); setFleetCursor(previous); }}>Previous</button>
            <button className="platform-btn" disabled={!detail.fleet?.next_cursor} onClick={() => { setFleetCursorHistory((current) => [...current, fleetCursor]); setFleetCursor(detail.fleet.next_cursor); }}>Next</button>
            <span>{number(detail.fleet?.total)} matching tenants</span>
          </Toolbar>
        </section>
        {selectedTenant && <section className="platform-card">
          <h2>Tenant 360</h2>
          {selectedTenant.loading ? <p>Loading tenant…</p> : <>
            <p><strong>{selectedTenant.overview?.name || selectedTenant.overview?.amo_code}</strong> · {selectedTenant.overview?.country || "—"} · <StatusBadge value={selectedTenant.health?.lifecycle || (selectedTenant.overview?.is_active ? "ACTIVE" : "INACTIVE")} /></p>
            <div className="platform-metric-grid">
              <MetricCard label="Health" value={<StatusBadge value={selectedTenant.health?.health?.status || "UNKNOWN"} />} />
              <MetricCard label="Users" value={number(selectedTenant.users?.total)} />
              <MetricCard label="Assets" value={number(selectedTenant.health?.asset_count)} />
              <MetricCard label="Storage" value={bytes(selectedTenant.usage?.resource?.storage_used_bytes)} />
              <MetricCard label="24h error rate" value={pct(selectedTenant.performance?.error_rate)} />
              <MetricCard label="24h p95" value={selectedTenant.performance?.p95_latency_ms == null ? "—" : `${Number(selectedTenant.performance.p95_latency_ms).toFixed(0)} ms`} />
              <MetricCard label="24h p99" value={selectedTenant.performance?.p99_latency_ms == null ? "—" : `${Number(selectedTenant.performance.p99_latency_ms).toFixed(0)} ms`} />
              <MetricCard label="Billing risk" value={<StatusBadge value={selectedTenant.health?.billing_risk || "UNKNOWN"} />} />
            </div>
            <h3>Modules</h3>
            <Table headers={["Module", "State", "Plan", "Effective to"]} rows={(selectedTenant.modules || []).map((item: any) => [item.module_code, <StatusBadge value={item.status} />, item.plan_code || "—", displayDate(item.effective_to)])} />
            <h3>Integrations</h3>
            <Table headers={["Integration", "Event", "State", "Failures", "Last delivery"]} rows={(selectedTenant.integrations || []).map((item: any) => [item.name, item.event_type, <StatusBadge value={item.status} />, number(item.failure_count), displayDate(item.last_delivery_at)])} />
            <h3>Support and security</h3>
            <Table headers={["Type", "State", "Detail", "Time"]} rows={[...(selectedTenant.support?.tickets || []).map((item: any) => ["Support", <StatusBadge value={item.status} />, `${item.priority}: ${item.title}`, displayDate(item.created_at)]), ...(selectedTenant.security || []).map((item: any) => ["Security", <StatusBadge value={item.severity} />, item.title, displayDate(item.created_at)])]} />
            <h3>Recent privileged activity</h3>
            <Table headers={["Action", "Reason", "Actor", "Time"]} rows={(selectedTenant.audit || []).slice(0, 40).map((item: any) => [item.action, item.reason || "—", item.actor_user_id || "system", displayDate(item.created_at)])} />
          </>}
        </section>}
      </>}

      {section === "Incidents" && <>
        <section className="platform-card"><Toolbar><button className="platform-btn primary" onClick={() => void createIncident()}>Create incident</button><span>{number(detail.total)} incidents</span></Toolbar><Table headers={["Severity", "State", "Title", "Source", "Started", "Open"]} rows={incidentItems.map((item: any) => [<StatusBadge value={item.severity} />, <StatusBadge value={item.state} />, item.title, item.source, displayDate(item.started_at), <button className="platform-btn" onClick={() => void openIncident(item.id)}>Timeline</button>])} /></section>
        {selectedIncident && <section className="platform-card"><h2>{selectedIncident.title}</h2><p>{selectedIncident.summary || "No summary recorded."}</p><Toolbar>{selectedIncident.state === "OPEN" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "ACKNOWLEDGED")}>Acknowledge</button>}{selectedIncident.state === "ACKNOWLEDGED" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "INVESTIGATING")}>Start investigation</button>}{selectedIncident.state === "INVESTIGATING" && <button className="platform-btn" onClick={() => void transitionIncident(selectedIncident.id, "MITIGATED")}>Mark mitigated</button>}{selectedIncident.state === "MITIGATED" && <button className="platform-btn primary" onClick={() => void transitionIncident(selectedIncident.id, "RESOLVED")}>Resolve</button>}</Toolbar><Table headers={["State", "Message", "Actor", "Time"]} rows={(selectedIncident.timeline || []).map((item: any) => [<StatusBadge value={item.event_type} />, item.message || "—", item.actor_user_id || "system", displayDate(item.created_at)])} /></section>}
      </>}

      {section === "Product" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Active tenants (30d)" value={number(detail.active_tenants)} />
          <MetricCard label="Controlled product events" value={number(detail.events)} />
          <MetricCard label="Workflow completion" value={pct(detail.workflow_funnel?.completion_rate)} />
          <MetricCard label="Workflow failure" value={pct(detail.workflow_funnel?.failure_rate)} tone="amber" />
          <MetricCard label="Buffered events" value={number(detail.sink?.buffer_depth)} />
          <MetricCard label="Dropped events" value={number(detail.sink?.dropped)} tone={Number(detail.sink?.dropped || 0) > 0 ? "red" : "green"} />
        </div>
        <section className="platform-card"><h2>Module adoption</h2><p>{detail.privacy || "Aggregated product analytics only."}</p><Table headers={["Module", "Active tenants", "Events", "Success", "Failed", "Avg duration"]} rows={(detail.modules || []).map((item: any) => [item.module, number(item.active_tenants), number(item.events), number(item.success), number(item.failed), item.avg_duration_ms == null ? "—" : `${Number(item.avg_duration_ms).toFixed(0)} ms`])} /></section>
      </>}

      {section === "Users" && <section className="platform-card">
        <h2>Global user operations</h2>
        <Toolbar>
          <input aria-label="Global user search" value={userDraft.q} onChange={(event) => setUserDraft((value) => ({ ...value, q: event.target.value }))} placeholder="Name, email or staff code" />
          <input aria-label="Role filter" value={userDraft.role} onChange={(event) => setUserDraft((value) => ({ ...value, role: event.target.value }))} placeholder="Role" />
          <select aria-label="User state filter" value={userDraft.status} onChange={(event) => setUserDraft((value) => ({ ...value, status: event.target.value }))}><option value="">All states</option><option value="active">Active</option><option value="disabled">Disabled</option></select>
          <select aria-label="MFA filter" value={userDraft.mfa} onChange={(event) => setUserDraft((value) => ({ ...value, mfa: event.target.value }))}><option value="">Any MFA</option><option value="yes">MFA registered</option><option value="no">No MFA</option></select>
          <select aria-label="Sort users" value={userDraft.sort} onChange={(event) => setUserDraft((value) => ({ ...value, sort: event.target.value as UserSort }))}><option value="updated">Recently updated</option><option value="last_login">Last login</option><option value="name">Name</option><option value="failed_logins">Failed logins</option></select>
          <button className="platform-btn primary" onClick={() => { setUserFilters(userDraft); setUserCursor(null); setUserCursorHistory([]); }}>Apply</button>
          <button className="platform-btn" onClick={() => { setUserDraft(emptyUserFilters); setUserFilters(emptyUserFilters); setUserCursor(null); setUserCursorHistory([]); }}>Clear</button>
        </Toolbar>
        <Toolbar>
          <button className="platform-btn" disabled={!selectedUserIds.length} onClick={() => void runUserBulk("ENABLE")}>Enable ({selectedUserIds.length})</button>
          <button className="platform-btn" disabled={!selectedUserIds.length} onClick={() => void runUserBulk("DISABLE")}>Disable</button>
          <button className="platform-btn" disabled={!selectedUserIds.length} onClick={() => void runUserBulk("REVOKE_SESSIONS")}>Revoke sessions</button>
          <button className="platform-btn" disabled={!selectedUserIds.length} onClick={() => void runUserBulk("REQUIRE_PASSWORD_RESET")}>Require password reset</button>
          <span>{number(detail.total)} users</span>
        </Toolbar>
        <Table headers={["Select", "User", "Tenant", "Role", "State", "MFA", "Last login", "Failed logins", "Password reset"]} rows={userItems.map((item: any) => [<input aria-label={`Select ${item.email}`} type="checkbox" checked={selectedUserIds.includes(item.id)} onChange={(event) => setSelectedUserIds((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} />, <><strong>{item.full_name || "Unnamed"}</strong><br /><small>{item.email}</small></>, item.tenant_name || item.tenant_id || "Platform", item.role, <StatusBadge value={item.is_active ? "ACTIVE" : "DISABLED"} />, item.mfa_registered ? "Registered" : "No", displayDate(item.last_login_at), number(item.failed_login_count), item.must_change_password ? "Required" : "No"])} />
        <Toolbar><button className="platform-btn" disabled={!userCursorHistory.length} onClick={() => { const history = [...userCursorHistory]; const previous = history.pop() ?? null; setUserCursorHistory(history); setUserCursor(previous); }}>Previous</button><button className="platform-btn" disabled={!detail.next_cursor} onClick={() => { setUserCursorHistory((current) => [...current, userCursor]); setUserCursor(detail.next_cursor); }}>Next</button></Toolbar>
      </section>}

      {section === "Commercial" && <>
        <div className="platform-metric-grid">
          {(detail.currencies || []).map((item: any) => <React.Fragment key={item.currency}><MetricCard label={`${item.currency} MRR`} value={money(item.mrr_cents, item.currency)} /><MetricCard label={`${item.currency} ARR`} value={money(item.arr_cents, item.currency)} /><MetricCard label={`${item.currency} overdue`} value={money(item.overdue_invoice_cents, item.currency)} tone={Number(item.overdue_invoices || 0) ? "amber" : "green"} /></React.Fragment>)}
        </div>
        <section className="platform-card"><h2>Plan revenue</h2><p>{detail.currency_rule}</p><Table headers={["Currency", "Plan", "Tenants", "MRR"]} rows={(detail.plans || []).map((item: any) => [item.currency, item.plan, number(item.tenants), money(item.mrr_cents, item.currency)])} /></section>
        <section className="platform-card"><h2>Renewal pipeline</h2><Table headers={["Window", "Tenant", "Plan", "Renews", "MRR"]} rows={Object.entries(detail.renewal_pipeline || {}).flatMap(([windowName, rows]: [string, any]) => (rows || []).map((item: any) => [windowName, item.tenant, item.plan, displayDate(item.renews_at), money(item.mrr_cents, item.currency)]))} /></section>
        <section className="platform-card"><h2>Top tenant revenue</h2><Table headers={["Tenant", "Plan", "State", "MRR"]} rows={(detail.tenants || []).slice(0, 100).map((item: any) => [item.tenant, item.plan, <StatusBadge value={item.status} />, money(item.mrr_cents, item.currency)])} /><p><strong>Cancellations in last 30 days:</strong> {number(detail.churn?.cancellations_30d)}. {detail.churn?.definition}</p><p><strong>Expansion/contraction:</strong> {detail.expansion_contraction?.available ? "Available" : detail.expansion_contraction?.reason}</p><p><strong>Module revenue:</strong> {detail.module_revenue?.available ? "Available" : detail.module_revenue?.reason}</p></section>
      </>}

      {section === "Changes" && <>
        <section className="platform-card"><Toolbar><button className="platform-btn primary" onClick={() => void createChangeMarker()}>Record change</button></Toolbar><h2>Change markers</h2><Table headers={["Kind", "Reference", "Title", "Time"]} rows={(detail.items || []).map((item: any) => [<StatusBadge value={item.kind} />, item.reference || "—", item.title, displayDate(item.occurred_at)])} /></section>
        <section className="platform-card"><h2>Maintenance windows</h2><Table headers={["Title", "State", "Impact", "Starts", "Ends"]} rows={(changes.maintenance || []).map((item: any) => [item.title, <StatusBadge value={item.status} />, item.impact_level, displayDate(item.starts_at), displayDate(item.ends_at)])} /></section>
      </>}

      {section === "Jobs" && <section className="platform-card"><h2>Durable operations jobs</h2><p>Side effects execute only from the lease-fenced worker. High-risk jobs require a different platform superuser to approve them.</p><Table headers={["Command", "Risk", "State", "Tenant", "Dry run", "Attempts", "Created", "Action"]} rows={jobItems.map((item: any) => [item.command_name, <StatusBadge value={item.risk_level} />, <StatusBadge value={item.status} />, item.tenant_id || "Platform", item.dry_run ? "Yes" : "No", number(item.attempt_count), displayDate(item.created_at), item.status === "NEEDS_APPROVAL" ? <button className="platform-btn" onClick={() => void approveJob(item.id)}>Approve</button> : "—"]) } /></section>}
    </PlatformShell>
  );
}
