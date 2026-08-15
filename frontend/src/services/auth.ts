/**
 * Auth service
 * - Defines getApiBaseUrl used by all frontend services.
 * - Talks to backend auth endpoints (amodb/apps/accounts/router_public.py).
 * - Manages JWT token, AMO + department context, and cached current user.
 * - Exposes authHeaders() so other services can call protected routes.
 */

import { getApiBaseUrl } from "./config";
import { clearBrandContext, setBrandContext } from "./branding";
import { setPortalDataMode } from "./runtimeMode";
import {
  getPortalConnectivitySnapshot,
  isPortalReady,
  recommendedRequestTimeoutMs,
} from "./portalConnectivity";

const TOKEN_KEY = "amo_portal_token";
const AMO_KEY = "amo_code";
const AMO_SLUG_KEY = "amo_slug";
const DEPT_KEY = "amo_department";
const USER_KEY = "amo_current_user";
const SESSION_EVENT_KEY = "amo_session_event";
const SESSION_SYNC_KEY = "amo_session_sync_v2";
const SESSION_LAST_USER_ACTIVITY_KEY = "amo_session_last_user_activity";
const ONBOARDING_STATUS_KEY = "amo_onboarding_status";
const LAST_LOGIN_IDENTIFIER_KEY = "amo_last_login_identifier";
const LOGIN_CONTEXT_CACHE_KEY = "amo_login_context_cache";
const PENDING_SESSION_REVOCATION_KEY = "amo_pending_session_revocation";

const DEFAULT_REQUEST_TIMEOUT_MS = 20000;
const LOGIN_CONTEXT_CACHE_TTL_MS = 5 * 60 * 1000;
const SESSION_EXTEND_THRESHOLD_SECONDS = 5 * 60;
const SESSION_EXTEND_COOLDOWN_MS = 60 * 1000;
export const PORTAL_IDLE_TIMEOUT_MS = 30 * 60 * 1000;
export const PORTAL_IDLE_WARNING_MS = 60 * 1000;
let sessionEnded = false;
let lastSessionExtendAttemptAt = 0;
let sessionExtendInFlight: Promise<LoginResponse | null> | null = null;
let sessionRecoveryInFlight: Promise<LoginResponse | null> | null = null;
let cachedUserRaw: string | null = null;
let cachedUserObject: PortalUser | null = null;

type TimedRequestOptions = RequestInit & { timeoutMs?: number; signal?: AbortSignal | null };

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function makeAbortError(message: string): DOMException {
  return new DOMException(message, "AbortError");
}

