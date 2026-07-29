import { useParams } from "react-router-dom";

import DocumentationAssistantPanel from "./DocumentationAssistantPanel";
import PublicationsReaderPage from "./PublicationsReaderPage";
import PublicationInlineReferenceController from "./PublicationInlineReferenceController";

export default function ManualReaderPage() {
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string; revId?: string }>();
  const tenant = (params.amoCode || params.tenantSlug || "").toLowerCase();

  return <>
    <PublicationsReaderPage />
    <PublicationInlineReferenceController />
    {tenant ? <DocumentationAssistantPanel
      tenant={tenant}
      manualId={params.manualId}
      revisionId={params.revId}
    /> : null}
  </>;
}
