import type { AuditSessionStageId } from "../../../services/qmsAuditSession";

export const AUDIT_SESSION_STAGES: readonly AuditSessionStageId[] = [
  "setup",
  "prepare",
  "live",
  "closing",
  "follow-up",
  "archive",
] as const;

const LIVE_STAGE_INDEX = AUDIT_SESSION_STAGES.indexOf("live");

/** True when the authoritative stage is Live or any later lifecycle stage. */
export function isAtLeastLiveStage(stageId: string | null | undefined): boolean {
  if (!stageId) return false;
  const index = AUDIT_SESSION_STAGES.indexOf(stageId as AuditSessionStageId);
  return index >= LIVE_STAGE_INDEX;
}

/** Functional secondary navigation within an audit occurrence (not lifecycle stages). */
export type AuditOccurrenceFunctionalTab =
  | "overview"
  | "checklist"
  | "evidence"
  | "findings"
  | "team"
  | "report";

export const AUDIT_OCCURRENCE_FUNCTIONAL_TABS: readonly {
  id: AuditOccurrenceFunctionalTab;
  label: string;
  stage: AuditSessionStageId;
  hash: string;
}[] = [
  { id: "overview", label: "Overview", stage: "setup", hash: "overview" },
  { id: "checklist", label: "Checklist", stage: "live", hash: "checklist" },
  { id: "evidence", label: "Evidence", stage: "live", hash: "evidence" },
  { id: "findings", label: "Findings", stage: "live", hash: "findings" },
  { id: "team", label: "Team", stage: "setup", hash: "team" },
  { id: "report", label: "Report", stage: "closing", hash: "report" },
] as const;

/** Keep secondary navigation inside the stage currently being viewed. */
export function auditOccurrenceFunctionalTabsForStage(stage: AuditSessionStageId | null) {
  if (!stage) return [];
  return AUDIT_OCCURRENCE_FUNCTIONAL_TABS.filter((entry) => entry.stage === stage);
}

export function auditSessionStageFromPath(pathname: string): AuditSessionStageId | null {
  const tail = pathname.split("?")[0].split("#")[0].split("/").filter(Boolean).at(-1)?.toLowerCase();
  return AUDIT_SESSION_STAGES.includes((tail || "") as AuditSessionStageId)
    ? (tail as AuditSessionStageId)
    : null;
}

export function auditSessionPath(amoCode: string, auditKey: string, stage: AuditSessionStageId): string {
  return `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/${encodeURIComponent(auditKey)}/${stage}`;
}

export function auditOccurrenceFunctionalPath(
  amoCode: string,
  auditKey: string,
  tab: AuditOccurrenceFunctionalTab,
): string {
  const def = AUDIT_OCCURRENCE_FUNCTIONAL_TABS.find((entry) => entry.id === tab);
  if (!def) return auditSessionPath(amoCode, auditKey, "setup");
  return `${auditSessionPath(amoCode, auditKey, def.stage)}#${def.hash}`;
}

export function auditOccurrenceFunctionalTabFromLocation(
  pathname: string,
  hash?: string,
): AuditOccurrenceFunctionalTab | null {
  const stage = auditSessionStageFromPath(pathname);
  if (!stage) return null;
  const fragment = (hash || "").replace(/^#/, "").toLowerCase();
  if (fragment) {
    const byHash = AUDIT_OCCURRENCE_FUNCTIONAL_TABS.find(
      (entry) => entry.hash === fragment && (entry.stage === stage || (entry.id === "team" && stage === "prepare")),
    );
    if (byHash) return byHash.id;
    if (fragment === "team" && (stage === "setup" || stage === "prepare")) return "team";
  }
  if (stage === "setup" || stage === "prepare") return fragment === "team" ? "team" : "overview";
  if (stage === "live") return "checklist";
  if (stage === "closing" || stage === "archive") return "report";
  return null;
}
