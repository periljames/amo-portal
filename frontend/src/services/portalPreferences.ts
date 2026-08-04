import { apiRequest } from "./apiClient";

export type PortalTextScale = "standard" | "large" | "extra-large";
export type PortalDensity = "comfortable" | "compact";
export type PortalMotion = "system" | "full" | "reduced";
export type PortalColorScheme = "system" | "light" | "dark";
export type PortalAccent = "tenant" | "blue" | "teal" | "green" | "amber" | "violet";

export type PortalPreferences = {
  user_id: string;
  amo_id: string | null;
  text_scale: PortalTextScale;
  density: PortalDensity;
  motion: PortalMotion;
  color_scheme: PortalColorScheme;
  accent: PortalAccent;
  version: number;
  updated_at: string | null;
};

export type PortalPreferencesPatch = Partial<Pick<
  PortalPreferences,
  "text_scale" | "density" | "motion" | "color_scheme" | "accent"
>>;

const PREFERENCES_PATH = "/auth/portal-preferences/";

export async function getPortalPreferences(): Promise<PortalPreferences> {
  return apiRequest<PortalPreferences>(PREFERENCES_PATH, {
    cacheTtlMs: 0,
    timeoutMs: 8_000,
  });
}

export async function updatePortalPreferences(
  patch: PortalPreferencesPatch,
): Promise<PortalPreferences> {
  return apiRequest<PortalPreferences>(PREFERENCES_PATH, {
    method: "PATCH",
    body: JSON.stringify(patch),
    timeoutMs: 8_000,
  });
}
