/**
 * Route-module preloading for the AMO Portal.
 *
 * Navigation should never wait for a user click before the browser starts
 * downloading a lazy route chunk. The sidebar calls preloadRoute on hover,
 * focus, and immediately before navigation. Idle preloading is intentionally
 * conservative so slow or metered connections are not flooded with requests.
 */

type RouteLoader = () => Promise<unknown>;

const loadPlanningProductionPages: RouteLoader = () => import("../pages/PlanningProductionPages");
const loadTechnicalRecordsPages: RouteLoader = () => import("../pages/TechnicalRecordsPages");
const loadRosteringPages: RouteLoader = () => import("../pages/rostering/RosteringPages");
const loadDocControlPages: RouteLoader = () => import("../pages/DocControlPages");
const loadQmsCanonicalPage: RouteLoader = () => import("../pages/qms/QmsCanonicalPage");
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
const loadReliabilityReportsPage: RouteLoader = () => import("../pages/ReliabilityReportsPage");
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
  { test: /\/(?:document-control|doc-control)(?:\/|$)/, loaders: [loadDocControlPages] },
  { test: /\/qms(?:\/|$)/, loaders: [loadQmsCanonicalPage] },
  { test: /\/manuals(?:\/|$)/, loaders: [loadManualsDashboardPage] },
  { test: /\/reliability\/ehm(?:\/|$)/, loaders: [loadEhmDashboardPage] },
  { test: /\/reliability(?:\/|$)/, loaders: [loadReliabilityReportsPage] },
  { test: /\/admin\/billing(?:\/|$)/, loaders: [loadSubscriptionManagementPage] },
  { test: /\/admin\/users(?:\/|$)/, loaders: [loadAdminDashboardPage] },
  { test: /\/admin(?:\/|$)/, loaders: [loadAdminOverviewPage] },
  { test: /\/maintenance\/[^/]+\/[^/]+(?:\/|$)/, loaders: [loadDashboardPage] },
];

const loaderPromises = new Map<RouteLoader, Promise<unknown>>();

function normalizePath(path: string): string {
  if (typeof window === "undefined") return path.split("?")[0] || path;
  try {
    return new URL(path, window.location.origin).pathname;
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
  const match = routeLoaders.find((entry) => entry.test.test(pathname));
  if (!match) return Promise.resolve([]);
  return Promise.all(match.loaders.map(loadOnce));
}

function shouldIdlePreload(): boolean {
  if (typeof navigator === "undefined") return false;
  const connection = (navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
  }).connection;
  if (connection?.saveData) return false;
  return !connection?.effectiveType || !["slow-2g", "2g"].includes(connection.effectiveType);
}

export function scheduleWorkspaceRoutePreload(paths: string[]): () => void {
  if (typeof window === "undefined" || !shouldIdlePreload()) return () => undefined;

  const uniquePaths = Array.from(new Set(paths.filter(Boolean))).slice(0, 8);
  let cancelled = false;
  const timeoutIds: number[] = [];
  const idleIds: number[] = [];
  const idleWindow = window as Window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
    cancelIdleCallback?: (id: number) => void;
  };

  uniquePaths.forEach((path, index) => {
    const run = () => {
      if (cancelled) return;
      void preloadRoute(path).catch(() => undefined);
    };
    const delay = 300 + index * 250;
    const timeoutId = idleWindow.setTimeout(() => {
      if (cancelled) return;
      if (typeof idleWindow.requestIdleCallback === "function") {
        idleIds.push(idleWindow.requestIdleCallback(run, { timeout: 1200 }));
      } else {
        run();
      }
    }, delay);
    timeoutIds.push(timeoutId);
  });

  return () => {
    cancelled = true;
    timeoutIds.forEach((id) => idleWindow.clearTimeout(id));
    if (typeof idleWindow.cancelIdleCallback === "function") {
      idleIds.forEach((id) => {
        try {
          idleWindow.cancelIdleCallback?.(id);
        } catch {
          // best effort only
        }
      });
    }
  };
}
