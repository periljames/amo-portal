import { apiGet, apiPost, apiPut } from "./crs";
import type { AccountRole } from "./auth";

export type ModuleAccessLevel = "view" | "manage";

export type AccessModule = {
  code: string;
  label: string;
  category: string;
  description: string;
};

export type TenantAccessProfile = {
  id: string;
  amo_id: string;
  code: string;
  display_name: string;
  base_role_key: AccountRole;
  category: string;
  reports_to_role_code: string | null;
  description: string | null;
  is_system: boolean;
  is_regulated: boolean;
  is_editable: boolean;
  is_active: boolean;
  version: number;
  module_permissions: Record<string, ModuleAccessLevel>;
  assigned_user_count: number;
};

export type TenantAccessProfileOption = Pick<
  TenantAccessProfile,
  "id" | "code" | "display_name" | "base_role_key" | "category" | "is_regulated"
>;

export type TenantAccessFramework = {
  source: string;
  modules: AccessModule[];
  profiles: TenantAccessProfile[];
  initialized: boolean;
};

export type AccessProfileCreate = {
  code: string;
  display_name: string;
  base_role_key: AccountRole;
  category: string;
  reports_to_role_code?: string | null;
  description?: string | null;
  module_permissions: Record<string, ModuleAccessLevel>;
};

export type AccessProfileUpdate = Partial<Omit<AccessProfileCreate, "code">> & {
  expected_version: number;
  is_active?: boolean;
};

export type AccessElevationStatus = "PENDING" | "APPROVED" | "DENIED" | "CANCELLED";

export type AccessElevationRequest = {
  id: string;
  amo_id: string;
  user_id: string;
  current_profile_id: string | null;
  requested_profile_id: string;
  requested_by_user_id: string;
  reason: string;
  status: AccessElevationStatus;
  decision_note: string | null;
  decided_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  user_name?: string | null;
  user_email?: string | null;
  staff_code?: string | null;
  current_profile_name?: string | null;
  requested_profile_name?: string | null;
  requested_profile_code?: string | null;
  requested_base_role_key?: string | null;
  decided_by_name?: string | null;
};

export type AccessElevationRequestList = { items: AccessElevationRequest[] };

export function getTenantAccessFramework(amoId?: string | null): Promise<TenantAccessFramework> {
  const query = amoId ? `?amo_id=${encodeURIComponent(amoId)}` : "";
  return apiGet<TenantAccessFramework>(`/accounts/admin/access-framework${query}`);
}

export function getActiveTenantAccessProfiles(): Promise<TenantAccessProfileOption[]> {
  return apiGet<TenantAccessProfileOption[]>("/auth/access-profiles");
}

export function initializeTenantAccessFramework(amoId?: string | null): Promise<{
  created: number;
  repaired: number;
  assigned: number;
  total: number;
}> {
  const query = amoId ? `?amo_id=${encodeURIComponent(amoId)}` : "";
  return apiPost(`/accounts/admin/access-framework/initialize${query}`, JSON.stringify({}));
}

export function createTenantAccessProfile(payload: AccessProfileCreate, amoId?: string | null): Promise<TenantAccessProfile> {
  const query = amoId ? `?amo_id=${encodeURIComponent(amoId)}` : "";
  return apiPost<TenantAccessProfile>(`/accounts/admin/access-profiles${query}`, JSON.stringify(payload));
}

export function updateTenantAccessProfile(
  profileId: string,
  payload: AccessProfileUpdate,
  amoId?: string | null,
): Promise<TenantAccessProfile> {
  const query = amoId ? `?amo_id=${encodeURIComponent(amoId)}` : "";
  return apiPut<TenantAccessProfile>(
    `/accounts/admin/access-profiles/${encodeURIComponent(profileId)}${query}`,
    JSON.stringify(payload),
  );
}

export function assignUserAccessProfile(
  userId: string,
  accessProfileId: string,
  amoId?: string | null,
): Promise<unknown> {
  const query = amoId ? `?amo_id=${encodeURIComponent(amoId)}` : "";
  return apiPut(
    `/accounts/admin/users/${encodeURIComponent(userId)}/access-profile${query}`,
    JSON.stringify({ access_profile_id: accessProfileId }),
  );
}

export function listMyAccessElevationRequests(): Promise<AccessElevationRequestList> {
  return apiGet<AccessElevationRequestList>("/auth/access-elevation-requests");
}

export function requestAccessElevation(
  requestedProfileId: string,
  reason: string,
): Promise<AccessElevationRequest> {
  return apiPost<AccessElevationRequest>(
    "/auth/access-elevation-requests",
    JSON.stringify({ requested_profile_id: requestedProfileId, reason }),
  );
}

export function cancelAccessElevationRequest(requestId: string): Promise<{ id: string; status: AccessElevationStatus }> {
  return apiPost(
    `/auth/access-elevation-requests/${encodeURIComponent(requestId)}/cancel`,
    JSON.stringify({}),
  );
}

export function listAdminAccessElevationRequests(
  status: AccessElevationStatus | "ALL" = "PENDING",
): Promise<AccessElevationRequestList> {
  const query = status === "ALL" ? "?status=" : `?status=${encodeURIComponent(status)}`;
  return apiGet<AccessElevationRequestList>(`/accounts/admin/access-elevation-requests${query}`);
}

export function decideAccessElevationRequest(
  requestId: string,
  decision: "APPROVE" | "DENY",
  note?: string,
): Promise<AccessElevationRequest> {
  return apiPost<AccessElevationRequest>(
    `/accounts/admin/access-elevation-requests/${encodeURIComponent(requestId)}/decision`,
    JSON.stringify({ decision, note: note?.trim() || null }),
  );
}
