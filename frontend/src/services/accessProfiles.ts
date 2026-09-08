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
