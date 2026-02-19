import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getApiBaseUrl } from "../../services/config";
import { getToken, handleAuthFailure } from "../../services/auth";

export type TenantBranding = {
  tenantSlug: string;
  preferredName: string;
  logoUrl: string | null;
  faviconUrl: string | null;
  accentColor: string;
  accentColor2: string | null;
  themeDefault: "dark" | "light";
  reader: {
    paperColor: string;
    inkColor: string;
    bgColor: string;
    headerStyle: "solid" | "blur";
    headerBlur: boolean;
    cornerRadius: "md" | "lg" | "xl";
    density: "comfortable" | "compact";
  };
};

const defaultBranding: TenantBranding = {
  tenantSlug: "",
  preferredName: "Manuals",
  logoUrl: null,
  faviconUrl: null,
  accentColor: "#0EA5E9",
  accentColor2: null,
  themeDefault: "light",
  reader: {
    paperColor: "#FFFFFF",
    inkColor: "#0F172A",
    bgColor: "#F1F5F9",
    headerStyle: "blur",
    headerBlur: true,
    cornerRadius: "lg",
    density: "comfortable",
  },
};

const BrandingContext = createContext<TenantBranding>(defaultBranding);

export function TenantBrandingProvider({ tenantSlug, children }: { tenantSlug: string; children: React.ReactNode }) {
  const [branding, setBranding] = useState<TenantBranding>({ ...defaultBranding, tenantSlug });

  useEffect(() => {
    if (!tenantSlug) return;
    const token = getToken();
    fetch(`${getApiBaseUrl()}/api/tenants/${tenantSlug}/branding`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
      .then(async (res) => {
        if (!res.ok) {
          if (res.status === 401) handleAuthFailure();
          throw new Error("branding fetch failed");
        }
        return (await res.json()) as TenantBranding;
      })
      .then(setBranding)
      .catch(() => setBranding((prev) => ({ ...prev, tenantSlug })));
  }, [tenantSlug]);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--tenant-accent", branding.accentColor);
    root.style.setProperty("--tenant-bg", branding.reader.bgColor);
    root.style.setProperty("--paper", branding.reader.paperColor);
    root.style.setProperty("--ink", branding.reader.inkColor);
  }, [branding]);

  const value = useMemo(() => branding, [branding]);
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export function useTenantBranding() {
  return useContext(BrandingContext);
}
