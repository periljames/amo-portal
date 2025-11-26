// src/services/adminUsers.ts
// - Handles admin-only user management.
// - Talks to backend: backend/amodb/apps/accounts/router_admin.py
//   * POST /accounts/admin/users  -> createAdminUser
//   * GET  /accounts/admin/users  -> listAdminUsers
// - Uses authHeaders() from auth.ts so only logged-in SUPERUSER/AMO_ADMIN
//   can call these endpoints.

import { apiPost, apiGet } from "./crs";
import { authHeaders, getCachedUser } from "./auth";
import type { AccountRole, RegulatoryAuthority } from "./auth";

// Re-export these so pages can `import type { AccountRole } from "../services/adminUsers";`
export type { AccountRole, RegulatoryAuthority };

export interface AdminUserCreatePayload {
  // BACKEND: schemas.UserCreate
  amo_id?: string; // will be filled from current user if not provided

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
  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Create a user via the admin API.
 *
 * Important:
 * - Backend expects amo_id in schemas.UserCreate.
 * - For normal AMO admins, router_admin will still force amo_id to the
 *   current user's AMO, but Pydantic needs the field to exist.
 */
export async function createAdminUser(
  payload: AdminUserCreatePayload
): Promise<AdminUserRead> {
  const current = getCachedUser();

  if (!current || !current.amo_id) {
    throw new Error(
      "Could not determine your AMO. Please sign out and sign in again."
    );
  }

  const body = {
    // ensure amo_id is present; superuser could override by passing amo_id
    amo_id: payload.amo_id ?? current.amo_id,
    ...payload,
    full_name:
      (payload.full_name || "").trim() ||
      `${payload.first_name} ${payload.last_name}`.trim(),
  };

  return apiPost<AdminUserRead>(
    "/accounts/admin/users",
    JSON.stringify(body),
    {
      headers: authHeaders(),
    }
  );
}

/**
 * List users in the current AMO (or all AMOs for SUPERUSER).
 * This hits GET /accounts/admin/users.
 */
export async function listAdminUsers(
  params: { skip?: number; limit?: number; search?: string } = {}
): Promise<AdminUserRead[]> {
  const sp = new URLSearchParams();
  if (typeof params.skip === "number") sp.set("skip", String(params.skip));
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (params.search && params.search.trim()) {
    sp.set("search", params.search.trim());
  }

  const qs = sp.toString();
  const path = qs
    ? `/accounts/admin/users?${qs}`
    : "/accounts/admin/users";

  return apiGet<AdminUserRead[]>(path, {
    headers: authHeaders(),
  });
}
