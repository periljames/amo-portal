type RouteLoader = () => Promise<unknown>;
import { qmsPageLoaders, qmsRouteLoaderKey } from "./qmsRouteLoaders";

const loadPlanningProductionPages: RouteLoader = () => import("../pages/PlanningProductionPages");
const loadTechnicalRecordsPages: RouteLoader = () => import("../pages/TechnicalRecordsPages");
const loadRosteringPages: RouteLoader = () => import("../pages/rostering/RosteringPages");
const loadDocControlPages: RouteLoader = () => import("../pages/DocControlPages");
const loadProcurementModule: RouteLoader = () => import("../pages/procurement/ProcurementModule");
const loadDashboardPage: RouteLoader = () => import("../pages/DashboardPage");
const loadProductionWorkspacePage: RouteLoader = () => import("../pages/ProductionWorkspacePage");
const loadMaintenanceDashboardPage: RouteLoader = () => import("../pages/maintenance/MaintenanceDashboardPage");
const loadMaintenanceWorkOrdersPage: RouteLoader = () => import("../pages/maintenance/MaintenanceWorkOrdersPage");
const loadMaintenanceWorkPackagesPage: RouteLoader = () => import("../pages/maintenance/MaintenanceWorkPackagesPage");
const loadMaintenanceDefectsPage: RouteLoader = () => import("../pages/maintenance/MaintenanceDefectsPage");
const loadMaintenanceNonRoutinesPage: RouteLoader = () => import("../pages/maintenance/MaintenanceNonRoutinesPage");
const loadMaintenanceInspectionsPage: RouteLoader = () => import("../pages/maintenance/MaintenanceInspectionsPage");
const loadMaintenancePartsToolsPage: RouteLoader = () => import("../pages/maintenance/MaintenancePartsToolsPage");
const loadMaintenanceCloseoutPage: RouteLoader = () => import("../pages/maintenance/MaintenanceCloseoutPage");
const loadMaintenanceReportsPage: RouteLoader = () => import("../pages/maintenance/MaintenanceReportsPage");
const loadMaintenanceSettingsPage: RouteLoader = () => import("../pages/maintenance/MaintenanceSettingsPage");
const loadManualsDashboardPage: RouteLoader = () => import("../pages/manuals/ManualsDashboardPage");
const loadManualReaderPage: RouteLoader = () => import("../pages/manuals/ManualReaderPage");
const loadReliabilityWorkspacePage: RouteLoader = () => import("../pages/reliability/ReliabilityWorkspacePage");
const loadEhmDashboardPage: RouteLoader = () => import("../pages/ehm/EhmDashboardPage");
const loadAdminOverviewPage: RouteLoader = () => import("../pages/AdminOverviewPage");
const loadAdminDashboardPage: RouteLoader = () => import("../pages/AdminDashboardPage");
const loadSubscriptionManagementPage: RouteLoader = () => import("../pages/SubscriptionManagementPage");

const routeLoaders: Array<{ test: RegExp; loaders: RouteLoader[] }> = [
  { test: /\/production\/records(?:\/|$)/, loaders: [loadTechnicalRecordsPages] },
  { test: /\/production\/workspace(?:\/|$)/, loaders: [loadProductionWorkspacePage] },
  { test: /\/(?:planning|production)(?:\/|$)/, loaders: [loadPlanningProductionPages] },
  { test: /\/rostering(?:\/|$)/, loaders: [loadRosteringPages] },
  { test: /\/maintenance\/work-orders(?:\/|$)/, loaders: [loadMaintenanceWorkOrdersPage] },
  { test: /\/maintenance\/work-packages(?:\/|$)/, loaders: [loadMaintenanceWorkPackagesPage] },
  { test: /\/maintenance\/defects(?:\/|$)/, loaders: [loadMaintenanceDefectsPage] },
  { test: /\/maintenance\/non-routines(?:\/|$)/, loaders: [loadMaintenanceNonRoutinesPage] },
  { test: /\/maintenance\/inspections(?:\/|$)/, loaders: [loadMaintenanceInspectionsPage] },
  { test: /\/maintenance\/parts-tools(?:\/|$)/, loaders: [loadMaintenancePartsToolsPage] },
  { test: /\/maintenance\/closeout(?:\/|$)/, loaders: [loadMaintenanceCloseoutPage] },
  { test: /\/maintenance\/reports(?:\/|$)/, loaders: [loadMaintenanceReportsPage] },
  { test: /\/maintenance\/settings(?:\/|$)/, loaders: [loadMaintenanceSettingsPage] },
  { test: /\/maintenance\/[^/]+\/maintenance(?:\/dashboard)?(?:\/|$)/, loaders: [loadMaintenanceDashboardPage] },
  { test: /\/maintenance\/[^/]+\/procurement(?:\/|$)/, loaders: [loadProcurementModule] },
  { test: /\/(?:document-control|doc-control)(?:\/|$)/, loaders: [loadDocControlPages] },
  { test: /\/(?:manuals|publications)\/[^/]+\/rev\/[^/]+\/read(?:\/|$)/, loaders: [loadManualReaderPage] },
  { test: /\/(?:manuals|publications)(?:\/|$)/, loaders: [loadManualsDashboardPage] },
  { test: /\/reliability\/ehm(?:\/|$)/, loaders: [loadEhmDashboardPage] },
  { test: /\/reliability(?:\/|$)/, loaders: [loadReliabilityWorkspacePage] },
  { test: /\/admin\/billing(?:\/|$)/, loaders: [loadSubscriptionManagementPage] },
  { test: /\/admin\/users(?:\/|$)/, loaders: [loadAdminDashboardPage] },
  { test: /\/admin(?:\/|$)/, loaders: [loadAdminOverviewPage] },
  { test: /\/maintenance\/[^/]+\/[^/]+(?:\/|$)/, loaders: [loadDashboardPage] },
];

