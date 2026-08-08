import React, { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";

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
const ProcurementModule = lazy(() => import("./pages/procurement/ProcurementModule"));
const PublicationReaderPage = lazy(() => import("./pages/manuals/ManualReaderPage"));
const PublicationDiffPage = lazy(() => import("./pages/manuals/ManualDiffPage"));
const PublicationWorkflowPage = lazy(() => import("./pages/manuals/ManualWorkflowPage"));
const PublicationExportsPage = lazy(() => import("./pages/manuals/ManualExportsPage"));

const DocControlDashboardPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDashboardPage })));
const DocControlLibraryPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlLibraryPage })));
const DocControlStructurePage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlStructurePage })));
const DocControlGeneratedRecordsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlGeneratedRecordsPage })));
const DocControlDocumentDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDocumentDetailPage })));
const DocControlDraftsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDraftsPage })));
const DocControlDraftDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDraftDetailPage })));
const DocControlChangeProposalPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlChangeProposalPage })));
const DocControlChangeProposalDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlChangeProposalDetailPage })));
const DocControlRevisionsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlRevisionsPage })));
const DocControlLEPPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlLEPPage })));
const DocControlAuthorityPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocumentControlAuthorityPage })));
const DocControlTRPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlTRPage })));
const DocControlTRDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlTRDetailPage })));
const DocControlDistributionPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDistributionPage })));
const DocControlDistributionDetailPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlDistributionDetailPage })));
const DocControlArchivePage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlArchivePage })));
const DocControlReviewsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlReviewsPage })));
const DocControlRegistersPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlRegistersPage })));
const DocControlSettingsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocControlSettingsPage })));
const DocumentControlCopiesPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocumentControlCopiesPage })));
const DocumentControlExternalSourcesPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocumentControlExternalSourcesPage })));
const DocumentControlIntegrationsPage = lazy(() => import("./pages/DocControlPages").then((module) => ({ default: module.DocumentControlIntegrationsPage })));

type GuardProps = { children: React.ReactElement };

function pathSegments(pathname: string): string[] {
  return pathname.split("/").filter(Boolean);
}

