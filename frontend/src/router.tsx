// src/router.tsx
// App routing
// - Public routes: /login and /maintenance/:amoCode/login
// - Protected routes (JWT required via services/auth): department dashboards,
//   CRS pages, aircraft import, QMS dashboard, and admin user management.
// - Uses RequireAuth wrapper to redirect unauthenticated users back to login.

import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";

import {
  fetchOnboardingStatus,
  getCachedOnboardingStatus,
  getCachedUser,
  getContext,
  isAuthenticated,
  type OnboardingStatus,
} from "./services/auth";
import { canViewFeature, getFirstAccessibleModuleRoute, type ModuleFeature } from "./utils/roleAccess";
import { hasQmsRolePermission, isPlatformSuperuser } from "./app/routeGuards";

function lazyNamed<T extends Record<string, React.ComponentType<any>>>(
  loader: () => Promise<T>,
  exportName: keyof T
) {
  return lazy(async () => ({ default: (await loader())[exportName] as React.ComponentType<any> }));
}

const DocControlPages = {
  LegacyDocControlRedirectPage: lazyNamed(() => import("./pages/DocControlPages"), "LegacyDocControlRedirectPage"),
  DocControlDashboardPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDashboardPage"),
  DocControlLibraryPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlLibraryPage"),
  DocControlDocumentDetailPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDocumentDetailPage"),
  DocControlDraftsPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDraftsPage"),
  DocControlDraftDetailPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDraftDetailPage"),
  DocControlChangeProposalPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlChangeProposalPage"),
  DocControlChangeProposalDetailPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlChangeProposalDetailPage"),
  DocControlRevisionsPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlRevisionsPage"),
  DocControlLEPPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlLEPPage"),
  DocControlTRPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlTRPage"),
  DocControlTRDetailPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlTRDetailPage"),
  DocControlDistributionPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDistributionPage"),
  DocControlDistributionDetailPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlDistributionDetailPage"),
  DocControlArchivePage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlArchivePage"),
  DocControlReviewsPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlReviewsPage"),
  DocControlRegistersPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlRegistersPage"),
  DocControlSettingsPage: lazyNamed(() => import("./pages/DocControlPages"), "DocControlSettingsPage"),
} as const;

const PlanningProductionPages = {
  PlanningDashboardPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningDashboardPage"),
  PlanningUtilisationPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningUtilisationPage"),
  PlanningForecastPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningForecastPage"),
  PlanningAmpPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningAmpPage"),
  PlanningTaskLibraryPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningTaskLibraryPage"),
  PlanningAdSbPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningAdSbPage"),
  PlanningWorkPackagesPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningWorkPackagesPage"),
  PlanningWorkOrdersPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningWorkOrdersPage"),
  PlanningDefermentsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningDefermentsPage"),
  PlanningNonRoutinePage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PlanningNonRoutinePage"),
  WatchlistsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "WatchlistsPage"),
  PublicationReviewPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "PublicationReviewPage"),
  ComplianceActionsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ComplianceActionsPage"),
  ProductionDashboardPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionDashboardPage"),
  ProductionControlBoardPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionControlBoardPage"),
  ProductionExecutionPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionExecutionPage"),
  ProductionFindingsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionFindingsPage"),
  ProductionMaterialsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionMaterialsPage"),
  ProductionReviewInspectionPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionReviewInspectionPage"),
  ProductionReleasePrepPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionReleasePrepPage"),
  ProductionComplianceItemsPage: lazyNamed(() => import("./pages/PlanningProductionPages"), "ProductionComplianceItemsPage"),
} as const;

const TechnicalRecordsPages = {
  TechnicalRecordsDashboardPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "TechnicalRecordsDashboardPage"),
  AircraftRecordsPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "AircraftRecordsPage"),
  AircraftRecordDetailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "AircraftRecordDetailPage"),
  LogbooksPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "LogbooksPage"),
  LogbookByTailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "LogbookByTailPage"),
  DeferralsPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "DeferralsPage"),
  DeferralDetailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "DeferralDetailPage"),
  MaintenanceRecordsPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "MaintenanceRecordsPage"),
  MaintenanceRecordDetailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "MaintenanceRecordDetailPage"),
  AirworthinessPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "AirworthinessPage"),
  ADRegisterPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "ADRegisterPage"),
  ADDetailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "ADDetailPage"),
  SBRegisterPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "SBRegisterPage"),
  SBDetailPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "SBDetailPage"),
  LLPPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "LLPPage"),
  ComponentsPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "ComponentsPage"),
  ReconciliationPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "ReconciliationPage"),
  TraceabilityPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "TraceabilityPage"),
  PacksPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "PacksPage"),
  TechnicalRecordsSettingsPage: lazyNamed(() => import("./pages/TechnicalRecordsPages"), "TechnicalRecordsSettingsPage"),
} as const;


