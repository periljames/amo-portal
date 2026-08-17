import { getApiBaseUrl } from "./config";

export type PortalConnectivityState =
  | "ONLINE"
  | "DEGRADED"
  | "OFFLINE"
  | "RECOVERING"
  | "SESSION_EXPIRED";

export type PortalConnectivitySnapshot = {
  state: PortalConnectivityState;
  changedAt: number;
  checkedAt: number | null;
  lastReadyAt: number | null;
  retryAt: number | null;
  attempt: number;
  reason: string | null;
};

const EVENT_NAME = "amo:portal-connectivity";
const CHANNEL_NAME = "amo:portal-connectivity-v1";
const LEADER_KEY = "amo_portal_connectivity_leader_v1";
// Longer than the healthy probe interval so another tab cannot take over
// between successful probes and create duplicate liveness traffic.
const LEADER_TTL_MS = 45_000;
const HEALTHY_PROBE_MS = 30_000;
const CONNECTIVITY_PROBE_TIMEOUT_MS = 1_500;
const BACKOFF_MS = [2_000, 5_000, 10_000, 20_000, 40_000, 60_000];
const tabId = typeof crypto !== "undefined" && "randomUUID" in crypto
  ? crypto.randomUUID()
  : `${Date.now()}-${Math.random()}`;

let snapshot: PortalConnectivitySnapshot = {
  state: typeof navigator !== "undefined" && navigator.onLine === false ? "OFFLINE" : "RECOVERING",
  changedAt: Date.now(),
  checkedAt: null,
  lastReadyAt: null,
  retryAt: null,
  attempt: 0,
  reason: null,
};
let channel: BroadcastChannel | null = null;
let timer: number | null = null;
let started = false;
let probeInFlight: Promise<PortalConnectivitySnapshot> | null = null;

type ConnectionHint = { effectiveType?: string; saveData?: boolean };

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

function apiUrl(path: string): string {
  const base = getApiBaseUrl().replace(/\/$/, "");
  return `${base}${path}`;
}

function broadcast(next: PortalConnectivitySnapshot): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<PortalConnectivitySnapshot>(EVENT_NAME, { detail: next }));
  channel?.postMessage({ type: "snapshot", snapshot: next });
}

function update(
  state: PortalConnectivityState,
  patch: Partial<PortalConnectivitySnapshot> = {},
  shouldBroadcast = true,
): PortalConnectivitySnapshot {
  const now = Date.now();
  snapshot = {
    ...snapshot,
    ...patch,
    state,
    changedAt: state === snapshot.state ? snapshot.changedAt : now,
  };
  if (shouldBroadcast) broadcast(snapshot);
  return snapshot;
}

function jitter(delay: number): number {
  return Math.max(500, Math.round(delay * (0.85 + Math.random() * 0.3)));
}

function nextDelay(): number {
  if (snapshot.state === "ONLINE") return HEALTHY_PROBE_MS;
  const index = Math.min(snapshot.attempt, BACKOFF_MS.length - 1);
  return jitter(BACKOFF_MS[index]);
}

function readLeader(): { id: string; expiresAt: number } | null {
  try {
    const value = JSON.parse(localStorage.getItem(LEADER_KEY) || "null") as { id?: unknown; expiresAt?: unknown } | null;
    if (!value || typeof value.id !== "string" || typeof value.expiresAt !== "number") return null;
    return { id: value.id, expiresAt: value.expiresAt };
  } catch {
    return null;
  }
}

function claimLeadership(force = false): boolean {
  if (typeof window === "undefined") return true;
  const now = Date.now();
  const current = readLeader();
  if (!force && current && current.id !== tabId && current.expiresAt > now) return false;
  try {
    localStorage.setItem(LEADER_KEY, JSON.stringify({ id: tabId, expiresAt: now + LEADER_TTL_MS }));
    return readLeader()?.id === tabId;
  } catch {
    return true;
  }
}

function schedule(delay = nextDelay()): void {
  if (typeof window === "undefined") return;
  if (timer !== null) window.clearTimeout(timer);
  snapshot = { ...snapshot, retryAt: Date.now() + delay };
  timer = window.setTimeout(() => void probePortalReadiness(), delay);
}

