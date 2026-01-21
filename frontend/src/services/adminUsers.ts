// src/services/adminUsers.ts
// - Handles admin-only user management.
// - Talks to backend: backend/amodb/apps/accounts/router_admin.py
//   * POST /accounts/admin/users  -> createAdminUser
//   * GET  /accounts/admin/users  -> listAdminUsers (supports amo_id, skip, limit, search)
//   * GET  /accounts/admin/amos   -> listAdminAmos (SUPERUSER only)
// - Uses authHeaders() from auth.ts so only logged-in SUPERUSER/AMO_ADMIN
//   can call these endpoints.

import { apiPost, apiGet } from "./crs";
import { authHeaders, getCachedUser } from "./auth";
import type { AccountRole, RegulatoryAuthority } from "./auth";

// Re-export these so pages can `import type { AccountRole } from "../services/adminUsers";`
export type { AccountRole, RegulatoryAuthority };

export interface AdminUserCreatePayload {
  // BACKEND: schemas.UserCreate
  amo_id?: string; // optional override (superuser only), otherwise resolved from context

  staff_code: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name?: string;
  role: AccountRole;
  position_title?: string;
  phone?: string;
  department_id?: string | null;

  regulatory_authority?: RegulatoryAuthority | null;
  licence_number?: string | null;
  licence_state_or_country?: string | null;
  licence_expires_on?: string | null; // ISO date string (YYYY-MM-DD)

  password: string;
}

/**
 * Shape of the user returned by /accounts/admin/users.
 * Kept in sync with UserRead from the backend.
 */
