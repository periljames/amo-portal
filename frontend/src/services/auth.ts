// src/services/auth.ts

import { API_BASE_URL } from "./crs";

const TOKEN_KEY = "amo_portal_token";
const AMO_KEY = "amo_code";
const DEPT_KEY = "amo_department";
const USER_KEY = "amo_current_user";

export type PortalUserId = string | number;

export interface PortalUser {
  id: PortalUserId;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
  is_amo_admin: boolean;
}

export interface AmoContext {
  id: string;
  amo_code: string;
  name: string;
  login_slug: string;
  contact_email?: string | null;
  contact_phone?: string | null;
  time_zone?: string | null;
}

export interface DepartmentContext {
  id: string;
  code: string;
  name: string;
  default_route?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: PortalUser;
  amo: AmoContext | null;
  department: DepartmentContext | null;
}

// -----------------------------------------------------------------------------
// localStorage helpers
// -----------------------------------------------------------------------------

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function setContext(amoCode: string | null, departmentCode: string | null): void {
  if (amoCode) {
    localStorage.setItem(AMO_KEY, amoCode);
  } else {
    localStorage.removeItem(AMO_KEY);
  }

  if (departmentCode) {
    localStorage.setItem(DEPT_KEY, departmentCode);
  } else {
    localStorage.removeItem(DEPT_KEY);
  }
}

export function getContext(): { amoCode: string | null; department: string | null } {
  return {
    amoCode: localStorage.getItem(AMO_KEY),
    department: localStorage.getItem(DEPT_KEY),
  };
}

export function clearContext(): void {
  localStorage.removeItem(AMO_KEY);
  localStorage.removeItem(DEPT_KEY);
}

export function cacheCurrentUser(user: PortalUser): void {
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

export function clearCachedUser(): void {
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// -----------------------------------------------------------------------------
// Authenticated headers helper (for other services like CRS)
// -----------------------------------------------------------------------------

export function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  const base: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (token) {
    (base as any).Authorization = `Bearer ${token}`;
  }

  return {
    ...base,
    ...(extra || {}),
  };
}

// -----------------------------------------------------------------------------
// API calls
// -----------------------------------------------------------------------------

/**
 * Login with AMO slug + email + password.
 *
 * Backend: POST /auth/login
 * Body: { amo_slug, email, password }
 *
 * On success:
 * - stores JWT in localStorage
 * - stores AMO + department context
 * - caches current user
 */
export async function login(
  amoSlug: string,
  email: string,
  password: string
): Promise<void> {
  const payload = {
    amo_slug: amoSlug.trim(),
    email: email.trim(),
    password,
  };

  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  const data: LoginResponse = await res.json();

  // Store JWT
  saveToken(data.access_token);

  // Store context (AMO code + department code)
  if (data.amo) {
    setContext(
      data.amo.amo_code,
      data.department ? data.department.code : null
    );
  } else {
    clearContext();
  }

  // Cache user
  if (data.user) {
    cacheCurrentUser(data.user);
  }
}

/**
 * Fetch currently logged-in user from backend.
 *
 * Backend: GET /auth/me
 */
export async function fetchCurrentUser(): Promise<PortalUser> {
  const token = getToken();
  if (!token) {
    throw new Error("No auth token");
  }

  const res = await fetch(`${API_BASE_URL}/auth/me`, {
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

/**
 * Request password reset.
 *
 * Backend: POST /auth/password-reset/request
 */
export async function requestPasswordReset(
  amoSlug: string,
  email: string
): Promise<void> {
  const payload = {
    amo_slug: amoSlug.trim(),
    email: email.trim(),
  };

  const res = await fetch(`${API_BASE_URL}/auth/password-reset/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  // Always return 200 from backend; still check for non-2xx as a network/error case.
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
}

/**
 * Confirm password reset with token.
 *
 * Backend: POST /auth/password-reset/confirm
 */
export async function confirmPasswordReset(
  token: string,
  newPassword: string
): Promise<void> {
  const payload = {
    token,
    new_password: newPassword,
  };

  const res = await fetch(`${API_BASE_URL}/auth/password-reset/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
}

/**
 * Clear all local auth/session state.
 */
export function logout(): void {
  clearToken();
  clearContext();
  clearCachedUser();
}