async function fetchWithTimeout(input: RequestInfo | URL, init: TimedRequestOptions = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, signal, ...rest } = init;
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort(makeAbortError(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`));
  }, timeoutMs);

  const abortFromCaller = () => controller.abort(makeAbortError("Request was cancelled"));
  if (signal) {
    if (signal.aborted) abortFromCaller();
    else signal.addEventListener("abort", abortFromCaller, { once: true });
  }

  try {
    return await fetch(input, { ...rest, signal: controller.signal });
  } catch (error) {
    if (isAbortError(error)) {
      throw new Error(timedOut ? "Request timed out. Confirm the backend is reachable, then retry." : "Request was cancelled.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    if (signal) signal.removeEventListener("abort", abortFromCaller);
  }
}

// Shared with adminUsers.ts enhancements (kept as a plain key to avoid circular imports)
const ACTIVE_AMO_ID_KEY = "amodb_active_amo_id";

export function normalizeDepartmentCode(value?: string | null): string | null {
  const v = (value || "").trim();
  if (!v) return null;
  return v.toLowerCase();
}

/**
 * These mirror the backend enums in accounts.models.
 * Keep them in sync with Python AccountRole / RegulatoryAuthority.
 */
export type AccountRole =
  | "SUPERUSER"
  | "AMO_ADMIN"
  | "USER"
  | "ACCOUNTABLE_EXECUTIVE"
  | "BASE_MAINTENANCE_MANAGER"
  | "LINE_MAINTENANCE_MANAGER"
  | "WORKSHOP_MANAGER"
  | "QUALITY_MANAGER"
  | "AUDITOR"
  | "SAFETY_MANAGER"
  | "PLANNING_ENGINEER"
  | "PRODUCTION_ENGINEER"
  | "CERTIFYING_ENGINEER"
  | "CERTIFYING_TECHNICIAN"
  | "TECHNICIAN"
  | "STORES"
  | "VIEW_ONLY"
  | "FINANCE_MANAGER"
  | "ACCOUNTS_OFFICER"
  | "STORES_MANAGER"
  | "STOREKEEPER"
  | "PROCUREMENT_OFFICER"
  | "QUALITY_INSPECTOR";

export type RegulatoryAuthority = "FAA" | "EASA" | "KCAA" | "CAA_UK" | "OTHER";

/**
 * This mirrors UserRead in backend accounts.schemas.
 * If the backend UserRead changes, update this interface to match.
 */
export interface PortalUser {
  id: string;
  amo_id: string | null;
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
  branding?: AmoBranding | null;
  is_demo?: boolean | null;
  data_mode?: "REAL" | "LIVE" | "DEMO" | null;
}

export type AmoBranding = {
  logoUrl?: string | null;
  logoUrlDark?: string | null;
  logoUrlLight?: string | null;
  updatedAt?: string | null;
};

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
  type: "expired" | "idle-warning" | "idle-logout" | "authenticated" | "activity" | "manual-logout"
    | "session-recovering" | "offline-continuity";
  reason?: string;
  at?: number;
  deadlineAt?: number;
};

type SessionSyncEnvelope = {
  id: string;
  at: number;
  detail: SessionEventDetail;
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
  sessionEnded = false;
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

  const normalizedDepartment = normalizeDepartmentCode(departmentCode);
  if (normalizedDepartment) localStorage.setItem(DEPT_KEY, normalizedDepartment);
  else localStorage.removeItem(DEPT_KEY);
}

export function getContext(): {
  amoCode: string | null;
  amoSlug: string | null;
  department: string | null;
} {
  const department = normalizeDepartmentCode(localStorage.getItem(DEPT_KEY));
  return {
    amoCode: localStorage.getItem(AMO_KEY),
    amoSlug: localStorage.getItem(AMO_SLUG_KEY),
    department,
  };
}

export function clearContext(): void {
  localStorage.removeItem(AMO_KEY);
  localStorage.removeItem(AMO_SLUG_KEY);
  localStorage.removeItem(DEPT_KEY);
}

export function cacheCurrentUser(user: PortalUser): void {
  const raw = JSON.stringify(user);
  localStorage.setItem(USER_KEY, raw);
  cachedUserRaw = raw;
  cachedUserObject = user;
}

export function saveLastLoginIdentifier(identifier: string): void {
  const trimmed = identifier.trim();
  if (!trimmed) return;
  localStorage.setItem(LAST_LOGIN_IDENTIFIER_KEY, trimmed);
}

export function getLastLoginIdentifier(): string {
  return localStorage.getItem(LAST_LOGIN_IDENTIFIER_KEY) || "";
}

export function getCachedUser(): PortalUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    cachedUserRaw = null;
    cachedUserObject = null;
    return null;
  }
  if (raw === cachedUserRaw && cachedUserObject) return cachedUserObject;
  try {
    const parsed = JSON.parse(raw) as PortalUser;
    cachedUserRaw = raw;
    cachedUserObject = parsed;
    return parsed;
  } catch {
    cachedUserRaw = null;
    cachedUserObject = null;
    return null;
  }
}

export function clearCachedUser(): void {
  localStorage.removeItem(USER_KEY);
  cachedUserRaw = null;
  cachedUserObject = null;
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

function getLoginContextCache(): Record<string, { at: number; value: LoginContextResponse }> {
  if (typeof sessionStorage === "undefined") return {};
  const raw = sessionStorage.getItem(LOGIN_CONTEXT_CACHE_KEY);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, { at: number; value: LoginContextResponse }>;
  } catch {
    sessionStorage.removeItem(LOGIN_CONTEXT_CACHE_KEY);
    return {};
  }
}

function getCachedLoginContextForIdentifier(identifier: string): LoginContextResponse | null {
  const key = identifier.trim().toLowerCase();
  if (!key) return null;
  const cached = getLoginContextCache()[key];
  if (!cached) return null;
  if (Date.now() - cached.at > LOGIN_CONTEXT_CACHE_TTL_MS) return null;
  return cached.value;
}

function cacheLoginContextForIdentifier(identifier: string, value: LoginContextResponse): void {
  if (typeof sessionStorage === "undefined") return;
  const key = identifier.trim().toLowerCase();
  if (!key) return;
  const cache = getLoginContextCache();
  cache[key] = { at: Date.now(), value };
  sessionStorage.setItem(LOGIN_CONTEXT_CACHE_KEY, JSON.stringify(cache));
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const normalized = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function getTokenSecondsRemaining(): number | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  const exp = Number(payload?.exp);
  if (!Number.isFinite(exp)) return null;
  return Math.floor(exp - Date.now() / 1000);
}

function sessionIsIdleExpired(now = Date.now()): boolean {
  const lastUserActivityAt = getLastUserSessionActivityAt();
  return Boolean(lastUserActivityAt && now - lastUserActivityAt >= PORTAL_IDLE_TIMEOUT_MS);
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  const remaining = getTokenSecondsRemaining();
  if (remaining != null && remaining <= 0) {
    if (sessionIsIdleExpired()) {
      endSession("idle");
      return false;
    }
    if (!getCachedUser()) return false;
    if (isPortalReady()) void recoverSession("route-guard");
    else emitSessionEvent({ type: "offline-continuity", reason: "access-token-expired-offline" });
    // Cached, tenant-scoped views remain usable while recovery is pending.
    // Authoritative requests are still blocked by ensureAuthenticatedRequestAllowed().
    return true;
  }
  return true;
}

export function getLastUserSessionActivityAt(): number | null {
  const value = Number(localStorage.getItem(SESSION_LAST_USER_ACTIVITY_KEY));
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function recordUserSessionActivity(reason = "interaction", at = Date.now()): void {
  if (!getToken() || sessionEnded) return;
  localStorage.setItem(SESSION_LAST_USER_ACTIVITY_KEY, String(at));
  emitSessionEvent({ type: "activity", reason, at });
}

export function ensureAuthenticatedRequestAllowed(): boolean {
  if (sessionEnded || !getToken()) return false;
  const remaining = getTokenSecondsRemaining();
  if (remaining !== null && remaining <= 0) {
    if (isPortalReady()) void recoverSession("token-expired-preflight");
    else emitSessionEvent({ type: "offline-continuity", reason: "token-expired-preflight" });
    return false;
  }
  if (sessionIsIdleExpired()) {
    endSession("idle");
    return false;
  }
  return true;
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
 * Login with AMO slug + identifier (email or staff code) + password.
 *
 * Backend: POST /auth/login (router_public.py)
 * Body: { amo_slug, email?, staff_code?, password }
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
  identifier: string,
  password: string
): Promise<LoginResponse> {
  const trimmedIdentifier = identifier.trim();
  const isEmail = trimmedIdentifier.includes("@");
  const payload = {
    amo_slug: resolveAmoSlug(amoSlug), // MUST match AMO.login_slug; blank => "system"
    email: isEmail ? trimmedIdentifier : undefined,
    staff_code: isEmail ? undefined : trimmedIdentifier,
    password,
  };

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const data: LoginResponse = await res.json();

  localStorage.removeItem(PENDING_SESSION_REVOCATION_KEY);
  saveToken(data.access_token);

  // Store context (AMO code + department code, if provided)
  if (data.amo) {
    setContext(
      data.amo.amo_code,
      data.department ? data.department.code : null,
      data.amo.login_slug
    );
    setBrandContext({
      name: data.amo.name,
      logoUrl: data.amo.branding?.logoUrl,
      logoUrlDark: data.amo.branding?.logoUrlDark,
      logoUrlLight: data.amo.branding?.logoUrlLight,
      updatedAt: data.amo.branding?.updatedAt,
    });
    setPortalDataMode(data.amo.is_demo || data.amo.data_mode === "DEMO" ? "DEMO" : "REAL");
    // Track currently active AMO id (useful later for SUPERUSER support workflows)
    setActiveAmoId(data.amo.id);
  } else {
    clearContext();
    clearActiveAmoId();
    clearBrandContext();
    setPortalDataMode("REAL");
  }

  if (data.user) {
    cacheCurrentUser(data.user);
    cacheOnboardingStatus({
      is_complete: !data.user.must_change_password,
      missing: data.user.must_change_password ? ["password_change"] : [],
    });
  }

  saveLastLoginIdentifier(trimmedIdentifier);
  recordUserSessionActivity("login");
  emitSessionEvent({ type: "authenticated" });

  return data;
}

/**
 * Resolve login context for a given email or staff code.
 *
 * Backend: GET /auth/login-context?identifier=...
 */
export async function getLoginContext(
  identifier: string
): Promise<LoginContextResponse> {
  const trimmed = identifier.trim();
  const cached = getCachedLoginContextForIdentifier(trimmed);
  if (cached) return cached;

  const query = new URLSearchParams({ identifier: trimmed }).toString();
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/login-context?${query}`, {
    timeoutMs: 15000,
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const context = (await res.json()) as LoginContextResponse;
  cacheLoginContextForIdentifier(trimmed, context);
  return context;
}

function applyRecoveredSession(data: LoginResponse): void {
  localStorage.removeItem(PENDING_SESSION_REVOCATION_KEY);
  saveToken(data.access_token);
  if (data.user) cacheCurrentUser(data.user);
  if (data.amo) {
    setContext(data.amo.amo_code, data.department ? data.department.code : null, data.amo.login_slug);
    setBrandContext({
      name: data.amo.name,
      logoUrl: data.amo.branding?.logoUrl,
      logoUrlDark: data.amo.branding?.logoUrlDark,
      logoUrlLight: data.amo.branding?.logoUrlLight,
      updatedAt: data.amo.branding?.updatedAt,
    });
    setPortalDataMode(data.amo.is_demo || data.amo.data_mode === "DEMO" ? "DEMO" : "REAL");
    setActiveAmoId(data.amo.id);
  } else if (data.user?.is_superuser) {
    clearContext();
    clearActiveAmoId();
    clearBrandContext();
    setPortalDataMode("REAL");
  }
  emitSessionEvent({ type: "authenticated", reason: "session-recovered" });
}

export function recoverSession(reason = "connectivity-recovered"): Promise<LoginResponse | null> {
  if (sessionRecoveryInFlight) return sessionRecoveryInFlight;
  if (sessionEnded || !getCachedUser()) return Promise.resolve(null);
  if (sessionIsIdleExpired()) {
    endSession("idle");
    return Promise.resolve(null);
  }
  if (!isPortalReady()) {
    const connectivity = getPortalConnectivitySnapshot();
    emitSessionEvent({ type: "offline-continuity", reason: connectivity.reason || reason });
    return Promise.resolve(null);
  }

  emitSessionEvent({ type: "session-recovering", reason });
  sessionRecoveryInFlight = (async () => {
    try {
      const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/refresh-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Portal-Refresh": "1",
          "X-AMO-Silent-Error": "1",
        },
        credentials: "include",
        body: JSON.stringify({ reason }),
        timeoutMs: recommendedRequestTimeoutMs("POST"),
      });
      if (res.status === 401 || res.status === 403) {
        expireLocalSession("recovery-session-expired");
        return null;
      }
      if (!res.ok) return null;
      const data = await res.json() as LoginResponse;
      applyRecoveredSession(data);
      return data;
    } catch {
      // A transport failure is not proof that the recovery credential is
      // invalid. Preserve the local workspace and retry after readiness.
      return null;
    }
  })().finally(() => {
    sessionRecoveryInFlight = null;
  });
  return sessionRecoveryInFlight;
}

