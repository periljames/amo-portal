import type { AuditSessionStageId } from "../../../services/qmsAuditSession";

export const AUDIT_SESSION_STAGES: readonly AuditSessionStageId[] = [
  "setup",
  "prepare",
  "live",
  "closing",
  "follow-up",
  "archive",
] as const;

export function auditSessionStageFromPath(pathname: string): AuditSessionStageId | null {
  const tail = pathname.split("?")[0].split("#")[0].split("/").filter(Boolean).at(-1)?.toLowerCase();
  return AUDIT_SESSION_STAGES.includes((tail || "") as AuditSessionStageId)
    ? (tail as AuditSessionStageId)
    : null;
}

export function auditSessionPath(amoCode: string, auditKey: string, stage: AuditSessionStageId): string {
  return `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/${encodeURIComponent(auditKey)}/${stage}`;
}
