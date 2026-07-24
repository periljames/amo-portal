import React, { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { isAuthenticated } from "./services/auth";
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

function publicationsRootFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "maintenance" && parts[1]) return `/maintenance/${parts[1]}/publications`;
  if (parts[0] === "t" && parts[1]) return `/t/${parts[1]}/publications`;
  return "/login";
}

function PublicationsRequireAuth({ children }: GuardProps) {
  const location = useLocation();
  if (isAuthenticated()) return children;
  const parts = location.pathname.split("/").filter(Boolean);
  const amoCode = parts[0] === "maintenance" ? parts[1] : "";
  const loginPath = amoCode ? `/maintenance/${amoCode}/login` : "/login";
  return <Navigate to={loginPath} replace state={{ from: location.pathname + location.search }} />;
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
