import { getApiBaseUrl } from "./config";
import {
  currentOfflineScope,
  enqueueOfflineMutation,
  newOfflineIdempotencyKey,
  readApiCache,
  writeApiCache,
  type OfflineOutboxEntry,
} from "./offlinePersistence";
import {
  getPortalConnectivitySnapshot,
  notePortalResponse,
  notePortalTransportFailure,
  recommendedRequestTimeoutMs,
} from "./portalConnectivity";

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

function networkAvailable(): boolean {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return false;
  const connectivity = getPortalConnectivitySnapshot();
  return connectivity.state === "online" && connectivity.databaseReady;
}

const AUTHORITATIVE_PATH_MARKERS = [
  "/approve",
  "/reject",
  "/submit",
  "/publish",
  "/certify",
  "/sign-off",
  "/signoff",
  "/payroll",
  "/permissions",
  "/authorisations",
  "/authorizations",
  "/upload",
  "/attachments",
];

export function isReplaySafeMutation(path: string, method: string): boolean {
  const normalizedMethod = method.toUpperCase();
  if (normalizedMethod === "DELETE") return false;
  if (!["POST", "PUT", "PATCH"].includes(normalizedMethod)) return false;
  const normalizedPath = normalizedCachePath(path).toLowerCase();
  return !AUTHORITATIVE_PATH_MARKERS.some((marker) => normalizedPath.includes(marker));
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
  const operation = await enqueueOfflineMutation({
    path: normalizedCachePath(path),
    method,
    headers,
    body: bodyAsString(init.body),
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
  const replaySafe = isGet || isReplaySafeMutation(path, method);
  const cachePath = normalizedCachePath(path);
  const requestScope = currentOfflineScope();

  if (!networkAvailable()) {
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
      if (cached) return cached;
    }
    assertRequestScope(requestScope);
    if (queueMutation && replaySafe) return queueRequest(cachePath, method, init, requestScope);
    throw new Error(isGet
      ? "This data has not been cached on this device yet. Reconnect once to make it available offline."
      : "The server is offline. This operation requires a live connection.");
  }

  const controller = new AbortController();
  const detachCallerSignal = combineAbortSignals(controller, signal);
  const effectiveTimeout = timeoutMs ?? recommendedRequestTimeoutMs(method);
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException(`Request timed out after ${Math.round(effectiveTimeout / 1000)} seconds`, "AbortError")),
    effectiveTimeout,
  );

  try {
    const response = await fetch(absoluteUrl(path), { ...requestInit, signal: controller.signal });
    notePortalResponse(response);
    assertRequestScope(requestScope);

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

    // Only a server response that explicitly guarantees the transaction was
    // not accepted may be moved to the local outbox.  Generic 5xx responses
    // remain visible because the server may have committed before failing.
    if (queueMutation && replaySafe && await confirmedNotAccepted(response)) {
      return queueRequest(cachePath, method, init, requestScope);
    }

    // An HTTP response proves the server was reached. Validation, permission,
    // rate-limit and server errors must remain visible to the caller; only a
    // confirmed offline state or a genuine transport failure may enter the
    // offline outbox.
    return response;
  } catch (error) {
    if (isAbortError(error)) {
      // GET has no ambiguous commit outcome, so a slow-link timeout may safely
      // fall back to the last encrypted device copy. Writes remain visible to
      // the user because the server may have committed before the timeout.
      if (cacheEnabled) {
        const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
        if (cached) return cached;
      }
      throw error;
    }
    if (!isNetworkFailure(error)) throw error;
    notePortalTransportFailure(error);
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback, requestScope);
      if (cached) return cached;
    }
    assertRequestScope(requestScope);
    if (queueMutation && replaySafe) return queueRequest(cachePath, method, init, requestScope);
    throw new Error(isGet
      ? "The server could not be reached and no cached copy is available."
      : "The server could not be reached. Reconnect and retry this operation.");
  } finally {
    window.clearTimeout(timeout);
    detachCallerSignal();
  }
}
