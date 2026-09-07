import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

const base = () => getApiBaseUrl();
const CLOUDFLARE_HOST = "speed.cloudflare.com";

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

export type SpeedTestPhase = "preparing" | "latency" | "download" | "upload" | "complete";
export type SpeedTestProgress = {
  phase: SpeedTestPhase;
  label: string;
  percent: number;
  current_mbps: number | null;
  elapsed_ms: number;
  bytes_transferred: number;
  samples: number;
  stable: boolean;
};

export type SpeedTestResult = {
  latency_ms: number;
  jitter_ms: number;
  download_mbps: number;
  upload_mbps: number;
  download_bytes: number;
  upload_bytes: number;
  server_upload_ms: number | null;
  loaded_download_latency_ms: number | null;
  loaded_upload_latency_ms: number | null;
  packet_loss_percent: number;
  duration_ms: number;
  confidence: "high" | "standard" | "limited";
  engine: string;
  target: string;
  edge_location: string | null;
  download_samples: number;
  upload_samples: number;
};

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
  details?: Record<string, unknown> | null;
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
  target?: string | null;
  error?: string | null;
  details?: Record<string, unknown> | null;
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

type AdaptiveTestOptions = {
  durationSeconds?: number;
  signal?: AbortSignal;
  onProgress?: (progress: SpeedTestProgress) => void;
};

type Target = {
  label: string;
  pingUrl: () => string;
  downloadUrl: (bytes: number) => string;
  uploadUrl: () => string;
  headers: () => HeadersInit;
  credentials?: RequestCredentials;
  downloadBlock: number;
  uploadBlock: number;
};

type DirectionResult = {
  mbps: number;
  bytes: number;
  elapsedMs: number;
  samples: number;
  stable: boolean;
  ray: string | null;
  serverMs: number | null;
};

