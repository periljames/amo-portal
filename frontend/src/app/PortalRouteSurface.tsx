import React, { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { getCachedUser, isAuthenticated } from "../services/auth";
import { fetchBillingAccessStatus } from "../services/billing";
import PortalRoutes from "../portalRoutes";

const DepartmentHomePage = lazy(() => import("../pages/DepartmentHomePage"));
const EhmDashboardPage = lazy(() => import("../pages/ehm/EhmDashboardPage"));
const EhmTrendsPage = lazy(() => import("../pages/ehm/EhmTrendsPage"));
const EhmUploadsPage = lazy(() => import("../pages/ehm/EhmUploadsPage"));

const DEPARTMENT_HOMES = new Set([
  "planning",
  "production",
  "maintenance",
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

function BillingAccessBoundary({ amoCode, children }: { amoCode: string; children: React.ReactElement }) {
  const location = useLocation();
  const currentUser = getCachedUser();
  const [checking, setChecking] = useState(false);
  const [locked, setLocked] = useState(false);
  const parts = pathSegments(location.pathname);
  const tenantSection = parts.slice(2).join("/");
  const isBillingCurePath = tenantSection.startsWith("admin/billing") || tenantSection.startsWith("admin/invoices");
  const isAuthOrOnboarding = tenantSection === "login" || tenantSection.startsWith("onboarding/");
  const shouldCheck = isAuthenticated()
    && !currentUser?.is_superuser
    && !isBillingCurePath
    && !isAuthOrOnboarding;

  useEffect(() => {
    if (!shouldCheck) {
      setChecking(false);
      setLocked(false);
      return;
    }
    let active = true;
    setChecking(true);
    fetchBillingAccessStatus()
      .then((status) => {
        if (!active) return;
        setLocked(Boolean(status.redirect_to_billing && !status.has_access));
      })
      .catch(() => {
        // Do not turn a transient billing-status read failure into a denial of
        // service. Module API enforcement remains authoritative server-side.
        if (active) setLocked(false);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => { active = false; };
  }, [location.pathname, shouldCheck]);

  if (checking) return <LoadingRoute label="account access" />;
  if (locked) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    const query = new URLSearchParams({ reason: "payment_required", returnTo });
    return (
      <Navigate
        to={`/maintenance/${encodeURIComponent(amoCode)}/admin/billing?${query.toString()}`}
        replace
        state={{ from: returnTo }}
      />
    );
  }
  return children;
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
  return (
    <BillingAccessBoundary amoCode={amoCode}>
      <Suspense fallback={<LoadingRoute label={label} />}>{children}</Suspense>
    </BillingAccessBoundary>
  );
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

  // PortalRoutes contains the wider route registry. Keep the billing boundary
  // outside it so every authenticated tenant surface follows the same cure path.
  return (
    <BillingAccessBoundary amoCode={amoCode}>
      <PortalRoutes />
    </BillingAccessBoundary>
  );
};

export default AppRouter;