function retryAfterMs(response: Response): number | null {
  const raw = response.headers.get("Retry-After")?.trim();
  if (!raw) return null;
  const seconds = Number(raw);
  if (Number.isFinite(seconds)) return Math.max(1_000, seconds * 1_000);
  const date = Date.parse(raw);
  return Number.isFinite(date) ? Math.max(1_000, date - Date.now()) : null;
}

async function parseReadyResponse(response: Response): Promise<{ ready: boolean; degraded: boolean; reason: string | null }> {
  const body = await response.clone().json().catch(() => null) as Record<string, unknown> | null;
  const ready = response.ok && body?.ready !== false && body?.status !== "degraded";
  const degraded = response.status === 503 || body?.status === "degraded" || body?.ready === false;
  const reason = typeof body?.error_code === "string"
    ? body.error_code
    : typeof body?.detail === "string"
      ? body.detail
      : response.ok ? null : `HTTP ${response.status}`;
  return { ready, degraded, reason };
}

async function requestConnectivityProbe(): Promise<{ response: Response; legacy: boolean }> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(
    () => controller.abort(new DOMException("Connectivity probe timed out", "AbortError")),
    CONNECTIVITY_PROBE_TIMEOUT_MS,
  );
  const init: RequestInit = {
    method: "GET",
    cache: "no-store",
    credentials: "include",
    headers: { Accept: "application/json", "X-AMO-Silent-Error": "1" },
    signal: controller.signal,
  };
  try {
    const response = await fetch(apiUrl("/livez"), init);
    if (response.status !== 404) return { response, legacy: false };
    // Older instances may not expose /livez yet. /health is process-only and
    // avoids the PostgreSQL/migration work performed by /readyz and /healthz.
    return { response: await fetch(apiUrl("/health"), init), legacy: true };
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function getPortalConnectivity(): PortalConnectivitySnapshot {
  return snapshot;
}

export function isPortalReady(): boolean {
  return snapshot.state === "ONLINE";
}

/**
 * Protected writes may wait briefly for recovery before deciding whether they
 * can run. Ordinary reads never call this path. If another tab owns a stale
 * leader lease, force a local lightweight liveness probe rather than waiting
 * for that lease to expire.
 */
export async function waitForPortalReadiness(timeoutMs = 2_000): Promise<PortalConnectivitySnapshot> {
  if (snapshot.state !== "RECOVERING") return snapshot;
  const probed = await probePortalReadiness();
  if (probed.state !== "RECOVERING" || typeof window === "undefined") return probed;
  const forced = await probePortalReadiness(true);
  if (forced.state !== "RECOVERING") return forced;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: PortalConnectivitySnapshot) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      window.removeEventListener(EVENT_NAME, listener);
      resolve(value);
    };
    const listener = (event: Event) => {
      const value = (event as CustomEvent<PortalConnectivitySnapshot>).detail;
      if (value.state !== "RECOVERING") finish(value);
    };
    const timeout = window.setTimeout(() => finish(snapshot), Math.max(500, timeoutMs));
    window.addEventListener(EVENT_NAME, listener);
  });
}

export function onPortalConnectivityChange(
  listener: (value: PortalConnectivitySnapshot) => void,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = (event: Event) => listener((event as CustomEvent<PortalConnectivitySnapshot>).detail);
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}

export function markPortalSessionExpired(reason = "session-expired"): void {
  const changed = snapshot.state !== "SESSION_EXPIRED" || snapshot.reason !== reason;
  update("SESSION_EXPIRED", { reason, retryAt: null }, changed);
  if (typeof window !== "undefined" && timer !== null) window.clearTimeout(timer);
}

export function notePortalResponse(response: Response): void {
  if (response.status === 503) {
    const delay = retryAfterMs(response) ?? nextDelay();
    const reason = response.headers.get("X-Error-Code") || "SERVICE_UNAVAILABLE";
    const changed = snapshot.state !== "DEGRADED" || snapshot.reason !== reason;
    update("DEGRADED", {
      checkedAt: Date.now(),
      attempt: Math.min(snapshot.attempt + 1, BACKOFF_MS.length - 1),
      reason,
      retryAt: Date.now() + delay,
    }, changed);
    schedule(delay);
    return;
  }
  if (response.ok && snapshot.state !== "SESSION_EXPIRED") {
    const now = Date.now();
    const changed = snapshot.state !== "ONLINE" || snapshot.reason !== null;
    update("ONLINE", {
      checkedAt: now,
      lastReadyAt: now,
      attempt: 0,
      reason: null,
    }, changed);
  }
}