export async function extendSession(reason = "active"): Promise<LoginResponse | null> {
  const token = getToken();
  if (!token || sessionEnded) return null;
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/extend-session`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ reason }),
    timeoutMs: 10000,
  });
  if (res.status === 401) {
    return recoverSession("access-token-expired");
  }
  if (!res.ok) throw new Error(await readErrorMessage(res));
  const data = (await res.json()) as LoginResponse;
  saveToken(data.access_token);
  if (data.user) cacheCurrentUser(data.user);
  if (data.amo) {
    setContext(data.amo.amo_code, data.department ? data.department.code : null, data.amo.login_slug);
    setPortalDataMode(data.amo.is_demo || data.amo.data_mode === "DEMO" ? "DEMO" : "REAL");
    setActiveAmoId(data.amo.id);
  }
  return data;
}

export function extendSessionIfNeeded(reason = "active"): Promise<LoginResponse | null> | null {
  const remaining = getTokenSecondsRemaining();
  if (remaining != null && remaining <= 0) {
    return isPortalReady()
      ? recoverSession("access-token-expired")
      : null;
  }
  if (remaining == null || remaining > SESSION_EXTEND_THRESHOLD_SECONDS || sessionEnded) return null;
  const now = Date.now();
  const lastUserActivityAt = getLastUserSessionActivityAt();
  // Network traffic is not proof that a person is present. Pollers may request
  // extension, but only recent keyboard/pointer activity may authorize it.
  if (!lastUserActivityAt || now - lastUserActivityAt >= PORTAL_IDLE_TIMEOUT_MS) return null;
  if (now - lastSessionExtendAttemptAt < SESSION_EXTEND_COOLDOWN_MS) return sessionExtendInFlight;
  lastSessionExtendAttemptAt = now;
  sessionExtendInFlight = extendSession(reason).finally(() => {
    sessionExtendInFlight = null;
  });
  return sessionExtendInFlight;
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

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/me`, {
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

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/password-reset/request`, {
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

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/password-reset/confirm`, {
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

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/auth/password-change`, {
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

  const res = await fetchWithTimeout(`${getApiBaseUrl()}/accounts/onboarding/status`, {
    method: "GET",
    headers: authHeaders(),
    timeoutMs: 8000,
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

async function sendPresenceBeacon(state: "online" | "away", reason?: string): Promise<void> {
  const token = getToken();
  if (!token) return;

  try {
    await fetchWithTimeout(`${getApiBaseUrl()}/api/realtime/presence`, { timeoutMs: 5000,
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      credentials: "include",
      keepalive: true,
      body: JSON.stringify({ state, reason }),
    });
  } catch {
    // best-effort only
  }
}

async function serverLogoutBestEffort(reason: "manual" | "idle"): Promise<void> {
  const token = getToken();
  if (!token) return;
  try {
    const response = await fetchWithTimeout(`${getApiBaseUrl()}/auth/logout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-AMO-Silent-Error": "1",
      },
      body: JSON.stringify({ reason }),
      credentials: "include",
      timeoutMs: 5000,
    });
    if (!response.ok) throw new Error(`Logout rejected (${response.status})`);
    localStorage.removeItem(PENDING_SESSION_REVOCATION_KEY);
  } catch {
    localStorage.setItem(PENDING_SESSION_REVOCATION_KEY, String(Date.now()));
    void flushPendingSessionRevocation();
  }
}

