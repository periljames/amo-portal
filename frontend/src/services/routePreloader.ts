// src/services/routePreloader.ts
import { getContext, type LoginContextResponse, type PortalUser } from "./auth";
import { getFirstAccessibleModuleRoute, getRoleDrivenDepartments } from "../utils/roleAccess";
import { getOperationalAccessUser } from "../utils/departmentAccess";
import { preloadRoute, scheduleWorkspaceRoutePreload } from "../app/routePreload";
import { readLoginHomeHint } from "./loginHomeHint";

type PreloadJob = {
  id: string;
  load: () => Promise<unknown>;
};

const loaded = new Set<string>();
const queued = new Set<string>();
let cancelScheduled: (() => void) | null = null;

const COMMON_AFTER_LOGIN: PreloadJob[] = [
  { id: "dashboard", load: () => import("../pages/DashboardPage") },
  { id: "layout", load: () => import("../components/Layout/DepartmentLayout") },
];

const MODULE_PRELOADERS: Record<string, PreloadJob[]> = {
  admin: [
    { id: "admin-dashboard", load: () => import("../pages/AdminDashboardPage") },
    { id: "admin-organisation", load: () => import("../pages/AdminAmoManagementPage") },
  ],
  quality: [
    { id: "qms-canonical", load: () => import("../pages/qms/QmsCanonicalPage") },
    { id: "qms-service", load: () => import("./qms") },
  ],
  planning: [
    { id: "planning-production-pages", load: () => import("../pages/PlanningProductionPages") },
  ],
  production: [
    { id: "production-pages", load: () => import("../pages/PlanningProductionPages") },
    { id: "technical-records-pages", load: () => import("../pages/TechnicalRecordsPages") },
  ],
  maintenance: [
    { id: "maintenance-dashboard", load: () => import("../pages/maintenance/MaintenanceDashboardPage") },
  ],
  "document-control": [
    { id: "doc-control-pages", load: () => import("../pages/DocControlPages") },
  ],
  training: [
    { id: "training-os", load: () => import("../pages/training/TrainingOperatingSystemPage") },
  ],
  rostering: [
    { id: "rostering-pages", load: () => import("../pages/rostering/RosteringPages") },
  ],
};

function runWhenIdle(callback: () => void, timeoutMs = 1800): void {
  if (typeof window === "undefined") return;
  const requestIdle = window.requestIdleCallback;
  if (typeof requestIdle === "function") {
    requestIdle(callback, { timeout: timeoutMs });
    return;
  }
  window.setTimeout(callback, Math.min(300, timeoutMs));
}

function enqueue(job: PreloadJob, priority = false): void {
  if (loaded.has(job.id) || queued.has(job.id)) return;
  queued.add(job.id);
  const start = () => {
    job.load()
      .then(() => loaded.add(job.id))
      .catch(() => undefined)
      .finally(() => queued.delete(job.id));
  };
  if (priority) {
    window.setTimeout(start, 0);
    return;
  }
  runWhenIdle(start);
}

function frequentPathsForTenant(amoCode: string, user: PortalUser | null): string[] {
  const home = getFirstAccessibleModuleRoute(amoCode, user, getContext().department);
  const base = `/maintenance/${encodeURIComponent(amoCode)}`;
  return [
    home,
    `${base}/quality`,
    `${base}/quality?workspace=people`,
    `${base}/training`,
    `${base}/rostering`,
    `${base}/admin`,
    `${base}/maintenance`,
  ].filter(Boolean);
}

function requestStaticShellPrecache(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.ready
    .then((registration) => {
      registration.active?.postMessage({ type: "PRECACHE_STATIC_SHELL" });
    })
    .catch(() => undefined);
}

function requestQmsPrecache(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.ready
    .then((registration) => {
      registration.active?.postMessage({ type: "PRECACHE_QMS" });
    })
    .catch(() => undefined);
}

/**
 * After email → tenant resolve (or tenant-URL login): warm shell + likely home
 * while the user types their password. Public JS/assets only — no API data.
 */
export function preloadAfterLoginContext(context: LoginContextResponse | null): void {
  if (!context || typeof window === "undefined") return;
  const slug = context.login_slug || context.amo_code;
  if (!slug) return;

  enqueue(COMMON_AFTER_LOGIN[1], true); // layout first
  enqueue(COMMON_AFTER_LOGIN[0], true);
  requestStaticShellPrecache();
  requestQmsPrecache();

  if (context.is_platform) {
    enqueue({ id: "platform-control", load: () => import("../pages/platform/PlatformOperationsPage") }, true);
    void preloadRoute("/platform/control").catch(() => undefined);
    return;
  }

  const base = `/maintenance/${encodeURIComponent(slug)}`;
  const homeHint = readLoginHomeHint(slug);
  const earlyPaths = [
    homeHint,
    `${base}/quality`,
    `${base}/quality?workspace=people`,
    `${base}/quality?workspace=missions`,
    `${base}/quality?workspace=intelligence`,
    `${base}/quality/audits/program`,
    `${base}/quality/calendar/week`,
    `${base}`,
    `${base}/admin/overview`,
    `${base}/profile`,
    `${base}/training`,
    `${base}/rostering`,
  ].filter((path, index, list): path is string => Boolean(path) && list.indexOf(path) === index);

  // Prioritize remembered home, then common first-hit lanes.
  earlyPaths.slice(0, 4).forEach((path) => {
    void preloadRoute(path).catch(() => undefined);
  });
  earlyPaths.slice(4).forEach((path) => {
    runWhenIdle(() => {
      void preloadRoute(path).catch(() => undefined);
    }, 900);
  });

  enqueue({ id: "qms-canonical-early", load: () => import("../pages/qms/QmsCanonicalPage") }, true);
  enqueue({ id: "qms-service-early", load: () => import("./qms") }, true);
  enqueue({ id: "qms-overview-early", load: () => import("../pages/qms/QmsOverviewPage") }, true);
}

export function preloadWorkspaceForUser(user: PortalUser | null, amoCodeOrSlug?: string | null): void {
  if (!user || typeof window === "undefined") return;
  const ctx = getContext();
  const amoCode = amoCodeOrSlug || ctx.amoSlug || ctx.amoCode;
  if (!amoCode) return;

  COMMON_AFTER_LOGIN.forEach((job, index) => enqueue(job, index < 2));

  const operationalUser = getOperationalAccessUser(user);
  const departments = getRoleDrivenDepartments(operationalUser, ctx.department);

  departments.slice(0, 4).forEach((department) => {
    MODULE_PRELOADERS[department]?.forEach((job) => enqueue(job, true));
  });

  const home = getFirstAccessibleModuleRoute(amoCode, user, ctx.department);
  void preloadRoute(home).catch(() => undefined);

  cancelScheduled?.();
  cancelScheduled = scheduleWorkspaceRoutePreload(frequentPathsForTenant(amoCode, user), {
    firstDelayMs: 0,
  });
  requestStaticShellPrecache();
}
