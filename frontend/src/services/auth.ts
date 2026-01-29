/**
 * Auth service
 * - Defines getApiBaseUrl used by all frontend services.
 * - Talks to backend auth endpoints (amodb/apps/accounts/router_public.py).
 * - Manages JWT token, AMO + department context, and cached current user.
 * - Exposes authHeaders() so other services can call protected routes.
 */

import { getApiBaseUrl } from "./config";

const TOKEN_KEY = "amo_portal_token";
const AMO_KEY = "amo_code";
const AMO_SLUG_KEY = "amo_slug";
const DEPT_KEY = "amo_department";
const USER_KEY = "amo_current_user";
const SESSION_EVENT_KEY = "amo_session_event";
const ONBOARDING_STATUS_KEY = "amo_onboarding_status";

// Shared with adminUsers.ts enhancements (kept as a plain key to avoid circular imports)
const ACTIVE_AMO_ID_KEY = "amodb_active_amo_id";

/**
 * These mirror the backend enums in accounts.models.
 * Keep them in sync with Python AccountRole / RegulatoryAuthority.
 */
export type AccountRole =
  | "SUPERUSER"
  | "AMO_ADMIN"
  | "QUALITY_MANAGER"
  | "SAFETY_MANAGER"
  | "PLANNING_ENGINEER"
  | "PRODUCTION_ENGINEER"
  | "CERTIFYING_ENGINEER"
  | "CERTIFYING_TECHNICIAN"
  | "TECHNICIAN"
  | "STORES"
  | "VIEW_ONLY";

export type RegulatoryAuthority = "FAA" | "EASA" | "KCAA" | "CAA_UK" | "OTHER";

/**
 * This mirrors UserRead in backend accounts.schemas.
 * If the backend UserRead changes, update this interface to match.
 */
export interface PortalUser {
  id: string;
  amo_id: string;
  department_id: string | null;
  staff_code: string;

  email: string;
  first_name: string;
  last_name: string;
  full_name: string;

  role: AccountRole;
  position_title: string | null;
  phone: string | null;

  regulatory_authority: RegulatoryAuthority | null;
  licence_number: string | null;
  licence_state_or_country: string | null;
  licence_expires_on: string | null;

