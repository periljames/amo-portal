// src/services/crs.ts
// - Generic HTTP helpers (apiGet/apiPost) for the AMO backend.
// - CRS endpoints -> backend/amodb/apps/crs/router.py:
//     * POST /crs/                      -> createCRS
//     * GET  /crs/prefill/:wo_no       -> prefillCRS
//     * GET  /crs/                     -> listCRS
//     * GET  /crs/:id/pdf              -> getCRSPdfUrl
// - Uses authHeaders() from auth.ts so requests carry the JWT.

import type { CRSCreate, CRSRead, CRSPrefill } from "../types/crs";
import { authHeaders } from "./auth";
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

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  const contentType = res.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    // @ts-expect-error – caller knows when T is void
    return undefined;
  }

  return (await res.json()) as T;
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

  return request<T>("POST", path, bodyInit, init);
}

export async function apiGet<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("GET", path, undefined, init);
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
