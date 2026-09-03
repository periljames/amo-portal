import React, { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import {
  fetchOnboardingStatus,
  getCachedOnboardingStatus,
  isAuthenticated,
  type OnboardingStatus,
} from "./services/auth";
import { classifyQmsPath, type QmsPathClassification } from "./pages/qms/routes/qmsRouteRegistry";
import { AppRouter as PortalRouteSurface } from "./app/PortalRouteSurface";

const QmsOverviewPage = lazy(() => import("./pages/qms/QmsOverviewPage"));
const QmsRegisterPage = lazy(() => import("./pages/qms/QmsRegisterPage"));
const QmsNotFoundPage = lazy(() => import("./pages/qms/QmsNotFoundPage"));
const QmsCarPerformanceReportPage = lazy(() => import("./pages/qms/QmsCarPerformanceReportPage"));
const ProcurementModule = lazy(() => import("./pages/procurement/ProcurementModule"));
const PublicationReaderPage = lazy(() => import("./pages/manuals/ManualReaderPage"));
const PublicationDiffPage = lazy(() => import("./pages/manuals/ManualDiffPage"));
const PublicationWorkflowPage = lazy(() => import("./pages/manuals/ManualWorkflowPage"));
const PublicationExportsPage = lazy(() => import("./pages/manuals/ManualExportsPage"));

const DocControlDashboardPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDashboardPage })));
const DocControlLibraryPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlLibraryPage })));
const DocControlChangesPortfolioPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlChangesPortfolioPage })));
const DocControlDocumentDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDocumentDetailPage })));
const DocControlDistributionPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDistributionPage })));
const DocControlCompliancePage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlCompliancePage })));
const DocControlReportsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlReportsPage })));
const DocControlAdministrationPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlAdministrationPage })));

type GuardProps = { children: React.ReactElement };

function pathSegments(pathname: string): string[] {
  return pathname.split("/").filter(Boolean);
}

function isSegmentPath(pathname: string, segment: "publications"): boolean {
  const parts = pathSegments(pathname);
  return (
    (parts[0] === "maintenance" && parts[2] === segment) ||
    (parts[0] === "t" && parts[2] === segment)
  );
}

function isProcurementPath(pathname: string): boolean {
  const parts = pathSegments(pathname);
  return Boolean(
    parts[0] === "maintenance" &&
    parts[1] &&
    parts[2] === "procurement"
  );
}

function isDocumentControlPath(pathname: string): boolean {
  const parts = pathSegments(pathname);
  return Boolean(
    parts[0] === "maintenance" && parts[1] && parts[2] === "document-control"
  );
}

function isQmsRegisterWorkspace(route: QmsPathClassification): boolean {
  if (route.kind !== "known" || !route.module) return false;
  const parts = (route.relativePath || "").split("/").filter(Boolean);
  if (parts.length > 2) return false;
  const view = parts[1] || route.module.defaultView;

  if (route.module.id === "calendar" || route.module.id === "evidence-vault" || route.module.id === "aerodoc") return false;
  // Programme/programme are governed specialist Audit Operations routes owned by
  // PortalRouteSurface. Only the remaining shallow audit registers stay on the
  // generic register shortcut.
  // Checklists are owned by QmsCanonicalPage (Assurance chrome + checklist library host).
  // Keep only shallow audit register shortcuts here.
  if (route.module.id === "audits") return ["reports", "templates"].includes(view);
  // CAR/CAPA has a governed specialist owner in PortalRouteSurface. Keeping it
  // out of this generic register shortcut prevents list/new/queue routes from
  // bypassing assignment, auditee response, evidence and Quality review controls.
  if (route.module.id === "cars") return false;
  // Findings list aliases and record details are owned by the Audit Assurance
  // Findings & Actions workspace in PortalRouteSurface.
  if (route.module.id === "findings") return false;
  return route.module.componentType === "canonical";
}

function isSupportedDocumentReaderPath(pathname: string): boolean {
  const parts = pathSegments(pathname);
  const qualityIndex = parts.indexOf("quality");
  if (qualityIndex < 0) return false;
  const relative = parts.slice(qualityIndex + 1);
  if (relative[0] !== "documents") return false;
  const reader = relative.length === 6 && relative[1] === "reader" && relative[2] && relative[3] === "revisions" && relative[4] && relative[5] === "view";
  const revision = relative.length === 5 && relative[1] && relative[2] === "revisions" && relative[3] && relative[4] === "view";
  return Boolean(reader || revision);
}

function isSupportedCarPerformanceReportPath(pathname: string): boolean {
  const parts = pathSegments(pathname);
  const qualityIndex = parts.indexOf("quality");
  if (qualityIndex < 0) return false;
  const relative = parts.slice(qualityIndex + 1);
  return relative.length === 2 && relative[0] === "reports" && relative[1] === "car-performance";
}

function workspaceSlugFromPath(pathname: string): string {
  const parts = pathSegments(pathname);
  if ((parts[0] === "maintenance" || parts[0] === "t") && parts[1]) return parts[1];
  return "system";
}

