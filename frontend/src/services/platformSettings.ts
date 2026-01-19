// src/services/platformSettings.ts
// - Platform-wide settings for superusers.

import { authHeaders } from "./auth";
import { apiGet, apiPut } from "./crs";

export type PlatformSettings = {
  id: number;
  api_base_url?: string | null;
  acme_directory_url?: string | null;
  acme_client?: string | null;
  certificate_status?: string | null;
  certificate_issuer?: string | null;
  certificate_expires_at?: string | null;
  last_renewed_at?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type PlatformSettingsUpdate = Partial<
  Pick<
    PlatformSettings,
    | "api_base_url"
    | "acme_directory_url"
    | "acme_client"
    | "certificate_status"
    | "certificate_issuer"
    | "certificate_expires_at"
    | "last_renewed_at"
    | "notes"
  >
>;

export async function fetchPlatformSettings(): Promise<PlatformSettings> {
  return apiGet<PlatformSettings>("/accounts/admin/platform-settings", {
    headers: authHeaders(),
  });
}

export async function updatePlatformSettings(
  payload: PlatformSettingsUpdate
): Promise<PlatformSettings> {
  return apiPut<PlatformSettings>("/accounts/admin/platform-settings", payload, {
    headers: authHeaders(),
  });
}
