import { apiRequest } from "./apiClient";

const STORAGE_PREFIX = "amo_admin_profile_session";
const CHANGE_EVENT = "amo-admin-profile-change";
const API_PREFIX = "/accounts/admin/admin-profile";

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

export function readCachedAdminProfileState(amoCode: string): AdminProfileState | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(storageKey(amoCode));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AdminProfileState;
    if (parsed.active && parsed.expires_at && Date.parse(parsed.expires_at) <= Date.now()) {
      window.sessionStorage.removeItem(storageKey(amoCode));
      return { ...parsed, active: false, session_id: null };
    }
    return parsed;
  } catch {
    window.sessionStorage.removeItem(storageKey(amoCode));
    return null;
  }
}

function cacheState(amoCode: string, state: AdminProfileState): AdminProfileState {
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(storageKey(amoCode), JSON.stringify(state));
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { amoCode, state } }));
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
  window.sessionStorage.removeItem(storageKey(amoCode));
}
