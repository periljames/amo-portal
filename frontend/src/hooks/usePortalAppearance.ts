import { useEffect, useState } from "react";

import { getCachedUser } from "../services/auth";

export type PortalDensity = "comfortable" | "compact";
export type PortalMotion = "system" | "full" | "reduced";
export type PortalTextScale = "standard" | "large" | "extra-large";

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

function textScaleStorageKey(): string {
  const user = getCachedUser();
  return `amo_portal_text_scale:${user?.id || "anonymous"}:${user?.amo_id || "platform"}`;
}

function readTextScale(): PortalTextScale {
  if (typeof window === "undefined") return "standard";
  const saved = window.localStorage.getItem(textScaleStorageKey());
  return saved === "large" || saved === "extra-large" ? saved : "standard";
}

function applyAppearance(density: PortalDensity, motion: PortalMotion, textScale = readTextScale()): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.portalDensity = density;
  document.body.dataset.portalDensity = density;
  document.documentElement.dataset.portalMotion = motion;
  document.body.dataset.portalMotion = motion;
  document.documentElement.dataset.portalTextScale = textScale;
  document.body.dataset.portalTextScale = textScale;
}

export function initialisePortalAppearance(): void {
  applyAppearance(readDensity(), readMotion(), readTextScale());
}

// DepartmentLayout imports this module before React commits the shell. Applying
// the stored values here avoids a comfortable/full-motion/small-text flash before
// the hooks and account preference synchronisation run.
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