export function notePortalNetworkFailure(reason = "network-unreachable"): void {
  const changed = snapshot.state !== "OFFLINE" || snapshot.reason !== reason;
  update("OFFLINE", {
    checkedAt: Date.now(),
    attempt: Math.min(snapshot.attempt + 1, BACKOFF_MS.length - 1),
    reason,
  }, changed);
  schedule();
}

export function probePortalReadiness(force = false): Promise<PortalConnectivitySnapshot> {
  if (probeInFlight) return probeInFlight;
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    const changed = snapshot.state !== "OFFLINE" || snapshot.reason !== "device-offline";
    const next = update("OFFLINE", { checkedAt: Date.now(), reason: "device-offline" }, changed);
    schedule();
    return Promise.resolve(next);
  }
  if (!claimLeadership(force)) {
    schedule(LEADER_TTL_MS + jitter(1_000));
    return Promise.resolve(snapshot);
  }

  // A routine liveness probe while already online is an observation, not a
  // connectivity transition. Keeping ONLINE here prevents each probe from
  // manufacturing RECOVERING -> ONLINE events that can trigger subscribers to
  // refetch and create request/revalidation feedback loops.
  if (snapshot.state !== "ONLINE") {
    update("RECOVERING", { reason: snapshot.reason }, false);
  }
  probeInFlight = (async () => {
    try {
      const { response, legacy } = await requestConnectivityProbe();
      const parsed = await parseReadyResponse(response);
      const now = Date.now();
      if (parsed.ready) {
        const reason = legacy ? "legacy-health-compatible" : null;
        const changed = snapshot.state !== "ONLINE" || snapshot.reason !== reason;
        const next = update("ONLINE", {
          checkedAt: now,
          lastReadyAt: now,
          attempt: 0,
          retryAt: now + HEALTHY_PROBE_MS,
          reason,
        }, changed);
        schedule(HEALTHY_PROBE_MS);
        return next;
      }
      const delay = retryAfterMs(response) ?? nextDelay();
      const state = parsed.degraded ? "DEGRADED" : "OFFLINE";
      const changed = snapshot.state !== state || snapshot.reason !== parsed.reason;
      const next = update(state, {
        checkedAt: now,
        attempt: Math.min(snapshot.attempt + 1, BACKOFF_MS.length - 1),
        retryAt: now + delay,
        reason: parsed.reason,
      }, changed);
      schedule(delay);
      return next;
    } catch (error) {
      notePortalNetworkFailure(error instanceof Error ? error.message : "network-unreachable");
      return snapshot;
    } finally {
      probeInFlight = null;
    }
  })();
  return probeInFlight;
}

export function startPortalConnectivity(): () => void {
  if (typeof window === "undefined" || started) return () => undefined;
  started = true;
  if (typeof BroadcastChannel !== "undefined") {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event: MessageEvent<{ type?: string; snapshot?: PortalConnectivitySnapshot }>) => {
      if (event.data?.type !== "snapshot" || !event.data.snapshot) return;
      const incoming = event.data.snapshot;
      if (incoming.checkedAt && (!snapshot.checkedAt || incoming.checkedAt >= snapshot.checkedAt)) {
        const changed = incoming.state !== snapshot.state || incoming.reason !== snapshot.reason;
        snapshot = incoming;
        if (changed) window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: snapshot }));
      }
    };
  }
  const recover = () => {
    update("RECOVERING", { reason: "connectivity-change" });
    void probePortalReadiness();
  };
  const offline = () => notePortalNetworkFailure("device-offline");
  const focus = () => void probePortalReadiness(true);
  const visibility = () => {
    if (document.visibilityState === "visible") void probePortalReadiness(true);
  };
  window.addEventListener("online", recover);
  window.addEventListener("offline", offline);
  window.addEventListener("focus", focus);
  document.addEventListener("visibilitychange", visibility);
  void probePortalReadiness();
  return () => {
    started = false;
    if (timer !== null) window.clearTimeout(timer);
    window.removeEventListener("online", recover);
    window.removeEventListener("offline", offline);
    window.removeEventListener("focus", focus);
    document.removeEventListener("visibilitychange", visibility);
    channel?.close();
    channel = null;
  };
}
