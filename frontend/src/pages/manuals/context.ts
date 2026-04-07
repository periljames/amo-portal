import { useParams } from "react-router-dom";

type ManualRouteParams = {
  tenantSlug?: string;
  amoCode?: string;
  department?: string;
  manualId?: string;
  docId?: string;
  revId?: string;
  chapterId?: string;
  sectionId?: string;
  subSectionId?: string;
  figureId?: string;
};

export function resolveManualRouteContext(params: ManualRouteParams) {
  const { tenantSlug, amoCode, department, manualId, docId, revId, chapterId, sectionId, subSectionId, figureId } = params;
  const tenant = tenantSlug || amoCode || "";
  const effectiveManualId = manualId || docId;
  const basePath = amoCode ? `/maintenance/${amoCode}/manuals` : `/t/${tenant}/manuals`;
  return {
    tenant,
    amoCode,
    department,
    manualId: effectiveManualId,
    revId,
    chapterId,
    sectionId,
    subSectionId,
    figureId,
    basePath,
  };
}

export function useManualRouteContext() {
  const params = useParams();
  return resolveManualRouteContext(params);
}
