import { apiRequest } from "./apiClient";
import { getCachedUser } from "./auth";

const STORAGE_PREFIX = "amo_admin_profile_session";
const CHANGE_EVENT = "amo-admin-profile-change";
const API_PREFIX = "/accounts/admin/admin-profile";
const expiryTimers = new Map<string, number>();

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

type AdminProfileSessionResponse = AdminProfileState & {
  message?: string | null;
};

function currentUserId(): string {
  try {
    return getCachedUser()?.id || "anonymous";
  } catch {
    return "anonymous";
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

function cacheState(amoCode: string, state: AdminProfileState): AdminProfileState {
  if (typeof window !== "undefined") {
    const userId = currentUserId();
    window.sessionStorage.setItem(storageKey(amoCode, userId), JSON.stringify(state));
    scheduleExpiry(amoCode, userId, state);
    dispatchState(amoCode, userId, state);
  }
  return state;
}

export function onAdminProfileChange(
  callback: (detail: AdminProfileChangeDetail) => void,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  const listener = (event: Event) => {
    const custom = event as CustomEvent<AdminProfileChangeDetail>;
    if (custom.detail) callback(custom.detail);
  };
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

export async function fetchAdminProfileState(amoCode: string): Promise<AdminProfileState> {
  const state = await apiRequest<AdminProfileState>(apiPath(amoCode, "state"), {
    timeoutMs: 8_000,
    cacheTtlMs: 5_000,
  });
  return cacheState(amoCode, state);
}

export async function activateAdminProfile(amoCode: string): Promise<AdminProfileState> {
  const state = await apiRequest<AdminProfileSessionResponse>(apiPath(amoCode, "activate"), {
    method: "POST",
    timeoutMs: 10_000,
    cacheTtlMs: 0,
  });
  return cacheState(amoCode, state);
}

export async function deactivateAdminProfile(amoCode: string): Promise<AdminProfileState> {
  const state = await apiRequest<AdminProfileSessionResponse>(apiPath(amoCode, "deactivate"), {
    method: "POST",
    timeoutMs: 10_000,
    cacheTtlMs: 0,
  });
  return cacheState(amoCode, state);
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
