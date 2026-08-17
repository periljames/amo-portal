import { getApiBaseUrl } from "./config";
import {
  currentOfflineScope,
  enqueueOfflineMutation,
  newOfflineIdempotencyKey,
  readApiCache,
  writeApiCache,
  type OfflineOutboxEntry,
} from "./offlinePersistence";
import { assertOfflineReplayAllowed, classifyOfflineMutation } from "./offlineCapabilities";
import {
  getPortalConnectivity,
  notePortalNetworkFailure,
  notePortalResponse,
  probePortalReadiness,
  recommendedRequestTimeoutMs,
  waitForPortalReadiness,
} from "./portalConnectivity";
import { isPortalRequestNetworkEligible } from "./portalRequestEligibility";

export type PortalOfflineOptions = {
  cache?: boolean;
  cacheTtlMs?: number;
  allowStaleFallback?: boolean;
  queueMutation?: boolean;
  entityType?: string;
  entityId?: string;
  idempotencyKey?: string;
};

export type PortalFetchInit = RequestInit & {
  timeoutMs?: number;
  offline?: PortalOfflineOptions;
};

export const PROXY_TRANSPORT_ERROR_HEADER = "X-AMO-Proxy-Transport-Error";

export function isProxyTransportFailureResponse(response: Response): boolean {
  return response.headers.get(PROXY_TRANSPORT_ERROR_HEADER) === "1";
}

export class OfflineQueuedError extends Error {
  readonly operation: OfflineOutboxEntry;
  readonly queued = true;

  constructor(operation: OfflineOutboxEntry) {
    super("Saved on this device. It will sync automatically when the server is reachable.");
    this.name = "OfflineQueuedError";
    this.operation = operation;
  }
}

export function isOfflineQueuedError(error: unknown): error is OfflineQueuedError {
  return error instanceof OfflineQueuedError || (
    error instanceof Error && error.name === "OfflineQueuedError" && "operation" in error
  );
}

const DEFAULT_CACHE_TTL_MS = 5 * 60_000;

const SENSITIVE_PATH_PARTS = [
  "/auth/",
  "password",
  "token",
  "/billing",
  "/invoices",
  "/email-logs",
  "/email-settings",
  "/security",
  "/permissions",
  "/diagnostics",
  "/platform/",
  "/attachments/",
  "/download",
  "/export",
  ".pdf",
  ".ics",
  ".xlsx",
  ".csv",
];

function absoluteUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const base = getApiBaseUrl().replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

function normalizedCachePath(path: string): string {
  if (!/^https?:\/\//i.test(path)) return path.startsWith("/") ? path : `/${path}`;
  try {
    const url = new URL(path);
    return `${url.pathname}${url.search}`;
  } catch {
    return path;
  }
}

export function isPortalCacheablePath(path: string): boolean {
  const normalized = normalizedCachePath(path).toLowerCase();
  return !SENSITIVE_PATH_PARTS.some((part) => normalized.includes(part));
}

export function isReplaySafeMutation(path: string, method: string): boolean {
  return classifyOfflineMutation(normalizedCachePath(path), method).capability === "draft-safe";
}

async function confirmedNotAccepted(response: Response): Promise<boolean> {
  if (response.status !== 503) return false;
  const detail = await response.clone().json().catch(() => null) as {
    request_accepted?: unknown;
    error_code?: unknown;
    detail?: { request_accepted?: unknown; error_code?: unknown };
  } | null;
  const body = detail?.detail && typeof detail.detail === "object" ? detail.detail : detail;
  return body?.request_accepted === false
    && ["DB_TEMPORARILY_UNAVAILABLE", "DB_POOL_TIMEOUT"].includes(String(body?.error_code || ""));
}

function networkAvailable(method = "GET"): boolean {
  return isPortalRequestNetworkEligible(
    method,
    getPortalConnectivity().state,
    typeof navigator === "undefined" || navigator.onLine !== false,
  );
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function isNetworkFailure(error: unknown): boolean {
  // AbortError is also used for user cancellation, route teardown, timeouts and
  // the portal-wide session guard. None of those are proof that the device is
  // offline, so silently placing the mutation in the outbox would hide the
  // real failure and can replay an action the user believes was rejected.
  if (isAbortError(error)) return false;
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return message.includes("failed to fetch")
    || message.includes("networkerror")
    || message.includes("network request failed")
    || message.includes("timed out")
    || message.includes("load failed")
    || message.includes("connection");
}

function assertRequestScope(scope: string): void {
  if (currentOfflineScope() !== scope) {
    throw new Error("AMO context changed while the request was in progress. Retry in the active AMO.");
  }
}

function cachedResponse(value: unknown, storedAt: number): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "X-AMO-Portal-Cache": "offline",
      "X-AMO-Portal-Cached-At": new Date(storedAt).toISOString(),
    },
  });
}

async function cachedFallback(path: string, allowExpired: boolean, scope: string): Promise<Response | null> {
  const cached = await readApiCache(path, allowExpired, scope);
  assertRequestScope(scope);
  return cached ? cachedResponse(cached.value, cached.storedAt) : null;
}

function bodyAsString(body: BodyInit | null | undefined): string | undefined {
  if (body == null) return undefined;
  if (typeof body === "string") return body;
  if (body instanceof URLSearchParams) return body.toString();
  return undefined;
}

function canQueueBody(body: BodyInit | null | undefined): boolean {
  return body == null || typeof body === "string" || body instanceof URLSearchParams;
}

