import { Navigate, useLocation, useParams } from "react-router-dom";

export { default as DocControlDashboardPage } from "./documentControl/DocumentControlDashboardPage";
export { default as DocControlLibraryPage } from "./documentControl/DocumentControlLibraryPage";
export { default as DocControlDocumentDetailPage } from "./documentControl/DocumentControlRecordEntryPage";

export {
  DocumentControlArchivePage as DocControlArchivePage,
  DocumentControlAuthorityPage,
  DocumentControlChangeRequestDetailPage as DocControlChangeProposalDetailPage,
  DocumentControlChangeRequestsPage as DocControlChangeProposalPage,
  DocumentControlCopiesPage,
  DocumentControlDistributionDetailPage as DocControlDistributionDetailPage,
  DocumentControlDistributionPage as DocControlDistributionPage,
  DocumentControlExternalSourcesPage,
  DocumentControlIntegrationsPage,
  DocumentControlLEPPage as DocControlLEPPage,
  DocumentControlRegistersPage as DocControlRegistersPage,
  DocumentControlReviewPage as DocControlReviewsPage,
  DocumentControlRevisionPackagePage as DocControlRevisionsPage,
  DocumentControlSettingsPage as DocControlSettingsPage,
  DocumentControlTemporaryRevisionDetailPage as DocControlTRDetailPage,
  DocumentControlTemporaryRevisionPage as DocControlTRPage,
  DocumentControlWorkflowDetailPage as DocControlDraftDetailPage,
  DocumentControlWorkflowPage as DocControlDraftsPage,
} from "./documentControl/DocumentControlWorklistPages";

export function LegacyDocControlRedirectPage() {
  const location = useLocation();
  const { amoCode = "" } = useParams<{ amoCode?: string }>();
  const suffix = location.pathname.replace(/^\/doc-control/, "");
  return <Navigate to={`/maintenance/${amoCode}/document-control${suffix}${location.search}${location.hash}`} replace />;
}
