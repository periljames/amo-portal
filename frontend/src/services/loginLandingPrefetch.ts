import { getContext, getToken, type PortalUser } from "./auth";
import { getPortalQueryClient } from "./portalQueryClient";
import { getQmsOperationalDashboard } from "./qmsDashboard";
import { listQmsMissions } from "./qmsMissions";
import {
  listAuditProgrammes,
  listAuditProgrammeSchedulingQueue,
  listAuditUniverse,
} from "./qmsAuditProgramme";
import { getQmsPeopleSummary, listQmsPrivileges } from "./qmsPeople";
import { getQmsIntelligenceOverview } from "./qmsIntelligence";
import { getQualityExcellenceOverview } from "./qualityExcellence";
import { getTrainingAccess, getTrainingControlRoom } from "./trainingOperating";
import { getRosterDashboard } from "./rostering";
import { fetchOverviewSummary } from "./adminOverview";
import { getRoleDrivenDepartments } from "../utils/roleAccess";
import { getOperationalAccessUser } from "../utils/departmentAccess";

/** Keep TanStack keys stable across SAFARILINK vs safarilink route casing. */
export function qmsAmoQueryKey(amoCode: string): string {
  return amoCode.trim().toLowerCase();
}

function currentMonthRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  const to = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const iso = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };
  return { from: iso(from), to: iso(to) };
}

