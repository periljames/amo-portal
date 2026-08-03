import React, { Suspense, lazy } from "react";
import { Navigate, useLocation } from "react-router-dom";

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

  if (parts.length === 3 && DEPARTMENT_HOMES.has(module)) {
    return (
      <AuthenticatedSurface amoCode={amoCode} label={`${module} home`}>
        <DepartmentHomePage />
      </AuthenticatedSurface>
    );
  }

  if (module === "reliability" && view === "reports" && parts.length === 4) {
    return (
      <AuthenticatedSurface amoCode={amoCode} label="reliability reports">
        <ReliabilityReportsPage />
      </AuthenticatedSurface>
    );
  }

  if (module === "ehm" && parts.length === 4) {
    if (view === "dashboard") {
      return (
        <AuthenticatedSurface amoCode={amoCode} label="EHM dashboard">
          <EhmDashboardPage />
        </AuthenticatedSurface>
      );
    }
    if (view === "trends") {
      return (
        <AuthenticatedSurface amoCode={amoCode} label="EHM trends">
          <EhmTrendsPage />
        </AuthenticatedSurface>
      );
    }
    if (view === "uploads") {
      return (
        <AuthenticatedSurface amoCode={amoCode} label="EHM uploads">
          <EhmUploadsPage />
        </AuthenticatedSurface>
      );
    }
  }

  return <PortalRoutes />;
};

export default AppRouter;
