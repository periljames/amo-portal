import React, { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { isAuthenticated } from "../services/auth";
import PortalRoutes from "../portalRoutes";

const DepartmentHomePage = lazy(() => import("../pages/DepartmentHomePage"));
const ReliabilityReportsPage = lazy(() => import("../pages/ReliabilityReportsPage"));
const EhmDashboardPage = lazy(() => import("../pages/ehm/EhmDashboardPage"));
const EhmTrendsPage = lazy(() => import("../pages/ehm/EhmTrendsPage"));
const EhmUploadsPage = lazy(() => import("../pages/ehm/EhmUploadsPage"));

const DEPARTMENT_HOMES = new Set([
  "planning",
  "production",
  "maintenance",
  "reliability",
  "safety",
  "stores",
  "workshops",
]);
const SIMPLE_DEPARTMENT_VIEWS = new Set(["operations", "settings"]);

function pathSegments(pathname: string): string[] {
  return pathname.split("/").filter(Boolean).map((value) => {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  });
}

function LoadingRoute({ label }: { label: string }): React.ReactElement {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <div className="page-loading__card">Loading {label}…</div>
    </div>
  );
}

function AuthenticatedSurface({
  amoCode,
  label,
  children,
}: {
  amoCode: string;
  label: string;
  children: React.ReactElement;
}): React.ReactElement {
  if (!isAuthenticated()) {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}/login`} replace />;
  }
  return <Suspense fallback={<LoadingRoute label={label} />}>{children}</Suspense>;
}

export const AppRouter: React.FC = () => {
  const location = useLocation();
  const parts = pathSegments(location.pathname);
  const isTenantPath = parts[0] === "maintenance" && Boolean(parts[1]);
  if (!isTenantPath) return <PortalRoutes />;

  const amoCode = parts[1];
  const module = parts[2] || "";
  const view = parts[3] || "";

  if (
    DEPARTMENT_HOMES.has(module)
    && (parts.length === 3 || (parts.length === 4 && SIMPLE_DEPARTMENT_VIEWS.has(view)))
  ) {
    return (
      <Routes location={location}>
        <Route
          path="/maintenance/:amoCode/:department"
          element={
            <AuthenticatedSurface amoCode={amoCode} label={`${module} home`}>
              <DepartmentHomePage />
            </AuthenticatedSurface>
          }
        />
        <Route
          path="/maintenance/:amoCode/:department/:section"
          element={
            <AuthenticatedSurface amoCode={amoCode} label={`${module} workspace`}>
              <DepartmentHomePage />
            </AuthenticatedSurface>
          }
        />
      </Routes>
    );
  }

  if (module === "reliability" && view === "reports" && parts.length === 4) {
    return (
      <Routes location={location}>
        <Route
          path="/maintenance/:amoCode/reliability/reports"
          element={
            <AuthenticatedSurface amoCode={amoCode} label="reliability reports">
              <ReliabilityReportsPage />
            </AuthenticatedSurface>
          }
        />
      </Routes>
    );
  }

  if (module === "ehm" && parts.length === 4) {
    const surfaces: Record<string, React.ReactElement> = {
      dashboard: <EhmDashboardPage />,
      trends: <EhmTrendsPage />,
      uploads: <EhmUploadsPage />,
    };
    const surface = surfaces[view];
    if (surface) {
      return (
        <Routes location={location}>
          <Route
            path={`/maintenance/:amoCode/ehm/${view}`}
            element={
              <AuthenticatedSurface amoCode={amoCode} label={`EHM ${view}`}>
                {surface}
              </AuthenticatedSurface>
            }
          />
        </Routes>
      );
    }
  }

  return <PortalRoutes />;
};

export default AppRouter;