function amoFromLandingPath(homePath: string, fallback: string): string {
  const match = homePath.match(/\/maintenance\/([^/?#]+)/i);
  if (!match?.[1]) return fallback;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function pathOf(homePath: string): string {
  return homePath.split(/[?#]/, 1)[0] || homePath;
}

function soft(job: Promise<unknown>): Promise<void> {
  return job.then(() => undefined).catch(() => undefined);
}

async function prefetchControlRoom(amoCode: string): Promise<void> {
  const queryClient = getPortalQueryClient();
  if (!queryClient) return;
  const amoKey = qmsAmoQueryKey(amoCode);
  await queryClient.prefetchQuery({
    queryKey: ["qms-operational-dashboard-v2", amoKey],
    queryFn: ({ signal }) => getQmsOperationalDashboard(amoCode, signal),
    staleTime: 20_000,
  });
}

async function prefetchMissions(amoCode: string): Promise<void> {
  const queryClient = getPortalQueryClient();
  if (!queryClient) return;
  const amoKey = qmsAmoQueryKey(amoCode);
  await queryClient.prefetchQuery({
    queryKey: ["qms-missions", amoKey, "", 0],
    queryFn: ({ signal }) => listQmsMissions(amoCode, { limit: 25, offset: 0 }, signal),
    staleTime: 10_000,
  });
}

async function prefetchAuditProgramme(amoCode: string): Promise<void> {
  const queryClient = getPortalQueryClient();
  if (!queryClient) return;
  const year = new Date().getFullYear();
  const amoKey = qmsAmoQueryKey(amoCode);
  await Promise.all([
    queryClient.prefetchQuery({
      queryKey: ["qms-audit-programmes", amoKey, year],
      queryFn: ({ signal }) => listAuditProgrammes(amoCode, year, signal),
      staleTime: 5_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ["qms-audit-universe", amoKey],
      queryFn: ({ signal }) => listAuditUniverse(amoCode, signal),
      staleTime: 10_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ["qms-audit-programme-scheduling-queue", amoKey],
      queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
      staleTime: 5_000,
    }),
  ]);
}

async function prefetchExcellenceOverview(amoCode: string): Promise<void> {
  const queryClient = getPortalQueryClient();
  if (!queryClient) return;
  const amoKey = qmsAmoQueryKey(amoCode);
  await queryClient.prefetchQuery({
    queryKey: ["qms-excellence-overview", amoKey],
    queryFn: () => getQualityExcellenceOverview(amoCode),
    staleTime: 10_000,
  });
}

async function prefetchRosteringDashboard(): Promise<void> {
  const queryClient = getPortalQueryClient();
  if (!queryClient) return;
  const range = currentMonthRange();
  await queryClient.prefetchQuery({
    queryKey: ["rostering", "dashboard", range.from, range.to],
    queryFn: () => getRosterDashboard(range),
    staleTime: 30_000,
  });
}

/** Warm People via service calls (page still uses local state; apiClient TTL helps first paint). */
async function warmPeopleHttp(amoCode: string): Promise<void> {
  await Promise.all([
    getQmsPeopleSummary(amoCode),
    listQmsPrivileges(amoCode),
  ]);
}

async function warmIntelligenceHttp(amoCode: string): Promise<void> {
  await getQmsIntelligenceOverview(amoCode);
}

async function warmTrainingHttp(): Promise<void> {
  await getTrainingAccess();
  await getTrainingControlRoom();
}

/**
 * Prefetch the authenticated landing surface (awaited on takeoff).
 * Keep this narrow so boarding stays snappy.
 */
export async function prefetchLoginLandingData(options: {
  user: PortalUser;
  amoSlug: string;
  homePath: string;
}): Promise<void> {
  if (!getToken()) return;

  const ctx = getContext();
  const fallback = ctx.amoCode || options.user.amo_code || options.amoSlug;
  if (!fallback) return;

  const path = pathOf(options.homePath);
  const routeAmo = amoFromLandingPath(path, fallback);
  const jobs: Array<Promise<void>> = [];

  if (path.includes("/quality") || path.includes("/audits/")) {
    jobs.push(soft(prefetchControlRoom(routeAmo)));
  }
  if (/\/quality\/audits\/program/i.test(path)) {
    jobs.push(soft(prefetchAuditProgramme(routeAmo)));
  }
  if (path.includes("/training")) {
    jobs.push(soft(warmTrainingHttp()));
  }
  if (path.includes("/rostering")) {
    jobs.push(soft(prefetchRosteringDashboard()));
  }
  if (path.includes("/admin")) {
    jobs.push(soft(fetchOverviewSummary({ silent: true }).then(() => undefined)));
  }

  if (!jobs.length && (path.includes("/quality") || path.includes("/audits/"))) {
    jobs.push(soft(prefetchControlRoom(routeAmo)));
  }

  if (!jobs.length) return;
  await Promise.all(jobs);
}

/**
 * Background fleet: warm the pages users open next without blocking takeoff.
 * Chunks are handled separately; this seeds live data / HTTP caches.
 */
export async function prefetchPortalWorkspaceFleet(options: {
  user: PortalUser;
  amoSlug: string;
  homePath: string;
}): Promise<void> {
  if (!getToken()) return;

  const ctx = getContext();
  const fallback = ctx.amoCode || options.user.amo_code || options.amoSlug;
  if (!fallback) return;

  const path = pathOf(options.homePath);
  const routeAmo = amoFromLandingPath(path, fallback);
  const departments = getRoleDrivenDepartments(
    getOperationalAccessUser(options.user),
    ctx.department,
  );

  const jobs: Array<Promise<void>> = [];

  if (departments.includes("quality") || path.includes("/quality") || path.includes("/audits/")) {
    jobs.push(soft(prefetchControlRoom(routeAmo)));
    jobs.push(soft(prefetchMissions(routeAmo)));
    jobs.push(soft(prefetchAuditProgramme(routeAmo)));
    jobs.push(soft(warmPeopleHttp(routeAmo)));
    jobs.push(soft(warmIntelligenceHttp(routeAmo)));
    jobs.push(soft(prefetchExcellenceOverview(routeAmo)));
  }

  if (departments.includes("admin") || path.includes("/admin") || options.user.is_amo_admin) {
    jobs.push(soft(fetchOverviewSummary({ silent: true }).then(() => undefined)));
  }

  // Personal / cross-module surfaces most users open next.
  jobs.push(soft(prefetchRosteringDashboard()));
  jobs.push(soft(warmTrainingHttp()));

  // Bound concurrency: run in two waves so we do not stampede the API.
  const mid = Math.ceil(jobs.length / 2);
  await Promise.all(jobs.slice(0, mid));
  await Promise.all(jobs.slice(mid));
}

export function schedulePortalWorkspaceFleetPrefetch(options: {
  user: PortalUser;
  amoSlug: string;
  homePath: string;
}): void {
  if (typeof window === "undefined") return;
  const start = () => {
    void prefetchPortalWorkspaceFleet(options);
  };
  const ric = window.requestIdleCallback;
  if (typeof ric === "function") {
    ric(start, { timeout: 1200 });
    return;
  }
  window.setTimeout(start, 200);
}

/** Kick landing data immediately after auth — before chunk imports contend. */
export function beginControlRoomPrefetch(options: {
  user: PortalUser;
  amoSlug: string;
  homePath: string;
}): Promise<void> {
  return prefetchLoginLandingData(options);
}
