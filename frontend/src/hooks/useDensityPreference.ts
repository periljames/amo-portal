import { useEffect, useState } from "react";

export type ViewDensity = "compact" | "comfortable";

const STORAGE_PREFIX = "qms.view-density";

export function useDensityPreference(scope: string, defaultDensity: ViewDensity = "compact") {
  const storageKey = `${STORAGE_PREFIX}.${scope}`;
  const [density, setDensity] = useState<ViewDensity>(() => {
    if (typeof window === "undefined") return defaultDensity;
    const stored = window.localStorage.getItem(storageKey);
    return stored === "compact" || stored === "comfortable" ? stored : defaultDensity;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(storageKey, density);
  }, [density, storageKey]);

  return { density, setDensity };
}
