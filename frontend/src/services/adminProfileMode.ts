import { apiRequest } from "./apiClient";
import { getCachedUser, onSessionEvent } from "./auth";

const STORAGE_PREFIX = "amo_admin_profile_session";
const CHANGE_EVENT = "amo-admin-profile-change";
const API_PREFIX = "/accounts/admin/admin-profile";
const expiryTimers = new Map<string, number>();
const AUTH_SESSION_BOUNDARY_EVENTS = new Set<string>([
  "authenticated",
  "manual-logout",
  "idle-logout",
  "expired",
]);

let authSessionGeneration = 0;
let trackedWindow: EventTarget | null = null;
let stopSessionTracking: (() => void) | null = null;

export type AdminProfileState = {
  eligible: boolean;
  active: boolean;
  session_id?: string | null;
  expires_at?: string | null;
  grant_type?: "PERMANENT" | "TEMPORARY" | null;
  reason?: string | null;
};

export type AdminProfileChangeDetail = {
  amoCode: string;
  userId: string;
  state: AdminProfileState;
};

export type AdminGrantStatus = "PENDING" | "ACTIVE" | "REVOKED" | "REJECTED" | "EXPIRED";

export type AdminAccessGrant = {
  id: string;
  amo_id: string;
  user_id: string;
  user_name?: string | null;
  user_email?: string | null;
  grant_type: "PERMANENT" | "TEMPORARY";
  valid_from?: string | null;
  valid_until?: string | null;
  status: AdminGrantStatus;
  reason: string;
  requested_by_user_id: string;
  requested_by_name?: string | null;
  created_at: string;
  approval_count: number;
  accountable_executive_approved: boolean;
  quality_manager_approved: boolean;
  current_user_decided: boolean;
};

export type AdminGrantCandidate = {
  id: string;
  full_name?: string | null;
  email: string;
  position_title?: string | null;
  access_profile_name?: string | null;
};

export type AdminGrantRequestPayload = {
  user_id: string;
  grant_type: "PERMANENT" | "TEMPORARY";
  valid_from?: string | null;
  valid_until?: string | null;
  reason: string;
};

export type AdminGrantDecisionResult = {
  id: string;
  status: AdminGrantStatus;
  approval_count?: number;
  required_approvals?: number;
  accountable_executive_approved?: boolean;
  quality_manager_approved?: boolean;
};

type AdminProfileSessionResponse = AdminProfileState & {
  message?: string | null;
};

type AdminProfileRequester = {
  userId: string;
  authGeneration: number;
};

export class StaleAdminProfileResponseError extends Error {
  constructor() {
    super("Admin Profile response belongs to a previous authentication session.");
    this.name = "StaleAdminProfileResponseError";
  }
}

function ensureAuthSessionTracking(): void {
  if (typeof window === "undefined") return;
  if (trackedWindow === window && stopSessionTracking) return;

  stopSessionTracking?.();
  trackedWindow = window;
  stopSessionTracking = onSessionEvent((detail) => {
    if (AUTH_SESSION_BOUNDARY_EVENTS.has(detail.type)) {
      authSessionGeneration += 1;
    }
  });
}

function currentUserId(): string {
  try {
    return getCachedUser()?.id || "anonymous";
  } catch {
    return "anonymous";
  }
}

function captureRequester(): AdminProfileRequester {
  ensureAuthSessionTracking();
  return {
    userId: currentUserId(),
    authGeneration: authSessionGeneration,
  };
}

function assertCurrentRequester(requester: AdminProfileRequester): void {
  ensureAuthSessionTracking();
  if (
    requester.userId === "anonymous"
    || currentUserId() !== requester.userId
    || authSessionGeneration !== requester.authGeneration
  ) {
    throw new StaleAdminProfileResponseError();
  }
}

function storageKey(amoCode: string, userId = currentUserId()): string {
  return `${STORAGE_PREFIX}:${userId}:${amoCode.toLowerCase()}`;
}

function apiPath(amoCode: string, action: "state" | "activate" | "deactivate"): string {
  return `${API_PREFIX}/${encodeURIComponent(amoCode)}/${action}`;
}

function dispatchState(
  amoCode: string,
  userId: string,
  state: AdminProfileState,
): void {
  window.dispatchEvent(new CustomEvent<AdminProfileChangeDetail>(CHANGE_EVENT, {
    detail: { amoCode, userId, state },
  }));
}

function clearExpiryTimerByKey(key: string): void {
  if (typeof window === "undefined") return;
  const timer = expiryTimers.get(key);
  if (timer !== undefined) window.clearTimeout(timer);
  expiryTimers.delete(key);
}

function clearExpiryTimer(amoCode: string, userId = currentUserId()): void {
  clearExpiryTimerByKey(storageKey(amoCode, userId));
}

function inactiveState(state: AdminProfileState): AdminProfileState {
  return {
    ...state,
    active: false,
    session_id: null,
    expires_at: null,
  };
}

function scheduleExpiry(
  amoCode: string,
  userId: string,
  state: AdminProfileState,
): void {
  if (typeof window === "undefined") return;
  const key = storageKey(amoCode, userId);
  clearExpiryTimerByKey(key);
  if (!state.active || !state.expires_at) return;

  const expiry = Date.parse(state.expires_at);
  if (!Number.isFinite(expiry)) return;
  const delay = Math.max(0, expiry - Date.now() + 25);
  const timer = window.setTimeout(() => {
    expiryTimers.delete(key);
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return;
    try {
      const current = JSON.parse(raw) as AdminProfileState;
      if (!current.active || current.session_id !== state.session_id) return;
      if (current.expires_at && Date.parse(current.expires_at) > Date.now()) {
        scheduleExpiry(amoCode, userId, current);
        return;
      }
      const expired = inactiveState(current);
      window.sessionStorage.setItem(key, JSON.stringify(expired));
      dispatchState(amoCode, userId, expired);
    } catch {
      window.sessionStorage.removeItem(key);
      dispatchState(amoCode, userId, inactiveState(state));
    }
  }, delay);
  expiryTimers.set(key, timer);
}

