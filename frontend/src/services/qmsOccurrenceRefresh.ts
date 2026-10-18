import type { QmsAuditRealtimeEvent } from "./qmsAuditRealtime";

const ANSWER_QUERIES = new Set([
  "live-audit-checklist", "qms-audit-checklist-execution", "audit-occurrence",
  "audit-session", "qms-audit-session", "qms-audit-activity", "audit-activity",
]);

export function isChecklistAnswerEvent(event: QmsAuditRealtimeEvent): boolean {
  const data = event.data && typeof event.data === "object" ? event.data as Record<string, unknown> : {};
  const entity = String(data.entityType || data.entity_type || "").toLowerCase();
  const type = String(data.type || event.event).toLowerCase();
  const updated = String(data.action || "").toLowerCase() === "updated" || /[._]updated$/.test(type);
  return updated && (entity === "qms.audit.checklist_item" || entity === "qmsauditchecklistitem"
    || type === "qms.audit.checklist_item.updated");
}

/** Answer events cannot change issued bindings or controlled-source candidates. */
export function occurrenceQueryNeedsRefresh(key: readonly unknown[], events?: readonly QmsAuditRealtimeEvent[]): boolean {
  if (!events?.length || events.some(event => !isChecklistAnswerEvent(event))) return true;
  return key.some(part => typeof part === "string" && ANSWER_QUERIES.has(part.toLowerCase()));
}
