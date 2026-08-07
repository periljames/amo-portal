// src/services/apiClient.ts
import {
  authHeaders,
  extendSessionIfNeeded,
  getCachedUser,
  getContext,
  handleAuthFailure,
  markSessionActivity,
} from "./auth";
import { getApiBaseUrl, normaliseBaseUrl } from "./config";
import { portalFetch, type PortalOfflineOptions } from "./offlineHttp";

export type ApiClientOptions = RequestInit & {
  timeoutMs?: number;
  cacheTtlMs?: number;
  persistCache?: boolean;
  staleWhileOfflineMs?: number;
  offline?: PortalOfflineOptions;
};

export class ApiClientError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.body = body;
  }
}

type CacheEntry = {
  scope: string;
  freshUntil: number;
  staleUntil: number;
  value: unknown;
};

type ParsedResponse<T> = {
  response: Response;
  body: T;
};

const DEFAULT_GET_CACHE_TTL_MS = 15_000;
const DEFAULT_STALE_OFFLINE_MS = 15 * 60_000;
const DEFAULT_DIRECT_DEV_BACKEND = "http://127.0.0.1:8080";
const PERSISTED_CACHE_PREFIX = "amo_api_cache_v2:";
const responseCache = new Map<string, CacheEntry>();
const inFlightGets = new Map<string, Promise<unknown>>();
let observedScope = "";

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function getMethod(options: RequestInit): string {
  return (options.method || "GET").toUpperCase();
}

export function currentApiCacheScope(): string {
  const user = getCachedUser();
  const context = getContext();
  const userId = user?.id || "anonymous";
  const amoId = user?.amo_id || "no-amo-id";
  const tenant = (context.amoSlug || context.amoCode || "no-tenant").toLowerCase();
  return `${userId}:${amoId}:${tenant}`;
}

function hashKey(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function persistedKey(cacheKey: string): string {
  return `${PERSISTED_CACHE_PREFIX}${hashKey(cacheKey)}`;
}

function ensureScope(): string {
  const next = currentApiCacheScope();
  if (!observedScope) observedScope = next;
  if (next !== observedScope) {
    responseCache.clear();
    inFlightGets.clear();
    observedScope = next;
  }
  return next;
}

function buildCacheKey(url: string, method: string, headers: Headers, scope: string): string {
  const auth = headers.get("Authorization") || "anonymous";
  let tokenMarker = auth;
  if (auth.startsWith("Bearer ")) {
    const token = auth.slice(7);
    tokenMarker = `bearer:${token.slice(0, 10)}:${token.slice(-10)}`;
  }
  return `${scope}:${method}:${url}:${tokenMarker}`;
}

function clearExpiredCache(now = Date.now()): void {
  for (const [key, entry] of responseCache) {
    if (entry.staleUntil <= now) responseCache.delete(key);
  }
}

function clearPersistedApiCache(): void {
  if (typeof window === "undefined") return;
  for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith(PERSISTED_CACHE_PREFIX)) window.sessionStorage.removeItem(key);
  }
}

export function clearApiResponseCache(): void {
  responseCache.clear();
  inFlightGets.clear();
  clearPersistedApiCache();
  observedScope = currentApiCacheScope();
}

export function clearQmsApiResponseCache(): void {
  clearApiResponseCache();
}

function readPersistedCache(cacheKey: string, scope: string): CacheEntry | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(persistedKey(cacheKey));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as CacheEntry;
    if (parsed.scope !== scope || parsed.staleUntil <= Date.now()) {
      window.sessionStorage.removeItem(persistedKey(cacheKey));
      return null;
    }
    responseCache.set(cacheKey, parsed);
    return parsed;
  } catch {
    window.sessionStorage.removeItem(persistedKey(cacheKey));
    return null;
  }
}

function writePersistedCache(cacheKey: string, entry: CacheEntry): void {
  if (typeof window === "undefined") return;
  try {
    const serialized = JSON.stringify(entry);
    if (serialized.length > 1_000_000) return;
    window.sessionStorage.setItem(persistedKey(cacheKey), serialized);
  } catch {
    // Session storage can be unavailable or full; memory caching remains active.
  }
}