export function readCachedAdminProfileState(amoCode: string): AdminProfileState | null {
  if (typeof window === "undefined") return null;
  ensureAuthSessionTracking();
  const userId = currentUserId();
  const key = storageKey(amoCode, userId);
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AdminProfileState;
    if (parsed.active && parsed.expires_at && Date.parse(parsed.expires_at) <= Date.now()) {
      const expired = inactiveState(parsed);
      window.sessionStorage.setItem(key, JSON.stringify(expired));
      clearExpiryTimerByKey(key);
      return expired;
    }
    scheduleExpiry(amoCode, userId, parsed);
    return parsed;
  } catch {
    clearExpiryTimerByKey(key);
    window.sessionStorage.removeItem(key);
    return null;
  }
}

function cacheState(
  amoCode: string,
  requester: AdminProfileRequester,
  state: AdminProfileState,
): AdminProfileState {
  assertCurrentRequester(requester);
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(storageKey(amoCode, requester.userId), JSON.stringify(state));
    scheduleExpiry(amoCode, requester.userId, state);
    dispatchState(amoCode, requester.userId, state);
  }
  return state;
}

export function onAdminProfileChange(
  callback: (detail: AdminProfileChangeDetail) => void,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  ensureAuthSessionTracking();
  const listener = (event: Event) => {
    const custom = event as CustomEvent<AdminProfileChangeDetail>;
    if (custom.detail) callback(custom.detail);
  };
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

export async function fetchAdminProfileState(amoCode: string): Promise<AdminProfileState> {
  const requester = captureRequester();
  const state = await apiRequest<AdminProfileState>(apiPath(amoCode, "state"), {
    timeoutMs: 8_000,
    cacheTtlMs: 5_000,
  });
  return cacheState(amoCode, requester, state);
}

export async function activateAdminProfile(amoCode: string): Promise<AdminProfileState> {
  const requester = captureRequester();
  const state = await apiRequest<AdminProfileSessionResponse>(apiPath(amoCode, "activate"), {
    method: "POST",
    timeoutMs: 10_000,
    cacheTtlMs: 0,
  });
  return cacheState(amoCode, requester, state);
}

export async function deactivateAdminProfile(amoCode: string): Promise<AdminProfileState> {
  const requester = captureRequester();
  const state = await apiRequest<AdminProfileSessionResponse>(apiPath(amoCode, "deactivate"), {
    method: "POST",
    timeoutMs: 10_000,
    cacheTtlMs: 0,
  });
  return cacheState(amoCode, requester, state);
}

export function hasActiveTenantAdminProfile(amoCode?: string | null): boolean {
  return Boolean(amoCode && readCachedAdminProfileState(amoCode)?.active);
}

export async function listAdminAccessGrants(amoCode: string): Promise<{
  items: AdminAccessGrant[];
  required_approver_roles: ["ACCOUNTABLE_EXECUTIVE", "QUALITY_MANAGER"];
}> {
  return apiRequest(`${API_PREFIX}/${encodeURIComponent(amoCode)}/grants`, {
    timeoutMs: 12_000,
    cacheTtlMs: 0,
  });
}

export async function listAdminGrantCandidates(amoCode: string): Promise<AdminGrantCandidate[]> {
  const result = await apiRequest<{ items: AdminGrantCandidate[] }>(
    `${API_PREFIX}/${encodeURIComponent(amoCode)}/grant-candidates`,
    { timeoutMs: 12_000, cacheTtlMs: 0 },
  );
  return result.items;
}

export async function requestAdminAccessGrant(
  amoCode: string,
  payload: AdminGrantRequestPayload,
): Promise<AdminGrantDecisionResult> {
  return apiRequest(`${API_PREFIX}/${encodeURIComponent(amoCode)}/grants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: 12_000,
    cacheTtlMs: 0,
  });
}

export async function approveAdminAccessGrant(
  amoCode: string,
  grantId: string,
  comment?: string,
): Promise<AdminGrantDecisionResult> {
  return apiRequest(
    `${API_PREFIX}/${encodeURIComponent(amoCode)}/grants/${encodeURIComponent(grantId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: comment?.trim() || null }),
      timeoutMs: 12_000,
      cacheTtlMs: 0,
    },
  );
}

export async function revokeAdminAccessGrant(
  amoCode: string,
  grantId: string,
  comment?: string,
): Promise<AdminGrantDecisionResult> {
  return apiRequest(
    `${API_PREFIX}/${encodeURIComponent(amoCode)}/grants/${encodeURIComponent(grantId)}/revoke`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: comment?.trim() || null }),
      timeoutMs: 12_000,
      cacheTtlMs: 0,
    },
  );
}

export function clearCachedAdminProfileState(amoCode: string): void {
  if (typeof window === "undefined") return;
  const userId = currentUserId();
  clearExpiryTimer(amoCode, userId);
  window.sessionStorage.removeItem(storageKey(amoCode, userId));
}

export function clearAllCachedAdminProfileStates(): void {
  if (typeof window === "undefined") return;
  for (const key of [...expiryTimers.keys()]) clearExpiryTimerByKey(key);
  for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith(`${STORAGE_PREFIX}:`)) {
      window.sessionStorage.removeItem(key);
    }
  }
}
