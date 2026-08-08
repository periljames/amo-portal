import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { getCachedUser, isAuthenticated } from "../services/auth";
import { fetchBillingAccessStatus } from "../services/billing";
import { fetchTenantModuleAccess } from "../services/moduleCommerce";
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

function commercialModuleForPath(parts: string[]): string | null {
  const section = String(parts[2] || "").toLowerCase();
  if (!section || section === "admin" || section === "onboarding" || section === "login") return null;
  if (["quality", "document-control", "documents", "publications", "manuals"].includes(section)) return "quality";
  if (["training", "competence"].includes(section)) return "training";
  if (["fleet", "aircraft", "components"].includes(section)) return "fleet";
  if (["planning", "production", "maintenance", "work", "work-orders", "technical-records", "maintenance-program"].includes(section)) return "work";
  if (["reliability", "ehm"].includes(section)) return "reliability";
  if (["finance", "accounting"].includes(section)) return "finance";
  if (["stores", "inventory"].includes(section)) return "inventory";
  if (section === "procurement") return "procurement";
  // Safety, workshops, rostering and other platform-included/non-commercial
  // surfaces are intentionally not inferred into a paid product here.
  return null;
}

function LoadingRoute({ label }: { label: string }): React.ReactElement {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <div className="page-loading__card">Loading {label}…</div>
    </div>
  );
}

type BillingRedirect = {
  reason: "payment_required" | "module_payment_required" | "module_required";
  moduleCode?: string | null;
};

function BillingAccessBoundary({ amoCode, children }: { amoCode: string; children: React.ReactElement }) {
  const location = useLocation();
  const currentUser = getCachedUser();
  const [checking, setChecking] = useState(false);
  const [redirect, setRedirect] = useState<BillingRedirect | null>(null);
  const parts = useMemo(() => pathSegments(location.pathname), [location.pathname]);
  const tenantSection = parts.slice(2).join("/");
  const commercialModule = useMemo(() => commercialModuleForPath(parts), [parts]);
  const isBillingCurePath = tenantSection.startsWith("admin/billing") || tenantSection.startsWith("admin/invoices");
  const isAuthOrOnboarding = tenantSection === "login" || tenantSection.startsWith("onboarding/");
  const shouldCheck = isAuthenticated()
    && !currentUser?.is_superuser
    && !isBillingCurePath
    && !isAuthOrOnboarding;

  useEffect(() => {
    if (!shouldCheck) {
      setChecking(false);
      setRedirect(null);
      return;
    }
    let active = true;
    setChecking(true);
    setRedirect(null);

    const check = async () => {
      const account = await fetchBillingAccessStatus();
      if (!active) return;
      if (account.redirect_to_billing && !account.has_access) {
        setRedirect({ reason: "payment_required" });
        return;
      }
      if (!commercialModule) return;
      const moduleAccess = await fetchTenantModuleAccess(commercialModule);
      if (!active || moduleAccess.has_access || !moduleAccess.redirect_to_billing) return;
      setRedirect({
        reason: moduleAccess.access_state === "MODULE_PAYMENT_REQUIRED"
          ? "module_payment_required"
          : "module_required",
        moduleCode: commercialModule,
      });
    };

    void check()
      .catch(() => {
        // A transient status-read failure must not become its own outage. API
        // entitlement dependencies remain authoritative server-side.
        if (active) setRedirect(null);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => { active = false; };
  }, [commercialModule, location.pathname, shouldCheck]);

  if (checking) return <LoadingRoute label="account access" />;
  if (redirect) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    const query = new URLSearchParams({ reason: redirect.reason, returnTo });
    if (redirect.moduleCode) query.set("module", redirect.moduleCode);
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

  return (
    <BillingAccessBoundary amoCode={amoCode}>
      <PortalRoutes />
    </BillingAccessBoundary>
  );
};

export default AppRouter;
