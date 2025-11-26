// src/router.tsx
// App routing
// - Public routes: /login and /maintenance/:amoCode/login
// - Protected routes (JWT required via services/auth): department dashboards,
//   CRS pages, aircraft import, and admin user management.
// - Uses RequireAuth wrapper to redirect unauthenticated users back to login.

import React from "react";
import {
  Routes,
  Route,
  Navigate,
  useLocation,
  useParams,
} from "react-router-dom";

import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import CRSNewPage from "./pages/CRSNewPage";
import AircraftImportPage from "./pages/AircraftImportPage";
import AdminUserNewPage from "./pages/AdminUserNewPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";

import { isAuthenticated } from "./services/auth";

type RequireAuthProps = {
  children: React.ReactElement;
};

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
  const { amoCode } = useParams<{ amoCode?: string }>();

  if (!isAuthenticated()) {
    const target = amoCode ? `/maintenance/${amoCode}/login` : "/login";

    return (
      <Navigate
        to={target}
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
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

      {/* Admin dashboard (System Admin area) */}
      <Route
        path="/maintenance/:amoCode/admin"
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

      {/* Department dashboard, e.g. /maintenance/safarilink/engineering */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
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

      {/* Catch-all → login */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
};

export default AppRouter;
