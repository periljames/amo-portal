import { getContext, type PortalUser } from "./auth";
import { getFirstAccessibleModuleRoute, getRoleDrivenDepartments } from "../utils/roleAccess";
import { getOperationalAccessUser } from "../utils/departmentAccess";
import { preloadRoute, scheduleWorkspaceRoutePreload } from "../app/routePreload";
import { preloadWorkspaceForUser } from "./routePreloader";
import {
  prefetchLoginLandingData,
  schedulePortalWorkspaceFleetPrefetch,
} from "./loginLandingPrefetch";
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

function postSw(type: string): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.ready
    .then((registration) => {
      registration.active?.postMessage({ type });
    })
    .catch(() => undefined);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function qualityControlRoomPath(amoSlug: string, home: string): string | null {
  if (home.includes("/quality") || home.includes("/audits/")) {
    const match = home.match(/^(.*?\/quality)(?:\/|$)/i);
    if (match?.[1]) return match[1];
    return `/maintenance/${encodeURIComponent(amoSlug)}/quality`;
  }
  return null;
}

/**
 * Critical path: Control Room data first, then home chunks. Fleet warm is background.
 */
export async function runLoginDepartureWarmup(options: {
  user: PortalUser;
  amoSlug: string;
  /** Exact post-login destination (return target / onboarding / role home). */
  landingPath?: string;
  onProgress: (progress: DepartureProgress) => void;
  takeoffStartedAt: number;
}): Promise<string> {
  const { user, amoSlug, onProgress, takeoffStartedAt } = options;
  const ctx = getContext();
  const home =
    options.landingPath?.trim()
    || getFirstAccessibleModuleRoute(amoSlug, user, ctx.department);
  const base = `/maintenance/${encodeURIComponent(amoSlug)}`;
  rememberLoginHome(amoSlug, home);

  onProgress({ active: true, phase: "rotate", label: departureLabel("rotate") });
  postSw("PRECACHE_STATIC_SHELL");
  postSw("PRECACHE_QMS");

  const controlRoomPath = qualityControlRoomPath(amoSlug, home);
  // Start Control Room API before chunk fan-out so it owns the network.
  const controlRoomData = controlRoomPath
    ? prefetchLoginLandingData({ user, amoSlug, homePath: controlRoomPath })
    : Promise.resolve();

  preloadWorkspaceForUser(user, amoSlug);

  const criticalChunks = Promise.all([
    import("../components/Layout/DepartmentLayout"),
    preloadRoute(home),
    controlRoomPath && controlRoomPath !== home.split(/[?#]/, 1)[0]
      ? preloadRoute(controlRoomPath)
      : Promise.resolve(),
  ]).catch(() => undefined);

  // Fleet warm — never blocks boarding, never races Control Room data.
  void Promise.all([
    preloadRoute(`${base}/quality`),
    preloadRoute(`${base}/quality?workspace=people`),
    preloadRoute(`${base}/quality?workspace=missions`),
    preloadRoute(`${base}/quality?workspace=intelligence`),
    preloadRoute(`${base}/quality/audits/program`),
    preloadRoute(`${base}/quality/calendar/week`),
    import("../pages/qms/QmsCanonicalPage"),
    import("../pages/qms/QmsOperationalControlCentre"),
    import("../pages/qms/QmsPeoplePage"),
    import("../pages/qms/QmsMissionsPage"),
    import("./qms"),
    preloadRoute(`${base}/training`),
    preloadRoute(`${base}/rostering`),
    preloadRoute(`${base}/maintenance`),
    preloadRoute(`${base}/admin`),
    preloadRoute(`${base}/admin/overview`),
  ]).catch(() => undefined);

  schedulePortalWorkspaceFleetPrefetch({ user, amoSlug, homePath: home });

  const operationalUser = getOperationalAccessUser(user);
  const departments = getRoleDrivenDepartments(operationalUser, ctx.department);
  if (departments.includes("document-control")) {
    void import("../pages/DocControlPages").catch(() => undefined);
  }
  if (departments.includes("planning") || departments.includes("production")) {
    void import("../pages/PlanningProductionPages").catch(() => undefined);
  }
  if (user.is_superuser || user.role === "SUPERUSER") {
    void import("../pages/platform/PlatformOperationsPage").catch(() => undefined);
  }

  scheduleWorkspaceRoutePreload(
    [
      home,
      `${base}/quality`,
      `${base}/quality?workspace=people`,
      `${base}/quality?workspace=missions`,
      `${base}/quality?workspace=intelligence`,
      `${base}/quality/audits/program`,
      `${base}/quality/calendar/week`,
      `${base}/training`,
      `${base}/rostering`,
      `${base}/admin`,
      `${base}/admin/overview`,
      `${base}/maintenance`,
      `${base}/document-control`,
    ],
    { firstDelayMs: 80 },
  );

  onProgress({ active: true, phase: "climb", label: departureLabel("climb") });
  await Promise.all([controlRoomData, criticalChunks]);

  const remaining = Math.max(0, TAKEOFF_MS - (performance.now() - takeoffStartedAt));
  if (remaining > 0) await sleep(remaining);

  onProgress({ active: true, phase: "cruise", label: departureLabel("cruise") });
  await sleep(60);
  return home;
}
