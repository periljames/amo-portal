import type { ChecklistExecutionGovernanceResponse, ChecklistExecutionGovernanceRow } from "./qmsChecklistExecutionGovernance";

export function restoreChecklistReceipts(rows: ChecklistExecutionGovernanceRow[], receipts: Record<string, ChecklistExecutionGovernanceRow>): ChecklistExecutionGovernanceRow[] {
  return rows.map(row => {
    const receipt = receipts[row.checklist_item_id];
    return receipt?.audit_id === row.audit_id && receipt.entity_version > row.entity_version ? receipt : row;
  });
}

/** A slower read must never replace a newer committed row already acknowledged. */
export function reconcileChecklistExecution(previous: ChecklistExecutionGovernanceResponse | undefined, incoming: ChecklistExecutionGovernanceResponse): ChecklistExecutionGovernanceResponse {
  if (!previous) return incoming;
  const known = new Map(previous.items.map(item => [item.checklist_item_id, item]));
  return { ...incoming, items: incoming.items.map(item => {
    const prior = known.get(item.checklist_item_id);
    return prior?.audit_id === item.audit_id && prior.entity_version > item.entity_version ? prior : item;
  }) };
}

export function acceptChecklistReceipt(previous: ChecklistExecutionGovernanceResponse | undefined, row: ChecklistExecutionGovernanceRow): ChecklistExecutionGovernanceResponse | undefined {
  if (!previous) return previous;
  return reconcileChecklistExecution(previous, { ...previous, items: previous.items.map(item => item.checklist_item_id === row.checklist_item_id && item.audit_id === row.audit_id ? row : item) });
}
