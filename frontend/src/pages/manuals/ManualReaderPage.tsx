import { useParams } from "react-router-dom";

import DocumentationAssistantPanel from "./DocumentationAssistantPanel";
import PublicationAssistedNavigationBridge from "./PublicationAssistedNavigationBridge";
import PublicationsReaderPage from "./PublicationsReaderPage";
import PublicationInlineReferenceController from "./PublicationInlineReferenceController";
import "./publicationReaderPost477Stability.css";

export default function ManualReaderPage() {
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string; revId?: string }>();
  const tenant = (params.amoCode || params.tenantSlug || "").toLowerCase();

  return <>
    <PublicationsReaderPage />
    <PublicationAssistedNavigationBridge />
    <PublicationInlineReferenceController />
    {tenant ? <DocumentationAssistantPanel
      tenant={tenant}
      manualId={params.manualId}
      revisionId={params.revId}
    /> : null}
  </>;
}