export async function flushPendingSessionRevocation(): Promise<boolean> {
  if (!localStorage.getItem(PENDING_SESSION_REVOCATION_KEY) || !isPortalReady()) return false;
  try {
    const response = await fetchWithTimeout(`${getApiBaseUrl()}/auth/revoke-recovery-session`, {
      method: "POST",
      headers: { "X-Portal-Refresh": "1", "X-AMO-Silent-Error": "1" },
      credentials: "include",
      timeoutMs: recommendedRequestTimeoutMs("POST"),
    });
    if (!response.ok) return false;
    localStorage.removeItem(PENDING_SESSION_REVOCATION_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * Clear all local auth/session state.
 */
export function logout(): void {
  sessionEnded = true;
  clearToken();
  clearContext();
  clearCachedUser();
  clearActiveAmoId();
  clearBrandContext();
  clearOnboardingStatus();
  localStorage.removeItem(SESSION_LAST_USER_ACTIVITY_KEY);
}

export function emitSessionEvent(detail: SessionEventDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(SESSION_EVENT_KEY, { detail }));
  if (!["activity", "idle-warning", "session-recovering", "offline-continuity"].includes(detail.type)) {
    const envelope: SessionSyncEnvelope = {
      id: typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      at: Date.now(),
      detail,
    };
    localStorage.setItem(SESSION_SYNC_KEY, JSON.stringify(envelope));
  }
}

export function onSessionEvent(
  handler: (detail: SessionEventDetail) => void
): () => void {
  if (typeof window === "undefined") return () => undefined;

  const listener = (event: Event) => {
    if (!(event instanceof CustomEvent)) return;
    handler(event.detail as SessionEventDetail);
  };

  const storageListener = (event: StorageEvent) => {
    if (event.key === SESSION_LAST_USER_ACTIVITY_KEY && event.newValue) {
      const at = Number(event.newValue);
      if (Number.isFinite(at) && at > 0) handler({ type: "activity", reason: "another-tab", at });
      return;
    }
    if (event.key !== SESSION_SYNC_KEY || !event.newValue) return;
    try {
      const envelope = JSON.parse(event.newValue) as SessionSyncEnvelope;
      if (envelope?.detail?.type) handler(envelope.detail);
    } catch {
      // Ignore malformed or legacy cross-tab session messages.
    }
  };

  window.addEventListener(SESSION_EVENT_KEY, listener);
  window.addEventListener("storage", storageListener);
  return () => {
    window.removeEventListener(SESSION_EVENT_KEY, listener);
    window.removeEventListener("storage", storageListener);
  };
}

export function markSessionActivity(reason = "interaction"): void {
  emitSessionEvent({ type: "activity", reason });
}

export function endSession(reason: "manual" | "idle" = "manual"): void {
  if (sessionEnded && !getToken()) return;
  void sendPresenceBeacon("away", reason);
  void serverLogoutBestEffort(reason);
  logout();
  emitSessionEvent({ type: reason === "idle" ? "idle-logout" : "manual-logout", reason });
}

function expireLocalSession(reason: string): void {
  if (sessionEnded && !getToken()) return;
  logout();
  emitSessionEvent({ type: "expired", reason });
}

export function handleAuthFailure(reason = "expired"): void {
  if (sessionEnded && !getToken()) return;
  if (sessionIsIdleExpired()) {
    endSession("idle");
    return;
  }
  if (isPortalReady()) {
    void recoverSession(reason);
    return;
  }
  emitSessionEvent({ type: "offline-continuity", reason });
}
