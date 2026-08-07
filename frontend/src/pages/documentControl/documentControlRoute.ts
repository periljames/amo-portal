import { useParams } from "react-router-dom";

export type DocumentControlRouteParams = {
  amoCode?: string;
  department?: string;
  docId?: string;
  draftId?: string;
  proposalId?: string;
  trId?: string;
  eventId?: string;
};

export function useDocumentControlRoute() {
  const params = useParams<DocumentControlRouteParams>();
  const amoCode = params.amoCode || "";
  return {
    ...params,
    amoCode,
    tenant: amoCode.toLowerCase(),
    basePath: `/maintenance/${amoCode}/document-control`,
    readerBasePath: `/maintenance/${amoCode}/publications`,
  };
}