const loaderPromises = new Map<RouteLoader, Promise<unknown>>();

function normalizePath(path: string): string {
  if (typeof window === "undefined") return path.split("?")[0] || path;
  try {
    const url = new URL(path, window.location.origin);
    return `${url.pathname}${url.search}`;
  } catch {
    return path.split("?")[0] || path;
  }
}

function loadOnce(loader: RouteLoader): Promise<unknown> {
  const existing = loaderPromises.get(loader);
  if (existing) return existing;
  const promise = loader().catch((error) => {
    loaderPromises.delete(loader);
    throw error;
  });
  loaderPromises.set(loader, promise);
  return promise;
}

export function preloadRoute(path: string): Promise<unknown[]> {
  const pathname = normalizePath(path);
  const qmsKey = qmsRouteLoaderKey(pathname);
  if (qmsKey) {
    const workspaceKeys = ["people", "missions", "intelligence", "assuranceHub"];
    return Promise.all([
      ...(workspaceKeys.includes(qmsKey) ? [loadOnce(qmsPageLoaders.overview)] : []),
      loadOnce(qmsPageLoaders[qmsKey]),
    ]);
  }
  const match = routeLoaders.find((entry) => entry.test.test(pathname.split("?")[0]));
  if (!match) return Promise.resolve([]);
  return Promise.all(match.loaders.map(loadOnce));
}

function shouldIdlePreload(): boolean {
  if (typeof navigator === "undefined" || navigator.onLine === false || document.visibilityState === "hidden") return false;
  const connection = (navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
  }).connection;
  if (connection?.saveData) return false;
  return !connection?.effectiveType || !["slow-2g", "2g"].includes(connection.effectiveType);
}

export function scheduleWorkspaceRoutePreload(
  paths: string[],
  options?: { firstDelayMs?: number; nextDelayMs?: number },
): () => void {
  if (typeof window === "undefined" || !shouldIdlePreload()) return () => undefined;

  const firstDelayMs = options?.firstDelayMs ?? 1200;
  const nextDelayMs = options?.nextDelayMs ?? 400;
  const uniquePaths = Array.from(new Set(paths.filter(Boolean))).slice(0, 8);
  let cancelled = false;
  let index = 0;
  let running = false;
  let timer: number | undefined;
  let idle: number | undefined;
  const idleWindow = window as Window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
    cancelIdleCallback?: (id: number) => void;
  };
  const schedule = () => {
    if (cancelled || running || timer !== undefined || idle !== undefined || index >= uniquePaths.length || !shouldIdlePreload()) return;
    timer = window.setTimeout(() => {
      timer = undefined;
      if (cancelled || !shouldIdlePreload()) return;
      const run = async () => {
        idle = undefined;
        if (cancelled || !shouldIdlePreload()) return;
        running = true;
        try { await preloadRoute(uniquePaths[index++]); } catch { /* Navigation retries failed imports. */ }
        finally { running = false; schedule(); }
      };
      if (idleWindow.requestIdleCallback) idle = idleWindow.requestIdleCallback(() => void run(), { timeout: 2500 });
      else void run();
    }, index === 0 ? firstDelayMs : nextDelayMs);
  };
  document.addEventListener("visibilitychange", schedule);
  window.addEventListener("online", schedule);
  schedule();
  return () => {
    cancelled = true;
    if (timer !== undefined) window.clearTimeout(timer);
    if (idle !== undefined) idleWindow.cancelIdleCallback?.(idle);
    document.removeEventListener("visibilitychange", schedule);
    window.removeEventListener("online", schedule);
  };
}
