// src/services/crs.ts
// Generic HTTP helpers used across the portal. JSON reads are persisted in the
// user/tenant offline cache. Only explicitly marked idempotent/version-aware
// mutations may enter the replay outbox.

import type { CRSCreate, CRSRead, CRSPrefill } from "../types/crs";
import { authHeaders, handleAuthFailure, markSessionActivity, extendSessionIfNeeded } from "./auth";
import { getApiBaseUrl } from "./config";
import { beginBackgroundLoading, beginLoading, endBackgroundLoading, endLoading } from "./loading";
import { portalFetch, type PortalOfflineOptions } from "./offlineHttp";

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type AppRequestInit = RequestInit & {
  silent?: boolean;
  suppressAuthLogout?: boolean;
  offline?: PortalOfflineOptions;
};

function buildJsonMisrouteHint(url: string, contentType: string): string {
  if (!contentType.toLowerCase().includes("text/html")) {
    return `Expected JSON from ${url}, but got ${contentType || "unknown"}`;
  }
  return [
    `Expected JSON from ${url}, but received HTML (${contentType || "unknown"}).`,
    "This usually means the request was sent to the Vite dev server instead of the API backend.",
    "Check VITE_API_BASE_URL and Vite proxy route patterns.",
  ].join(" ");
}

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: BodyInit,
  init: AppRequestInit = {},
  loadingMode?: "foreground" | "background",
): Promise<T> {
  const { silent: silentRequest, suppressAuthLogout, offline, ...fetchInit } = init;
  const mode = loadingMode ?? (method === "GET" || silentRequest ? "background" : "foreground");
  if (mode === "background") beginBackgroundLoading();
  else beginLoading();

  try {
    markSessionActivity(`api:${method.toLowerCase()}:start:${path}`);
    void extendSessionIfNeeded(`api:${method.toLowerCase()}:${path}`)?.catch(() => undefined);
    const res = await portalFetch(path, {
      method,
      body,
      ...fetchInit,
      timeoutMs: method === "GET" ? 12_000 : 45_000,
      offline: {
        cache: method === "GET",
        cacheTtlMs: offline?.cacheTtlMs ?? 5 * 60_000,
        allowStaleFallback: offline?.allowStaleFallback ?? true,
        queueMutation: offline?.queueMutation === true,
        entityType: offline?.entityType,
        entityId: offline?.entityId,
        idempotencyKey: offline?.idempotencyKey,
      },
    });

    if (res.status === 401) {
      const shouldSuppressAuthLogout = Boolean(suppressAuthLogout) || path.startsWith("/training/");
      if (!shouldSuppressAuthLogout) handleAuthFailure("expired");
      throw new Error("Session expired or this training endpoint is not authorised. Please refresh your session if this continues.");
    }

    if (!res.ok) {
      const contentType = res.headers.get("Content-Type") || "";
      const text = await res.text();
      let parsedBody: unknown = null;
      let message: string = text || `HTTP ${res.status}`;
      if (contentType.toLowerCase().includes("application/json")) {
        try {
          parsedBody = JSON.parse(text) as unknown;
          const record = parsedBody && typeof parsedBody === "object" ? parsedBody as Record<string, unknown> : {};
          const detail = record.detail;
          if (typeof detail === "string") {
            message = detail;
          } else if (detail && typeof detail === "object") {
            const detailRecord = detail as Record<string, unknown>;
            message = String(detailRecord.message || detailRecord.code || record.message || `HTTP ${res.status}`);
          } else {
            message = String(record.message || message);
          }
        } catch {
          // Keep raw text fallback.
        }
      }
      console.error(`API ${method} ${path} failed:`, res.status, contentType, text.slice(0, 300));
      const error = new Error(message || `HTTP ${res.status}`) as Error & { status?: number; detail?: unknown; responseBody?: unknown };
      error.status = res.status;
      error.detail = parsedBody && typeof parsedBody === "object" ? (parsedBody as Record<string, unknown>).detail : undefined;
      error.responseBody = parsedBody;
      throw error;
    }

    markSessionActivity(`api:${method.toLowerCase()}:ok:${path}`);

    if (res.status === 204 || res.status === 205) return null as T;

    const contentType = res.headers.get("Content-Type") || "";
    if (!contentType.includes("application/json")) {
      const text = await res.text();
      console.error(`API ${method} ${path} returned non-JSON success response:`, contentType, text.slice(0, 300));
      throw new Error(buildJsonMisrouteHint(path, contentType));
    }

    return (await res.json()) as T;
  } finally {
    if (mode === "background") endBackgroundLoading();
    else endLoading();
  }
}

