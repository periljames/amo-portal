// src/services/branding.ts

export type BrandContext = {
  name?: string | null;
  tagline?: string | null;
  accent?: string | null;
  accentSoft?: string | null;
  accentSecondary?: string | null;
  logoUrl?: string | null;
  logoUrlDark?: string | null;
  logoUrlLight?: string | null;
  updatedAt?: string | null;
};

const BRAND_STORAGE_KEY = "amo_brand_context";
export const BRANDING_EVENT = "amo_branding_change";

export function getBrandContext(): BrandContext {
  if (typeof window === "undefined") return {};
  const raw = window.localStorage.getItem(BRAND_STORAGE_KEY);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as BrandContext;
  } catch {
    return {};
  }
}

export function setBrandContext(ctx: BrandContext): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(BRAND_STORAGE_KEY, JSON.stringify(ctx));
  window.dispatchEvent(new Event(BRANDING_EVENT));
}

export function clearBrandContext(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(BRAND_STORAGE_KEY);
  window.dispatchEvent(new Event(BRANDING_EVENT));
}
