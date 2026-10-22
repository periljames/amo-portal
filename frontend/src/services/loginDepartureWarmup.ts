import { getContext, type PortalUser } from "./auth";
import { getFirstAccessibleModuleRoute } from "../utils/roleAccess";
import { preloadRoute } from "../app/routePreload";
import { rememberLoginHome } from "./loginHomeHint";

export type DeparturePhase = "idle" | "taxi" | "roll" | "rotate" | "climb" | "cruise";

export type DepartureProgress = {
  /** When true, the CTA plays the CSS takeoff sequence (not JS-tweened). */
  active: boolean;
  phase: DeparturePhase;
  label: string;
};

/** Visual takeoff length — matches login.module.css takeoff animations. */
export const TAKEOFF_MS = 1180;

const PHASE_LABELS: Record<Exclude<DeparturePhase, "idle">, string> = {
  taxi: "Cleared for departure",
  roll: "Takeoff roll",
  rotate: "Rotate",
  climb: "Climbing",
  cruise: "Airborne",
};

export function departurePhaseForPercent(percent: number): DeparturePhase {
  if (percent < 18) return "taxi";
  if (percent < 42) return "roll";
  if (percent < 62) return "rotate";
  if (percent < 90) return "climb";
  return "cruise";
}

export function departureLabel(phase: DeparturePhase): string {
  return phase === "idle" ? "Sign In" : PHASE_LABELS[phase];
}

/** Best-effort post-login warmup: never block a valid session indefinitely. */
export async function waitForLoginPreloads(
  tasks: Promise<unknown>[],
  maxWaitMs = 3_000,
): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      Promise.allSettled(tasks),
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, maxWaitMs);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

/** Authentication completion never waits for downloads, dashboard data or animation. */
export async function runLoginDepartureWarmup(options: {
 user: PortalUser; amoSlug: string; landingPath?: string;
 onProgress: (progress: DepartureProgress) => void; takeoffStartedAt: number;
}): Promise<string> {
 const home = options.landingPath?.trim() || getFirstAccessibleModuleRoute(options.amoSlug, options.user, getContext().department);
 rememberLoginHome(options.amoSlug, home);
 void preloadRoute(home).catch(() => undefined);
 return home;
}