export interface AdminUserRead {
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

/**
 * AMO type returned by GET /accounts/admin/amos (SUPERUSER only).
 * (Matches backend AMORead shape.)
 */
export interface AdminAmoRead {
  id: string;
  amo_code: string;
  name: string;
  login_slug: string;
  icao_code?: string | null;
  country?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  time_zone?: string | null;
  is_demo?: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AdminAmoCreatePayload {
  amo_code: string;
  name: string;
  login_slug: string;
  icao_code?: string | null;
  country?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  time_zone?: string | null;
  is_demo?: boolean;
}

export type DataMode = "DEMO" | "REAL";

export interface AdminContext {
  user_id: string;
  active_amo_id: string | null;
  data_mode: DataMode;
  last_real_amo_id: string | null;
  updated_at: string;
}

/**
 * Optional support: store the current "admin context" AMO in localStorage.
 * Useful for SUPERUSER support workflows (switch AMO without re-login).
 *
 * Note: stores amo_id, not amoCode/login_slug.
 */
export const LS_ACTIVE_AMO_ID = "amodb_active_amo_id";

// Optional backward/alternate key support (in case you already used another one elsewhere)
const ACTIVE_AMO_ID_KEY_ALT = "amodb_admin_active_amo_id";

export function setActiveAmoId(amoId: string) {
  const v = (amoId || "").trim();
  if (!v) return;
  localStorage.setItem(LS_ACTIVE_AMO_ID, v);
  // keep alt key in sync if it exists in your app already
  localStorage.setItem(ACTIVE_AMO_ID_KEY_ALT, v);
}

export function getActiveAmoId(): string | null {
  const primary = localStorage.getItem(LS_ACTIVE_AMO_ID);
  if (primary && primary.trim()) return primary.trim();

  const alt = localStorage.getItem(ACTIVE_AMO_ID_KEY_ALT);
  return alt && alt.trim() ? alt.trim() : null;
}

export function clearActiveAmoId() {
  localStorage.removeItem(LS_ACTIVE_AMO_ID);
  localStorage.removeItem(ACTIVE_AMO_ID_KEY_ALT);
}

export async function getAdminContext(): Promise<AdminContext> {
  return apiGet<AdminContext>("/accounts/admin/context", {
    headers: authHeaders(),
  });
}

export async function setAdminContext(payload: {
  active_amo_id?: string | null;
  data_mode?: DataMode;
}): Promise<AdminContext> {
  return apiPost<AdminContext>(
    "/accounts/admin/context",
    JSON.stringify(payload),
    { headers: authHeaders() }
  );
}

type CreateOptions = {
  /**
   * Target AMO id override (SUPERUSER only).
   * If omitted, falls back to:
   *  - payload.amo_id
   *  - active AMO id from localStorage
   *  - current logged-in user's amo_id
   */
  amoId?: string;
};

function resolveTargetAmoId(
  payload: AdminUserCreatePayload,
  opts?: CreateOptions
): string {
  const current = getCachedUser();

  if (!current) {
    throw new Error("You are not logged in. Please sign in again.");
  }

  const currentAmoId = (current as any).amo_id as string | undefined;
  const isSuperuser = !!(current as any).is_superuser;

  const candidate =
    (payload.amo_id || "").trim() ||
    (opts?.amoId || "").trim() ||
    (getActiveAmoId() || "").trim() ||
    (currentAmoId || "").trim();

  if (!candidate) {
    throw new Error(
      "Could not determine the target AMO. Please sign out and sign in again."
    );
  }

  // Non-superusers must never target another AMO.
  if (!isSuperuser) {
    if (!currentAmoId) {
      throw new Error(
        "Could not determine your AMO. Please sign out and sign in again."
      );
    }
    if (candidate !== currentAmoId) {
      throw new Error("You do not have permission to create users in this AMO.");
    }
  }

  return candidate;
}

/**
 * Create a user via the admin API.
 *
 * Notes:
 * - Backend expects amo_id in schemas.UserCreate.
 * - For normal AMO admins, server enforces amo_id == current user's AMO.
 * - For SUPERUSER, we allow explicit targeting by passing amo_id.
 */
export async function createAdminUser(
  payload: AdminUserCreatePayload,
  opts?: CreateOptions
): Promise<AdminUserRead> {
  const targetAmoId = resolveTargetAmoId(payload, opts);

  const fullName =
    (payload.full_name || "").trim() ||
    `${payload.first_name} ${payload.last_name}`.trim();

  const body: AdminUserCreatePayload = {
    ...payload,
    amo_id: targetAmoId, // force resolved value into the request
    full_name: fullName,
  };

  return apiPost<AdminUserRead>("/accounts/admin/users", JSON.stringify(body), {
    headers: authHeaders(),
  });
}

type ListParams = {
  /**
   * For SUPERUSER: you can request users for a specific AMO.
   * If omitted (and SUPERUSER), we fall back to active AMO id or user's own AMO.
   * For non-superusers, this is ignored client-side (not sent).
   */
  amo_id?: string;

  skip?: number;
  limit?: number;
  search?: string;
};

type ListOptions = {
  signal?: AbortSignal;
};

function resolveListAmoId(params?: ListParams): string | undefined {
  const current = getCachedUser();
  if (!current) return undefined;

  const currentAmoId = (current as any).amo_id as string | undefined;
  const isSuperuser = !!(current as any).is_superuser;

  if (!isSuperuser) {
    // Never send amo_id for non-superusers (prevents accidental cross-AMO calls)
    return undefined;
  }

  const candidate =
    (params?.amo_id || "").trim() ||
    (getActiveAmoId() || "").trim() ||
    (currentAmoId || "").trim();

  return candidate || undefined;
}

/**
 * List users in the current AMO (or selected AMO for SUPERUSER).
 * This hits GET /accounts/admin/users and supports:
 * - amo_id (superuser only)
 * - skip / limit / search
 */
export async function listAdminUsers(
  params: ListParams = {},
  options: ListOptions = {}
): Promise<AdminUserRead[]> {
  const sp = new URLSearchParams();

  const amoId = resolveListAmoId(params);
  if (amoId) sp.set("amo_id", amoId);

  if (typeof params.skip === "number") sp.set("skip", String(params.skip));
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (params.search && params.search.trim()) {
    sp.set("search", params.search.trim());
  }

  const qs = sp.toString();
  const path = qs ? `/accounts/admin/users?${qs}` : "/accounts/admin/users";

  return apiGet<AdminUserRead[]>(path, {
    headers: authHeaders(),
    signal: options.signal,
  });
}

/**
 * SUPERUSER ONLY: list all AMOs for the AMO picker.
 * GET /accounts/admin/amos
 */
export async function listAdminAmos(): Promise<AdminAmoRead[]> {
  return apiGet<AdminAmoRead[]>("/accounts/admin/amos", {
    headers: authHeaders(),
  });
}

/**
 * SUPERUSER ONLY: create an AMO.
 * POST /accounts/admin/amos
 */
export async function createAdminAmo(
  payload: AdminAmoCreatePayload
): Promise<AdminAmoRead> {
  return apiPost<AdminAmoRead>("/accounts/admin/amos", JSON.stringify(payload), {
    headers: authHeaders(),
  });
}
