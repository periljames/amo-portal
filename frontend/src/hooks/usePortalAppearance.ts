import { useEffect, useState } from "react";

export type PortalDensity = "comfortable" | "compact";
export type PortalMotion = "system" | "full" | "reduced";

const DENSITY_KEY = "amo_portal_density";
const MOTION_KEY = "amo_portal_motion";

function readDensity(): PortalDensity {
  if (typeof window === "undefined") return "comfortable";
  return window.localStorage.getItem(DENSITY_KEY) === "compact" ? "compact" : "comfortable";
}

function readMotion(): PortalMotion {
  if (typeof window === "undefined") return "system";
  const saved = window.localStorage.getItem(MOTION_KEY);
  return saved === "full" || saved === "reduced" ? saved : "system";
}

function applyAppearance(density: PortalDensity, motion: PortalMotion): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.portalDensity = density;
  document.body.dataset.portalDensity = density;
  document.documentElement.dataset.portalMotion = motion;
  document.body.dataset.portalMotion = motion;
}

export function initialisePortalAppearance(): void {
  applyAppearance(readDensity(), readMotion());
}

// DepartmentLayout imports this module before React commits the shell. Applying
// the stored values here avoids a comfortable/full-motion flash before the hook
// effects run, while the hook remains the only writer after user interaction.
initialisePortalAppearance();

export function usePortalAppearance() {
  const [density, setDensity] = useState<PortalDensity>(readDensity);
  const [motion, setMotion] = useState<PortalMotion>(readMotion);

  useEffect(() => {
    applyAppearance(density, motion);
    window.localStorage.setItem(DENSITY_KEY, density);
    window.localStorage.setItem(MOTION_KEY, motion);
  }, [density, motion]);

  return { density, setDensity, motion, setMotion };
}