async function queueRequest(
  path: string,
  method: string,
  init: PortalFetchInit,
  requestScope: string,
): Promise<never> {
  if (!canQueueBody(init.body)) {
    throw new Error("This file or binary operation cannot be stored offline. Reconnect before retrying.");
  }
  const headers = new Headers(init.headers);
  const idempotencyKey = init.offline?.idempotencyKey
    || headers.get("Idempotency-Key")
    || newOfflineIdempotencyKey(method.toLowerCase());
  headers.set("Idempotency-Key", idempotencyKey);
  const serializedBody = bodyAsString(init.body);
  assertOfflineReplayAllowed(normalizedCachePath(path), method, serializedBody);
  const operation = await enqueueOfflineMutation({
    path: normalizedCachePath(path),
    method,
    headers,
    body: serializedBody,
    entityType: init.offline?.entityType,
    entityId: init.offline?.entityId,
    idempotencyKey,
    scope: requestScope,
  });
  throw new OfflineQueuedError(operation);
}

function combineAbortSignals(controller: AbortController, caller?: AbortSignal | null): () => void {
  if (!caller) return () => undefined;
  const abort = () => controller.abort(caller.reason || new DOMException("Request cancelled", "AbortError"));
  if (caller.aborted) abort();
  else caller.addEventListener("abort", abort, { once: true });
  return () => caller.removeEventListener("abort", abort);
}

export async function portalFetch(path: string, init: PortalFetchInit = {}): Promise<Response> {
  const { timeoutMs, offline, signal, ...requestInit } = init;
  const method = (requestInit.method || "GET").toUpperCase();
  const isGet = method === "GET";
  const cacheEnabled = isGet && offline?.cache !== false && isPortalCacheablePath(path);
  const allowStaleFallback = offline?.allowStaleFallback !== false;
  const queueMutation = !isGet && offline?.queueMutation === true;
  const cachePath = normalizedCachePath(path);
  const requestScope = currentOfflineScope();
  const isAbsoluteTransportAttempt = /^https?:\/\//i.test(path);
  const connectivityState = getPortalConnectivity().state;

  if (connectivityState === "RECOVERING") {
    // Navigation/read requests are never blocked by the control-plane probe.
    // Probe concurrently so the shared status can converge in the background.
    if (isGet) void probePortalReadiness();
    else await waitForPortalReadiness();
  }

  // apiClient's alternate backend is an absolute URL. If the primary route
  // just failed and marked the shared portal state OFFLINE, that direct probe
  // must still be allowed to run; otherwise the fallback is blocked by the
  // very failure it is meant to recover from. Browser-online reads also bypass
  // stale shared OFFLINE state so navigation can recover without a health gate.
  if (!networkAvailable(method) && !isAbsoluteTransportAttempt) {
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
      if (cached) return cached;
    }
    assertRequestScope(requestScope);
    if (queueMutation) return queueRequest(cachePath, method, init, requestScope);
    throw new Error(isGet
      ? "This data has not been cached on this device yet. Reconnect once to make it available offline."
      : "The server is offline. This operation requires a live connection.");
  }

  const controller = new AbortController();
  const detachCallerSignal = combineAbortSignals(controller, signal);
  const effectiveTimeout = timeoutMs ?? recommendedRequestTimeoutMs(method);
  const timeout = globalThis.setTimeout(
    () => controller.abort(new DOMException(`Request timed out after ${Math.round(effectiveTimeout / 1000)} seconds`, "AbortError")),
    effectiveTimeout,
  );

  try {
    const response = await fetch(absoluteUrl(path), { ...requestInit, signal: controller.signal });
    const proxyTransportFailure = isProxyTransportFailureResponse(response);
    // A Vite proxy connection failure is an HTTP-shaped transport error. Do
    // not classify it as a backend response or replace it with stale cache;
    // apiClient needs the marker so it can try the independently configured
    // direct backend exactly once.
    if (!proxyTransportFailure) notePortalResponse(response);
    assertRequestScope(requestScope);
    if (proxyTransportFailure) return response;

    if (response.ok) {
      if (cacheEnabled) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const value = await response.clone().json().catch(() => undefined);
          assertRequestScope(requestScope);
          if (value !== undefined) {
            void writeApiCache(
              cachePath,
              value,
              offline?.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS,
              requestScope,
            );
          }
        }
      }
      return response;
    }

    if (response.status === 408 || response.status === 425 || response.status === 429 || response.status >= 500) {
      if (cacheEnabled) {
        const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
        if (cached) return cached;
      }
    }

    // Queue only when the server explicitly guarantees that it rejected the
    // command before processing. Generic 5xx responses have an ambiguous
    // commit outcome and must remain visible until their receipt is resolved.
    if (queueMutation && await confirmedNotAccepted(response)) {
      return queueRequest(cachePath, method, init, requestScope);
    }

    // An HTTP response proves the server was reached. Validation, permission,
    // rate-limit and server errors must remain visible to the caller; only a
    // confirmed offline state or a genuine transport failure may enter the
    // offline outbox.
    return response;
  } catch (error) {
    if (isAbortError(error)) {
      if (cacheEnabled) {
        const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
        if (cached) return cached;
      }
      throw error;
    }
    if (!isNetworkFailure(error)) throw error;
    notePortalNetworkFailure(error instanceof Error ? error.message : "network-unreachable");
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
      if (cached) return cached;
    }
    assertRequestScope(requestScope);
    if (queueMutation) return queueRequest(cachePath, method, init, requestScope);
    throw new Error(isGet
      ? "The server could not be reached and no cached copy is available."
      : "The server could not be reached. Reconnect and retry this operation.");
  } finally {
    globalThis.clearTimeout(timeout);
    detachCallerSignal();
  }
}
