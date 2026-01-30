// src/services/platformSettings.ts
// - Platform-wide settings for superusers.

import { authHeaders, getToken, handleAuthFailure } from "./auth";
import { apiGet, apiPut } from "./crs";
import { getApiBaseUrl } from "./config";

export type PlatformSettings = {
  id: number;
  api_base_url?: string | null;
  platform_name?: string | null;
  platform_tagline?: string | null;
  brand_accent?: string | null;
  brand_accent_soft?: string | null;
  brand_accent_secondary?: string | null;
  platform_logo_filename?: string | null;
  platform_logo_content_type?: string | null;
  platform_logo_uploaded_at?: string | null;
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
    | "platform_name"
    | "platform_tagline"
    | "brand_accent"
    | "brand_accent_soft"
    | "brand_accent_secondary"
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

function buildAuthHeader(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function uploadPlatformLogo(file: File): Promise<PlatformSettings> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${getApiBaseUrl()}/accounts/admin/platform-assets/logo`, {
    method: "POST",
    headers: buildAuthHeader(),
    body: form,
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }

  return (await res.json()) as PlatformSettings;
}

export async function fetchPlatformLogoBlob(): Promise<Blob | null> {
  const res = await fetch(`${getApiBaseUrl()}/accounts/admin/platform-assets/logo`, {
    method: "GET",
    headers: authHeaders(),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }

  return await res.blob();
}
