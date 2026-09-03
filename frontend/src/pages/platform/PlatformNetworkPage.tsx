import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  platformDiagnostics,
  type NetworkHistory,
  type NetworkProbeResult,
  type SpeedTestResult,
} from "../../services/platformDiagnostics";
import { DataTable, EmptyState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";

type ScenarioKey = "client_portal" | "client_internet" | "server_internet" | "server_database";

type Normalised = {
  ok: boolean;
  target: string | null;
  latency_ms: number | null;
  jitter_ms: number | null;
  download_mbps: number | null;
  upload_mbps: number | null;
  error?: string | null;
};

const SCENARIOS: { key: ScenarioKey; title: string; blurb: string; kind: "client" | "server" }[] = [
  { key: "client_internet", title: "This browser → Internet", blurb: "Your connection to the wider web (Ookla-style)", kind: "client" },
  { key: "client_portal", title: "This browser → Portal", blurb: "Your connection to the AMO Portal", kind: "client" },
  { key: "server_internet", title: "Server → Internet", blurb: "Provider/ISP capacity vs. SLA", kind: "server" },
  { key: "server_database", title: "Server → Database", blurb: "Internal app ↔ PostgreSQL link", kind: "server" },
];

const SCENARIO_LABEL: Record<string, string> = {
  client_internet: "Browser → Internet",
  client_portal: "Browser → Portal",
  server_internet: "Server → Internet",
  server_database: "Server → Database",
};

const mbps = (value?: number | null): string => (value == null ? "—" : `${value.toFixed(1)} Mbps`);
const ms = (value?: number | null): string => (value == null ? "—" : `${value.toFixed(1)} ms`);

function niceMax(value: number): number {
  const steps = [50, 100, 250, 500, 1000, 2500, 5000, 10000];
  for (const step of steps) if (value <= step) return step;
  return Math.ceil(value / 1000) * 1000;
}

const Gauge: React.FC<{ value: number | null; label: string }> = ({ value, label }) => {
  const v = value ?? 0;
  const max = niceMax(Math.max(v, 50));
  const pct = Math.max(0, Math.min(v / max, 1));
  const length = Math.PI * 60;
  return (
    <div className="platform-gauge">
      <svg viewBox="0 0 140 78" width="100%" height="86">
        <path d="M10,70 A60,60 0 0 1 130,70" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="10" strokeLinecap="round" />
        <path
          d="M10,70 A60,60 0 0 1 130,70"
          fill="none"
          stroke="var(--platform-accent, #3b67f2)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${(pct * length).toFixed(1)} ${length.toFixed(1)}`}
        />
      </svg>
      <div className="platform-gauge__value">{value == null ? "—" : v.toFixed(1)}<span>Mbps</span></div>
      <div className="platform-gauge__label">{label}</div>
    </div>
  );
};

function normaliseSpeed(result: SpeedTestResult, target: string): Normalised {
  return {
    ok: true,
    target,
    latency_ms: result.latency_ms,
    jitter_ms: result.jitter_ms,
    download_mbps: result.download_mbps,
    upload_mbps: result.upload_mbps,
  };
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

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const runScenario = async (key: ScenarioKey) => {
    setRunning(key);
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
  };

  const runAll = async () => {
    for (const scenario of SCENARIOS) {
      // eslint-disable-next-line no-await-in-loop
      await runScenario(scenario.key);
    }
  };

  const scenarioHistory = history?.scenarios?.[chartScenario];
  const chartData = useMemo(
    () => (scenarioHistory?.points ?? []).map((point) => ({
      at: point.at ? new Date(point.at).getTime() : 0,
      download: point.download_mbps,
      upload: point.upload_mbps,
      latency: point.latency_ms,
    })),
    [scenarioHistory],
  );

  const recentRows = useMemo(() => {
    if (!history) return [];
    const rows: { at: string; scenario: string; download: number | null; upload: number | null; latency: number | null; ok: boolean; source: string }[] = [];
    for (const [name, data] of Object.entries(history.scenarios)) {
      for (const point of data.points) {
        rows.push({ at: point.at, scenario: name, download: point.download_mbps, upload: point.upload_mbps, latency: point.latency_ms, ok: point.ok, source: point.source });
      }
    }
    return rows.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()).slice(0, 15);
  }, [history]);

  return (
    <PlatformShell
      title="Network Diagnostics"
      subtitle="Speed, latency and SLA history across every connection"
      actions={<button className="platform-btn primary" onClick={runAll} disabled={running !== null}>{running ? "Testing…" : "Run all tests"}</button>}
    >
      {error ? <div className="platform-inline-note bad">{error}</div> : null}

      <section className="platform-grid platform-grid--live">
        {SCENARIOS.map((scenario) => {
          const result = results[scenario.key];
          const isRunning = running === scenario.key;
          return (
            <section className="platform-card platform-net-card" key={scenario.key}>
              <div className="platform-net-card__head">
                <div>
                  <strong>{scenario.title}</strong>
                  <small>{scenario.blurb}</small>
                </div>
                <StatusBadge value={scenario.kind === "server" ? "SERVER" : "CLIENT"} />
              </div>
              <Gauge value={result?.download_mbps ?? null} label="Download" />
              <div className="platform-net-card__stats">
                <span><em>Upload</em>{mbps(result?.upload_mbps)}</span>
                <span><em>Ping</em>{ms(result?.latency_ms)}</span>
                <span><em>Jitter</em>{ms(result?.jitter_ms)}</span>
              </div>
              {isRunning ? <div className="platform-inline-note">{stage || "Running…"}</div> : null}
              {result?.error ? <div className="platform-inline-note bad">{result.error}</div> : null}
              <button className="platform-btn primary" onClick={() => runScenario(scenario.key)} disabled={running !== null}>
                {isRunning ? "Testing…" : "Run test"}
              </button>
            </section>
          );
        })}
      </section>

      <section className="platform-section-head">
        <h2>SLA history</h2>
        <div className="platform-actions">
          <select value={chartScenario} onChange={(event) => setChartScenario(event.target.value as ScenarioKey)}>
            {SCENARIOS.map((scenario) => <option key={scenario.key} value={scenario.key}>{SCENARIO_LABEL[scenario.key]}</option>)}
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
        <MetricCard label="Avg download" value={mbps(scenarioHistory?.download_mbps.avg)} caption={`min ${mbps(scenarioHistory?.download_mbps.min)} · p95 ${mbps(scenarioHistory?.download_mbps.p95)}`} />
        <MetricCard label="Avg latency" value={ms(scenarioHistory?.latency_ms.avg)} caption={`max ${ms(scenarioHistory?.latency_ms.max)}`} />
        <MetricCard label="Samples" value={scenarioHistory?.total ?? 0} caption={`${scenarioHistory?.failures ?? 0} failures`} />
        <MetricCard label={`SLA breaches (<${sla} Mbps)`} value={scenarioHistory?.sla_breaches ?? 0} tone={(scenarioHistory?.sla_breaches ?? 0) > 0 ? "amber" : "green"} caption={`${window} window`} />
      </section>

      <section className="platform-card">
        <h2>{SCENARIO_LABEL[chartScenario]} — download throughput</h2>
        {chartData.length ? (
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={chartData} margin={{ top: 10, right: 16, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
                <XAxis dataKey="at" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={(value) => new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} tick={{ fontSize: 10, fill: "#8796ad" }} minTickGap={60} />
                <YAxis tick={{ fontSize: 10, fill: "#8796ad" }} width={44} />
                <Tooltip labelFormatter={(value) => new Date(Number(value)).toLocaleString()} formatter={(value: number, name) => [value == null ? "—" : `${Number(value).toFixed(1)} Mbps`, name]} contentStyle={{ background: "#0e1a2f", border: "1px solid rgba(148,163,184,0.24)", borderRadius: 8, fontSize: 12 }} />
                {sla > 0 ? <ReferenceLine y={sla} stroke="#e25565" strokeDasharray="5 4" label={{ value: `SLA ${sla}`, fill: "#e25565", fontSize: 10, position: "insideTopRight" }} /> : null}
                <Line type="monotone" dataKey="download" name="Download" stroke="var(--platform-accent, #3b67f2)" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="upload" name="Upload" stroke="#22c55e" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState label="No measurements yet for this window. Run a test or wait for the scheduled probes." />}
      </section>

      <section className="platform-card">
        <h2>Recent measurements</h2>
        {recentRows.length ? (
          <DataTable>
            <thead><tr><th>When</th><th>Scenario</th><th>Download</th><th>Upload</th><th>Ping</th><th>Source</th><th>Status</th></tr></thead>
            <tbody>
              {recentRows.map((row, index) => (
                <tr key={`${row.at}-${row.scenario}-${index}`}>
                  <td>{new Date(row.at).toLocaleString()}</td>
                  <td>{SCENARIO_LABEL[row.scenario] ?? row.scenario}</td>
                  <td>{mbps(row.download)}</td>
                  <td>{mbps(row.upload)}</td>
                  <td>{ms(row.latency)}</td>
                  <td>{row.source}</td>
                  <td><StatusBadge value={row.ok ? "OK" : "FAILED"} /></td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : <EmptyState label="No measurements logged yet." />}
      </section>
    </PlatformShell>
  );
}