export async function apiPost<T>(path: string, body?: unknown, init: AppRequestInit = {}): Promise<T> {
  let bodyInit: BodyInit | undefined;
  if (body === undefined || body === null) bodyInit = undefined;
  else if (typeof body === "string" || body instanceof FormData) bodyInit = body;
  else bodyInit = JSON.stringify(body);

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return request<T>("POST", path, bodyInit, { ...init, headers });
}

export async function apiPut<T>(path: string, body?: unknown, init: AppRequestInit = {}): Promise<T> {
  let bodyInit: BodyInit | undefined;
  if (body === undefined || body === null) bodyInit = undefined;
  else if (typeof body === "string" || body instanceof FormData) bodyInit = body;
  else bodyInit = JSON.stringify(body);

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return request<T>("PUT", path, bodyInit, { ...init, headers });
}

export async function apiGet<T>(path: string, init: AppRequestInit = {}): Promise<T> {
  return request<T>("GET", path, undefined, init);
}

export async function apiPatch<T>(path: string, body?: unknown, init: AppRequestInit = {}): Promise<T> {
  let bodyInit: BodyInit | undefined;
  if (body === undefined || body === null) bodyInit = undefined;
  else if (typeof body === "string" || body instanceof FormData) bodyInit = body;
  else bodyInit = JSON.stringify(body);

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return request<T>("PATCH", path, bodyInit, { ...init, headers });
}

export async function apiDelete<T>(path: string, body?: unknown, init: AppRequestInit = {}): Promise<T> {
  let bodyInit: BodyInit | undefined;
  if (body === undefined || body === null) bodyInit = undefined;
  else if (typeof body === "string" || body instanceof FormData) bodyInit = body;
  else bodyInit = JSON.stringify(body);

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return request<T>("DELETE", path, bodyInit, { ...init, headers });
}

export async function apiPostForm<T>(path: string, formData: FormData, init: AppRequestInit = {}): Promise<T> {
  return request<T>("POST", path, formData, { ...init, offline: { ...init.offline, queueMutation: false } });
}

// -----------------------------------------------------------------------------
// CRS API FUNCTIONS
// -----------------------------------------------------------------------------

export async function createCRS(payload: CRSCreate): Promise<CRSRead> {
  return apiPost<CRSRead>("/crs/", payload, {
    headers: authHeaders(),
  });
}

export async function prefillCRS(woNo: string): Promise<CRSPrefill> {
  if (!woNo.trim()) throw new Error("Work order number is required for prefill.");
  const encoded = encodeURIComponent(woNo.trim());
  return apiGet<CRSPrefill>(`/crs/prefill/${encoded}`, {
    headers: authHeaders(),
  });
}

export async function listCRS(skip = 0, limit = 50, onlyActive = true): Promise<CRSRead[]> {
  const params = new URLSearchParams();
  params.set("skip", String(skip));
  params.set("limit", String(limit));
  params.set("only_active", String(onlyActive));
  return apiGet<CRSRead[]>(`/crs/?${params.toString()}`, {
    headers: authHeaders(),
  });
}

export function getCRSPdfUrl(crsId: number): string {
  return `${getApiBaseUrl()}/crs/${crsId}/pdf`;
}

export type CRSTemplateMeta = {
  pages: Array<{ index: number; width: number; height: number }>;
  fields: Array<{ name: string; page_index: number; x: number; y: number; width: number; height: number }>;
};

export async function fetchCRSTemplateMeta(): Promise<CRSTemplateMeta> {
  return apiGet<CRSTemplateMeta>("/crs/template/meta", {
    headers: authHeaders(),
  });
}

export async function fetchCRSTemplatePdf(): Promise<Blob> {
  const url = `${getApiBaseUrl()}/crs/template/pdf`;
  const res = await portalFetch(url, {
    method: "GET",
    headers: authHeaders(),
    offline: { cache: false },
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  const contentType = res.headers.get("Content-Type") || "";
  if (!res.ok || !contentType.includes("application/pdf")) {
    const text = await res.text().catch(() => "");
    console.error(`API GET ${url} failed or returned non-PDF:`, res.status, contentType, text.slice(0, 300));
    throw new Error(text || `Expected PDF from ${url}, but got ${contentType || "unknown"}`);
  }
  return res.blob();
}
