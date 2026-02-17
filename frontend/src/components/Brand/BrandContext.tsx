// src/components/Brand/BrandContext.tsx
import React from "react";

export type BrandTheme = {
  name: string;
  tagline?: string | null;
  accent: string;
  accentSoft: string;
  accentSecondary: string;
  logoUrl?: string | null;
  logoUrlDark?: string | null;
  logoUrlLight?: string | null;
  updatedAt?: string | null;
};

export type BrandContextValue = BrandTheme & {
  hasCustomLogo: boolean;
};

export const BrandContext = React.createContext<BrandContextValue>({
  name: "AMO Portal",
  tagline: null,
  accent: "#2563eb",
  accentSoft: "rgba(37, 99, 235, 0.08)",
  accentSecondary: "#1d4ed8",
  logoUrl: null,
  logoUrlDark: null,
  logoUrlLight: null,
  updatedAt: null,
  hasCustomLogo: false,
});