const LoginPage = lazy(() => import("./pages/LoginPage"));
const PlatformControlPage = lazy(() => import("./pages/PlatformControlPage"));
const PlatformTenantsPage = lazy(() => import("./pages/platform/PlatformTenantsPage"));
const PlatformUsersPage = lazy(() => import("./pages/platform/PlatformUsersPage"));
const PlatformBillingPage = lazy(() => import("./pages/platform/PlatformBillingPage"));
const PlatformAnalyticsPage = lazy(() => import("./pages/platform/PlatformAnalyticsPage"));
const PlatformSecurityPage = lazy(() => import("./pages/platform/PlatformSecurityPage"));
const PlatformIntegrationsPage = lazy(() => import("./pages/platform/PlatformIntegrationsPage"));
const PlatformInfrastructurePage = lazy(() => import("./pages/platform/PlatformInfrastructurePage"));
const PasswordResetPage = lazy(() => import("./pages/PasswordResetPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const EhmDashboardPage = lazy(() => import("./pages/ehm/EhmDashboardPage"));
const EhmTrendsPage = lazy(() => import("./pages/ehm/EhmTrendsPage"));
const EhmUploadsPage = lazy(() => import("./pages/ehm/EhmUploadsPage"));
const ReliabilityReportsPage = lazy(() => import("./pages/ReliabilityReportsPage"));
const CRSNewPage = lazy(() => import("./pages/CRSNewPage"));
const AircraftImportPage = lazy(() => import("./pages/AircraftImportPage"));
const ComponentImportPage = lazy(() => import("./pages/ComponentImportPage"));
const AircraftDocumentsPage = lazy(() => import("./pages/AircraftDocumentsPage"));
const WorkOrderSearchPage = lazy(() => import("./pages/work/WorkOrderSearchPage"));
const WorkOrderDetailPage = lazy(() => import("./pages/work/WorkOrderDetailPage"));
const TaskSummaryPage = lazy(() => import("./pages/work/TaskSummaryPage"));
const TaskPrintPage = lazy(() => import("./pages/work/TaskPrintPage"));
const AdminUserNewPage = lazy(() => import("./pages/AdminUserNewPage"));
const AdminUserDetailPage = lazy(() => import("./pages/AdminUserDetailPage"));
const AdminDashboardPage = lazy(() => import("./pages/AdminDashboardPage"));
const AdminOverviewPage = lazy(() => import("./pages/AdminOverviewPage"));
const AdminAmoManagementPage = lazy(() => import("./pages/AdminAmoManagementPage"));
const AdminAmoProfilePage = lazy(() => import("./pages/AdminAmoProfilePage"));
const AdminAmoAssetsPage = lazy(() => import("./pages/AdminAmoAssetsPage"));
const AdminUsageSettingsPage = lazy(() => import("./pages/AdminUsageSettingsPage"));
const AdminInvoicesPage = lazy(() => import("./pages/AdminInvoicesPage"));
const AdminInvoiceDetailPage = lazy(() => import("./pages/AdminInvoiceDetailPage"));
const EmailLogsPage = lazy(() => import("./pages/EmailLogsPage"));
const EmailServerSettingsPage = lazy(() => import("./pages/EmailServerSettingsPage"));
const TrainingPage = lazy(() => import("./pages/MyTrainingPage"));
const QmsCanonicalPage = lazy(() => import("./pages/qms/QmsCanonicalPage"));
const QMSTrainingUserPage = lazy(() => import("./pages/QMSTrainingUserPage"));
const AeroDocAuditModePage = lazy(() => import("./pages/AeroDocAuditModePage"));
const AeroDocComplianceHealthPage = lazy(() => import("./pages/AeroDocComplianceHealthPage"));
const AeroDocHangarDashboardPage = lazy(() => import("./pages/AeroDocHangarDashboardPage"));
const QualityCarsPage = lazy(() => import("./pages/QualityCarsPage"));
const PublicCarInvitePage = lazy(() => import("./pages/PublicCarInvitePage"));
const SubscriptionManagementPage = lazy(() => import("./pages/SubscriptionManagementPage"));
const UpsellPage = lazy(() => import("./pages/UpsellPage"));
const UserWidgetsPage = lazy(() => import("./pages/UserWidgetsPage"));
const OnboardingPasswordPage = lazy(() => import("./pages/OnboardingPasswordPage"));
const PublicCertificateVerificationPage = lazy(() => import("./pages/PublicCertificateVerificationPage"));
const VerifyScanPage = lazy(() => import("./pages/VerifyScanPage"));

const QualityAuditScheduleDetailPage = lazy(() => import("./pages/QualityAuditScheduleDetailPage"));
const QualityAuditRunHubPage = lazy(() => import("./pages/QualityAuditRunHubPage"));
const QualityEvidenceViewerPage = lazy(() => import("./pages/QualityEvidenceViewerPage"));

const ManualsDashboardPage = lazy(() => import("./pages/manuals/ManualsDashboardPage"));
const ManualOverviewPage = lazy(() => import("./pages/manuals/ManualOverviewPage"));
const ManualReaderPage = lazy(() => import("./pages/manuals/ManualReaderPage"));
const ManualDiffPage = lazy(() => import("./pages/manuals/ManualDiffPage"));
const ManualWorkflowPage = lazy(() => import("./pages/manuals/ManualWorkflowPage"));
const ManualExportsPage = lazy(() => import("./pages/manuals/ManualExportsPage"));
const ManualMasterListPage = lazy(() => import("./pages/manuals/ManualMasterListPage"));
const ProductionWorkspacePage = lazy(() => import("./pages/ProductionWorkspacePage"));
const UserProfilePage = lazy(() => import("./pages/UserProfilePage"));
const MaintenanceDashboardPage = lazy(() => import("./pages/maintenance/MaintenanceDashboardPage"));
const MaintenanceWorkOrdersPage = lazy(() => import("./pages/maintenance/MaintenanceWorkOrdersPage"));
const MaintenanceWorkOrderDetailPage = lazy(() => import("./pages/maintenance/MaintenanceWorkOrderDetailPage"));
const MaintenanceWorkPackagesPage = lazy(() => import("./pages/maintenance/MaintenanceWorkPackagesPage"));
const MaintenanceDefectsPage = lazy(() => import("./pages/maintenance/MaintenanceDefectsPage"));
const MaintenanceDefectDetailPage = lazy(() => import("./pages/maintenance/MaintenanceDefectDetailPage"));
const MaintenanceNonRoutinesPage = lazy(() => import("./pages/maintenance/MaintenanceNonRoutinesPage"));
const MaintenanceNonRoutineDetailPage = lazy(() => import("./pages/maintenance/MaintenanceNonRoutineDetailPage"));
const MaintenanceInspectionsPage = lazy(() => import("./pages/maintenance/MaintenanceInspectionsPage"));
const MaintenanceInspectionDetailPage = lazy(() => import("./pages/maintenance/MaintenanceInspectionDetailPage"));
const MaintenancePartsToolsPage = lazy(() => import("./pages/maintenance/MaintenancePartsToolsPage"));
const MaintenanceCloseoutPage = lazy(() => import("./pages/maintenance/MaintenanceCloseoutPage"));
const MaintenanceReportsPage = lazy(() => import("./pages/maintenance/MaintenanceReportsPage"));
const MaintenanceSettingsPage = lazy(() => import("./pages/maintenance/MaintenanceSettingsPage"));

type RequireAuthProps = {
  children: React.ReactElement;
};

type RequireTenantAdminProps = {
  children: React.ReactElement;
};

function LegacyTrainingCompetenceRedirect(): React.ReactElement {
  const { amoCode } = useParams<{ amoCode?: string; department?: string }>();
  const location = useLocation();
  const target = `/maintenance/${amoCode || "UNKNOWN"}/qms/training-competence${location.search}`;
  return <Navigate to={target} replace />;
}

function LegacyQmsRedirect(): React.ReactElement {
  const { amoCode } = useParams<{ amoCode?: string; department?: string }>();
  const location = useLocation();
  const parts = location.pathname.split("/").filter(Boolean);
  const qmsIndex = parts.indexOf("qms");
  const suffix = qmsIndex >= 0 ? parts.slice(qmsIndex + 1).join("/") : "";
  const target = `/maintenance/${amoCode || "UNKNOWN"}/qms${suffix ? `/${suffix}` : ""}${location.search}`;
  return <Navigate to={target} replace />;
}

function QmsInboxRedirect(): React.ReactElement {
  const { amoCode } = useParams<{ amoCode?: string }>();
  return <Navigate to={`/maintenance/${amoCode || "UNKNOWN"}/qms/inbox/assigned-to-me`} replace />;
}

function QmsProgrammeRedirect(): React.ReactElement {
  const { amoCode } = useParams<{ amoCode?: string }>();
  return <Navigate to={`/maintenance/${amoCode || "UNKNOWN"}/qms/audits/program`} replace />;
}

type RequireQmsPermissionProps = {
  permission: string;
  children: React.ReactElement;
};

const RequireQmsPermission: React.FC<RequireQmsPermissionProps> = ({ permission, children }) => {
  if (isPlatformSuperuser()) {
    return <Navigate to="/platform/control" replace />;
  }
  if (!hasQmsRolePermission(permission)) {
    return (
      <div style={{ padding: "2rem" }}>
        You do not have permission to access this QMS page.
      </div>
    );
  }
  return children;
};


function inferAmoCodeFromPath(pathname: string): string | null {
  // supports:
  // /maintenance/:amoCode/login
  // /maintenance/:amoCode/admin
  // /maintenance/:amoCode/:department/...
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "maintenance") {
    return parts[1] || null;
  }
  return null;
}

/**
 * RequireAuth
 * - Checks if a JWT token exists (via isAuthenticated()).
 * - If not, redirects to the correct login URL:
 *   * /maintenance/:amoCode/login when an AMO slug is present in the URL.
 *   * /login for generic access.
 * - Preserves the "from" location in state for post-login redirect.
 */
const RequireAuth: React.FC<RequireAuthProps> = ({ children }) => {
  const location = useLocation();
  const redirectedRef = useRef(false);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(
    getCachedOnboardingStatus()
  );
  const [onboardingChecked, setOnboardingChecked] = useState(
    !!getCachedOnboardingStatus()
  );
  const isAuthed = isAuthenticated();
  const isOnboardingRoute = location.pathname.includes("/onboarding");

  useEffect(() => {
    if (!isAuthed || onboardingChecked) return;
    let active = true;
    fetchOnboardingStatus()
      .then((status) => {
        if (!active) return;
        setOnboardingStatus(status);
        setOnboardingChecked(true);
      })
      .catch(() => {
        if (!active) return;
        setOnboardingChecked(true);
      });
    return () => {
      active = false;
    };
  }, [isAuthed, onboardingChecked]);

  if (!isAuthed) {
    const amoCode = inferAmoCodeFromPath(location.pathname);
    const target = amoCode ? `/maintenance/${amoCode}/login` : "/login";

    return (
      <Navigate
        to={target}
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  if (!onboardingChecked && !isOnboardingRoute) {
    return <PageRouteLoading label="Preparing workspaceâ€¦" />;
  }

  if (
    onboardingStatus &&
    !onboardingStatus.is_complete &&
    !isOnboardingRoute &&
    !redirectedRef.current
  ) {
    redirectedRef.current = true;
    const amoCode = inferAmoCodeFromPath(location.pathname) || "system";
    return <Navigate to={`/maintenance/${amoCode}/onboarding/setup`} replace />;
  }

  return children;
};

/**
 * RequireTenantAdmin
 * - Requires the user to be a superuser or AMO admin.
 * - Falls back to the AMO overview (or login) when unauthorized.
 */
const RequireTenantAdmin: React.FC<RequireTenantAdminProps> = ({ children }) => {
  const location = useLocation();
  const amoCode = inferAmoCodeFromPath(location.pathname);
  const currentUser = getCachedUser();
  const isTenantAdmin = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin;

  if (!currentUser) {
    const target = amoCode ? `/maintenance/${amoCode}/login` : "/login";
    return (
      <Navigate
        to={target}
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  if (!isTenantAdmin) {
    const fallback = amoCode
      ? `/maintenance/${amoCode}/admin/overview`
      : "/login";
    return <Navigate to={fallback} replace />;
  }

  return children;
};

function resolveDefaultDepartment(amoCode: string): string {
  const currentUser = getCachedUser();
  if (currentUser?.is_superuser) {
    return "platform/control";
  }
  if (currentUser?.is_amo_admin) {
    return "admin/overview";
  }
  const target = getFirstAccessibleModuleRoute(amoCode, currentUser, getContext().department);
  return target.replace(`/maintenance/${amoCode}/`, "");
}

const DepartmentHomeRedirect: React.FC = () => {
  const location = useLocation();
  const amoCode = inferAmoCodeFromPath(location.pathname) || "system";
  return <Navigate to={`/maintenance/${amoCode}/${resolveDefaultDepartment(amoCode)}`} replace />;
};

const QualityRootRedirect: React.FC = () => {
  const location = useLocation();
  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  const amoCode = inferAmoCodeFromPath(location.pathname) || getContext().amoSlug || getContext().amoCode || "system";
  return <Navigate to={`/maintenance/${amoCode}/qms${location.search}`} replace />;
};

const LegacyEngineeringRedirect: React.FC = () => {
  const location = useLocation();
  const parts = location.pathname.split("/").filter(Boolean);
  const nextParts = parts.map((part) => (part === "engineering" ? "maintenance" : part));
  const target = `/${nextParts.join("/")}${location.search}`;
  return <Navigate to={target} replace />;
};

const LegacyTechnicalRecordsRedirect: React.FC = () => {
  const location = useLocation();
  const amoCode = inferAmoCodeFromPath(location.pathname) || getContext().amoSlug || getContext().amoCode || "system";
  const parts = location.pathname.split("/").filter(Boolean);
  const recordsIndex = parts.indexOf("records");
  const suffix = recordsIndex >= 0 ? parts.slice(recordsIndex + 1).join("/") : "";
  const base = `/maintenance/${amoCode}/production/records`;
  const target = suffix ? `${base}/${suffix}${location.search}` : `${base}${location.search}`;
  return <Navigate to={target} replace />;
};


const RequireFeatureAccess: React.FC<{ feature: ModuleFeature; children: React.ReactElement }> = ({ feature, children }) => {
  const location = useLocation();
  const currentUser = getCachedUser();
  const amoCode = inferAmoCodeFromPath(location.pathname) || getContext().amoSlug || getContext().amoCode || "system";
  if (!canViewFeature(currentUser, feature, getContext().department)) {
    return <Navigate to={getFirstAccessibleModuleRoute(amoCode, currentUser, getContext().department)} replace />;
  }
  return children;
};

const PageRouteLoading: React.FC<{ label?: string }> = ({ label = "Loadingâ€¦" }) => (
  <div className="page-loading" role="status" aria-live="polite">
    <div className="page-loading__card">
      <div className="page-loading__spinner" />
      <div className="page-loading__label">{label}</div>
    </div>
  </div>
);

class PortalRouteErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; message: string }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error?.message || "Unexpected portal rendering error." };
  }

  componentDidCatch(error: Error) {
    console.error("Portal route render failure", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="page-loading" role="alert">
          <div className="page-loading__card">
            <div className="page-loading__label">Portal page could not be rendered. {this.state.message}</div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * AppRouter
 * - Defines all app routes.
 * - BrowserRouter is already applied in src/main.tsx.
 */
export const AppRouter: React.FC = () => {
  return (
    <PortalRouteErrorBoundary>
      <Suspense fallback={<PageRouteLoading label="Loading portal workspaceâ€¦" />}>
        <Routes>

      <Route path="/doc-control" element={<RequireAuth><DocControlPages.LegacyDocControlRedirectPage /></RequireAuth>} />
      <Route path="/doc-control/*" element={<RequireAuth><DocControlPages.LegacyDocControlRedirectPage /></RequireAuth>} />

      <Route path="/maintenance/:amoCode/document-control" element={<RequireAuth><DocControlPages.DocControlDashboardPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/library" element={<RequireAuth><DocControlPages.DocControlLibraryPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/library/:docId" element={<RequireAuth><DocControlPages.DocControlDocumentDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/drafts" element={<RequireAuth><DocControlPages.DocControlDraftsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/drafts/:draftId" element={<RequireAuth><DocControlPages.DocControlDraftDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/change-proposals" element={<RequireAuth><DocControlPages.DocControlChangeProposalPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/change-proposals/:proposalId" element={<RequireAuth><DocControlPages.DocControlChangeProposalDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/revisions/:docId" element={<RequireAuth><DocControlPages.DocControlRevisionsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/lep/:docId" element={<RequireAuth><DocControlPages.DocControlLEPPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/tr" element={<RequireAuth><DocControlPages.DocControlTRPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/tr/:trId" element={<RequireAuth><DocControlPages.DocControlTRDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/distribution" element={<RequireAuth><DocControlPages.DocControlDistributionPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/distribution/:eventId" element={<RequireAuth><DocControlPages.DocControlDistributionDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/archive" element={<RequireAuth><DocControlPages.DocControlArchivePage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/reviews" element={<RequireAuth><DocControlPages.DocControlReviewsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/registers" element={<RequireAuth><DocControlPages.DocControlRegistersPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/document-control/settings" element={<RequireAuth><DocControlPages.DocControlSettingsPage /></RequireAuth>} />

      <Route path="/maintenance/:amoCode/:department/doc-control" element={<RequireAuth><DocControlPages.DocControlDashboardPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/library" element={<RequireAuth><DocControlPages.DocControlLibraryPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/library/:docId" element={<RequireAuth><DocControlPages.DocControlDocumentDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/drafts" element={<RequireAuth><DocControlPages.DocControlDraftsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/drafts/:draftId" element={<RequireAuth><DocControlPages.DocControlDraftDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/change-proposals" element={<RequireAuth><DocControlPages.DocControlChangeProposalPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/change-proposals/:proposalId" element={<RequireAuth><DocControlPages.DocControlChangeProposalDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/revisions/:docId" element={<RequireAuth><DocControlPages.DocControlRevisionsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/lep/:docId" element={<RequireAuth><DocControlPages.DocControlLEPPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/tr" element={<RequireAuth><DocControlPages.DocControlTRPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/tr/:trId" element={<RequireAuth><DocControlPages.DocControlTRDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/distribution" element={<RequireAuth><DocControlPages.DocControlDistributionPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/distribution/:eventId" element={<RequireAuth><DocControlPages.DocControlDistributionDetailPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/archive" element={<RequireAuth><DocControlPages.DocControlArchivePage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/reviews" element={<RequireAuth><DocControlPages.DocControlReviewsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/registers" element={<RequireAuth><DocControlPages.DocControlRegistersPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/doc-control/settings" element={<RequireAuth><DocControlPages.DocControlSettingsPage /></RequireAuth>} />

      {/* Root â†’ login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Platform login */}
      <Route path="/login" element={<LoginPage />} />

      {/* Platform superuser control plane */}
      <Route
        path="/platform/control"
        element={
          <RequireAuth>
            <PlatformControlPage />
          </RequireAuth>
        }
      />

      <Route path="/platform/tenants" element={<RequireAuth><PlatformTenantsPage /></RequireAuth>} />
      <Route path="/platform/users" element={<RequireAuth><PlatformUsersPage /></RequireAuth>} />
      <Route path="/platform/billing" element={<RequireAuth><PlatformBillingPage /></RequireAuth>} />
      <Route path="/platform/analytics" element={<RequireAuth><PlatformAnalyticsPage /></RequireAuth>} />
      <Route path="/platform/security" element={<RequireAuth><PlatformSecurityPage /></RequireAuth>} />
      <Route path="/platform/integrations" element={<RequireAuth><PlatformIntegrationsPage /></RequireAuth>} />
      <Route path="/platform/infrastructure" element={<RequireAuth><PlatformInfrastructurePage /></RequireAuth>} />

      <Route
        path="/verify/certificate/:certificateNumber"
        element={<PublicCertificateVerificationPage />}
      />
      <Route path="/verify/scan" element={<VerifyScanPage />} />


      {/* AMO-specific login, e.g. /maintenance/safarilink/login */}
      <Route path="/maintenance/:amoCode/login" element={<LoginPage />} />

      {/* Password reset */}
      <Route path="/reset-password" element={<PasswordResetPage />} />

      {/* CAR invite response page (external auditees) */}
      <Route path="/car-invite" element={<PublicCarInvitePage />} />

      {/* If someone visits /maintenance/:amoCode directly, send them somewhere safe */}
      <Route
        path="/maintenance/:amoCode"
        element={<DepartmentHomeRedirect />}
      />

      {/* Admin dashboard (System Admin area) */}
      <Route
        path="/maintenance/:amoCode/admin"
        element={<Navigate to="overview" replace />}
      />

      {/* Admin - overview */}
      <Route
        path="/maintenance/:amoCode/admin/overview"
        element={
          <RequireAuth>
            <AdminOverviewPage />
          </RequireAuth>
        }
      />

      {/* Admin - AMO management */}
      <Route
        path="/maintenance/:amoCode/admin/amos"
        element={
          <RequireAuth>
            <AdminAmoManagementPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/amo-profile"
        element={
          <RequireAuth>
            <AdminAmoProfilePage />
          </RequireAuth>
        }
      />

      {/* Admin - users */}
      <Route
        path="/maintenance/:amoCode/admin/users"
        element={
          <RequireAuth>
            <AdminDashboardPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/users/:userId"
        element={
          <RequireAuth>
            <RequireTenantAdmin>
              <AdminUserDetailPage />
            </RequireTenantAdmin>
          </RequireAuth>
        }
      />

      {/* Admin - create user */}
      <Route
        path="/maintenance/:amoCode/admin/users/new"
        element={
          <RequireAuth>
            <AdminUserNewPage />
          </RequireAuth>
        }
      />

      {/* Admin - AMO asset setup */}
      <Route
        path="/maintenance/:amoCode/admin/amo-assets"
        element={
          <RequireAuth>
            <AdminAmoAssetsPage />
          </RequireAuth>
        }
      />

      {/* Admin - billing */}
      <Route
        path="/maintenance/:amoCode/admin/billing"
        element={
          <RequireAuth>
            <RequireTenantAdmin>
              <SubscriptionManagementPage />
            </RequireTenantAdmin>
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/invoices"
        element={
          <RequireAuth>
            <RequireTenantAdmin>
              <AdminInvoicesPage />
            </RequireTenantAdmin>
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/invoices/:invoiceId"
        element={
          <RequireAuth>
            <RequireTenantAdmin>
              <AdminInvoiceDetailPage />
            </RequireTenantAdmin>
          </RequireAuth>
        }
      />

      {/* Admin - usage throttling */}
      <Route
        path="/maintenance/:amoCode/admin/settings"
        element={
          <RequireAuth>
            <RequireTenantAdmin>
              <AdminUsageSettingsPage />
            </RequireTenantAdmin>
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/email-logs"
        element={
          <RequireAuth>
            <EmailLogsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/admin/email-settings"
        element={
          <RequireAuth>
            <EmailServerSettingsPage />
          </RequireAuth>
        }
      />

      {/* Onboarding / password setup */}
      <Route
        path="/maintenance/:amoCode/onboarding"
        element={<Navigate to="setup" replace />}
      />
      <Route
        path="/maintenance/:amoCode/onboarding/setup"
        element={
          <RequireAuth>
            <OnboardingPasswordPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/profile"
        element={
          <RequireAuth>
            <UserProfilePage />
          </RequireAuth>
        }
      />

      <Route path="/maintenance/:amoCode/planning" element={<RequireAuth><RequireFeatureAccess feature="planning.dashboard"><PlanningProductionPages.PlanningDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/dashboard" element={<RequireAuth><RequireFeatureAccess feature="planning.dashboard"><PlanningProductionPages.PlanningDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/utilisation-monitoring" element={<RequireAuth><RequireFeatureAccess feature="planning.utilisation-monitoring"><PlanningProductionPages.PlanningUtilisationPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/forecast-due-list" element={<RequireAuth><RequireFeatureAccess feature="planning.forecast-due-list"><PlanningProductionPages.PlanningForecastPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/amp" element={<RequireAuth><RequireFeatureAccess feature="planning.amp"><PlanningProductionPages.PlanningAmpPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/task-library" element={<RequireAuth><RequireFeatureAccess feature="planning.task-library"><PlanningProductionPages.PlanningTaskLibraryPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/ad-sb-eo-control" element={<RequireAuth><RequireFeatureAccess feature="planning.ad-sb-eo-control"><PlanningProductionPages.PlanningAdSbPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/work-packages" element={<RequireAuth><RequireFeatureAccess feature="planning.work-packages"><PlanningProductionPages.PlanningWorkPackagesPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/work-orders" element={<RequireAuth><RequireFeatureAccess feature="planning.work-orders"><PlanningProductionPages.PlanningWorkOrdersPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/deferments" element={<RequireAuth><RequireFeatureAccess feature="planning.deferments"><PlanningProductionPages.PlanningDefermentsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/non-routine-review" element={<RequireAuth><RequireFeatureAccess feature="planning.non-routine-review"><PlanningProductionPages.PlanningNonRoutinePage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/watchlists" element={<RequireAuth><RequireFeatureAccess feature="planning.watchlists"><PlanningProductionPages.WatchlistsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/publication-review" element={<RequireAuth><RequireFeatureAccess feature="planning.publication-review"><PlanningProductionPages.PublicationReviewPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/planning/compliance-actions" element={<RequireAuth><RequireFeatureAccess feature="planning.compliance-actions"><PlanningProductionPages.ComplianceActionsPage /></RequireFeatureAccess></RequireAuth>} />

      <Route path="/maintenance/:amoCode/production/dashboard" element={<RequireAuth><RequireFeatureAccess feature="production.dashboard"><PlanningProductionPages.ProductionDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/control-board" element={<RequireAuth><RequireFeatureAccess feature="production.control-board"><PlanningProductionPages.ProductionControlBoardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/work-order-execution" element={<RequireAuth><RequireFeatureAccess feature="production.work-order-execution"><PlanningProductionPages.ProductionExecutionPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/findings" element={<RequireAuth><RequireFeatureAccess feature="production.findings"><PlanningProductionPages.ProductionFindingsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/materials" element={<RequireAuth><RequireFeatureAccess feature="production.materials"><PlanningProductionPages.ProductionMaterialsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/review-inspection" element={<RequireAuth><RequireFeatureAccess feature="production.review-inspection"><PlanningProductionPages.ProductionReviewInspectionPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/release-prep" element={<RequireAuth><RequireFeatureAccess feature="production.release-prep"><PlanningProductionPages.ProductionReleasePrepPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/compliance-items" element={<RequireAuth><RequireFeatureAccess feature="production.compliance-items"><PlanningProductionPages.ProductionComplianceItemsPage /></RequireFeatureAccess></RequireAuth>} />


      <Route
        path="/maintenance/:amoCode/production"
        element={
          <RequireAuth>
            <Navigate to="dashboard" replace />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/production/workspace"
        element={
          <RequireAuth>
            <ProductionWorkspacePage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/production/fleet"
        element={
          <RequireAuth>
            <ProductionWorkspacePage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/production/fleet/:tailId"
        element={
          <RequireAuth>
            <ProductionWorkspacePage />
          </RequireAuth>
        }
      />

      <Route path="/production" element={<RequireAuth><ProductionWorkspacePage /></RequireAuth>} />
      <Route path="/production/fleet" element={<RequireAuth><ProductionWorkspacePage /></RequireAuth>} />
      <Route path="/production/fleet/:tailId" element={<RequireAuth><ProductionWorkspacePage /></RequireAuth>} />

      <Route path="/maintenance/:amoCode/maintenance" element={<RequireAuth><RequireFeatureAccess feature="maintenance.dashboard"><MaintenanceDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/dashboard" element={<RequireAuth><RequireFeatureAccess feature="maintenance.dashboard"><MaintenanceDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/work-orders" element={<RequireAuth><RequireFeatureAccess feature="maintenance.work-orders"><MaintenanceWorkOrdersPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/work-orders/:woId" element={<RequireAuth><RequireFeatureAccess feature="maintenance.work-orders"><MaintenanceWorkOrderDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/work-packages" element={<RequireAuth><RequireFeatureAccess feature="maintenance.work-packages"><MaintenanceWorkPackagesPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/defects" element={<RequireAuth><RequireFeatureAccess feature="maintenance.defects"><MaintenanceDefectsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/defects/:defectId" element={<RequireAuth><RequireFeatureAccess feature="maintenance.defects"><MaintenanceDefectDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/non-routines" element={<RequireAuth><RequireFeatureAccess feature="maintenance.non-routines"><MaintenanceNonRoutinesPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/non-routines/:nrId" element={<RequireAuth><RequireFeatureAccess feature="maintenance.non-routines"><MaintenanceNonRoutineDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/inspections" element={<RequireAuth><RequireFeatureAccess feature="maintenance.inspections"><MaintenanceInspectionsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/inspections/:inspectionId" element={<RequireAuth><RequireFeatureAccess feature="maintenance.inspections"><MaintenanceInspectionDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/parts-tools" element={<RequireAuth><RequireFeatureAccess feature="maintenance.parts-tools"><MaintenancePartsToolsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/closeout" element={<RequireAuth><RequireFeatureAccess feature="maintenance.closeout"><MaintenanceCloseoutPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/reports" element={<RequireAuth><RequireFeatureAccess feature="maintenance.reports"><MaintenanceReportsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/maintenance/settings" element={<RequireAuth><RequireFeatureAccess feature="maintenance.settings"><MaintenanceSettingsPage /></RequireFeatureAccess></RequireAuth>} />

      <Route path="/maintenance/:amoCode/engineering" element={<LegacyEngineeringRedirect />} />
      <Route path="/maintenance/:amoCode/engineering/*" element={<LegacyEngineeringRedirect />} />

      <Route path="/maintenance/:amoCode/production/records" element={<RequireAuth><RequireFeatureAccess feature="production.records.dashboard"><TechnicalRecordsPages.TechnicalRecordsDashboardPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/aircraft" element={<RequireAuth><RequireFeatureAccess feature="production.records.aircraft"><TechnicalRecordsPages.AircraftRecordsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/aircraft/:tailId" element={<RequireAuth><RequireFeatureAccess feature="production.records.aircraft"><TechnicalRecordsPages.AircraftRecordDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/logbooks" element={<RequireAuth><RequireFeatureAccess feature="production.records.logbooks"><TechnicalRecordsPages.LogbooksPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/logbooks/:tailId" element={<RequireAuth><RequireFeatureAccess feature="production.records.logbooks"><TechnicalRecordsPages.LogbookByTailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/deferrals" element={<RequireAuth><RequireFeatureAccess feature="production.records.deferrals"><TechnicalRecordsPages.DeferralsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/deferrals/:deferralId" element={<RequireAuth><RequireFeatureAccess feature="production.records.deferrals"><TechnicalRecordsPages.DeferralDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/maintenance-records" element={<RequireAuth><RequireFeatureAccess feature="production.records.maintenance-records"><TechnicalRecordsPages.MaintenanceRecordsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/maintenance-records/:recordId" element={<RequireAuth><RequireFeatureAccess feature="production.records.maintenance-records"><TechnicalRecordsPages.MaintenanceRecordDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/airworthiness" element={<RequireAuth><RequireFeatureAccess feature="production.records.airworthiness"><TechnicalRecordsPages.AirworthinessPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/airworthiness/ad" element={<RequireAuth><RequireFeatureAccess feature="production.records.airworthiness"><TechnicalRecordsPages.ADRegisterPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/airworthiness/ad/:adId" element={<RequireAuth><RequireFeatureAccess feature="production.records.airworthiness"><TechnicalRecordsPages.ADDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/airworthiness/sb" element={<RequireAuth><RequireFeatureAccess feature="production.records.airworthiness"><TechnicalRecordsPages.SBRegisterPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/airworthiness/sb/:sbId" element={<RequireAuth><RequireFeatureAccess feature="production.records.airworthiness"><TechnicalRecordsPages.SBDetailPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/llp" element={<RequireAuth><RequireFeatureAccess feature="production.records.llp-components"><TechnicalRecordsPages.LLPPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/components" element={<RequireAuth><RequireFeatureAccess feature="production.records.llp-components"><TechnicalRecordsPages.ComponentsPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/reconciliation" element={<RequireAuth><RequireFeatureAccess feature="production.records.reconciliation"><TechnicalRecordsPages.ReconciliationPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/traceability" element={<RequireAuth><RequireFeatureAccess feature="production.records.traceability"><TechnicalRecordsPages.TraceabilityPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/packs" element={<RequireAuth><RequireFeatureAccess feature="production.records.packs"><TechnicalRecordsPages.PacksPage /></RequireFeatureAccess></RequireAuth>} />
      <Route path="/maintenance/:amoCode/production/records/settings" element={<RequireAuth><RequireFeatureAccess feature="production.records.settings"><TechnicalRecordsPages.TechnicalRecordsSettingsPage /></RequireFeatureAccess></RequireAuth>} />


      {/* Canonical QMS route surface. Register, workflow, reporting, feedback, and archive views are remastered in QmsCanonicalPage. */}
      <Route
        path="/maintenance/:amoCode/qms"
        element={
          <RequireAuth>
            <RequireQmsPermission permission="qms.dashboard.view">
              <QmsCanonicalPage />
            </RequireQmsPermission>
          </RequireAuth>
        }
      />

      <Route path="/maintenance/:amoCode/qms/tasks" element={<RequireAuth><QmsInboxRedirect /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/audits/programme" element={<RequireAuth><QmsProgrammeRedirect /></RequireAuth>} />

      <Route path="/maintenance/:amoCode/qms/documents/reader/:docId/revisions/:revId/view" element={<RequireAuth><RequireQmsPermission permission="qms.document.view"><ManualReaderPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/documents/:docId/revisions/:revId/view" element={<RequireAuth><RequireQmsPermission permission="qms.document.view"><ManualReaderPage /></RequireQmsPermission></RequireAuth>} />

      <Route path="/maintenance/:amoCode/qms/audits/schedules/:scheduleId" element={<RequireAuth><RequireQmsPermission permission="qms.audit.view"><QualityAuditScheduleDetailPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/audits/:auditId/*" element={<RequireAuth><RequireQmsPermission permission="qms.audit.view"><QualityAuditRunHubPage /></RequireQmsPermission></RequireAuth>} />

      <Route path="/maintenance/:amoCode/qms/cars/:carId/*" element={<RequireAuth><RequireQmsPermission permission="qms.car.view"><QualityCarsPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/training-competence/people/:userId/*" element={<RequireAuth><RequireQmsPermission permission="qms.training.view"><QMSTrainingUserPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/evidence-vault/:evidenceId" element={<RequireAuth><RequireQmsPermission permission="qms.evidence.view"><QualityEvidenceViewerPage /></RequireQmsPermission></RequireAuth>} />

      <Route path="/maintenance/:amoCode/qms/aerodoc/hangar" element={<RequireAuth><RequireQmsPermission permission="qms.document.view"><AeroDocHangarDashboardPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/aerodoc/compliance" element={<RequireAuth><RequireQmsPermission permission="qms.document.view"><AeroDocComplianceHealthPage /></RequireQmsPermission></RequireAuth>} />
      <Route path="/maintenance/:amoCode/qms/aerodoc/audit-mode" element={<RequireAuth><RequireQmsPermission permission="qms.audit.execute"><AeroDocAuditModePage /></RequireQmsPermission></RequireAuth>} />

      <Route path="/maintenance/:amoCode/qms/*" element={<RequireAuth><RequireQmsPermission permission="qms.dashboard.view"><QmsCanonicalPage /></RequireQmsPermission></RequireAuth>} />

      {/* Legacy QMS route surfaces are no longer active. They redirect to the canonical route. */}
      <Route path="/maintenance/:amoCode/quality" element={<QualityRootRedirect />} />
      <Route path="/maintenance/:amoCode/:department/training-competence" element={<RequireAuth><LegacyTrainingCompetenceRedirect /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/*" element={<RequireAuth><LegacyQmsRedirect /></RequireAuth>} />

      {/* Department dashboard, e.g. /maintenance/safarilink/maintenance */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        }
      />

      <Route path="/maintenance/:amoCode/manuals" element={<RequireAuth><ManualsDashboardPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/master-list" element={<RequireAuth><ManualMasterListPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/:manualId" element={<RequireAuth><ManualOverviewPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/:manualId/rev/:revId/read" element={<RequireAuth><ManualReaderPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/:manualId/rev/:revId/diff" element={<RequireAuth><ManualDiffPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/:manualId/rev/:revId/workflow" element={<RequireAuth><ManualWorkflowPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/manuals/:manualId/rev/:revId/exports" element={<RequireAuth><ManualExportsPage /></RequireAuth>} />

      <Route path="/t/:tenantSlug/manuals" element={<RequireAuth><ManualsDashboardPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/master-list" element={<RequireAuth><ManualMasterListPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/:manualId" element={<RequireAuth><ManualOverviewPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/read" element={<RequireAuth><ManualReaderPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/diff" element={<RequireAuth><ManualDiffPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/workflow" element={<RequireAuth><ManualWorkflowPage /></RequireAuth>} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/exports" element={<RequireAuth><ManualExportsPage /></RequireAuth>} />


      <Route path="/records" element={<LegacyTechnicalRecordsRedirect />} />
      <Route path="/records/*" element={<LegacyTechnicalRecordsRedirect />} />

      {/* Catch-all â†’ login */}
      <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </PortalRouteErrorBoundary>
  );
};

export default AppRouter;

