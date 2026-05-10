// src/services/routePreloader.ts
import { getContext, type PortalUser } from "./auth";
import { getRoleDrivenDepartments } from "../utils/roleAccess";

type PreloadJob = {
  id: string;
  load: () => Promise<unknown>;
};

const loaded = new Set<string>();
const queued = new Set<string>();

const COMMON_AFTER_LOGIN: PreloadJob[] = [
  { id: "dashboard", load: () => import("../pages/DashboardPage") },
  { id: "layout", load: () => import("../components/Layout/DepartmentLayout") },
];

const MODULE_PRELOADERS: Record<string, PreloadJob[]> = {
  admin: [
    { id: "admin-dashboard", load: () => import("../pages/AdminDashboardPage") },
    { id: "admin-users", load: () => import("../pages/AdminAmoManagementPage") },
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
};

function runWhenIdle(callback: () => void): void {
  if (typeof window === "undefined") return;
  const requestIdle = window.requestIdleCallback;
  if (typeof requestIdle === "function") {
    requestIdle(callback, { timeout: 2500 });
    return;
  }
  window.setTimeout(callback, 300);
}

function enqueue(job: PreloadJob): void {
  if (loaded.has(job.id) || queued.has(job.id)) return;
  queued.add(job.id);
  runWhenIdle(() => {
    job.load()
      .then(() => loaded.add(job.id))
      .catch(() => undefined)
      .finally(() => queued.delete(job.id));
  });
}

export function preloadWorkspaceForUser(user: PortalUser | null, amoCodeOrSlug?: string | null): void {
  if (!user || typeof window === "undefined") return;
  const ctx = getContext();
  const amoCode = amoCodeOrSlug || ctx.amoSlug || ctx.amoCode;
  if (!amoCode) return;

  COMMON_AFTER_LOGIN.forEach(enqueue);

  const departments = user.is_amo_admin || user.is_superuser
    ? ["admin", "quality", "planning", "production", "maintenance", "document-control"]
    : getRoleDrivenDepartments(user, ctx.department);

  departments.slice(0, user.is_amo_admin ? 6 : 3).forEach((department) => {
    MODULE_PRELOADERS[department]?.forEach(enqueue);
  });
}
