import { auditSessionPath } from "../../features/qms/auditSession/auditSessionRoutes";
import type { QMSAuditOut } from "../../services/qmsCore";
import { toAuditReferenceSlug } from "../../utils/auditSlug";
import { auditNextAction } from "./auditNextAction";

/** Stage-aware audit occurrence URL for list/register navigation. */
export function auditNavigationHref(amoCode: string, audit: QMSAuditOut): string {
  const { stage } = auditNextAction(audit);
  const auditKey = toAuditReferenceSlug(audit.audit_ref || audit.id);
  return auditSessionPath(amoCode, auditKey, stage);
}