function networkCacheMultiplier(): number {
  if (typeof navigator === "undefined") return 1;
  const connection = (navigator as Navigator & {
    connection?: { effectiveType?: string; saveData?: boolean };
  }).connection;
  if (connection?.saveData) return 4;
  if (connection?.effectiveType === "slow-2g" || connection?.effectiveType === "2g") return 4;
  if (connection?.effectiveType === "3g") return 2;
  return 1;
}

function isLocalDevSurface(): boolean {
  if (typeof window === "undefined") return false;
  const { hostname, port } = window.location;
  return ["localhost", "127.0.0.1"].includes(hostname) && ["5173", "4173"].includes(port);
}

function resolveDirectDevBackend(): string {
  const configured = import.meta.env.VITE_DIRECT_API_BASE_URL || import.meta.env.VITE_API_DIRECT_BASE_URL;
  return normaliseBaseUrl(configured || DEFAULT_DIRECT_DEV_BACKEND);
}

function buildRequestUrls(path: string): string[] {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const configuredBase = getApiBaseUrl();
  const primary = `${configuredBase}${cleanPath}`;
  const direct = `${resolveDirectDevBackend()}${cleanPath}`;
  if (isLocalDevSurface()) return direct === primary ? [primary] : [primary, direct];
  return [primary];
}

async function readResponseBody<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return (await response.json().catch(() => null)) as T;
  return (await response.text().catch(() => "")) as T;
}

function errorMessageFromBody(response: Response, responseBody: unknown): string {
  if (responseBody && typeof responseBody === "object") {
    const body = responseBody as { detail?: unknown; message?: unknown; error?: unknown };
    const detail = body.detail ?? body.message ?? body.error;
    if (typeof detail === "string") return detail;
    if (detail != null) {
      try {
        return JSON.stringify(detail);
      } catch {
        return String(detail);
      }
    }
  }
  if (typeof responseBody === "string" && responseBody.trim()) return responseBody.trim();
  return response.statusText || "Request failed";
}

