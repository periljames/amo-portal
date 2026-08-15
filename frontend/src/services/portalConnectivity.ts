import { getApiBaseUrl } from "./config";

export type PortalConnectivityState = "checking" | "online" | "degraded" | "offline" | "recovering";

export type PortalConnectivitySnapshot = {
  state: PortalConnectivityState;
  browserOnline: boolean;
  apiReachable: boolean;
  databaseReady: boolean;
  checkedAt: number | null;
  lastReadyAt: number | null;
  outageStartedAt: number | null;
  latencyMs: number | null;
  retryAfterSeconds: number;
  reason: string | null;
};

type ConnectionHint = {
  effectiveType?: string;
  saveData?: boolean;
  downlink?: number;
};

const CONNECTIVITY_EVENT = "amo:portal-connectivity";
const CONNECTIVITY_CHANNEL = "amo:portal-connectivity-v1";
const LAST_READY_KEY = "amo_portal_last_ready_at";
const listeners = new Set<(snapshot: PortalConnectivitySnapshot) => void>();
let broadcastChannel: BroadcastChannel | null = null;
let monitorTimer: number | null = null;
let monitorRunning = false;
let probeInFlight: Promise<PortalConnectivitySnapshot> | null = null;
let failureCount = 0;
let readinessPath = "/readyz";

const readinessRequestInit = (signal: AbortSignal): RequestInit => ({
  method: "GET",
  cache: "no-store",
  credentials: "include",
  headers: { Accept: "application/json", "X-AMO-Silent-Error": "1" },
  signal,
});

function isJsonResponse(response: Response): boolean {
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  return contentType.includes("application/json") || contentType.includes("+json");
}

async function requestReadiness(signal: AbortSignal): Promise<Response> {
  const base = getApiBaseUrl().replace(/\/$/, "");
  const response = await fetch(`${base}${readinessPath}`, readinessRequestInit(signal));

  // Older reverse-proxy allow-lists route /healthz but send the newer /readyz
  // probe to the SPA. Fall back once, then retain the working path so a legacy
  // deployment does not emit a 404 on every monitoring cycle.
  if (readinessPath === "/readyz" && (response.status === 404 || !isJsonResponse(response))) {
    const fallback = await fetch(`${base}/healthz`, readinessRequestInit(signal));
    if (fallback.status !== 404 && isJsonResponse(fallback)) readinessPath = "/healthz";
    return fallback;
  }
  return response;
}

function storedLastReadyAt(): number | null {
  try {
    if (typeof localStorage === "undefined") return null;
    const value = Number(localStorage.getItem(LAST_READY_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

let snapshot: PortalConnectivitySnapshot = {
  state: "checking",
  browserOnline: typeof navigator === "undefined" ? true : navigator.onLine,
  apiReachable: false,
  databaseReady: false,
  checkedAt: null,
  lastReadyAt: storedLastReadyAt(),
  outageStartedAt: null,
  latencyMs: null,
  retryAfterSeconds: 0,
  reason: "Checking portal availability",
};

function connectionHint(): ConnectionHint {
  if (typeof navigator === "undefined") return {};
  return ((navigator as Navigator & { connection?: ConnectionHint }).connection || {});
}

export function recommendedRequestTimeoutMs(method = "GET"): number {
  const write = method.toUpperCase() !== "GET";
  const hint = connectionHint();
  if (hint.effectiveType === "slow-2g" || hint.effectiveType === "2g") return write ? 90_000 : 45_000;
  if (hint.effectiveType === "3g" || hint.saveData) return write ? 60_000 : 30_000;
  return write ? 30_000 : 12_000;
}

function channel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return null;
  if (broadcastChannel) return broadcastChannel;
  broadcastChannel = new BroadcastChannel(CONNECTIVITY_CHANNEL);
  broadcastChannel.onmessage = (event: MessageEvent<PortalConnectivitySnapshot>) => {
    const incoming = event.data;
    if (!incoming?.state || (incoming.checkedAt || 0) < (snapshot.checkedAt || 0)) return;
    snapshot = incoming;
    listeners.forEach((listener) => listener(snapshot));
    window.dispatchEvent(new CustomEvent(CONNECTIVITY_EVENT, { detail: snapshot }));
  };
  return broadcastChannel;
}

function publish(next: PortalConnectivitySnapshot, broadcast = true): PortalConnectivitySnapshot {
  snapshot = next;
  try {
    if (next.lastReadyAt && typeof localStorage !== "undefined") {
      localStorage.setItem(LAST_READY_KEY, String(next.lastReadyAt));
    }
  } catch {
    // Availability monitoring must not fail when browser storage is disabled.
  }
  listeners.forEach((listener) => listener(snapshot));
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CONNECTIVITY_EVENT, { detail: snapshot }));
    if (broadcast) channel()?.postMessage(snapshot);
  }
  return snapshot;
}

