import React, { useEffect, useMemo, useRef, useState } from "react";

import { getToken } from "../../services/auth";
import {
  operationsStreamUrl,
  platformOperationsApi,
  type DataMode,
  type OpsSnapshot,
} from "../../services/platformOperations";
import { MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";

const sections = ["NOC", "SLOs", "Capacity", "Tenant Fleet", "Incidents", "Product", "Commercial", "Changes", "Jobs"] as const;
type Section = (typeof sections)[number];

function pct(value: unknown, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${(number * 100).toFixed(digits)}%`;
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
        } catch { /* malformed frame is isolated */ }
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

export default function PlatformOperationsPage() {
  const [mode, setMode] = useState<DataMode>("REAL");
  const [section, setSection] = useState<Section>("NOC");
  const [snapshot, setSnapshot] = useState<OpsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<"connecting" | "live" | "degraded">("connecting");
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    setConnection("connecting");
    setError(null);
    void platformOperationsApi.snapshot(mode)
      .then((next) => { if (generation.current === current) { setSnapshot(next); setConnection("live"); } })
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

  const overview = snapshot?.overview || {};
  const slo = snapshot?.slo || {};
  const capacity = snapshot?.capacity || {};
  const fleet = snapshot?.fleet || {};
  const incidents = snapshot?.incidents || {};
  const product = snapshot?.product || {};
  const commercial = snapshot?.commercial || {};
  const changes = snapshot?.changes || {};
  const jobs = snapshot?.jobs || {};
  const fleetItems = fleet.items || [];
  const incidentItems = incidents.items || [];
  const jobItems = jobs.items || [];

  const subtitle = useMemo(() => {
    const generated = snapshot?.generated_at ? new Date(snapshot.generated_at).toLocaleString() : "awaiting first prepared snapshot";
    return `Prepared operations snapshot · ${mode} data · ${generated}`;
  }, [mode, snapshot?.generated_at]);

  return (
    <PlatformShell
      title="Operations Control Center"
      subtitle={subtitle}
      actions={
        <div className="platform-toolbar-actions">
          <StatusBadge value={connection === "live" ? "LIVE" : connection === "connecting" ? "CONNECTING" : "DEGRADED"} />
          <button className={`platform-btn ${mode === "REAL" ? "primary" : ""}`} onClick={() => setMode("REAL")}>REAL</button>
          <button className={`platform-btn ${mode === "DEMO" ? "primary" : ""}`} onClick={() => setMode("DEMO")}>DEMO</button>
        </div>
      }
    >
      {error ? <section className="platform-card"><strong>Operations gateway degraded.</strong><p>{error}</p><p>The last prepared snapshot remains visible when available; tenant API traffic is independent of this gateway.</p></section> : null}

      <div className="platform-tabs" role="tablist" aria-label="Operations views">
        {sections.map((item) => <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}>{item}</button>)}
      </div>

      {section === "NOC" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Platform status" value={<StatusBadge value={overview.platform_status || slo.status || "UNKNOWN"} />} caption="Prepared state; not browser-side DB polling" tone="green" />
          <MetricCard label="Host CPU" value={overview.cpu_percent == null ? "No Prometheus sample" : `${Number(overview.cpu_percent).toFixed(1)}%`} caption="Bare-metal/node telemetry when Prometheus is connected" tone="blue" />
          <MetricCard label="Host memory" value={overview.memory_percent == null ? "No Prometheus sample" : `${Number(overview.memory_percent).toFixed(1)}%`} tone="purple" />
          <MetricCard label="Error budget remaining" value={pct(slo.error_budget_remaining)} caption={`Availability target ${pct(slo.availability_target, 3)}`} tone={Number(slo.error_budget_remaining || 0) < 0.5 ? "red" : "green"} />
          <MetricCard label="Active tenants" value={number(overview.active_tenants)} caption={`${number(fleet.critical)} critical · ${number(fleet.warning)} warning`} />
          <MetricCard label="Durable work queue" value={number(overview.queue_depth)} caption="High-risk work remains approval-gated" tone="amber" />
        </div>
        <section className="platform-card"><h2>Critical tenant fleet</h2><Table headers={["Tenant", "Mode", "Health", "Users", "Requests", "p95", "Quota"]} rows={fleetItems.slice(0, 20).map((item) => [<strong>{item.name || item.amo_code}</strong>, item.data_mode, <StatusBadge value={item.health?.status} />, number(item.users), number(item.requests_window), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`, item.quota_percent == null ? "—" : `${Number(item.quota_percent).toFixed(1)}%`])} /></section>
      </>}

      {section === "SLOs" && <>
        <div className="platform-metric-grid">
          <MetricCard label="Availability" value={pct(slo.availability, 3)} caption={`Target ${pct(slo.availability_target, 3)}`} tone={slo.status === "CRITICAL" ? "red" : "green"} />
          <MetricCard label="Error rate" value={pct(slo.error_rate)} caption={`${number(slo.failures)} failed / ${number(slo.requests)} requests`} />
          <MetricCard label="p95 latency" value={slo.p95_latency_ms == null ? "—" : `${Number(slo.p95_latency_ms).toFixed(0)} ms`} caption={`Target ${number(slo.latency_target_ms)} ms`} />
          <MetricCard label="Budget consumed" value={pct(slo.error_budget_consumed)} />
        </div>
        <section className="platform-card"><h2>Route SLOs</h2><Table headers={["Route", "Status", "Requests", "Error rate", "p95"]} rows={(slo.routes || []).map((item: any) => [item.route, <StatusBadge value={item.status} />, number(item.requests), pct(item.error_rate), item.p95_latency_ms == null ? "—" : `${Number(item.p95_latency_ms).toFixed(0)} ms`])} /></section>
      </>}

      {section === "Capacity" && <div className="platform-metric-grid">
        <MetricCard label="Capacity state" value={<StatusBadge value={capacity.status || "UNKNOWN"} />} />
        <MetricCard label="Estimated headroom" value={`${number(capacity.estimated_headroom_percent)}%`} caption="Pressure indicator; load proof remains authoritative" />
        <MetricCard label="DB connection utilisation" value={pct(capacity.db_connection_utilisation)} caption={`${number(capacity.db_connections_active)} / ${number(capacity.db_connections_max)}`} />
        <MetricCard label="Requests/min" value={number(capacity.requests_per_minute)} />
        <MetricCard label="Queue depth" value={number(capacity.queue_depth)} />
        <MetricCard label="Storage represented" value={bytes(overview.storage_used_bytes)} />
      </div>}

      {section === "Tenant Fleet" && <section className="platform-card"><h2>Tenant Fleet Health</h2><Table headers={["Tenant", "Code", "Country", "State", "Health", "Score", "Users", "Traffic", "Quota", "Last telemetry"]} rows={fleetItems.map((item) => [item.name, item.amo_code, item.country || "—", item.active ? "ACTIVE" : "INACTIVE", <StatusBadge value={item.health?.status} />, number(item.health?.score), `${number(item.active_users)} / ${number(item.users)}`, number(item.requests_window), item.quota_percent == null ? "—" : `${Number(item.quota_percent).toFixed(1)}%`, item.last_telemetry_at ? new Date(item.last_telemetry_at).toLocaleString() : "—"])} /></section>}

      {section === "Incidents" && <section className="platform-card"><h2>Incidents & high-severity alerts</h2><Table headers={["Severity", "Status", "Title", "Tenant", "Created"]} rows={incidentItems.map((item) => [<StatusBadge value={item.severity} />, <StatusBadge value={item.status} />, item.title, item.tenant_id || "Platform", item.created_at ? new Date(item.created_at).toLocaleString() : "—"])} /></section>}

      {section === "Product" && <>
        <div className="platform-metric-grid"><MetricCard label="DAU" value={number(product.dau)} /><MetricCard label="WAU" value={number(product.wau)} /><MetricCard label="MAU" value={number(product.mau)} /><MetricCard label="DAU / MAU" value={pct(product.dau_mau_ratio)} /></div>
        <section className="platform-card"><h2>Operational product usage</h2><p>{String(product.note || "")}</p><Table headers={["Route", "Requests"]} rows={(product.top_routes || []).map((item: any) => [item.route, number(item.requests)])} /></section>
      </>}

      {section === "Commercial" && <div className="platform-metric-grid">
        <MetricCard label="MRR" value={`${commercial.currency || overview.currency || ""} ${number((Number(commercial.mrr || 0)) / 100)}`} />
        <MetricCard label="ARR" value={`${commercial.currency || overview.currency || ""} ${number((Number(commercial.arr || 0)) / 100)}`} />
        <MetricCard label="Active subscriptions" value={number(commercial.active_subscriptions)} />
        <MetricCard label="Trials" value={number(commercial.trial_subscriptions)} />
        <MetricCard label="Overdue invoices" value={number(commercial.overdue_invoices)} tone="amber" />
        <MetricCard label="Grace-period tenants" value={number(commercial.grace_period_tenants)} />
      </div>}

      {section === "Changes" && <><section className="platform-card"><h2>Maintenance windows</h2><Table headers={["Title", "State", "Impact", "Starts", "Ends"]} rows={(changes.maintenance || []).map((item) => [item.title, <StatusBadge value={item.status} />, item.impact_level, item.starts_at ? new Date(item.starts_at).toLocaleString() : "—", item.ends_at ? new Date(item.ends_at).toLocaleString() : "—"])} /></section><section className="platform-card"><h2>Change evidence</h2><Table headers={["Action", "Entity", "Tenant", "Reason", "Time"]} rows={(changes.events || []).map((item) => [item.action, item.entity_type || "—", item.tenant_id || "Platform", item.reason || "—", item.created_at ? new Date(item.created_at).toLocaleString() : "—"])} /></section></>}

      {section === "Jobs" && <section className="platform-card"><h2>Durable operations jobs</h2><Table headers={["Command", "Risk", "State", "Tenant", "Dry run", "Created"]} rows={jobItems.map((item) => [item.command_name, <StatusBadge value={item.risk_level} />, <StatusBadge value={item.status} />, item.tenant_id || "Platform", item.dry_run ? "Yes" : "No", item.created_at ? new Date(item.created_at).toLocaleString() : "—"])} /></section>}
    </PlatformShell>
  );
}