function isSegmentPath(pathname: string, segment: "manuals" | "publications"): boolean {
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
    parts[0] === "maintenance" && parts[1] && (
      parts[2] === "document-control" ||
      (parts[3] === "doc-control" && parts[2])
    )
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
  if (route.module.id === "audits") return ["checklists", "reports", "templates"].includes(view);
  // CAR/CAPA has a governed specialist owner in PortalRouteSurface. Keeping it
  // out of this generic register shortcut prevents list/new/queue routes from
  // bypassing assignment, auditee response, evidence and Quality review controls.
  if (route.module.id === "cars") return false;
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

function isSupportedAuditProgrammeSchedulePath(pathname: string): boolean {
  const parts = pathSegments(pathname);
  const qualityIndex = parts.indexOf("quality");
  if (qualityIndex < 0) return false;
  const relative = parts.slice(qualityIndex + 1);
  return Boolean(
    relative.length === 6 &&
    relative[0] === "audits" &&
    relative[1] === "program" &&
    relative[2] &&
    relative[3] === "items" &&
    relative[4] &&
    relative[5] === "schedule"
  );
}

function rosteringWorkforceRedirect(pathname: string): string | null {
  const parts = pathSegments(pathname);
  if (parts[0] !== "maintenance" || !parts[1] || parts[2] !== "rostering" || parts[3] !== "workforce") return null;
  return `/maintenance/${encodeURIComponent(parts[1])}/rostering/settings?section=workforce`;
}

function canonicaliseManualsPath(pathname: string): string {
  const parts = pathname.split("/");
  const index = parts.findIndex((part, partIndex) => part === "manuals" && (partIndex === 2 || partIndex === 3));
  if (index >= 0) parts[index] = "publications";
  return parts.join("/") || "/";
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

function PublicationsWorkspaceRedirect({ record = false, register = false }: { record?: boolean; register?: boolean }) {
  const location = useLocation();
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string }>();
  const tenant = params.amoCode || params.tenantSlug || "system";
  const suffix = register ? "/registers" : record && params.manualId ? `/library/${params.manualId}` : "/library";
  return <Navigate to={`/maintenance/${tenant}/document-control${suffix}${location.search}${location.hash}`} replace />;
}

function CanonicalDocumentControlRedirect() {
  const location = useLocation();
  const parts = pathSegments(location.pathname);
  if (parts[0] !== "maintenance" || !parts[1] || parts[3] !== "doc-control") return <Navigate to="/login" replace />;
  const suffix = parts.slice(4).join("/");
  return <Navigate to={`/maintenance/${parts[1]}/document-control${suffix ? `/${suffix}` : ""}${location.search}${location.hash}`} replace />;
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
        <Route path="/maintenance/:amoCode/:department/doc-control/*" element={<CanonicalDocumentControlRedirect />} />
        <Route path="/maintenance/:amoCode/document-control" element={<WorkspaceRequireAuth><DocControlDashboardPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/library" element={<WorkspaceRequireAuth><DocControlLibraryPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/structure" element={<WorkspaceRequireAuth><DocControlStructurePage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/records" element={<WorkspaceRequireAuth><DocControlGeneratedRecordsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/library/:docId" element={<WorkspaceRequireAuth><DocControlDocumentDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/drafts" element={<WorkspaceRequireAuth><DocControlDraftsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/drafts/:draftId" element={<WorkspaceRequireAuth><DocControlDraftDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/change-proposals" element={<WorkspaceRequireAuth><DocControlChangeProposalPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/change-proposals/:proposalId" element={<WorkspaceRequireAuth><DocControlChangeProposalDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/revisions/:docId" element={<WorkspaceRequireAuth><DocControlRevisionsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/lep/:docId" element={<WorkspaceRequireAuth><DocControlLEPPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/authority" element={<WorkspaceRequireAuth><DocControlAuthorityPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/tr" element={<WorkspaceRequireAuth><DocControlTRPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/tr/:trId" element={<WorkspaceRequireAuth><DocControlTRDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/distribution" element={<WorkspaceRequireAuth><DocControlDistributionPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/distribution/:eventId" element={<WorkspaceRequireAuth><DocControlDistributionDetailPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/reviews" element={<WorkspaceRequireAuth><DocControlReviewsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/controlled-copies" element={<WorkspaceRequireAuth><DocumentControlCopiesPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/external-sources" element={<WorkspaceRequireAuth><DocumentControlExternalSourcesPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/integrations" element={<WorkspaceRequireAuth><DocumentControlIntegrationsPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/archive" element={<WorkspaceRequireAuth><DocControlArchivePage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/registers" element={<WorkspaceRequireAuth><DocControlRegistersPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/document-control/settings" element={<WorkspaceRequireAuth><DocControlSettingsPage /></WorkspaceRequireAuth>} />
        <Route path="*" element={<Navigate to="." replace />} />
      </Routes>
    </Suspense>
  );
}

function PublicationsRouteSurface() {
  return (
    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading publication…</div></div>}>
      <Routes>
        <Route path="/maintenance/:amoCode/publications" element={<PublicationsWorkspaceRedirect />} />
        <Route path="/maintenance/:amoCode/publications/master-list" element={<PublicationsWorkspaceRedirect register />} />
        <Route path="/maintenance/:amoCode/publications/:manualId" element={<PublicationsWorkspaceRedirect record />} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/read" element={<WorkspaceRequireAuth><PublicationReaderPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/diff" element={<WorkspaceRequireAuth><PublicationDiffPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/workflow" element={<WorkspaceRequireAuth><PublicationWorkflowPage /></WorkspaceRequireAuth>} />
        <Route path="/maintenance/:amoCode/publications/:manualId/rev/:revId/exports" element={<WorkspaceRequireAuth><PublicationExportsPage /></WorkspaceRequireAuth>} />

        <Route path="/t/:tenantSlug/publications" element={<PublicationsWorkspaceRedirect />} />
        <Route path="/t/:tenantSlug/publications/master-list" element={<PublicationsWorkspaceRedirect register />} />
        <Route path="/t/:tenantSlug/publications/:manualId" element={<PublicationsWorkspaceRedirect record />} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/read" element={<WorkspaceRequireAuth><PublicationReaderPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/diff" element={<WorkspaceRequireAuth><PublicationDiffPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/workflow" element={<WorkspaceRequireAuth><PublicationWorkflowPage /></WorkspaceRequireAuth>} />
        <Route path="/t/:tenantSlug/publications/:manualId/rev/:revId/exports" element={<WorkspaceRequireAuth><PublicationExportsPage /></WorkspaceRequireAuth>} />
        <Route path="*" element={<PublicationsWorkspaceRedirect />} />
      </Routes>
    </Suspense>
  );
}

export const AppRouter: React.FC = () => {
  const location = useLocation();
  const workforceTarget = rosteringWorkforceRedirect(location.pathname);
  const qmsRoute = classifyQmsPath(location.pathname);

  if (workforceTarget) {
    return <Navigate to={`${workforceTarget}${location.hash}`} replace state={location.state} />;
  }
  if (isSegmentPath(location.pathname, "manuals")) {
    return <Navigate to={`${canonicaliseManualsPath(location.pathname)}${location.search}${location.hash}`} replace state={location.state} />;
  }
  if (qmsRoute.kind === "legacy" && qmsRoute.canonicalTarget) {
    return <Navigate to={`${qmsRoute.canonicalTarget}${location.search}${location.hash}`} replace state={location.state} />;
  }
  if (qmsRoute.kind === "overview") return <QmsOverviewRouteSurface />;
  if (isQmsRegisterWorkspace(qmsRoute)) return <QmsRegisterRouteSurface />;
  if (
    qmsRoute.kind === "unknown" &&
    !isSupportedDocumentReaderPath(location.pathname) &&
    !isSupportedAuditProgrammeSchedulePath(location.pathname)
  ) return <QmsNotFoundRouteSurface />;
  if (isProcurementPath(location.pathname)) return <ProcurementRouteSurface />;
  if (isDocumentControlPath(location.pathname)) return <DocumentControlRouteSurface />;
  if (isSegmentPath(location.pathname, "publications")) return <PublicationsRouteSurface />;
  return <PortalRouteSurface />;
};

export default AppRouter;