function nextState(partial: Partial<PortalConnectivitySnapshot>): PortalConnectivitySnapshot {
  const now = Date.now();
  const state = partial.state || snapshot.state;
  const available = state === "online";
  return {
    ...snapshot,
    ...partial,
    state,
    checkedAt: partial.checkedAt ?? now,
    lastReadyAt: available ? now : snapshot.lastReadyAt,
    outageStartedAt: available ? null : (snapshot.outageStartedAt || now),
  };
}

export function getPortalConnectivitySnapshot(): PortalConnectivitySnapshot {
  return snapshot;
}

export function isPortalReady(): boolean {
  return snapshot.state === "online" && snapshot.databaseReady;
}

export function subscribePortalConnectivity(
  listener: (value: PortalConnectivitySnapshot) => void,
  emitCurrent = true,
): () => void {
  listeners.add(listener);
  channel();
  if (emitCurrent) listener(snapshot);
  return () => listeners.delete(listener);
}

function parseRetryAfter(response: Response): number {
  const value = Number(response.headers.get("Retry-After"));
  return Number.isFinite(value) && value > 0 ? Math.min(300, Math.ceil(value)) : 0;
}

function scheduleNext(): void {
  if (!monitorRunning || typeof window === "undefined") return;
  if (monitorTimer !== null) window.clearTimeout(monitorTimer);
  const visible = typeof document === "undefined" || document.visibilityState === "visible";
  const delay = isPortalReady()
    ? (visible ? 30_000 : 90_000)
    : Math.max(
      snapshot.retryAfterSeconds * 1000,
      Math.min(visible ? 15_000 : 60_000, 1_500 * (2 ** Math.min(failureCount, 4))),
    );
  monitorTimer = window.setTimeout(() => void probePortalConnectivity("scheduled"), Math.max(1_000, delay));
}