const median = (values: number[]): number => {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

const jitter = (values: number[]): number => {
  if (values.length < 2) return 0;
  return values.slice(1).reduce((sum, value, index) => sum + Math.abs(value - values[index]), 0) / (values.length - 1);
};

export const isThroughputStable = (values: number[], windowSize = 4): boolean => {
  if (values.length < windowSize) return false;
  const recent = values.slice(-windowSize);
  const mean = recent.reduce((sum, value) => sum + value, 0) / recent.length;
  if (mean <= 0) return false;
  const variance = recent.reduce((sum, value) => sum + (value - mean) ** 2, 0) / recent.length;
  return Math.sqrt(variance) / mean <= 0.08;
};

const wait = (milliseconds: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds);
  const abort = () => {
    window.clearTimeout(timer);
    reject(new DOMException("Test cancelled", "AbortError"));
  };
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
});

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base()}${path}`, { headers: authHeaders(), credentials: "include", cache: "no-store" });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

function withNonce(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}_=${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function ping(target: Target, signal?: AbortSignal): Promise<number> {
  const started = performance.now();
  const response = await fetch(withNonce(target.pingUrl()), {
    headers: target.headers(), credentials: target.credentials, cache: "no-store", signal,
  });
  if (!response.ok) throw new Error(`Latency probe failed (${response.status})`);
  await response.arrayBuffer();
  return performance.now() - started;
}

async function loadedLatency(target: Target, active: () => boolean, signal?: AbortSignal): Promise<number | null> {
  const values: number[] = [];
  while (active() && !signal?.aborted) {
    try {
      values.push(await ping(target, signal));
    } catch (error) {
      if (signal?.aborted) throw error;
    }
    if (active()) await wait(250, signal);
  }
  return values.length ? median(values) : null;
}

function phaseProgress(phase: "download" | "upload", elapsedMs: number, targetMs: number): number {
  const fraction = Math.min(1, elapsedMs / targetMs);
  return phase === "download" ? 15 + fraction * 45 : 60 + fraction * 39;
}

async function runDownload(
  target: Target,
  targetMs: number,
  signal: AbortSignal | undefined,
  report: (progress: SpeedTestProgress) => void,
): Promise<DirectionResult> {
  const started = performance.now();
  const rates: number[] = [];
  let total = 0;
  let ray: string | null = null;
  let lastReport = 0;
  while (true) {
    const sampleStarted = performance.now();
    const response = await fetch(withNonce(target.downloadUrl(target.downloadBlock)), {
      headers: target.headers(), credentials: target.credentials, cache: "no-store", signal,
    });
    if (!response.ok) throw new Error(`Download test failed (${response.status})`);
    ray = response.headers.get("cf-ray") || ray;
    let sampleBytes = 0;
    if (response.body) {
      const reader = response.body.getReader();
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        sampleBytes += part.value.byteLength;
        total += part.value.byteLength;
        const now = performance.now();
        if (now - lastReport >= 100) {
          const elapsed = Math.max(1, now - started);
          report({
            phase: "download", label: "Measuring download", percent: phaseProgress("download", elapsed, targetMs),
            current_mbps: total * 8 / elapsed / 1000, elapsed_ms: elapsed, bytes_transferred: total,
            samples: rates.length, stable: isThroughputStable(rates),
          });
          lastReport = now;
        }
      }
    } else {
      const buffer = await response.arrayBuffer();
      sampleBytes = buffer.byteLength;
      total += buffer.byteLength;
    }
    const sampleElapsed = Math.max(1, performance.now() - sampleStarted);
    rates.push(sampleBytes * 8 / sampleElapsed / 1000);
    const elapsed = performance.now() - started;
    const stable = isThroughputStable(rates);
    report({
      phase: "download", label: stable ? "Download stabilised" : "Stabilising download", percent: phaseProgress("download", elapsed, targetMs),
      current_mbps: total * 8 / Math.max(1, elapsed) / 1000, elapsed_ms: elapsed, bytes_transferred: total,
      samples: rates.length, stable,
    });
    if ((elapsed >= targetMs && stable) || elapsed >= targetMs + 6000 || total >= 768 * 1024 * 1024) {
      return { mbps: total * 8 / Math.max(1, elapsed) / 1000, bytes: total, elapsedMs: elapsed, samples: rates.length, stable, ray, serverMs: null };
    }
  }
}

function uploadBlock(
  target: Target,
  payload: ArrayBuffer,
  signal: AbortSignal | undefined,
  progress: (loaded: number) => void,
): Promise<{ ray: string | null; serverMs: number | null }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", withNonce(target.uploadUrl()));
    xhr.withCredentials = target.credentials === "include";
    new Headers(target.headers()).forEach((value, key) => xhr.setRequestHeader(key, value));
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => progress(event.loaded);
    xhr.onerror = () => reject(new Error("Upload test could not reach the target"));
    xhr.onabort = () => reject(new DOMException("Test cancelled", "AbortError"));
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`Upload test failed (${xhr.status})`));
        return;
      }
      let serverMs: number | null = null;
      try { serverMs = Number((JSON.parse(xhr.responseText) as { server_ms?: number }).server_ms) || null; } catch { /* public edge has no JSON body */ }
      resolve({ ray: xhr.getResponseHeader("cf-ray"), serverMs });
    };
    const abort = () => xhr.abort();
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
    xhr.send(payload);
  });
}

async function runUpload(
  target: Target,
  targetMs: number,
  signal: AbortSignal | undefined,
  report: (progress: SpeedTestProgress) => void,
): Promise<DirectionResult> {
  const started = performance.now();
  const rates: number[] = [];
  const payload = new ArrayBuffer(target.uploadBlock);
  let total = 0;
  let ray: string | null = null;
  let serverMs: number | null = null;
  while (true) {
    const sampleStarted = performance.now();
    const before = total;
    const response = await uploadBlock(target, payload, signal, (loaded) => {
      const elapsed = Math.max(1, performance.now() - started);
      report({
        phase: "upload", label: "Measuring upload", percent: phaseProgress("upload", elapsed, targetMs),
        current_mbps: (before + loaded) * 8 / elapsed / 1000, elapsed_ms: elapsed,
        bytes_transferred: before + loaded, samples: rates.length, stable: isThroughputStable(rates),
      });
    });
    total += payload.byteLength;
    ray = response.ray || ray;
    serverMs = response.serverMs ?? serverMs;
    const sampleElapsed = Math.max(1, performance.now() - sampleStarted);
    rates.push(payload.byteLength * 8 / sampleElapsed / 1000);
    const elapsed = performance.now() - started;
    const stable = isThroughputStable(rates);
    report({
      phase: "upload", label: stable ? "Upload stabilised" : "Stabilising upload", percent: phaseProgress("upload", elapsed, targetMs),
      current_mbps: total * 8 / Math.max(1, elapsed) / 1000, elapsed_ms: elapsed,
      bytes_transferred: total, samples: rates.length, stable,
    });
    if ((elapsed >= targetMs && stable) || elapsed >= targetMs + 6000 || total >= 512 * 1024 * 1024) {
      return { mbps: total * 8 / Math.max(1, elapsed) / 1000, bytes: total, elapsedMs: elapsed, samples: rates.length, stable, ray, serverMs };
    }
  }
}

async function adaptiveSpeedTest(target: Target, options?: AdaptiveTestOptions): Promise<SpeedTestResult> {
  const durationMs = Math.max(6000, Math.min(15000, (options?.durationSeconds ?? 8) * 1000));
  const report = options?.onProgress ?? (() => undefined);
  const testStarted = performance.now();
  report({ phase: "preparing", label: "Warming connection", percent: 1, current_mbps: null, elapsed_ms: 0, bytes_transferred: 0, samples: 0, stable: false });
  await fetch(withNonce(target.downloadUrl(250_000)), {
    headers: target.headers(), credentials: target.credentials, cache: "no-store", signal: options?.signal,
  }).then((response) => {
    if (!response.ok) throw new Error(`Warm-up failed (${response.status})`);
    return response.arrayBuffer();
  });

  const latencies: number[] = [];
  let latencyFailures = 0;
  for (let index = 0; index < 9; index += 1) {
    try { latencies.push(await ping(target, options?.signal)); } catch (error) {
      if (options?.signal?.aborted) throw error;
      latencyFailures += 1;
    }
    report({ phase: "latency", label: "Sampling idle latency", percent: 3 + ((index + 1) / 9) * 12, current_mbps: null, elapsed_ms: performance.now() - testStarted, bytes_transferred: 0, samples: index + 1, stable: false });
  }
  if (!latencies.length) throw new Error("The target did not return a latency sample");

  let downloadActive = true;
  const downloadLoadedLatency = loadedLatency(target, () => downloadActive, options?.signal).catch((error) => {
    if (options?.signal?.aborted) return null;
    throw error;
  });
  let download: DirectionResult;
  try {
    download = await runDownload(target, durationMs, options?.signal, report);
  } finally {
    downloadActive = false;
  }
  const loadedDownload = await downloadLoadedLatency;

  let uploadActive = true;
  const uploadLoadedLatency = loadedLatency(target, () => uploadActive, options?.signal).catch((error) => {
    if (options?.signal?.aborted) return null;
    throw error;
  });
  let upload: DirectionResult;
  try {
    upload = await runUpload(target, durationMs, options?.signal, report);
  } finally {
    uploadActive = false;
  }
  const loadedUpload = await uploadLoadedLatency;

  const ray = download.ray || upload.ray;
  const edgeLocation = ray && ray.includes("-") ? ray.split("-").pop()?.toUpperCase() || null : null;
  const durationComplete = download.elapsedMs >= durationMs && upload.elapsedMs >= durationMs;
  const confidence = durationComplete && download.stable && upload.stable ? "high" : durationComplete ? "standard" : "limited";
  const result: SpeedTestResult = {
    latency_ms: median(latencies), jitter_ms: jitter(latencies), download_mbps: download.mbps, upload_mbps: upload.mbps,
    download_bytes: download.bytes, upload_bytes: upload.bytes, server_upload_ms: upload.serverMs,
    loaded_download_latency_ms: loadedDownload, loaded_upload_latency_ms: loadedUpload,
    packet_loss_percent: latencyFailures / 9 * 100, duration_ms: performance.now() - testStarted,
    confidence, engine: "adaptive-http-goodput-v2", target: target.label, edge_location: edgeLocation,
    download_samples: download.samples, upload_samples: upload.samples,
  };
  report({ phase: "complete", label: "Measurement complete", percent: 100, current_mbps: result.download_mbps, elapsed_ms: result.duration_ms, bytes_transferred: result.download_bytes + result.upload_bytes, samples: result.download_samples + result.upload_samples, stable: confidence === "high" });
  return result;
}

const portalTarget = (): Target => ({
  label: "AMO Portal API",
  pingUrl: () => `${base()}/platform/diagnostics/ping`,
  downloadUrl: (bytes) => `${base()}/platform/diagnostics/speedtest/download?bytes=${bytes}`,
  uploadUrl: () => `${base()}/platform/diagnostics/speedtest/upload`,
  headers: () => authHeaders(), credentials: "include", downloadBlock: 8 * 1024 * 1024, uploadBlock: 4 * 1024 * 1024,
});

const internetTarget = (): Target => ({
  label: "Cloudflare nearest edge",
  pingUrl: () => `https://${CLOUDFLARE_HOST}/__down?bytes=1000`,
  downloadUrl: (bytes) => `https://${CLOUDFLARE_HOST}/__down?bytes=${bytes}`,
  uploadUrl: () => `https://${CLOUDFLARE_HOST}/__up`,
  headers: () => ({}), downloadBlock: 16 * 1024 * 1024, uploadBlock: 8 * 1024 * 1024,
});