  is_active: boolean;
  is_superuser: boolean;
  is_amo_admin: boolean;
  must_change_password: boolean;

  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string;
  updated_at: string;
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

export interface LoginContextResponse {
  login_slug: string;
  amo_code: string | null;
  amo_name: string | null;
  is_platform: boolean;
}

export type SessionEventDetail = {
  type: "expired" | "idle-warning" | "idle-logout";
  reason?: string;
};

export type OnboardingStatus = {
  is_complete: boolean;
  missing: string[];
};

export type PasswordResetResponse = {
  message: string;
  reset_link?: string | null;
};

export type PasswordResetDeliveryMethod = "email" | "whatsapp" | "both";

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

export function setContext(
  amoCode: string | null,
  departmentCode: string | null,
  amoSlug?: string | null
): void {
  if (amoCode) localStorage.setItem(AMO_KEY, amoCode);
  else localStorage.removeItem(AMO_KEY);

  if (amoSlug) localStorage.setItem(AMO_SLUG_KEY, amoSlug);
  else localStorage.removeItem(AMO_SLUG_KEY);

  if (departmentCode) localStorage.setItem(DEPT_KEY, departmentCode);
  else localStorage.removeItem(DEPT_KEY);
}

export function getContext(): {
  amoCode: string | null;
  amoSlug: string | null;
  department: string | null;
} {
  return {
    amoCode: localStorage.getItem(AMO_KEY),
    amoSlug: localStorage.getItem(AMO_SLUG_KEY),
    department: localStorage.getItem(DEPT_KEY),
  };
}

export function clearContext(): void {
  localStorage.removeItem(AMO_KEY);
  localStorage.removeItem(AMO_SLUG_KEY);
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

export function cacheOnboardingStatus(status: OnboardingStatus | null): void {
  if (typeof sessionStorage === "undefined") return;
  if (!status) {
    sessionStorage.removeItem(ONBOARDING_STATUS_KEY);
    return;
  }
  sessionStorage.setItem(ONBOARDING_STATUS_KEY, JSON.stringify(status));
}

export function getCachedOnboardingStatus(): OnboardingStatus | null {
  if (typeof sessionStorage === "undefined") return null;
  const raw = sessionStorage.getItem(ONBOARDING_STATUS_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OnboardingStatus;
  } catch {
    return null;
  }
}

export function clearOnboardingStatus(): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.removeItem(ONBOARDING_STATUS_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// Optional: active AMO id support (for SUPERUSER support workflows)
export function setActiveAmoId(amoId: string | null): void {
  const v = (amoId || "").trim();
  if (!v) localStorage.removeItem(ACTIVE_AMO_ID_KEY);
  else localStorage.setItem(ACTIVE_AMO_ID_KEY, v);
}

export function getActiveAmoId(): string | null {
  const v = localStorage.getItem(ACTIVE_AMO_ID_KEY);
  return v && v.trim() ? v.trim() : null;
}

export function clearActiveAmoId(): void {
  localStorage.removeItem(ACTIVE_AMO_ID_KEY);
}

// -----------------------------------------------------------------------------
// Authenticated headers helper (for other services like CRS / adminUsers)
// -----------------------------------------------------------------------------

export function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  const headers = new Headers();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (extra) {
    const extras = new Headers(extra);
    extras.forEach((value, key) => headers.set(key, value));
  }

  return headers;
}

// -----------------------------------------------------------------------------
// helpers
// -----------------------------------------------------------------------------

async function readErrorMessage(res: Response): Promise<string> {
  // Try JSON first (FastAPI often returns { detail: ... })
  try {
    const data = await res.clone().json();
    const detail =
      (data && (data.detail || data.message || data.error)) ?? null;
    if (detail) return typeof detail === "string" ? detail : JSON.stringify(detail);
  } catch {
    // ignore
  }

  // Fallback to text
  try {
    const text = await res.text();
    if (text && text.trim()) return text.trim();
  } catch {
    // ignore
  }

  return `HTTP ${res.status}`;
}

function resolveAmoSlug(input: string | null | undefined): string {
  // Support mode: allow blank slug to mean platform login
  const v = (input || "").trim();
  return v ? v : "system";
}

// -----------------------------------------------------------------------------
// API calls
// -----------------------------------------------------------------------------

/**
 * Login with AMO slug + email + password.
 *
 * Backend: POST /auth/login (router_public.py)
 * Body: { amo_slug, email, password }
 *
 * Enhancements:
 * - If amoSlug is blank, defaults to "system" (platform support login).
 *
 * On success:
 * - stores JWT in localStorage
 * - stores AMO + department context
 * - caches current user
 * - stores active AMO id (if amo context is present)
 */
export async function login(
  amoSlug: string,
  email: string,
  password: string
): Promise<LoginResponse> {
  const payload = {
    amo_slug: resolveAmoSlug(amoSlug), // MUST match AMO.login_slug; blank => "system"
    email: email.trim(),
    password,
  };

  const res = await fetch(`${getApiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const data: LoginResponse = await res.json();

  saveToken(data.access_token);

  // Store context (AMO code + department code, if provided)
  if (data.amo) {
    setContext(
      data.amo.amo_code,
      data.department ? data.department.code : null,
      data.amo.login_slug
    );
    // Track currently active AMO id (useful later for SUPERUSER support workflows)
    setActiveAmoId(data.amo.id);
  } else {
    clearContext();
    clearActiveAmoId();
  }

  if (data.user) {
    cacheCurrentUser(data.user);
  }

  return data;
}

/**
 * Resolve login context for a given email.
 *
 * Backend: GET /auth/login-context?email=...
 */
export async function getLoginContext(
  email: string
): Promise<LoginContextResponse> {
  const query = new URLSearchParams({ email: email.trim() }).toString();
  const res = await fetch(`${getApiBaseUrl()}/auth/login-context?${query}`);

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  return (await res.json()) as LoginContextResponse;
}

/**
 * Fetch currently logged-in user from backend.
 *
 * Backend: GET /auth/me (router_public.py)
 */
export async function fetchCurrentUser(): Promise<PortalUser> {
  const token = getToken();
  if (!token) {
    throw new Error("No auth token");
  }

  const res = await fetch(`${getApiBaseUrl()}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    // If token expired/invalid, clear local state to avoid a “ghost session”
    if (res.status === 401) handleAuthFailure("expired");
    throw new Error(await readErrorMessage(res));
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
  email: string,
  deliveryMethod: PasswordResetDeliveryMethod = "email"
): Promise<PasswordResetResponse> {
  const payload = {
    amo_slug: resolveAmoSlug(amoSlug),
    email: email.trim(),
    delivery_method: deliveryMethod,
  };

  const res = await fetch(`${getApiBaseUrl()}/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  return (await res.json()) as PasswordResetResponse;
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

  const res = await fetch(`${getApiBaseUrl()}/auth/password-reset/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<PortalUser> {
  const payload = {
    current_password: currentPassword,
    new_password: newPassword,
  };

  const res = await fetch(`${getApiBaseUrl()}/auth/password-change`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const user = (await res.json()) as PortalUser;
  cacheCurrentUser(user);
  cacheOnboardingStatus({ is_complete: true, missing: [] });
  return user;
}

export async function fetchOnboardingStatus(options?: {
  force?: boolean;
}): Promise<OnboardingStatus> {
  const cached = getCachedOnboardingStatus();
  if (cached && !options?.force) {
    return cached;
  }

  const res = await fetch(`${getApiBaseUrl()}/accounts/onboarding/status`, {
    method: "GET",
    headers: authHeaders(),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const status = (await res.json()) as OnboardingStatus;
  cacheOnboardingStatus(status);
  return status;
}

/**
 * Clear all local auth/session state.
 */
export function logout(): void {
  clearToken();
  clearContext();
  clearCachedUser();
  clearActiveAmoId();
  clearOnboardingStatus();
}

export function emitSessionEvent(detail: SessionEventDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(SESSION_EVENT_KEY, { detail }));
}

export function onSessionEvent(
  handler: (detail: SessionEventDetail) => void
): () => void {
  if (typeof window === "undefined") return () => undefined;

  const listener = (event: Event) => {
    if (!(event instanceof CustomEvent)) return;
    handler(event.detail as SessionEventDetail);
  };

  window.addEventListener(SESSION_EVENT_KEY, listener);
  return () => window.removeEventListener(SESSION_EVENT_KEY, listener);
}

export function handleAuthFailure(reason = "expired"): void {
  logout();
  emitSessionEvent({ type: "expired", reason });
}
