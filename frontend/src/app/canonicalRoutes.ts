// src/app/canonicalRoutes.ts
// Canonical cross-module route contracts for AMO Portal.
// Keep these builders stable and use them instead of hand-building paths in new modules.

export type AmoRouteParams = {
  amoCode: string;
};

export type UserRouteParams = AmoRouteParams & {
  userId: string;
};

export type WorkOrderRouteParams = AmoRouteParams & {
  woId: string | number;
};

export const canonicalModuleRoutes = {
  cockpit: "/maintenance/:amoCode",
  adminOverview: "/maintenance/:amoCode/admin/overview",
  adminUsers: "/maintenance/:amoCode/admin/users",
  adminUserDetail: "/maintenance/:amoCode/admin/users/:userId",
  qmsRoot: "/maintenance/:amoCode/qms",
  qmsTrainingRoot: "/maintenance/:amoCode/qms/training-competence/dashboard",
  qmsTrainingPerson: "/maintenance/:amoCode/qms/training-competence/people/:userId",
  myTraining: "/maintenance/:amoCode/training",
  planningDashboard: "/maintenance/:amoCode/planning/dashboard",
  planningWorkPackages: "/maintenance/:amoCode/planning/work-packages",
  planningWorkOrders: "/maintenance/:amoCode/planning/work-orders",
  productionDashboard: "/maintenance/:amoCode/production/dashboard",
  productionControlBoard: "/maintenance/:amoCode/production/control-board",
  maintenanceDashboard: "/maintenance/:amoCode/maintenance/dashboard",
  maintenanceWorkOrders: "/maintenance/:amoCode/maintenance/work-orders",
  maintenanceWorkOrderDetail: "/maintenance/:amoCode/maintenance/work-orders/:woId",
  technicalRecordsDashboard: "/maintenance/:amoCode/production/records",
  technicalRecordsPacks: "/maintenance/:amoCode/production/records/packs",
  manualsRoot: "/maintenance/:amoCode/manuals",
  foundationsContractsApi: "/foundations/contracts",
  foundationsBaseStationsApi: "/foundations/base-stations",
  rosteringRoot: "/maintenance/:amoCode/rostering",
  rosteringDashboard: "/maintenance/:amoCode/rostering/dashboard",
  rosteringCalendar: "/maintenance/:amoCode/rostering/calendar",
  rosteringPlanningBoard: "/maintenance/:amoCode/rostering/planning-board",
  rosteringMyRoster: "/maintenance/:amoCode/rostering/my-roster",
  rosteringTrainingImpact: "/maintenance/:amoCode/rostering/training-impact",
  rosteringReports: "/maintenance/:amoCode/rostering/reports",
  rosteringSettings: "/maintenance/:amoCode/rostering/settings",
} as const;

function encodeSegment(value: string | number): string {
  return encodeURIComponent(String(value));
}

export const buildCanonicalRoute = {
  adminOverview: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/admin/overview`,
  adminUsers: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/admin/users`,
  adminUserDetail: ({ amoCode, userId }: UserRouteParams) => `/maintenance/${encodeSegment(amoCode)}/admin/users/${encodeSegment(userId)}`,
  qmsRoot: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/qms`,
  qmsTrainingRoot: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/qms/training-competence/dashboard`,
  qmsTrainingPerson: ({ amoCode, userId }: UserRouteParams) => `/maintenance/${encodeSegment(amoCode)}/qms/training-competence/people/${encodeSegment(userId)}`,
  myTraining: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/training`,
  planningWorkPackages: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/planning/work-packages`,
  planningWorkOrders: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/planning/work-orders`,
  productionControlBoard: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/production/control-board`,
  maintenanceWorkOrders: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/maintenance/work-orders`,
  maintenanceWorkOrderDetail: ({ amoCode, woId }: WorkOrderRouteParams) => `/maintenance/${encodeSegment(amoCode)}/maintenance/work-orders/${encodeSegment(woId)}`,
  technicalRecordsPacks: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/production/records/packs`,
  rosteringRoot: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering`,
  rosteringDashboard: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/dashboard`,
  rosteringCalendar: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/calendar`,
  rosteringPlanningBoard: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/planning-board`,
  rosteringMyRoster: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/my-roster`,
  rosteringTrainingImpact: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/training-impact`,
  rosteringReports: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/reports`,
  rosteringSettings: ({ amoCode }: AmoRouteParams) => `/maintenance/${encodeSegment(amoCode)}/rostering/settings`,
} as const;