async function fetchOnce<T>(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  callerSignal: AbortSignal | null | undefined,
  offline: PortalOfflineOptions,
): Promise<ParsedResponse<T>> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`, "AbortError"));
  }, timeoutMs);

  const abortFromCaller = () => {
    const reason = callerSignal && "reason" in callerSignal ? callerSignal.reason : undefined;
    controller.abort(reason || new DOMException("Request was cancelled", "AbortError"));
  };

  if (callerSignal) {
    if (callerSignal.aborted) abortFromCaller();
    else callerSignal.addEventListener("abort", abortFromCaller, { once: true });
  }

  try {
    const response = await portalFetch(url, {
      ...init,
      signal: controller.signal,
      timeoutMs,
      offline,
    });
    const body = await readResponseBody<T>(response);
    return { response, body };
  } catch (error) {
    if (isAbortError(error)) {
      const reason = controller.signal.reason;
      const message = reason instanceof Error ? reason.message : String(reason || "Request timed out or was cancelled");
      throw new Error(timedOut ? "Request timed out. Confirm the backend is reachable, then retry." : message);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    if (callerSignal) callerSignal.removeEventListener("abort", abortFromCaller);
  }
}

function isRetryableNetworkError(error: unknown): boolean {
  if (error instanceof ApiClientError) return error.status >= 500;
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    return message.includes("failed to fetch")
      || message.includes("networkerror")
      || message.includes("request timed out")
      || message.includes("server could not be reached")
      || message.includes("no cached copy is available")
      || message.includes("connection");
  }
  return false;
}

export async function apiRequest<T>(path: string, options: ApiClientOptions = {}): Promise<T> {
  const {
    timeoutMs = 30_000,
    cacheTtlMs,
    persistCache = false,
    staleWhileOfflineMs = DEFAULT_STALE_OFFLINE_MS,
    offline,
    headers,
    body,
    signal,
    ...rest
  } = options;
  const finalHeaders = new Headers(authHeaders(headers));
  if (body && !(body instanceof FormData) && !finalHeaders.has("Content-Type")) finalHeaders.set("Content-Type", "application/json");

  const method = getMethod(rest);
  markSessionActivity(`api:${method.toLowerCase()}:start:${path}`);
  void extendSessionIfNeeded(`api:${method.toLowerCase()}:${path}`)?.catch(() => undefined);

  const scope = ensureScope();
  const urls = buildRequestUrls(path);
  const primaryUrl = urls[0];
  const canUseCache = method === "GET" && !body && cacheTtlMs !== 0;
  const ttlMultiplier = networkCacheMultiplier();
  const effectiveCacheTtlMs = Math.min((cacheTtlMs ?? DEFAULT_GET_CACHE_TTL_MS) * ttlMultiplier, 5 * 60_000);
  const effectiveStaleMs = Math.max(staleWhileOfflineMs, effectiveCacheTtlMs);
  const cacheKey = canUseCache ? buildCacheKey(primaryUrl, method, finalHeaders, scope) : "";
  let staleEntry: CacheEntry | null = null;

  if (canUseCache) {
    const now = Date.now();
    clearExpiredCache(now);
    const cached = responseCache.get(cacheKey) || (persistCache ? readPersistedCache(cacheKey, scope) : null);
    if (cached) {
      if (cached.freshUntil > now) return cached.value as T;
      if (cached.staleUntil > now) staleEntry = cached;
    }
    const inFlight = inFlightGets.get(cacheKey);
    if (inFlight) return inFlight as Promise<T>;
  }

  const requestPromise = (async () => {
    let lastError: unknown;
    for (let index = 0; index < urls.length; index += 1) {
      const url = urls[index];
      try {
        const { response, body: responseBody } = await fetchOnce<T>(
          url,
          { ...rest, method, body, headers: finalHeaders },
          timeoutMs,
          signal,
          {
            cache: canUseCache,
            cacheTtlMs: effectiveCacheTtlMs,
            allowStaleFallback: true,
            queueMutation: offline?.queueMutation === true,
            entityType: offline?.entityType,
            entityId: offline?.entityId,
            idempotencyKey: offline?.idempotencyKey,
          },
        );

        if (!response.ok) {
          const detail = errorMessageFromBody(response, responseBody);
          if (response.status === 401) handleAuthFailure("expired");
          throw new ApiClientError(response.status, detail, responseBody);
        }

        markSessionActivity(`api:${method.toLowerCase()}:ok:${path}`);
        if (canUseCache && effectiveCacheTtlMs > 0) {
          const now = Date.now();
          const entry: CacheEntry = {
            scope,
            freshUntil: now + effectiveCacheTtlMs,
            staleUntil: now + effectiveStaleMs,
            value: responseBody,
          };
          responseCache.set(cacheKey, entry);
          if (persistCache) writePersistedCache(cacheKey, entry);
        } else if (method !== "GET") {
          clearApiResponseCache();
        }
        return responseBody as T;
      } catch (error) {
        lastError = error;
        const canTryNext = index < urls.length - 1 && isRetryableNetworkError(error) && !signal?.aborted;
        if (canTryNext) {
          console.warn("[apiClient] primary request failed; retrying alternate backend route", { path, error });
          continue;
        }
        if (staleEntry && isRetryableNetworkError(error) && staleEntry.scope === currentApiCacheScope()) {
          console.warn("[apiClient] serving tenant-scoped stale response after network failure", { path, error });
          return staleEntry.value as T;
        }
        throw error;
      }
    }
    if (staleEntry && staleEntry.scope === currentApiCacheScope()) return staleEntry.value as T;
    throw lastError instanceof Error ? lastError : new Error("Request failed.");
  })().finally(() => {
    if (canUseCache) inFlightGets.delete(cacheKey);
  });

  if (canUseCache) inFlightGets.set(cacheKey, requestPromise as Promise<unknown>);
  return requestPromise;
}

export function qualityPath(amoCode: string, suffix = ""): string {
  const safeAmoCode = encodeURIComponent(amoCode);
  const cleanSuffix = suffix.startsWith("/") ? suffix : `/${suffix}`;
  return `/api/maintenance/${safeAmoCode}/quality${suffix ? cleanSuffix : ""}`;
}

export function qmsPath(amoCode: string, suffix = ""): string {
  return qualityPath(amoCode, suffix);
}
