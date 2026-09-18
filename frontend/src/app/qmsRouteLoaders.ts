/** Shared lazy entry points for navigation, intent preloading, and QMS dispatch. */
export const qmsPageLoaders = {
  canonical: () => import("../pages/qms/QmsCanonicalPage"),
  overview: () => import("../pages/qms/QmsOverviewPage"),
  checklist: () => import("../components/QMS/QualityChecklistTemplateHost"),
  cars: () => import("../pages/QualityCarsPage"),
  programmeSchedule: () => import("../pages/qms/QmsAuditProgrammeSchedulePage"),
  programme: () => import("../pages/qms/QmsAuditProgrammeWorkspacePage"),
  module: () => import("../pages/qms/QmsModuleWorkspacePage"),
  carControl: () => import("../pages/qms/QmsCarControlLoopPage"),
  carReport: () => import("../pages/qms/QmsCarPerformanceReportPage"),
  providers: () => import("../pages/qms/QmsExternalProvidersPage"),
  register: () => import("../pages/qms/QmsRegisterPage"),
  planner: () => import("../pages/qms/planner/QmsPlannerLivePage"),
  setup: () => import("../features/qms/auditSession/AuditSetupWorkspace"),
  prepare: () => import("../features/qms/auditSession/AuditPrepareWorkspace"),
  live: () => import("../features/qms/auditSession/LiveAuditWorkspace"),
  closing: () => import("../features/qms/auditSession/AuditClosingWorkspace"),
  followUp: () => import("../features/qms/auditSession/AuditFollowUpWorkspace"),
  archive: () => import("../features/qms/auditSession/AuditArchiveWorkspace"),
};

export function qmsRouteLoaderKey(path: string): keyof typeof qmsPageLoaders | null {
  const pathname = path.split(/[?#]/)[0];
  if (!/\/quality(?:\/|$)|\/qms(?:\/|$)/i.test(pathname)) return null;
  if (/\/quality\/?$/i.test(pathname)) return "overview";
  const stage = /\/audits\/[^/]+\/(setup|prepare|live|closing|follow-up|archive)\/?$/i.exec(pathname)?.[1]?.toLowerCase();
  if (stage) return stage === "follow-up" ? "followUp" : stage as "setup" | "prepare" | "live" | "closing" | "archive";
  if (/\/calendar(?:\/|$)/i.test(pathname)) return "planner";
  if (/\/audits\/checklists(?:\/|$)/i.test(pathname)) return "checklist";
  if (/\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i.test(pathname)) return "programmeSchedule";
  if (/\/audits\/program(?:\/|$)/i.test(pathname)) return "programme";
  if (/\/suppliers(?:\/|$)/i.test(pathname)) return "providers";
  if (/\/reports\/car-performance(?:\/|$)/i.test(pathname)) return "carReport";
  if (/\/evidence-vault(?:\/|$)/i.test(pathname)) return "register";
  if (/\/cars(?:\/|$)/i.test(pathname)) return "cars";
  return "canonical";
}