export const platformDiagnostics = {
  live: () => getJson<LiveMetrics>("/platform/infrastructure/live"),
  dbCheck: async (samples = 8): Promise<DbCheckResult> => {
    const res = await fetch(`${base()}/platform/diagnostics/db-check`, {
      method: "POST", headers: authHeaders({ "Content-Type": "application/json" }), credentials: "include", body: JSON.stringify({ samples }),
    });
    if (!res.ok) throw new Error(`Database check failed (${res.status})`);
    return (await res.json()) as DbCheckResult;
  },
  speedTest: (options?: AdaptiveTestOptions) => adaptiveSpeedTest(portalTarget(), options),
  clientInternetTest: (options?: AdaptiveTestOptions) => adaptiveSpeedTest(internetTarget(), options),
  internetTest: () => postJson<NetworkProbeResult>("/platform/diagnostics/network/internet", {}),
  databaseTest: () => postJson<NetworkProbeResult>("/platform/diagnostics/network/database", {}),
  logClient: (scenario: "client_portal" | "client_internet", result: SpeedTestResult) =>
    postJson<{ id: string }>("/platform/diagnostics/network/client", {
      scenario, target: result.target, ok: true, latency_ms: result.latency_ms, jitter_ms: result.jitter_ms,
      download_bps: result.download_mbps * 1_000_000, upload_bps: result.upload_mbps * 1_000_000,
      download_bytes: result.download_bytes, upload_bytes: result.upload_bytes,
      details: {
        engine: result.engine, confidence: result.confidence, edge_location: result.edge_location,
        packet_loss_percent: result.packet_loss_percent, loaded_download_latency_ms: result.loaded_download_latency_ms,
        loaded_upload_latency_ms: result.loaded_upload_latency_ms, duration_ms: result.duration_ms,
        download_samples: result.download_samples, upload_samples: result.upload_samples,
      },
    }),
  networkHistory: (window: "24h" | "7d" | "30d", slaDownloadMbps?: number) =>
    getJson<NetworkHistory>(`/platform/diagnostics/network/history?window=${window}${slaDownloadMbps ? `&sla_download_mbps=${slaDownloadMbps}` : ""}`),
};
