// src/services/apiClient.ts
import { authHeaders, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

export type ApiClientOptions = RequestInit & {
  timeoutMs?: number;
  cacheTtlMs?: number;
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
  expiresAt: number;
  value: unknown;
};

const DEFAULT_GET_CACHE_TTL_MS = 15_000;
const responseCache = new Map<string, CacheEntry>();
const inFlightGets = new Map<string, Promise<unknown>>();

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function getMethod(options: RequestInit): string {
  return (options.method || "GET").toUpperCase();
}

function buildCacheKey(url: string, method: string, headers: Headers): string {
  const auth = headers.get("Authorization") || "anonymous";
  let tokenMarker = auth;
  if (auth.startsWith("Bearer ")) {
    const token = auth.slice(7);
    tokenMarker = `bearer:${token.slice(0, 12)}:${token.slice(-12)}`;
  }
  return `${method}:${url}:${tokenMarker}`;
}

function clearExpiredCache(now = Date.now()): void {
  for (const [key, entry] of responseCache) {
    if (entry.expiresAt <= now) responseCache.delete(key);
  }
}

export function clearApiResponseCache(): void {
  responseCache.clear();
  inFlightGets.clear();
}

export async function apiRequest<T>(path: string, options: ApiClientOptions = {}): Promise<T> {
  const { timeoutMs = 30000, cacheTtlMs, headers, body, signal, ...rest } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`, "AbortError"));
  }, timeoutMs);

  const abortFromCaller = () => {
    const reason = signal && "reason" in signal ? signal.reason : undefined;
    controller.abort(reason || new DOMException("Request was cancelled", "AbortError"));
  };
  if (signal) {
    if (signal.aborted) abortFromCaller();
    else signal.addEventListener("abort", abortFromCaller, { once: true });
  }

  const finalHeaders = new Headers(authHeaders(headers));
  if (body && !(body instanceof FormData) && !finalHeaders.has("Content-Type")) {
    finalHeaders.set("Content-Type", "application/json");
  }

  const method = getMethod(rest);
  const url = `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const canUseCache = method === "GET" && !body && cacheTtlMs !== 0;
  const effectiveCacheTtlMs = cacheTtlMs ?? DEFAULT_GET_CACHE_TTL_MS;
  const cacheKey = canUseCache ? buildCacheKey(url, method, finalHeaders) : "";

  if (canUseCache) {
    const now = Date.now();
    clearExpiredCache(now);
    const cached = responseCache.get(cacheKey);
    if (cached && cached.expiresAt > now) return cached.value as T;
    const inFlight = inFlightGets.get(cacheKey);
    if (inFlight) return inFlight as Promise<T>;
  }

  const requestPromise = (async () => {
    try {
      const response = await fetch(url, {
        ...rest,
        method,
        body,
        headers: finalHeaders,
        signal: controller.signal,
      });
      const contentType = response.headers.get("content-type") || "";
      const responseBody = contentType.includes("application/json")
        ? await response.json().catch(() => null)
        : await response.text().catch(() => "");

      if (!response.ok) {
        const detail =
          responseBody && typeof responseBody === "object" && "detail" in responseBody
            ? String((responseBody as { detail?: unknown }).detail)
            : response.statusText || "Request failed";
        if (response.status === 401) handleAuthFailure("expired");
        throw new ApiClientError(response.status, detail, responseBody);
      }

      if (canUseCache && effectiveCacheTtlMs > 0) {
        responseCache.set(cacheKey, { expiresAt: Date.now() + effectiveCacheTtlMs, value: responseBody });
      }
      return responseBody as T;
    } catch (error) {
      if (isAbortError(error)) {
        const reason = controller.signal.reason;
        const message = reason instanceof Error ? reason.message : String(reason || "Request timed out or was cancelled");
        throw new Error(timedOut ? "Request timed out. Confirm the backend is reachable, then retry." : message);
      }
      throw error;
    } finally {
      if (canUseCache) inFlightGets.delete(cacheKey);
    }
  })();

  if (canUseCache) inFlightGets.set(cacheKey, requestPromise as Promise<unknown>);

  try {
    return await requestPromise;
  } finally {
    window.clearTimeout(timeout);
    if (signal) signal.removeEventListener("abort", abortFromCaller);
  }
}

export function qmsPath(amoCode: string, suffix = ""): string {
  const safeAmoCode = encodeURIComponent(amoCode);
  const cleanSuffix = suffix.startsWith("/") ? suffix : `/${suffix}`;
  return `/api/maintenance/${safeAmoCode}/qms${suffix ? cleanSuffix : ""}`;
}
