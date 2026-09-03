import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

const base = () => getApiBaseUrl();

export type LiveMetrics = {
  sampled_at: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  db_connections_active: number | null;
  db_connections_max: number | null;
  db_utilisation_percent: number | null;
  queue_depth: number | null;
  network_rx_bytes_per_sec: number | null;
  network_tx_bytes_per_sec: number | null;
};

export type DbCheckResult = {
  ok: boolean;
  error: string | null;
  samples: number;
  min_ms: number | null;
  avg_ms: number | null;
  max_ms: number | null;
  connections_active: number | null;
  connections_max: number | null;
  utilisation_percent: number | null;
  database_size_bytes: number | null;
  server_version: string | null;
  checked_at: string;
};

export type SpeedTestResult = {
  latency_ms: number;
  jitter_ms: number;
  download_mbps: number;
  upload_mbps: number;
  download_bytes: number;
  upload_bytes: number;
  server_upload_ms: number | null;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    headers: authHeaders(),
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

async function pingOnce(): Promise<number> {
  const started = performance.now();
  const res = await fetch(`${base()}/platform/diagnostics/ping`, {
    headers: authHeaders(),
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Ping failed (${res.status})`);
  await res.json();
  return performance.now() - started;
}

export type NetworkProbeResult = {
  scenario: string;
  target: string | null;
  ok: boolean;
  latency_ms: number | null;
  jitter_ms: number | null;
  download_bps: number | null;
  upload_bps: number | null;
  download_bytes: number | null;
  upload_bytes: number | null;
  error: string | null;
};

export type NetworkStats = { min: number | null; avg: number | null; max: number | null; p95: number | null; samples: number };
export type NetworkPoint = {
  at: string;
  latency_ms: number | null;
  jitter_ms: number | null;
  download_mbps: number | null;
  upload_mbps: number | null;
  ok: boolean;
  source: string;
};
export type ScenarioHistory = {
  points: NetworkPoint[];
  latency_ms: NetworkStats;
  download_mbps: NetworkStats;
  upload_mbps: NetworkStats;
  failures: number;
  total: number;
  sla_download_mbps: number | null;
  sla_breaches: number;
};
export type NetworkHistory = { window: string; since: string; scenarios: Record<string, ScenarioHistory> };

const CLOUDFLARE_HOST = "speed.cloudflare.com";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

export const platformDiagnostics = {
  live: () => getJson<LiveMetrics>("/platform/infrastructure/live"),

  dbCheck: async (samples = 8): Promise<DbCheckResult> => {
    const res = await fetch(`${base()}/platform/diagnostics/db-check`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      credentials: "include",
      body: JSON.stringify({ samples }),
    });
    if (!res.ok) throw new Error(`Database check failed (${res.status})`);
    return (await res.json()) as DbCheckResult;
  },

  speedTest: async (opts?: {
    downloadBytes?: number;
    uploadBytes?: number;
    onProgress?: (stage: string) => void;
  }): Promise<SpeedTestResult> => {
    const downloadBytes = opts?.downloadBytes ?? 12_000_000;
    const uploadBytes = opts?.uploadBytes ?? 8_000_000;

    // Latency + jitter from a short burst of pings.
    opts?.onProgress?.("Measuring latency");
    const pings: number[] = [];
    for (let i = 0; i < 5; i += 1) pings.push(await pingOnce());
    const latency = pings.reduce((a, b) => a + b, 0) / pings.length;
    const jitter =
      pings.length > 1
        ? pings.slice(1).reduce((acc, v, i) => acc + Math.abs(v - pings[i]), 0) / (pings.length - 1)
        : 0;

    // Download throughput.
    opts?.onProgress?.("Measuring download");
    const dStart = performance.now();
    const dRes = await fetch(
      `${base()}/platform/diagnostics/speedtest/download?bytes=${downloadBytes}`,
      { headers: authHeaders(), credentials: "include", cache: "no-store" },
    );
    if (!dRes.ok) throw new Error(`Download test failed (${dRes.status})`);
    const buf = await dRes.arrayBuffer();
    const dSeconds = Math.max(0.001, (performance.now() - dStart) / 1000);
    const downloadMbps = (buf.byteLength * 8) / dSeconds / 1_000_000;

    // Upload throughput.
    opts?.onProgress?.("Measuring upload");
    const payload = new Uint8Array(uploadBytes);
    const uStart = performance.now();
    const uRes = await fetch(`${base()}/platform/diagnostics/speedtest/upload`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/octet-stream" }),
      credentials: "include",
      body: payload,
    });
    if (!uRes.ok) throw new Error(`Upload test failed (${uRes.status})`);
    const uJson = (await uRes.json()) as { bytes_received: number; server_ms: number };
    const uSeconds = Math.max(0.001, (performance.now() - uStart) / 1000);
    const uploadMbps = (uploadBytes * 8) / uSeconds / 1_000_000;

    return {
      latency_ms: latency,
      jitter_ms: jitter,
      download_mbps: downloadMbps,
      upload_mbps: uploadMbps,
      download_bytes: buf.byteLength,
      upload_bytes: uploadBytes,
      server_upload_ms: uJson.server_ms ?? null,
    };
  },

  // Browser -> public internet (Ookla-equivalent), measured directly against
  // Cloudflare's public speed endpoints (CORS-enabled, no auth).
  clientInternetTest: async (opts?: {
    downloadBytes?: number;
    uploadBytes?: number;
    onProgress?: (stage: string) => void;
  }): Promise<SpeedTestResult> => {
    const downloadBytes = opts?.downloadBytes ?? 25_000_000;
    const uploadBytes = opts?.uploadBytes ?? 10_000_000;
    const pingUrl = `https://${CLOUDFLARE_HOST}/__down?bytes=1000`;

    opts?.onProgress?.("Measuring latency");
    const pings: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      const t = performance.now();
      await fetch(pingUrl, { cache: "no-store" });
      pings.push(performance.now() - t);
    }
    const latency = pings.reduce((a, b) => a + b, 0) / pings.length;
    const jitter = pings.length > 1
      ? pings.slice(1).reduce((acc, v, i) => acc + Math.abs(v - pings[i]), 0) / (pings.length - 1)
      : 0;

    opts?.onProgress?.("Measuring download");
    const dStart = performance.now();
    const dRes = await fetch(`https://${CLOUDFLARE_HOST}/__down?bytes=${downloadBytes}`, { cache: "no-store" });
    const buf = await dRes.arrayBuffer();
    const dSeconds = Math.max(0.001, (performance.now() - dStart) / 1000);
    const downloadMbps = (buf.byteLength * 8) / dSeconds / 1_000_000;

    opts?.onProgress?.("Measuring upload");
    const payload = new Uint8Array(uploadBytes);
    const uStart = performance.now();
    await fetch(`https://${CLOUDFLARE_HOST}/__up`, { method: "POST", body: payload, headers: { "Content-Type": "application/octet-stream" } });
    const uSeconds = Math.max(0.001, (performance.now() - uStart) / 1000);
    const uploadMbps = (uploadBytes * 8) / uSeconds / 1_000_000;

    return {
      latency_ms: latency,
      jitter_ms: jitter,
      download_mbps: downloadMbps,
      upload_mbps: uploadMbps,
      download_bytes: buf.byteLength,
      upload_bytes: uploadBytes,
      server_upload_ms: null,
    };
  },

  // Server-side probes (persisted for history).
  internetTest: () => postJson<NetworkProbeResult>("/platform/diagnostics/network/internet", {}),
  databaseTest: () => postJson<NetworkProbeResult>("/platform/diagnostics/network/database", {}),

  // Log a browser-measured result so it appears in history alongside the rest.
  logClient: (scenario: "client_portal" | "client_internet", result: SpeedTestResult, target: string) =>
    postJson<{ id: string }>("/platform/diagnostics/network/client", {
      scenario,
      target,
      ok: true,
      latency_ms: result.latency_ms,
      jitter_ms: result.jitter_ms,
      download_bps: result.download_mbps * 1_000_000,
      upload_bps: result.upload_mbps * 1_000_000,
      download_bytes: result.download_bytes,
      upload_bytes: result.upload_bytes,
    }),

  networkHistory: (window: "24h" | "7d" | "30d", slaDownloadMbps?: number) =>
    getJson<NetworkHistory>(
      `/platform/diagnostics/network/history?window=${window}${slaDownloadMbps ? `&sla_download_mbps=${slaDownloadMbps}` : ""}`,
    ),
};
