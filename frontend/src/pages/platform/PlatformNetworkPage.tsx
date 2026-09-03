import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

import {
  platformDiagnostics,
  type NetworkHistory,
  type NetworkProbeResult,
  type SpeedTestResult,
} from "../../services/platformDiagnostics";
import { EmptyState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";

type ScenarioKey = "client_internet" | "client_portal" | "server_internet" | "server_database";

type Normalised = {
  ok: boolean;
  target: string | null;
  latency_ms: number | null;
  jitter_ms: number | null;
  download_mbps: number | null;
  upload_mbps: number | null;
  error?: string | null;
};

const SCENARIOS: { key: ScenarioKey; short: string; title: string; blurb: string }[] = [
  { key: "client_internet", short: "Internet", title: "Browser → Internet", blurb: "Your link to the wider web" },
  { key: "client_portal", short: "Portal", title: "Browser → Portal", blurb: "Your link to the AMO Portal" },
  { key: "server_internet", short: "Server · Net", title: "Server → Internet", blurb: "Provider / ISP capacity vs. SLA" },
  { key: "server_database", short: "Server · DB", title: "Server → Database", blurb: "Internal app ↔ PostgreSQL" },
];
const SCENARIO_LABEL: Record<string, string> = Object.fromEntries(SCENARIOS.map((s) => [s.key, s.title]));

const fmtMbps = (value?: number | null): string => (value == null ? "—" : `${value.toFixed(1)}`);
const fmtMs = (value?: number | null): string => (value == null ? "—" : `${value.toFixed(1)}`);

function niceMax(value: number): number {
  for (const step of [50, 100, 250, 500, 1000, 2500, 5000, 10000]) if (value <= step) return step;
  return Math.ceil(value / 1000) * 1000;
}

const Gauge: React.FC<{ value: number | null }> = ({ value }) => {
  const v = value ?? 0;
  const max = niceMax(Math.max(v, 50));
  const pct = Math.max(0, Math.min(v / max, 1));
  const length = Math.PI * 80;
  return (
    <svg className="platform-net-gauge" viewBox="0 0 200 108" role="img" aria-label="Download gauge">
      <path d="M20,100 A80,80 0 0 1 180,100" fill="none" stroke="rgba(148,163,184,0.16)" strokeWidth="12" strokeLinecap="round" />
      <path
        d="M20,100 A80,80 0 0 1 180,100"
        fill="none"
        stroke="var(--platform-accent, #3b67f2)"
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${(pct * length).toFixed(1)} ${length.toFixed(1)}`}
      />
      <text x="100" y="86" textAnchor="middle" className="platform-net-gauge__num">{value == null ? "—" : v.toFixed(1)}</text>
      <text x="100" y="102" textAnchor="middle" className="platform-net-gauge__unit">Mbps download</text>
    </svg>
  );
};

function normaliseSpeed(result: SpeedTestResult, target: string): Normalised {
  return { ok: true, target, latency_ms: result.latency_ms, jitter_ms: result.jitter_ms, download_mbps: result.download_mbps, upload_mbps: result.upload_mbps };
}
function normaliseProbe(result: NetworkProbeResult): Normalised {
  return {
    ok: result.ok,
    target: result.target,
    latency_ms: result.latency_ms,
    jitter_ms: result.jitter_ms,
    download_mbps: result.download_bps == null ? null : result.download_bps / 1_000_000,
    upload_mbps: result.upload_bps == null ? null : result.upload_bps / 1_000_000,
    error: result.error,
  };
}

export default function PlatformNetworkPage() {
  const [target, setTarget] = useState<ScenarioKey>("client_internet");
  const [results, setResults] = useState<Partial<Record<ScenarioKey, Normalised>>>({});
  const [running, setRunning] = useState<ScenarioKey | null>(null);
  const [stage, setStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const [window, setWindow] = useState<"24h" | "7d" | "30d">("24h");
  const [sla, setSla] = useState<number>(100);
  const [chartScenario, setChartScenario] = useState<ScenarioKey>("server_internet");
  const [history, setHistory] = useState<NetworkHistory | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await platformDiagnostics.networkHistory(window, sla || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    }
  }, [window, sla]);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const runScenario = useCallback(async (key: ScenarioKey) => {
    setRunning(key);
    setTarget(key);
    setError(null);
    setStage("");
    try {
      let normalised: Normalised;
      if (key === "client_internet") {
        const r = await platformDiagnostics.clientInternetTest({ onProgress: setStage });
        normalised = normaliseSpeed(r, "speed.cloudflare.com");
        await platformDiagnostics.logClient("client_internet", r, "speed.cloudflare.com").catch(() => undefined);
      } else if (key === "client_portal") {
        const r = await platformDiagnostics.speedTest({ onProgress: setStage });
        normalised = normaliseSpeed(r, "portal");
        await platformDiagnostics.logClient("client_portal", r, "portal").catch(() => undefined);
      } else if (key === "server_internet") {
        setStage("Testing from server");
        normalised = normaliseProbe(await platformDiagnostics.internetTest());
      } else {
        setStage("Testing database link");
        normalised = normaliseProbe(await platformDiagnostics.databaseTest());
      }
      setResults((current) => ({ ...current, [key]: normalised }));
      void loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setRunning(null);
      setStage("");
    }
  }, [loadHistory]);

  // Latest known value per leg: live result if run this session, else the most
  // recent stored measurement from history.
  const latestByLeg = useMemo(() => {
    const map: Record<string, { download: number | null; latency: number | null; ok: boolean }> = {};
    for (const scenario of SCENARIOS) {
      const live = results[scenario.key];
      if (live) {
        map[scenario.key] = { download: live.download_mbps, latency: live.latency_ms, ok: live.ok };
        continue;
      }
      const points = history?.scenarios?.[scenario.key]?.points ?? [];
      const last = points[points.length - 1];
      map[scenario.key] = last ? { download: last.download_mbps, latency: last.latency_ms, ok: last.ok } : { download: null, latency: null, ok: true };
    }
    return map;
  }, [results, history]);

  const active = results[target];
  const activeMeta = SCENARIOS.find((s) => s.key === target)!;
  const scenarioHistory = history?.scenarios?.[chartScenario];

  const chartData = useMemo(
    () => (scenarioHistory?.points ?? []).map((point) => ({
      at: point.at ? new Date(point.at).getTime() : 0,
      download: point.download_mbps,
      upload: point.upload_mbps,
    })),
    [scenarioHistory],
  );

  const logRows = useMemo(() => {
    if (!history) return [];
    const rows: Record<string, unknown>[] = [];
    for (const [name, data] of Object.entries(history.scenarios)) {
      for (const point of data.points) {
        rows.push({ at: point.at, scenario: SCENARIO_LABEL[name] ?? name, download: point.download_mbps, upload: point.upload_mbps, latency: point.latency_ms, source: point.source, status: point.ok ? "OK" : "FAILED" });
      }
    }
    return rows.sort((a, b) => new Date(String(b.at)).getTime() - new Date(String(a.at)).getTime());
  }, [history]);

  const columnDefs = useMemo<ColDef[]>(() => [
    { headerName: "When", field: "at", sort: "desc", flex: 1.4, minWidth: 170, valueFormatter: (p) => (p.value ? new Date(String(p.value)).toLocaleString() : "—") },
    { headerName: "Connection", field: "scenario", flex: 1.3, minWidth: 150 },
    { headerName: "Download (Mbps)", field: "download", flex: 1, minWidth: 130, type: "numericColumn", valueFormatter: (p) => (p.value == null ? "—" : Number(p.value).toFixed(1)) },
    { headerName: "Upload (Mbps)", field: "upload", flex: 1, minWidth: 130, type: "numericColumn", valueFormatter: (p) => (p.value == null ? "—" : Number(p.value).toFixed(1)) },
    { headerName: "Ping (ms)", field: "latency", flex: 0.9, minWidth: 110, type: "numericColumn", valueFormatter: (p) => (p.value == null ? "—" : Number(p.value).toFixed(1)) },
    { headerName: "Source", field: "source", flex: 0.8, minWidth: 100 },
    { headerName: "Status", field: "status", flex: 0.7, minWidth: 90 },
  ], []);

  const defaultColDef = useMemo<ColDef>(() => ({ sortable: true, filter: true, resizable: true, suppressHeaderMenuButton: true }), []);

  return (
    <PlatformShell
      title="Network Diagnostics"
      subtitle="Speed, latency and SLA history across every connection"
      actions={<button className="platform-btn" onClick={loadHistory}>Refresh</button>}
    >
      {error ? <div className="platform-inline-note bad">{error}</div> : null}

      {/* ---- Speed test (single Ookla-style test with a target selector) ---- */}
      <section className="platform-two platform-two--spaced">
        <div className="platform-card platform-net-hero">
          <div className="platform-net-hero__top">
            <div>
              <h2>Speed test</h2>
              <small>{activeMeta.title} · {activeMeta.blurb}</small>
            </div>
            <div className="platform-seg" role="tablist" aria-label="Test target">
              {SCENARIOS.map((scenario) => (
                <button
                  key={scenario.key}
                  role="tab"
                  aria-selected={target === scenario.key}
                  className={target === scenario.key ? "active" : undefined}
                  onClick={() => setTarget(scenario.key)}
                  disabled={running !== null}
                >
                  {scenario.short}
                </button>
              ))}
            </div>
          </div>

          <div className="platform-net-hero__body">
            <Gauge value={active?.download_mbps ?? null} />
            <div className="platform-net-hero__metrics">
              <div><span>Download</span><strong>{fmtMbps(active?.download_mbps)}<em>Mbps</em></strong></div>
              <div><span>Upload</span><strong>{fmtMbps(active?.upload_mbps)}<em>Mbps</em></strong></div>
              <div><span>Ping</span><strong>{fmtMs(active?.latency_ms)}<em>ms</em></strong></div>
              <div><span>Jitter</span><strong>{fmtMs(active?.jitter_ms)}<em>ms</em></strong></div>
            </div>
          </div>

          <div className="platform-net-hero__foot">
            <span className="platform-muted">{running === target ? (stage || "Running…") : active?.target ? `Target: ${active.target}` : "Choose a target and run"}</span>
            <button className="platform-btn primary" onClick={() => runScenario(target)} disabled={running !== null}>
              {running === target ? "Testing…" : "Run test"}
            </button>
          </div>
          {active?.error ? <div className="platform-inline-note bad">{active.error}</div> : null}
        </div>

        <div className="platform-card">
          <h2>All connections</h2>
          <div className="platform-net-legs">
            {SCENARIOS.map((scenario) => {
              const latest = latestByLeg[scenario.key];
              const isRunning = running === scenario.key;
              return (
                <button
                  key={scenario.key}
                  className={`platform-net-leg${target === scenario.key ? " active" : ""}`}
                  onClick={() => runScenario(scenario.key)}
                  disabled={running !== null}
                >
                  <span className="platform-net-leg__id">
                    <span className={`platform-status-dot ${latest?.ok === false ? "offline" : "live"}`} />
                    <span><strong>{scenario.title}</strong><small>{scenario.blurb}</small></span>
                  </span>
                  <span className="platform-net-leg__val">
                    <strong>{fmtMbps(latest?.download)}<em>Mbps</em></strong>
                    <small>{fmtMs(latest?.latency)} ms</small>
                  </span>
                  <span className="platform-net-leg__go">{isRunning ? "…" : "▸"}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---- SLA history ---- */}
      <section className="platform-section-head">
        <h2>SLA history</h2>
        <div className="platform-actions">
          <select value={chartScenario} onChange={(event) => setChartScenario(event.target.value as ScenarioKey)}>
            {SCENARIOS.map((scenario) => <option key={scenario.key} value={scenario.key}>{scenario.title}</option>)}
          </select>
          <select value={window} onChange={(event) => setWindow(event.target.value as "24h" | "7d" | "30d")}>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <label className="platform-net-sla"><span>SLA ≥</span><input type="number" min={0} value={sla} onChange={(event) => setSla(Number(event.target.value) || 0)} /><span>Mbps</span></label>
        </div>
      </section>

      <section className="platform-grid">
        <MetricCard label="Avg download" value={`${fmtMbps(scenarioHistory?.download_mbps.avg)} Mbps`} caption={`min ${fmtMbps(scenarioHistory?.download_mbps.min)} · p95 ${fmtMbps(scenarioHistory?.download_mbps.p95)}`} />
        <MetricCard label="Avg latency" value={`${fmtMs(scenarioHistory?.latency_ms.avg)} ms`} caption={`max ${fmtMs(scenarioHistory?.latency_ms.max)} ms`} />
        <MetricCard label="Samples" value={scenarioHistory?.total ?? 0} caption={`${scenarioHistory?.failures ?? 0} failures`} />
        <MetricCard label={`SLA breaches (<${sla})`} value={scenarioHistory?.sla_breaches ?? 0} tone={(scenarioHistory?.sla_breaches ?? 0) > 0 ? "amber" : "green"} caption={`${window} · ${SCENARIO_LABEL[chartScenario]}`} />
      </section>

      <section className="platform-card">
        {chartData.length ? (
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <AreaChart data={chartData} margin={{ top: 8, right: 18, bottom: 0, left: -8 }}>
                <defs>
                  <linearGradient id="netDown" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--platform-accent, #3b67f2)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--platform-accent, #3b67f2)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.14)" />
                <XAxis dataKey="at" type="number" domain={["dataMin", "dataMax"]} scale="time" tick={{ fontSize: 10, fill: "#8796ad" }} minTickGap={70} tickFormatter={(value) => new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} />
                <YAxis tick={{ fontSize: 10, fill: "#8796ad" }} width={44} unit="" />
                <Tooltip labelFormatter={(value) => new Date(Number(value)).toLocaleString()} formatter={(value: number, name: string) => [value == null ? "—" : `${Number(value).toFixed(1)} Mbps`, name]} contentStyle={{ background: "#0e1a2f", border: "1px solid rgba(148,163,184,0.24)", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {sla > 0 ? <ReferenceLine y={sla} stroke="#e25565" strokeDasharray="5 4" label={{ value: `SLA ${sla}`, fill: "#e25565", fontSize: 10, position: "insideTopRight" }} /> : null}
                <Area type="monotone" dataKey="download" name="Download" stroke="var(--platform-accent, #3b67f2)" strokeWidth={2} fill="url(#netDown)" isAnimationActive={false} />
                <Area type="monotone" dataKey="upload" name="Upload" stroke="#22c55e" strokeWidth={1.5} fill="transparent" isAnimationActive={false} />
                <Brush dataKey="at" height={20} travellerWidth={8} stroke="rgba(148,163,184,0.4)" fill="rgba(148,163,184,0.06)" tickFormatter={(value) => new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState label="No measurements for this window yet. Run a test or wait for the scheduled probes." />}
      </section>

      {/* ---- Measurement log (AG Grid) ---- */}
      <section className="platform-card">
        <div className="platform-section-head compact"><h2>Measurement log</h2><StatusBadge value={`${logRows.length} ROWS`} /></div>
        <div className="ag-theme-alpine-dark platform-net-grid">
          <AgGridReact
            rowData={logRows}
            columnDefs={columnDefs}
            defaultColDef={defaultColDef}
            pagination
            paginationPageSize={20}
            paginationPageSizeSelector={[20, 50, 100]}
            animateRows
          />
        </div>
      </section>
    </PlatformShell>
  );
}
