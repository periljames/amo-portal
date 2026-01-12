// src/router.tsx
// App routing
// - Public routes: /login and /maintenance/:amoCode/login
// - Protected routes (JWT required via services/auth): department dashboards,
//   CRS pages, aircraft import, QMS dashboard, and admin user management.
// - Uses RequireAuth wrapper to redirect unauthenticated users back to login.

import React from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";

import LoginPage from "./pages/LoginPage";
import PasswordResetPage from "./pages/PasswordResetPage";
import OnboardingPasswordPage from "./pages/OnboardingPasswordPage";
import DashboardPage from "./pages/DashboardPage";
import CRSNewPage from "./pages/CRSNewPage";
import AircraftImportPage from "./pages/AircraftImportPage";
import AdminUserNewPage from "./pages/AdminUserNewPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import AdminOverviewPage from "./pages/AdminOverviewPage";
import AdminAmoManagementPage from "./pages/AdminAmoManagementPage";
import AdminAmoAssetsPage from "./pages/AdminAmoAssetsPage";
import TrainingPage from "./pages/MyTrainingPage";
import QMSHomePage from "./pages/QMSHomePage";
import QualityCarsPage from "./pages/QualityCarsPage";
import UpsellPage from "./pages/UpsellPage";
import SubscriptionManagementPage from "./pages/SubscriptionManagementPage";

import { getCachedUser, isAuthenticated } from "./services/auth";

type RequireAuthProps = {
  children: React.ReactElement;
};

type RequireTenantAdminProps = {
  children: React.ReactElement;
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

  if (!isAuthenticated()) {
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

  const currentUser = getCachedUser();
  if (currentUser?.must_change_password) {
    const isOnboardingRoute = location.pathname.includes("/onboarding");
    if (!isOnboardingRoute) {
      const amoCode = inferAmoCodeFromPath(location.pathname) || "root";
      return <Navigate to={`/maintenance/${amoCode}/onboarding`} replace />;
    }
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
    <Routes>
      {/* Root → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Global login */}
      <Route path="/login" element={<LoginPage />} />

      {/* AMO-specific login, e.g. /maintenance/safarilink/login */}
      <Route path="/maintenance/:amoCode/login" element={<LoginPage />} />

      {/* Password reset */}
      <Route path="/reset-password" element={<PasswordResetPage />} />

      {/* First-login onboarding */}
      <Route
        path="/maintenance/:amoCode/onboarding"
        element={
          <RequireAuth>
            <OnboardingPasswordPage />
          </RequireAuth>
        }
      />

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

      {/* Admin - users */}
      <Route
        path="/maintenance/:amoCode/admin/users"
        element={
          <RequireAuth>
            <AdminDashboardPage />
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

      {/* Department dashboard, e.g. /maintenance/safarilink/engineering */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
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
        path="/maintenance/:amoCode/:department/qms/cars"
        element={
          <RequireAuth>
            <QualityCarsPage />
          </RequireAuth>
        }
      />

      {/* Catch-all → login */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
};

export default AppRouter;
