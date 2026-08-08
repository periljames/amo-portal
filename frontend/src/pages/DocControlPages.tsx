import { Navigate, useLocation, useParams } from "react-router-dom";

import CompliancePage from "./documentControl/DocumentControlCompliancePortfolioPage";
import AdministrationPage from "./documentControl/DocumentControlAdministrationPage";
import ReportsPage from "./documentControl/DocumentControlReportsPage";

export { default as DocControlDashboardPage } from "./documentControl/DocumentGovernanceDashboardPage";
export { default as DocControlLibraryPage } from "./documentControl/DocumentLibraryHubPage";
export { default as DocControlDocumentDetailPage } from "./documentControl/DocumentControlRecordEntryPage";
export { default as DocControlGovernanceDetailPage } from "./documentControl/DocumentGovernanceRecordPage";
export { default as DocControlChangesPortfolioPage } from "./documentControl/DocumentControlChangesPortfolioPage";
export { default as DocControlDistributionPage } from "./documentControl/DocumentControlDistributionPortfolioPage";
export { default as DocControlDistributionPortfolioPage } from "./documentControl/DocumentControlDistributionPortfolioPage";
export { default as DocControlCompliancePortfolioPage } from "./documentControl/DocumentControlCompliancePortfolioPage";
export { default as DocControlReportsPage } from "./documentControl/DocumentControlReportsPage";
export { default as DocControlAdministrationPage } from "./documentControl/DocumentControlAdministrationPage";
export { default as DocControlStructurePage } from "./documentControl/DocumentControlStructurePage";
export { default as DocControlGeneratedRecordsPage } from "./documentControl/DocumentControlRecordsPage";
export { default as DocumentControlCopiesPage } from "./documentControl/DocumentLibraryCopiesPage";

export {
  DocumentControlChangeRequestDetailPage as DocControlChangeProposalDetailPage,
  DocumentControlDistributionDetailPage as DocControlDistributionDetailPage,
  DocumentControlLEPPage as DocControlLEPPage,
  DocumentControlRevisionPackagePage as DocControlRevisionsPage,
  DocumentControlTemporaryRevisionDetailPage as DocControlTRDetailPage,
  DocumentControlWorkflowDetailPage as DocControlDraftDetailPage,
} from "./documentControl/DocumentControlWorklistPages";

function useCanonicalBasePath(): string {
  const { amoCode = "" } = useParams<{ amoCode?: string }>();
  return `/maintenance/${encodeURIComponent(amoCode)}/document-control`;
}

function WorkspaceRedirect({ suffix, view }: { suffix: string; view?: string }) {
  const location = useLocation();
  const basePath = useCanonicalBasePath();
  const query = new URLSearchParams(location.search);
  if (view) query.set("view", view);
  const search = query.toString();
  return <Navigate to={`${basePath}${suffix}${search ? `?${search}` : ""}${location.hash}`} replace />;
}

export function DocControlDraftsPage() {
  return <WorkspaceRedirect suffix="/changes" view="in-review" />;
}

export function DocControlChangeProposalPage() {
  return <WorkspaceRedirect suffix="/changes" view="requests" />;
}

export function DocumentControlAuthorityPage() {
  return <WorkspaceRedirect suffix="/changes" view="authority" />;
}

export function DocControlTRPage() {
  return <WorkspaceRedirect suffix="/changes" view="temporary-revisions" />;
}

export function DocControlReviewsPage() {
  const location = useLocation();
  if (location.pathname.endsWith("/reviews")) return <WorkspaceRedirect suffix="/compliance" view="reviews" />;
  return <CompliancePage />;
}

export function DocumentControlExternalSourcesPage() {
  return <WorkspaceRedirect suffix="/compliance" view="external-sources" />;
}

export function DocumentControlIntegrationsPage() {
  return <WorkspaceRedirect suffix="/compliance" view="relationships" />;
}

export function DocControlArchivePage() {
  const location = useLocation();
  const basePath = useCanonicalBasePath();
  const query = new URLSearchParams(location.search);
  query.set("status", "ARCHIVED");
  return <Navigate to={`${basePath}/library?${query.toString()}${location.hash}`} replace />;
}

export function DocControlRegistersPage() {
  const location = useLocation();
  if (location.pathname.endsWith("/registers")) return <WorkspaceRedirect suffix="/reports" />;
  return <ReportsPage />;
}

export function DocControlSettingsPage() {
  const location = useLocation();
  if (location.pathname.endsWith("/settings")) return <WorkspaceRedirect suffix="/administration" />;
  return <AdministrationPage />;
}

export function LegacyDocControlRedirectPage() {
  const location = useLocation();
  const { amoCode = "" } = useParams<{ amoCode?: string }>();
  const suffix = location.pathname.replace(/^\/doc-control/, "");
  return <Navigate to={`/maintenance/${amoCode}/document-control${suffix}${location.search}${location.hash}`} replace />;
}
