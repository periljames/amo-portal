import { useParams } from "react-router-dom";

export function useManualRouteContext() {
  const { tenantSlug, amoCode, department, manualId, docId, revId } = useParams();
  const tenant = tenantSlug || amoCode || "";
  const effectiveManualId = manualId || docId;
  const basePath = amoCode
    ? `/maintenance/${amoCode}/manuals`
    : `/t/${tenant}/manuals`;
  return { tenant, amoCode, department, manualId: effectiveManualId, revId, basePath };
}
