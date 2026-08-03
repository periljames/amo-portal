import { apiRequest } from "./apiClient";

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

type AdminProfileSessionResponse = AdminProfileState & {
  message?: string | null;
};

function storageKey(amoCode: string): string {
  return `${STORAGE_PREFIX}:${amoCode.toLowerCase()}`;
}

function apiPath(amoCode: string, action: "state" | "activate" | "deactivate"): string {
  return `${API_PREFIX}/${encodeURIComponent(amoCode)}/${action}`;
}

function dispatchState(amoCode: string, state: AdminProfileState): void {
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { amoCode, state } }));
}

function clearExpiryTimer(amoCode: string): void {
  if (typeof window === "undefined") return;
  const key = amoCode.toLowerCase();
  const timer = expiryTimers.get(key);
  if (timer !== undefined) window.clearTimeout(timer);
  expiryTimers.delete(key);
}

function inactiveState(state: AdminProfileState): AdminProfileState {
  return {
    ...state,
    active: false,
    session_id: null,
    expires_at: null,
  };
}

function scheduleExpiry(amoCode: string, state: AdminProfileState): void {
  if (typeof window === "undefined") return;
  clearExpiryTimer(amoCode);
  if (!state.active || !state.expires_at) return;

  const expiry = Date.parse(state.expires_at);
  if (!Number.isFinite(expiry)) return;
  const delay = Math.max(0, expiry - Date.now() + 25);
  const key = amoCode.toLowerCase();
  const timer = window.setTimeout(() => {
    expiryTimers.delete(key);
    const raw = window.sessionStorage.getItem(storageKey(amoCode));
    if (!raw) return;
    try {
      const current = JSON.parse(raw) as AdminProfileState;
      if (!current.active || current.session_id !== state.session_id) return;
      if (current.expires_at && Date.parse(current.expires_at) > Date.now()) {
        scheduleExpiry(amoCode, current);
        return;
      }
      const expired = inactiveState(current);
      window.sessionStorage.setItem(storageKey(amoCode), JSON.stringify(expired));
      dispatchState(amoCode, expired);
    } catch {
      window.sessionStorage.removeItem(storageKey(amoCode));
      dispatchState(amoCode, inactiveState(state));
    }
  }, delay);
  expiryTimers.set(key, timer);
}

export function readCachedAdminProfileState(amoCode: string): AdminProfileState | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(storageKey(amoCode));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AdminProfileState;
    if (parsed.active && parsed.expires_at && Date.parse(parsed.expires_at) <= Date.now()) {
      const expired = inactiveState(parsed);
      window.sessionStorage.setItem(storageKey(amoCode), JSON.stringify(expired));
      clearExpiryTimer(amoCode);
      return expired;
    }
    scheduleExpiry(amoCode, parsed);
    return parsed;
  } catch {
    clearExpiryTimer(amoCode);
    window.sessionStorage.removeItem(storageKey(amoCode));
    return null;
  }
}

function cacheState(amoCode: string, state: AdminProfileState): AdminProfileState {
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(storageKey(amoCode), JSON.stringify(state));
    scheduleExpiry(amoCode, state);
    dispatchState(amoCode, state);
  }
  return state;
}

export function onAdminProfileChange(
  callback: (detail: { amoCode: string; state: AdminProfileState }) => void,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  const listener = (event: Event) => {
    const custom = event as CustomEvent<{ amoCode: string; state: AdminProfileState }>;
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
  clearExpiryTimer(amoCode);
  window.sessionStorage.removeItem(storageKey(amoCode));
}
