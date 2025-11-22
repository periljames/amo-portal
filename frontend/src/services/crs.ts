// src/services/crs.ts

import type { CRSCreate, CRSRead, CRSPrefill } from "../types/crs";

// -----------------------------------------------------------------------------
// BASE API + GENERIC REQUEST HELPERS
// -----------------------------------------------------------------------------

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

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
    // @ts-expect-error – caller should know when T is void
    return undefined;
  }

  return (await res.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body?: BodyInit,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("POST", path, body, init);
}

export async function apiGet<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("GET", path, undefined, init);
}

// -----------------------------------------------------------------------------
// AUTH + CONTEXT HELPERS
// -----------------------------------------------------------------------------

const TOKEN_KEY = "amo_portal_token";
const AMO_KEY = "amo_code";
const DEPT_KEY = "amo_department";
const USER_KEY = "amo_current_user";

export type PortalUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
};

// ---- token helpers ----
export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// ---- context (AMO + department) ----
export function setContext(amoCode: string, department: string) {
  localStorage.setItem(AMO_KEY, amoCode);
  localStorage.setItem(DEPT_KEY, department);
}

export function getContext(): { amoCode: string | null; department: string | null } {
  return {
    amoCode: localStorage.getItem(AMO_KEY),
    department: localStorage.getItem(DEPT_KEY),
  };
}

export function clearContext() {
  localStorage.removeItem(AMO_KEY);
  localStorage.removeItem(DEPT_KEY);
}

// ---- current user cache ----
export function cacheCurrentUser(user: PortalUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getCachedUser(): PortalUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PortalUser;
  } catch {
    return null;
  }
}

export function clearCachedUser() {
  localStorage.removeItem(USER_KEY);
}

// ---- auth helpers ----
export function isAuthenticated(): boolean {
  return !!getToken();
}

export async function login(email: string, password: string): Promise<void> {
  const formData = new URLSearchParams();
  formData.append("username", email.trim());
  formData.append("password", password);
  formData.append("grant_type", "password");
  formData.append("scope", "");
  formData.append("client_id", "");
  formData.append("client_secret", "");

  const data = await apiPost<TokenResponse>("/auth/token", formData, {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });

  saveToken(data.access_token);
}

export async function fetchCurrentUser(): Promise<PortalUser> {
  const token = getToken();
  if (!token) {
    throw new Error("No auth token");
  }

  const res = await fetch(`${API_BASE_URL}/users/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  const user = (await res.json()) as PortalUser;
  cacheCurrentUser(user);
  return user;
}

export function logout() {
  clearToken();
  clearContext();
  clearCachedUser();
}

// -----------------------------------------------------------------------------
// INTERNAL: AUTH HEADERS FOR PROTECTED ENDPOINTS
// -----------------------------------------------------------------------------

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  const base: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (token) {
    base["Authorization"] = `Bearer ${token}`;
  }

  return {
    ...base,
    ...(extra || {}),
  };
}

// -----------------------------------------------------------------------------
// CRS API FUNCTIONS
// -----------------------------------------------------------------------------

/**
 * Create a new CRS (POST /crs/)
 */
export async function createCRS(payload: CRSCreate): Promise<CRSRead> {
  return apiPost<CRSRead>("/crs/", JSON.stringify(payload), {
    headers: authHeaders(),
  });
}

/**
 * Prefill CRS from Work Order (GET /crs/prefill/{wo_no})
 */
export async function prefillCRS(woNo: string): Promise<CRSPrefill> {
  if (!woNo.trim()) {
    throw new Error("Work order number is required for prefill.");
  }

  const encoded = encodeURIComponent(woNo.trim());
  return apiGet<CRSPrefill>(`/crs/prefill/${encoded}`, {
    headers: authHeaders(),
  });
}

/**
 * List CRS records (GET /crs/)
 */
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

/**
 * Build PDF URL for a given CRS id (GET /crs/{id}/pdf)
 */
export function getCRSPdfUrl(crsId: number): string {
  return `${API_BASE_URL}/crs/${crsId}/pdf`;
}
