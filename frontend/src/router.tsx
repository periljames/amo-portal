// src/router.tsx
// App routing
// - Public routes: /login and /maintenance/:amoCode/login
// - Protected routes (JWT required via services/auth): department dashboards,
//   CRS pages, aircraft import, QMS dashboard, and admin user management.
// - Uses RequireAuth wrapper to redirect unauthenticated users back to login.

import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import * as DocControlPages from "./pages/DocControlPages";
import * as TechnicalRecordsPages from "./pages/TechnicalRecordsPages";

import {
  fetchOnboardingStatus,
  getCachedOnboardingStatus,
  getCachedUser,
  isAuthenticated,
  type OnboardingStatus,
} from "./services/auth";

const LoginPage = lazy(() => import("./pages/LoginPage"));
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
const QMSHomePage = lazy(() => import("./pages/QMSHomePage"));
const QMSDocumentsPage = lazy(() => import("./pages/QMSDocumentsPage"));
const QMSAuditsPage = lazy(() => import("./pages/QMSAuditsPage"));
const QMSChangeControlPage = lazy(() => import("./pages/QMSChangeControlPage"));
const MyTasksPage = lazy(() => import("./pages/MyTasksPage"));
const QMSTrainingPage = lazy(() => import("./pages/QMSTrainingPage"));
const QMSTrainingUserPage = lazy(() => import("./pages/QMSTrainingUserPage"));
const QMSEventsPage = lazy(() => import("./pages/QMSEventsPage"));
const QMSKpisPage = lazy(() => import("./pages/QMSKpisPage"));
const AeroDocAuditModePage = lazy(() => import("./pages/AeroDocAuditModePage"));
const AeroDocComplianceHealthPage = lazy(() => import("./pages/AeroDocComplianceHealthPage"));
const AeroDocHangarDashboardPage = lazy(() => import("./pages/AeroDocHangarDashboardPage"));
const QualityCarsPage = lazy(() => import("./pages/QualityCarsPage"));
const PublicCarInvitePage = lazy(() => import("./pages/PublicCarInvitePage"));
const SubscriptionManagementPage = lazy(() => import("./pages/SubscriptionManagementPage"));
const UpsellPage = lazy(() => import("./pages/UpsellPage"));
const UserWidgetsPage = lazy(() => import("./pages/UserWidgetsPage"));
const OnboardingPasswordPage = lazy(() => import("./pages/OnboardingPasswordPage"));

const QualityAuditPlannerPage = lazy(() => import("./pages/QualityAuditPlannerPage"));
const QualityAuditPlannerCalendarPage = lazy(() => import("./pages/QualityAuditPlannerCalendarPage"));
const QualityAuditPlannerListPage = lazy(() => import("./pages/QualityAuditPlannerListPage"));
const QualityAuditScheduleDetailPage = lazy(() => import("./pages/QualityAuditScheduleDetailPage"));
const QualityAuditRunHubPage = lazy(() => import("./pages/QualityAuditRunHubPage"));
const QualityCloseoutHubPage = lazy(() => import("./pages/QualityCloseoutHubPage"));
const QualityCloseoutFindingsPage = lazy(() => import("./pages/QualityCloseoutFindingsPage"));
const QualityCloseoutCarsPage = lazy(() => import("./pages/QualityCloseoutCarsPage"));
const QualityAuditEvidencePage = lazy(() => import("./pages/QualityAuditEvidencePage"));
const QualityAuditRegisterPage = lazy(() => import("./pages/QualityAuditRegisterPage"));
const QualityEvidenceLibraryPage = lazy(() => import("./pages/QualityEvidenceLibraryPage"));
const QualityEvidenceViewerPage = lazy(() => import("./pages/QualityEvidenceViewerPage"));

const ManualsDashboardPage = lazy(() => import("./pages/manuals/ManualsDashboardPage"));
const ManualOverviewPage = lazy(() => import("./pages/manuals/ManualOverviewPage"));
const ManualReaderPage = lazy(() => import("./pages/manuals/ManualReaderPage"));
const ManualDiffPage = lazy(() => import("./pages/manuals/ManualDiffPage"));
const ManualWorkflowPage = lazy(() => import("./pages/manuals/ManualWorkflowPage"));
const ManualExportsPage = lazy(() => import("./pages/manuals/ManualExportsPage"));
const ManualMasterListPage = lazy(() => import("./pages/manuals/ManualMasterListPage"));
const ProductionWorkspacePage = lazy(() => import("./pages/ProductionWorkspacePage"));


