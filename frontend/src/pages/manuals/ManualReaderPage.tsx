import { useParams } from "react-router-dom";

import DocumentationAssistantPanel from "./DocumentationAssistantPanel";
import PublicationAssistedNavigationBridge from "./PublicationAssistedNavigationBridge";
import PublicationInlineReferenceController from "./PublicationInlineReferenceController";
import PublicationReaderChromeBridge from "./PublicationReaderChromeBridge";
import PublicationsReaderPage from "./PublicationsReaderPage";

export default function ManualReaderPage() {
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string; revId?: string }>();
  const tenant = (params.amoCode || params.tenantSlug || "").toLowerCase();

  return <>
    <PublicationsReaderPage />
    <PublicationReaderChromeBridge />
    <PublicationAssistedNavigationBridge />
    <PublicationInlineReferenceController />
    {tenant ? <DocumentationAssistantPanel
      tenant={tenant}
      manualId={params.manualId}
      revisionId={params.revId}
    /> : null}
  </>;
}
