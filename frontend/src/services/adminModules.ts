// src/services/adminModules.ts
// - Handles per-AMO module subscriptions (admin/superuser).

import { apiGet, apiPost } from "./crs";
import { authHeaders } from "./auth";

export type ModuleSubscriptionStatus = "ENABLED" | "DISABLED" | "TRIAL" | "SUSPENDED";

export interface ModuleSubscriptionRead {
  id: string;
  amo_id: string;
  module_code: string;
  status: ModuleSubscriptionStatus;
  effective_from?: string | null;
  effective_to?: string | null;
  plan_code?: string | null;
  metadata_json?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ModuleSubscriptionCreate {
  module_code: string;
  status: ModuleSubscriptionStatus;
  plan_code?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  metadata_json?: string | null;
}

export async function listTenantModules(tenantId: string): Promise<ModuleSubscriptionRead[]> {
  return apiGet<ModuleSubscriptionRead[]>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/modules`,
    { headers: authHeaders() }
  );
}

export async function enableTenantModule(
  tenantId: string,
  moduleCode: string,
  payload?: Partial<ModuleSubscriptionCreate>
): Promise<ModuleSubscriptionRead> {
  return apiPost<ModuleSubscriptionRead>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/modules/${encodeURIComponent(
      moduleCode
    )}/enable`,
    payload ?? {},
    { headers: authHeaders() }
  );
}

export async function disableTenantModule(
  tenantId: string,
  moduleCode: string
): Promise<ModuleSubscriptionRead> {
  return apiPost<ModuleSubscriptionRead>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/modules/${encodeURIComponent(
      moduleCode
    )}/disable`,
    {},
    { headers: authHeaders() }
  );
}