function WorkspaceRequireAuth({ children }: GuardProps) {
  const location = useLocation();
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(getCachedOnboardingStatus());
  const [onboardingChecked, setOnboardingChecked] = useState(Boolean(getCachedOnboardingStatus()));
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
    return () => { active = false; };
  }, [isAuthed, onboardingChecked]);

  if (!isAuthed) {
    const parts = pathSegments(location.pathname);
    const amoCode = parts[0] === "maintenance" ? parts[1] : "";
    return <Navigate to={amoCode ? `/maintenance/${amoCode}/login` : "/login"} replace state={{ from: location.pathname + location.search }} />;
  }

  if (!onboardingChecked && !isOnboardingRoute) {
    return <div className="page-loading" role="status" aria-live="polite"><div className="page-loading__card"><div className="page-loading__spinner" /><div className="page-loading__label">Preparing workspace…</div></div></div>;
  }

  if (onboardingStatus && !onboardingStatus.is_complete && !isOnboardingRoute) {
    return <Navigate to={`/maintenance/${workspaceSlugFromPath(location.pathname)}/onboarding/setup`} replace />;
  }

  return children;
}

function QmsOverviewRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading Quality overview…</div></div>}>
      <WorkspaceRequireAuth><QmsOverviewPage /></WorkspaceRequireAuth>
    </Suspense>
  );
}

function QmsRegisterRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading Quality register…</div></div>}>
      <WorkspaceRequireAuth><QmsRegisterPage /></WorkspaceRequireAuth>
    </Suspense>
  );
}

function QmsNotFoundRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Checking Quality route…</div></div>}>
      <WorkspaceRequireAuth><QmsNotFoundPage /></WorkspaceRequireAuth>
    </Suspense>
  );
}

function QmsCarPerformanceReportRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading CAR performance…</div></div>}>
      <WorkspaceRequireAuth><QmsCarPerformanceReportPage /></WorkspaceRequireAuth>
    </Suspense>
  );
}

function ProcurementRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading Procurement & Supply Chain…</div></div>}>
      <WorkspaceRequireAuth><ProcurementModule /></WorkspaceRequireAuth>
    </Suspense>
  );
}

function DocumentControlRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading Document Control…</div></div>}>
      <Routes>
        <Route path="/maintenance/:amoCode/document-control" element={<WorkspaceRequireAuth><DocControlDashboardPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/library" element={<WorkspaceRequireAuth><DocControlLibraryPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/library/:docId" element={<WorkspaceRequireAuth><DocControlDocumentDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/changes" element={<WorkspaceRequireAuth><DocControlChangesPortfolioPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/distribution" element={<WorkspaceRequireAuth><DocControlDistributionPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/compliance" element={<WorkspaceRequireAuth><DocControlCompliancePage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/reports" element={<WorkspaceRequireAuth><DocControlReportsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/administration" element={<WorkspaceRequireAuth><DocControlAdministrationPage /></WorkspaceRequireAuth>} />
        <Route path="*" element={<Navigate to="." replace />} />
      </Routes>
    </Suspense>
  );
}

function PublicationsRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading publication…</div></div>}>
      <Routes>
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/read" element={<WorkspaceRequireAuth><PublicationReaderPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/diff" element={<WorkspaceRequireAuth><PublicationDiffPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/workflow" element={<WorkspaceRequireAuth><PublicationWorkflowPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/exports" element={<WorkspaceRequireAuth><PublicationExportsPage /></WorkspaceRequireAuth>} />

        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/read" element={<WorkspaceRequireAuth><PublicationReaderPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/diff" element={<WorkspaceRequireAuth><PublicationDiffPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/workflow" element={<WorkspaceRequireAuth><PublicationWorkflowPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/exports" element={<WorkspaceRequireAuth><PublicationExportsPage /></WorkspaceRequireAuth>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Suspense>
  );
}

export const AppRouter: React.FC = () => {
  const location = useLocation();
  const qmsRoute = classifyQmsPath(location.pathname);

  // Legacy/alias planner entry and bare calendar → canonical week view (avoids "route not found").
  const plannerOrBareCalendar = location.pathname.match(
    /^\/maintenance\/([^/]+)\/quality\/(?:planner|calendar)\/?$/i,
  );
  if (plannerOrBareCalendar) {
    const amo = plannerOrBareCalendar[1];
    return <Navigate to={`/maintenance/${amo}/quality/calendar/week`} replace />;
  }

  if (isSupportedCarPerformanceReportPath(location.pathname)) return <QmsCarPerformanceReportRouteSurface />;
  if (qmsRoute.kind === "overview") return <QmsOverviewRouteSurface />;
  if (isQmsRegisterWorkspace(qmsRoute)) return <QmsRegisterRouteSurface />;
  if (
    qmsRoute.kind === "unknown" &&
    !isSupportedDocumentReaderPath(location.pathname)
  ) return <QmsNotFoundRouteSurface />;
  if (isProcurementPath(location.pathname)) return <ProcurementRouteSurface />;
  if (isDocumentControlPath(location.pathname)) return <DocumentControlRouteSurface />;
  if (isSegmentPath(location.pathname, "publications")) return <PublicationsRouteSurface />;
  return <PortalRouteSurface />;
};

export default AppRouter;
