import { getApiBaseUrl } from "./config";
import {
  enqueueOfflineMutation,
  newOfflineIdempotencyKey,
  readApiCache,
  writeApiCache,
  type OfflineOutboxEntry,
} from "./offlinePersistence";

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

const DEFAULT_GET_TIMEOUT_MS = 12_000;
const DEFAULT_WRITE_TIMEOUT_MS = 30_000;
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
  return typeof navigator === "undefined" || navigator.onLine !== false;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function isNetworkFailure(error: unknown): boolean {
  if (isAbortError(error)) return true;
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return message.includes("failed to fetch")
    || message.includes("networkerror")
    || message.includes("network request failed")
    || message.includes("timed out")
    || message.includes("load failed")
    || message.includes("connection");
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

async function cachedFallback(path: string, allowExpired: boolean): Promise<Response | null> {
  const cached = await readApiCache(path, allowExpired);
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

async function queueRequest(path: string, method: string, init: PortalFetchInit): Promise<never> {
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

  if (!networkAvailable()) {
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback);
      if (cached) return cached;
    }
    if (queueMutation) return queueRequest(cachePath, method, init);
    throw new Error(isGet
      ? "This data has not been cached on this device yet. Reconnect once to make it available offline."
      : "The server is offline. This operation requires a live connection.");
  }

  const controller = new AbortController();
  const detachCallerSignal = combineAbortSignals(controller, signal);
  const effectiveTimeout = timeoutMs ?? (isGet ? DEFAULT_GET_TIMEOUT_MS : DEFAULT_WRITE_TIMEOUT_MS);
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException(`Request timed out after ${Math.round(effectiveTimeout / 1000)} seconds`, "AbortError")),
    effectiveTimeout,
  );

  try {
    const response = await fetch(absoluteUrl(path), { ...requestInit, signal: controller.signal });
    if (cacheEnabled && response.ok) {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const value = await response.clone().json().catch(() => undefined);
        if (value !== undefined) {
          void writeApiCache(cachePath, value, offline?.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS);
        }
      }
    }
    return response;
  } catch (error) {
    if (!isNetworkFailure(error)) throw error;
    if (cacheEnabled) {
      const cached = await cachedFallback(cachePath, allowStaleFallback);
      if (cached) return cached;
    }
    if (queueMutation) return queueRequest(cachePath, method, init);
    throw new Error(isGet
      ? "The server could not be reached and no cached copy is available."
      : "The server could not be reached. Reconnect and retry this operation.");
  } finally {
    window.clearTimeout(timeout);
    detachCallerSignal();
  }
}
