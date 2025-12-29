// src/services/crs.ts
// - Generic HTTP helpers (apiGet/apiPost) for the AMO backend.
// - CRS endpoints -> backend/amodb/apps/crs/router.py:
//     * POST /crs/                      -> createCRS
//     * GET  /crs/prefill/:wo_no       -> prefillCRS
//     * GET  /crs/                     -> listCRS
//     * GET  /crs/template/pdf         -> fetchCRSTemplatePdf
//     * GET  /crs/template/meta        -> fetchCRSTemplateMeta
//     * GET  /crs/:id/pdf              -> getCRSPdfUrl
// - Uses authHeaders() from auth.ts so requests carry the JWT.

import type { CRSCreate, CRSRead, CRSPrefill } from "../types/crs";
import { authHeaders, handleAuthFailure } from "./auth";
import { API_BASE_URL } from "./config";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: BodyInit,
  init: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    method,
    body,
    ...init,
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const contentType = res.headers.get("Content-Type") || "";
    const text = await res.text();
    // Log for easier debugging in the browser console
    console.error(
      `API ${method} ${url} failed:`,
      res.status,
      contentType,
      text.slice(0, 300)
    );
    throw new Error(text || `HTTP ${res.status}`);
  }

  if (res.status === 204 || res.status === 205) {
    return null as T;
  }

  const contentType = res.headers.get("Content-Type") || "";

  // We expect these helpers to talk to JSON endpoints.
  if (!contentType.includes("application/json")) {
    const text = await res.text();
    console.error(
      `API ${method} ${url} returned non-JSON success response:`,
      contentType,
      text.slice(0, 300)
    );
    throw new Error(
      `Expected JSON from ${url}, but got ${contentType || "unknown"}`
    );
  }

  try {
    return (await res.json()) as T;
  } catch (err) {
    console.error(
      `API ${method} ${url} JSON parse error:`,
      err
    );
    throw err;
  }
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  init: RequestInit = {}
): Promise<T> {
  let bodyInit: BodyInit | undefined;

  if (body === undefined || body === null) {
    bodyInit = undefined;
  } else if (typeof body === "string" || body instanceof FormData) {
    bodyInit = body;
  } else {
    bodyInit = JSON.stringify(body);
  }

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData)) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  return request<T>("POST", path, bodyInit, { ...init, headers });
}

export async function apiGet<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("GET", path, undefined, init);
}

export async function apiDelete<T>(
  path: string,
  body?: unknown,
  init: RequestInit = {}
): Promise<T> {
  let bodyInit: BodyInit | undefined;

  if (body === undefined || body === null) {
    bodyInit = undefined;
  } else if (typeof body === "string" || body instanceof FormData) {
    bodyInit = body;
  } else {
    bodyInit = JSON.stringify(body);
  }

  const headers = new Headers(init.headers);
  if (bodyInit !== undefined && !(bodyInit instanceof FormData)) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  return request<T>("DELETE", path, bodyInit, { ...init, headers });
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
  if (!woNo.trim()) {
    throw new Error("Work order number is required for prefill.");
  }

  const encoded = encodeURIComponent(woNo.trim());
  return apiGet<CRSPrefill>(`/crs/prefill/${encoded}`, {
    headers: authHeaders(),
  });
}

export async function listCRS(
  skip = 0,
  limit = 50,
  onlyActive = true
): Promise<CRSRead[]> {
  const params = new URLSearchParams();
  params.set("skip", String(skip));
  params.set("limit", String(limit));
  params.set("only_active", String(onlyActive));

  return apiGet<CRSRead[]>(`/crs/?${params.toString()}`, {
    headers: authHeaders(),
  });
}

export function getCRSPdfUrl(crsId: number): string {
  return `${API_BASE_URL}/crs/${crsId}/pdf`;
}

// -----------------------------------------------------------------------------
// CRS template helpers (PDF + meta)
// -----------------------------------------------------------------------------

// Shape based on backend /crs/template/meta response.
// If you later define a stricter type, update this accordingly.
export type CRSTemplateMeta = {
  pages: Array<{
    index: number;
    width: number;
    height: number;
  }>;
  fields: Array<{
    name: string;
    page_index: number;
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
};

export async function fetchCRSTemplateMeta(): Promise<CRSTemplateMeta> {
  return apiGet<CRSTemplateMeta>("/crs/template/meta", {
    headers: authHeaders(),
  });
}

export async function fetchCRSTemplatePdf(): Promise<Blob> {
  const url = `${API_BASE_URL}/crs/template/pdf`;

  const res = await fetch(url, {
    method: "GET",
    headers: authHeaders(),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  const contentType = res.headers.get("Content-Type") || "";

  if (!res.ok || !contentType.includes("application/pdf")) {
    const text = await res.text().catch(() => "");
    console.error(
      `API GET ${url} failed or returned non-PDF:`,
      res.status,
      contentType,
      text.slice(0, 300)
    );
    throw new Error(
      text ||
        `Expected PDF from ${url}, but got ${contentType || "unknown"}`
    );
  }

  return res.blob();
}
