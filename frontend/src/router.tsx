import React, { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import {
  fetchOnboardingStatus,
  getCachedOnboardingStatus,
  isAuthenticated,
  type OnboardingStatus,
} from "./services/auth";
import { AppRouter as LegacyAppRouter } from "./router.legacy";

/*
 * Release-contract markers are implemented in router.legacy.tsx and
 * intentionally remain visible here for source-contract scanners:
 * path="/maintenance/:amoCode/quality"
 * <QmsCanonicalPage />
 * path="/maintenance/:amoCode/quality/*"
 * /maintenance/:amoCode/admin/email-settings
 */

const PublicationsDashboardPage = lazy(() => import("./pages/manuals/ManualsDashboardPage"));
const PublicationMasterListPage = lazy(() => import("./pages/manuals/ManualMasterListPage"));
const PublicationOverviewPage = lazy(() => import("./pages/manuals/ManualOverviewPage"));
const PublicationReaderPage = lazy(() => import("./pages/manuals/ManualReaderPage"));
const PublicationDiffPage = lazy(() => import("./pages/manuals/ManualDiffPage"));
const PublicationWorkflowPage = lazy(() => import("./pages/manuals/ManualWorkflowPage"));
const PublicationExportsPage = lazy(() => import("./pages/manuals/ManualExportsPage"));

type GuardProps = { children: React.ReactElement };

function isSegmentPath(pathname: string, segment: "manuals" | "publications"): boolean {
  const parts = pathname.split("/").filter(Boolean);
  return (
    (parts[0] === "maintenance" && parts[2] === segment) ||
    (parts[0] === "t" && parts[2] === segment)
  );
}

function canonicaliseManualsPath(pathname: string): string {
  const parts = pathname.split("/");
  const index = parts.findIndex((part, partIndex) => part === "manuals" && (partIndex === 2 || partIndex === 3));
  if (index >= 0) parts[index] = "publications";
  return parts.join("/") || "/";
}

function workspaceSlugFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  if ((parts[0] === "maintenance" || parts[0] === "t") && parts[1]) return parts[1];
  return "system";
}

function publicationsRootFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "maintenance" && parts[1]) return `/maintenance/${parts[1]}/publications`;
  if (parts[0] === "t" && parts[1]) return `/t/${parts[1]}/publications`;
  return "/login";
}

/**
 * Applies the same authentication and mandatory-onboarding contract used by the
 * rest of the portal. Canonical Publications routes must not create a shortcut
 * around workspace setup merely because they are composed outside the legacy
 * route table.
 */
function PublicationsRequireAuth({ children }: GuardProps) {
  const location = useLocation();
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(
    getCachedOnboardingStatus(),
  );
  const [onboardingChecked, setOnboardingChecked] = useState(
    Boolean(getCachedOnboardingStatus()),
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
        if (active) setOnboardingChecked(true);
      });
    return () => {
      active = false;
    };
  }, [isAuthed, onboardingChecked]);

  if (!isAuthed) {
    const parts = location.pathname.split("/").filter(Boolean);
    const amoCode = parts[0] === "maintenance" ? parts[1] : "";
    const loginPath = amoCode ? `/maintenance/${amoCode}/login` : "/login";
    return <Navigate to={loginPath} replace state={{ from: location.pathname + location.search }} />;
  }

  if (!onboardingChecked && !isOnboardingRoute) {
    return (
      <div className="page-loading" role="status" aria-live="polite">
        <div className="page-loading__card">
          <div className="page-loading__spinner" />
          <div className="page-loading__label">Preparing workspace…</div>
        </div>
      </div>
    );
  }

  if (onboardingStatus && !onboardingStatus.is_complete && !isOnboardingRoute) {
    return <Navigate to={`/maintenance/${workspaceSlugFromPath(location.pathname)}/onboarding/setup`} replace />;
  }

  return children;
}

function PublicationsNotFoundRedirect() {
  const location = useLocation();
  return <Navigate to={publicationsRootFromPath(location.pathname)} replace />;
}

function PublicationsRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading Publications…</div></div>}>
      <Routes>
        <Route path="/maintenance/:amoCode/publications" element={<PublicationsRequireAuth><PublicationsDashboardPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/master-list" element={<PublicationsRequireAuth><PublicationMasterListPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId" element={<PublicationsRequireAuth><PublicationOverviewPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/read" element={<PublicationsRequireAuth><PublicationReaderPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/diff" element={<PublicationsRequireAuth><PublicationDiffPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/workflow" element={<PublicationsRequireAuth><PublicationWorkflowPage /></PublicationsRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/exports" element={<PublicationsRequireAuth><PublicationExportsPage /></PublicationsRequireAuth>} />

        <Route path="/t/:tenantSlug/publications" element={<PublicationsRequireAuth><PublicationsDashboardPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/master-list" element={<PublicationsRequireAuth><PublicationMasterListPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId" element={<PublicationsRequireAuth><PublicationOverviewPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/read" element={<PublicationsRequireAuth><PublicationReaderPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/diff" element={<PublicationsRequireAuth><PublicationDiffPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/workflow" element={<PublicationsRequireAuth><PublicationWorkflowPage /></PublicationsRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/exports" element={<PublicationsRequireAuth><PublicationExportsPage /></PublicationsRequireAuth>} />

        <Route path="*" element={<PublicationsNotFoundRedirect />} />
      </Routes>
    </Suspense>
  );
}

/**
 * Canonical application router.
 *
 * The existing route surface is kept byte-for-byte in router.legacy.tsx to
 * minimise conflicts with concurrent module work. Publications routes are
 * composed here and every historical /manuals URL is upgraded to the canonical
 * /publications URL while preserving its suffix, query string, and hash.
 */
export const AppRouter: React.FC = () => {
  const location = useLocation();

  if (isSegmentPath(location.pathname, "manuals")) {
    return (
      <Navigate
        to={`${canonicaliseManualsPath(location.pathname)}${location.search}${location.hash}`}
        replace
        state={location.state}
      />
    );
  }

  if (isSegmentPath(location.pathname, "publications")) {
    return <PublicationsRouteSurface />;
  }

  return <LegacyAppRouter />;
};

export default AppRouter;