type RequireAuthProps = {
  children: React.ReactElement;
};

type RequireTenantAdminProps = {
  children: React.ReactElement;
};


type QualityAliasRedirectProps = {
  suffix: string;
};

const QualityAliasRedirect: React.FC<QualityAliasRedirectProps> = ({ suffix }) => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const target = `/maintenance/${amoCode ?? "UNKNOWN"}/quality/qms${suffix}`;
  return <Navigate to={target} replace />;
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
    return null;
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

/**
 * AppRouter
 * - Defines all app routes.
 * - BrowserRouter is already applied in src/main.tsx.
 */
export const AppRouter: React.FC = () => {
  return (
    <Suspense fallback={<div className="page-loading">Loading…</div>}>
    <Routes>

      <Route path="/doc-control" element={<RequireAuth><DocControlPages.LegacyDocControlRedirectPage /></RequireAuth>} />
      <Route path="/doc-control/*" element={<RequireAuth><DocControlPages.LegacyDocControlRedirectPage /></RequireAuth>} />

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

      {/* Root → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Platform login */}
      <Route path="/login" element={<LoginPage />} />

      {/* AMO-specific login, e.g. /maintenance/safarilink/login */}
      <Route path="/maintenance/:amoCode/login" element={<LoginPage />} />

      {/* Password reset */}
      <Route path="/reset-password" element={<PasswordResetPage />} />

      {/* CAR invite response page (external auditees) */}
      <Route path="/car-invite" element={<PublicCarInvitePage />} />

      {/* If someone visits /maintenance/:amoCode directly, send them somewhere safe */}
      <Route
        path="/maintenance/:amoCode"
        element={<Navigate to="planning" replace />}
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

      {/* Department dashboard, e.g. /maintenance/safarilink/engineering */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        }
      />


      <Route
        path="/maintenance/:amoCode/production"
        element={
          <RequireAuth>
            <Navigate to="workspace" replace />
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

      {/* Work orders */}
      <Route
        path="/maintenance/:amoCode/:department/work-orders"
        element={
          <RequireAuth>
            <WorkOrderSearchPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/:department/work-orders/:id"
        element={
          <RequireAuth>
            <WorkOrderDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/:department/tasks"
        element={
          <RequireAuth>
            <MyTasksPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/:department/tasks/:taskId"
        element={
          <RequireAuth>
            <TaskSummaryPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/:department/tasks/:taskId/print"
        element={
          <RequireAuth>
            <TaskPrintPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/ehm"
        element={
          <RequireAuth>
            <EhmDashboardPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/ehm/dashboard"
        element={
          <RequireAuth>
            <EhmDashboardPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/ehm/trends"
        element={
          <RequireAuth>
            <EhmTrendsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/ehm/uploads"
        element={
          <RequireAuth>
            <EhmUploadsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/reliability"
        element={
          <RequireAuth>
            <ReliabilityReportsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/reliability/reports"
        element={
          <RequireAuth>
            <ReliabilityReportsPage />
          </RequireAuth>
        }
      />

      {/* Upsell + pricing page */}
      <Route
        path="/maintenance/:amoCode/upsell"
        element={
          <RequireAuth>
            <UpsellPage />
          </RequireAuth>
        }
      />

      {/* Training status view, e.g. /maintenance/safarilink/planning/training */}
      <Route
        path="/maintenance/:amoCode/:department/training"
        element={
          <RequireAuth>
            <TrainingPage />
          </RequireAuth>
        }
      />

      {/* User widgets settings */}
      <Route
        path="/maintenance/:amoCode/:department/settings/widgets"
        element={
          <RequireAuth>
            <UserWidgetsPage />
          </RequireAuth>
        }
      />

      {/* New CRS, e.g. /maintenance/safarilink/planning/crs/new */}
      <Route
        path="/maintenance/:amoCode/:department/crs/new"
        element={
          <RequireAuth>
            <CRSNewPage />
          </RequireAuth>
        }
      />

      {/* Aircraft import, e.g. /maintenance/safarilink/engineering/aircraft-import */}
      <Route
        path="/maintenance/:amoCode/:department/aircraft-import"
        element={
          <RequireAuth>
            <AircraftImportPage />
          </RequireAuth>
        }
      />
      <Route
        path="/maintenance/:amoCode/:department/component-import"
        element={
          <RequireAuth>
            <ComponentImportPage />
          </RequireAuth>
        }
      />

      {/* Aircraft documents, e.g. /maintenance/safarilink/planning/aircraft-documents */}
      <Route
        path="/maintenance/:amoCode/:department/aircraft-documents"
        element={
          <RequireAuth>
            <AircraftDocumentsPage />
          </RequireAuth>
        }
      />

      {/* QMS dashboard, e.g. /maintenance/safarilink/quality/qms */}
      <Route
        path="/maintenance/:amoCode/:department/qms"
        element={
          <RequireAuth>
            <QMSHomePage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/tasks"
        element={
          <RequireAuth>
            <MyTasksPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/documents"
        element={
          <RequireAuth>
            <QMSDocumentsPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/audits"
        element={
          <RequireAuth>
            <QMSAuditsPage />
          </RequireAuth>
        }
      />
      <Route path="/maintenance/:amoCode/:department/qms/audits/plan" element={<RequireAuth><QualityAuditPlannerPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/register" element={<RequireAuth><QualityAuditRegisterPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/closeout" element={<RequireAuth><QualityCloseoutHubPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/closeout/:auditId" element={<RequireAuth><QualityCloseoutHubPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/closeout/findings/:findingId" element={<RequireAuth><QualityCloseoutFindingsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/closeout/cars/:carId" element={<RequireAuth><QualityCloseoutCarsPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/audits/:auditId/findings" element={<RequireAuth><QualityCloseoutFindingsPage /></RequireAuth>} />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/schedules/calendar"
        element={<RequireAuth><QualityAuditPlannerCalendarPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/schedules/list"
        element={<RequireAuth><QualityAuditPlannerListPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/schedules/:scheduleId"
        element={<RequireAuth><QualityAuditScheduleDetailPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/closeout/findings"
        element={<RequireAuth><QualityCloseoutFindingsPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/closeout/cars"
        element={<RequireAuth><QualityCloseoutCarsPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/:auditId"
        element={<RequireAuth><QualityAuditRunHubPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/audits/:auditId/evidence"
        element={<RequireAuth><QualityAuditEvidencePage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/evidence"
        element={<RequireAuth><QualityEvidenceLibraryPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/:department/qms/evidence/:evidenceId"
        element={<RequireAuth><QualityEvidenceViewerPage /></RequireAuth>}
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/change-control"
        element={
          <RequireAuth>
            <QMSChangeControlPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/cars"
        element={
          <RequireAuth>
            <QualityCarsPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/training"
        element={
          <RequireAuth>
            <QMSTrainingPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/training/:userId"
        element={
          <RequireAuth>
            <QMSTrainingUserPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/events"
        element={
          <RequireAuth>
            <QMSEventsPage />
          </RequireAuth>
        }
      />

      <Route
        path="/maintenance/:amoCode/:department/qms/kpis"
        element={
          <RequireAuth>
            <QMSKpisPage />
          </RequireAuth>
        }
      />

      <Route path="/maintenance/:amoCode/:department/qms/aerodoc/hangar" element={<RequireAuth><AeroDocHangarDashboardPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/aerodoc/compliance" element={<RequireAuth><AeroDocComplianceHealthPage /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/:department/qms/aerodoc/audit-mode" element={<RequireAuth><AeroDocAuditModePage /></RequireAuth>} />

      <Route path="/maintenance/:amoCode/quality/audits" element={<RequireAuth><QualityAliasRedirect suffix="/audits" /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/quality/audits/plan" element={<RequireAuth><QualityAliasRedirect suffix="/audits/plan" /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/quality/audits/register" element={<RequireAuth><QualityAliasRedirect suffix="/audits/register" /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/quality/audits/closeout" element={<RequireAuth><QualityAliasRedirect suffix="/audits/closeout" /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/quality/audits/schedules/calendar" element={<RequireAuth><QualityAliasRedirect suffix="/audits/schedules/calendar" /></RequireAuth>} />
      <Route path="/maintenance/:amoCode/quality/audits/schedules/list" element={<RequireAuth><QualityAliasRedirect suffix="/audits/schedules/list" /></RequireAuth>} />
      <Route
        path="/maintenance/:amoCode/quality/audits/schedules/:scheduleId"
        element={<RequireAuth><QualityAuditScheduleDetailPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/audits/:auditId"
        element={<RequireAuth><QualityAuditRunHubPage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/audits/:auditId/evidence"
        element={<RequireAuth><QualityAuditEvidencePage /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/audits/closeout/findings"
        element={<RequireAuth><QualityAliasRedirect suffix="/audits/closeout/findings" /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/audits/closeout/cars"
        element={<RequireAuth><QualityAliasRedirect suffix="/audits/closeout/cars" /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/evidence"
        element={<RequireAuth><QualityAliasRedirect suffix="/evidence" /></RequireAuth>}
      />
      <Route
        path="/maintenance/:amoCode/quality/evidence/:evidenceId"
        element={<RequireAuth><QualityEvidenceViewerPage /></RequireAuth>}
      />



      <Route
        path="/maintenance/:amoCode/:department/qms/documents/:docId/revisions/:revId/view"
        element={<RequireAuth><ManualReaderPage /></RequireAuth>}
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


      <Route path="/records" element={<RequireAuth><TechnicalRecordsPages.TechnicalRecordsDashboardPage /></RequireAuth>} />
      <Route path="/records/aircraft" element={<RequireAuth><TechnicalRecordsPages.AircraftRecordsPage /></RequireAuth>} />
      <Route path="/records/aircraft/:tailId" element={<RequireAuth><TechnicalRecordsPages.AircraftRecordDetailPage /></RequireAuth>} />
      <Route path="/records/logbooks" element={<RequireAuth><TechnicalRecordsPages.LogbooksPage /></RequireAuth>} />
      <Route path="/records/logbooks/:tailId" element={<RequireAuth><TechnicalRecordsPages.LogbookByTailPage /></RequireAuth>} />
      <Route path="/records/deferrals" element={<RequireAuth><TechnicalRecordsPages.DeferralsPage /></RequireAuth>} />
      <Route path="/records/deferrals/:deferralId" element={<RequireAuth><TechnicalRecordsPages.DeferralDetailPage /></RequireAuth>} />
      <Route path="/records/maintenance-records" element={<RequireAuth><TechnicalRecordsPages.MaintenanceRecordsPage /></RequireAuth>} />
      <Route path="/records/maintenance-records/:recordId" element={<RequireAuth><TechnicalRecordsPages.MaintenanceRecordDetailPage /></RequireAuth>} />
      <Route path="/records/airworthiness" element={<RequireAuth><TechnicalRecordsPages.AirworthinessPage /></RequireAuth>} />
      <Route path="/records/airworthiness/ad" element={<RequireAuth><TechnicalRecordsPages.ADRegisterPage /></RequireAuth>} />
      <Route path="/records/airworthiness/ad/:adId" element={<RequireAuth><TechnicalRecordsPages.ADDetailPage /></RequireAuth>} />
      <Route path="/records/airworthiness/sb" element={<RequireAuth><TechnicalRecordsPages.SBRegisterPage /></RequireAuth>} />
      <Route path="/records/airworthiness/sb/:sbId" element={<RequireAuth><TechnicalRecordsPages.SBDetailPage /></RequireAuth>} />
      <Route path="/records/llp" element={<RequireAuth><TechnicalRecordsPages.LLPPage /></RequireAuth>} />
      <Route path="/records/components" element={<RequireAuth><TechnicalRecordsPages.ComponentsPage /></RequireAuth>} />
      <Route path="/records/reconciliation" element={<RequireAuth><TechnicalRecordsPages.ReconciliationPage /></RequireAuth>} />
      <Route path="/records/traceability" element={<RequireAuth><TechnicalRecordsPages.TraceabilityPage /></RequireAuth>} />
      <Route path="/records/packs" element={<RequireAuth><TechnicalRecordsPages.PacksPage /></RequireAuth>} />
      <Route path="/records/settings" element={<RequireAuth><TechnicalRecordsPages.TechnicalRecordsSettingsPage /></RequireAuth>} />

      {/* Catch-all → login */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
    </Suspense>
  );
};

export default AppRouter;
