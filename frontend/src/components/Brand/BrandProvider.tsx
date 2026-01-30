// src/components/Brand/BrandProvider.tsx
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { getActiveAmoId } from "../../services/adminUsers";
import { fetchAmoLogoBlob } from "../../services/amoAssets";
import { fetchPlatformLogoBlob, fetchPlatformSettings } from "../../services/platformSettings";
import { getCachedUser, getToken } from "../../services/auth";
import { getBrandContext, setBrandContext, BRANDING_EVENT } from "../../services/branding";
import { BrandContext, type BrandContextValue, type BrandTheme } from "./BrandContext";

type BrandProviderProps = {
  children: React.ReactNode;
  nameOverride?: string | null;
  logoUrlOverride?: string | null;
  preferStoredName?: boolean;
  logoSource?: "amo" | "platform";
};

const DEFAULT_BRAND: BrandTheme = {
  name: "Safarilink",
  accent: "#22c55e",
  accentSoft: "rgba(34, 197, 94, 0.1)",
  accentSecondary: "#16a34a",
  logoUrl: null,
};

function resolveBrandTheme(
  nameOverride?: string | null,
  logoUrlOverride?: string | null,
  preferStoredName = true
): BrandTheme {
  const stored = getBrandContext();
  const resolvedName = preferStoredName
    ? stored.name || nameOverride
    : nameOverride || stored.name;
  return {
    ...DEFAULT_BRAND,
    name: (resolvedName || DEFAULT_BRAND.name || "").trim() || DEFAULT_BRAND.name,
    tagline: stored.tagline || null,
    accent: (stored.accent || DEFAULT_BRAND.accent).trim(),
    accentSoft: (stored.accentSoft || DEFAULT_BRAND.accentSoft).trim(),
    accentSecondary: (stored.accentSecondary || DEFAULT_BRAND.accentSecondary).trim(),
    logoUrl: logoUrlOverride || null,
  };
}

function resolveAmoId(): string | null {
  const user = getCachedUser();
  if (!user) return null;
  if (user.is_superuser) {
    return getActiveAmoId() || user.amo_id || null;
  }
  return user.amo_id || null;
}

export const BrandProvider: React.FC<BrandProviderProps> = ({
  children,
  nameOverride,
  logoUrlOverride,
  preferStoredName = true,
  logoSource = "amo",
}) => {
  const [brandVersion, setBrandVersion] = useState(0);
  const [logoUrl, setLogoUrl] = useState<string | null>(logoUrlOverride || null);
  const [hasCustomLogo, setHasCustomLogo] = useState(false);
  const logoUrlRef = useRef<string | null>(null);
  const platformBrandLoadedRef = useRef(false);

  const brandTheme = useMemo(
    () => resolveBrandTheme(nameOverride, logoUrlOverride, preferStoredName),
    [nameOverride, logoUrlOverride, preferStoredName, brandVersion]
  );

  const amoId = useMemo(() => resolveAmoId(), [brandVersion]);

  useLayoutEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    root.style.setProperty("--brand-name", brandTheme.name);
    root.style.setProperty("--brand-tagline", brandTheme.tagline || "");
    root.style.setProperty("--brand-accent", brandTheme.accent);
    root.style.setProperty("--brand-accent-soft", brandTheme.accentSoft);
    root.style.setProperty("--brand-accent-secondary", brandTheme.accentSecondary);
  }, [brandTheme]);

  useEffect(() => {
    if (logoUrlOverride) {
      setLogoUrl(logoUrlOverride);
      setHasCustomLogo(true);
      return;
    }

    const token = getToken();
    if (!token || (!amoId && logoSource === "amo")) {
      if (logoUrlRef.current) {
        window.URL.revokeObjectURL(logoUrlRef.current);
        logoUrlRef.current = null;
      }
      setLogoUrl(null);
      setHasCustomLogo(false);
      return;
    }

    let mounted = true;

    const loadLogo = async () => {
      try {
        const blob =
          logoSource === "platform"
            ? await fetchPlatformLogoBlob()
            : await fetchAmoLogoBlob(amoId);
        if (!blob) {
          if (mounted) {
            setLogoUrl(null);
            setHasCustomLogo(false);
          }
          return;
        }
        const nextUrl = window.URL.createObjectURL(blob);
        if (logoUrlRef.current) {
          window.URL.revokeObjectURL(logoUrlRef.current);
        }
        logoUrlRef.current = nextUrl;
        if (mounted) {
          setLogoUrl(nextUrl);
          setHasCustomLogo(true);
        }
      } catch {
        if (mounted) {
          setLogoUrl(null);
          setHasCustomLogo(false);
        }
      }
    };

    void loadLogo();

    return () => {
      mounted = false;
    };
  }, [logoUrlOverride, amoId, logoSource]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleBrandingChange = () => {
      setBrandVersion((prev) => prev + 1);
    };

    window.addEventListener(BRANDING_EVENT, handleBrandingChange);
    return () => {
      window.removeEventListener(BRANDING_EVENT, handleBrandingChange);
    };
  }, []);

  useEffect(() => {
    if (logoSource !== "platform") return;
    if (platformBrandLoadedRef.current) return;
    if (!getToken()) return;

    const stored = getBrandContext();
    if (stored.name || stored.tagline) {
      platformBrandLoadedRef.current = true;
      return;
    }

    fetchPlatformSettings()
      .then((data) => {
        setBrandContext({
          name: data.platform_name || "AMO Portal",
          tagline: data.platform_tagline || null,
          accent: data.brand_accent || null,
          accentSoft: data.brand_accent_soft || null,
          accentSecondary: data.brand_accent_secondary || null,
        });
      })
      .finally(() => {
        platformBrandLoadedRef.current = true;
      });
  }, [logoSource]);

  useEffect(() => {
    return () => {
      if (logoUrlRef.current) {
        window.URL.revokeObjectURL(logoUrlRef.current);
        logoUrlRef.current = null;
      }
    };
  }, []);

  const value: BrandContextValue = {
    ...brandTheme,
    logoUrl,
    hasCustomLogo,
  };

  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
};