export async function probePortalConnectivity(reason = "manual"): Promise<PortalConnectivitySnapshot> {
  if (probeInFlight) return probeInFlight;
  probeInFlight = (async () => {
    const browserOnline = typeof navigator === "undefined" ? true : navigator.onLine;
    if (!browserOnline) {
      failureCount += 1;
      return publish(nextState({
        state: "offline",
        browserOnline: false,
        apiReachable: false,
        databaseReady: false,
        latencyMs: null,
        retryAfterSeconds: 2,
        reason: "Device network unavailable",
      }));
    }

    const controller = new AbortController();
    const started = performance.now();
    const timeout = window.setTimeout(
      () => controller.abort(new DOMException("Readiness probe timed out", "AbortError")),
      Math.min(15_000, recommendedRequestTimeoutMs("GET")),
    );
    try {
      if (snapshot.state !== "checking" && snapshot.state !== "online") {
        publish(nextState({ state: "recovering", browserOnline: true, reason: "Checking server recovery" }));
      }
      const response = await requestReadiness(controller.signal);
      const latencyMs = Math.max(0, Math.round(performance.now() - started));
      const body = await response.clone().json().catch(() => ({})) as {
        ready?: boolean;
        status?: string;
        db?: boolean;
        error_code?: string;
        migrations?: { ready?: boolean; detail?: string | null };
      };
      if (response.ok && body.ready !== false && body.db !== false) {
        failureCount = 0;
        return publish(nextState({
          state: "online",
          browserOnline: true,
          apiReachable: true,
          databaseReady: true,
          latencyMs,
          retryAfterSeconds: 0,
          reason: null,
        }));
      }
      failureCount += 1;
      return publish(nextState({
        state: "degraded",
        browserOnline: true,
        apiReachable: true,
        databaseReady: false,
        latencyMs,
        retryAfterSeconds: parseRetryAfter(response),
        reason: body.db === false
          ? "Server reachable; database recovery in progress"
          : body.migrations?.ready === false
            ? body.migrations.detail || "Server upgrade in progress"
            : body.status === "degraded"
              ? "Server reachable; required services are recovering"
              : `Server not ready (${response.status})`,
      }));
    } catch (error) {
      failureCount += 1;
      return publish(nextState({
        state: "offline",
        browserOnline: true,
        apiReachable: false,
        databaseReady: false,
        latencyMs: null,
        retryAfterSeconds: 0,
        reason: error instanceof Error ? error.message : `Portal unavailable (${reason})`,
      }));
    } finally {
      window.clearTimeout(timeout);
    }
  })();

  try {
    return await probeInFlight;
  } finally {
    probeInFlight = null;
    scheduleNext();
  }
}

export function notePortalResponse(response: Response): void {
  const readiness = response.headers.get("X-Portal-Readiness");
  // Only the readiness endpoint is allowed to promote global availability.
  // A successful lightweight/read-only request does not prove that migrations,
  // workers and the writer database are all ready for authoritative actions.
  if (response.ok && readiness === "ready") {
    failureCount = 0;
    if (isPortalReady()) return;
    publish(nextState({
      state: "online",
      browserOnline: true,
      apiReachable: true,
      databaseReady: true,
      retryAfterSeconds: 0,
      reason: null,
    }));
    return;
  }
  if (readiness === "degraded" || readiness === "offline" || response.status === 503) {
    failureCount += 1;
    if (snapshot.state === "degraded" && !snapshot.databaseReady) return;
    publish(nextState({
      state: "degraded",
      browserOnline: true,
      apiReachable: true,
      databaseReady: false,
      retryAfterSeconds: parseRetryAfter(response),
      reason: "Server reachable; authoritative services unavailable",
    }));
  }
}

export function notePortalTransportFailure(error: unknown): void {
  failureCount += 1;
  publish(nextState({
    state: "offline",
    browserOnline: typeof navigator === "undefined" ? true : navigator.onLine,
    apiReachable: false,
    databaseReady: false,
    latencyMs: null,
    retryAfterSeconds: 0,
    reason: error instanceof Error ? error.message : "Portal connection interrupted",
  }));
  scheduleNext();
}

export function startPortalConnectivityMonitor(): () => void {
  if (monitorRunning || typeof window === "undefined") return () => undefined;
  monitorRunning = true;
  const wake = () => void probePortalConnectivity("browser-event");
  const visible = () => {
    if (document.visibilityState === "visible") wake();
  };
  window.addEventListener("online", wake);
  window.addEventListener("offline", wake);
  window.addEventListener("focus", wake);
  window.addEventListener("pageshow", wake);
  document.addEventListener("visibilitychange", visible);
  void probePortalConnectivity("startup");
  return () => {
    monitorRunning = false;
    if (monitorTimer !== null) window.clearTimeout(monitorTimer);
    monitorTimer = null;
    window.removeEventListener("online", wake);
    window.removeEventListener("offline", wake);
    window.removeEventListener("focus", wake);
    window.removeEventListener("pageshow", wake);
    document.removeEventListener("visibilitychange", visible);
  };
}
