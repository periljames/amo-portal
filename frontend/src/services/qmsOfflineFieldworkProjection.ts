import { listOfflineMutations, type OfflineOutboxEntry } from "./offlinePersistence";
import type { ChecklistExecutionGovernanceRow } from "./qmsChecklistExecutionGovernance";

function body(entry: OfflineOutboxEntry): Record<string, unknown> {
  try {
    const value = JSON.parse(entry.body || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}

export async function pendingFieldworkPlan(amoCode: string, auditId: string, itemId: string, serverVersion: number) {
  const marker = `/api/maintenance/${encodeURIComponent(amoCode)}/quality/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(itemId)}/`;
  const entries = (await listOfflineMutations()).filter((entry) => entry.path.startsWith(marker)
    && entry.entityType === "qms-audit-checklist-item");
  if (entries.some((entry) => entry.status === "conflict" || entry.status === "failed")) {
    throw new Error("Review this checklist item's pending sync issue before saving another change.");
  }
  let baseVersion = serverVersion;
  for (const entry of entries) {
    const version = body(entry).base_version;
    if (!Number.isSafeInteger(version) || Number(version) < 0) throw new Error("The pending checklist version could not be read. Review device changes before saving again.");
    baseVersion = Math.max(baseVersion, Number(version) + 1);
  }
  return { baseVersion, queueOnly: entries.length > 0 };
}

/** Overlay durable device edits without claiming that the server accepted them. */
export function projectPendingChecklistItems(items: ChecklistExecutionGovernanceRow[], entries: OfflineOutboxEntry[]) {
  const changes = new Map<string, Record<string, unknown>>();
  for (const entry of entries) {
    if (!entry.entityId || !["queued", "syncing", "conflict", "failed"].includes(entry.status)) continue;
    const value = body(entry);
    const fields = ["canonical_response_status", "response_value", "auditor_notes", "sampled_item_information", "evidence_references", "assessment"];
    changes.set(entry.entityId, { ...changes.get(entry.entityId), ...Object.fromEntries(fields.filter((field) => field in value).map((field) => [field, value[field]])) });
  }
  return items.map((item) => changes.has(item.checklist_item_id)
    ? { ...item, ...changes.get(item.checklist_item_id) } as ChecklistExecutionGovernanceRow : item);
}
