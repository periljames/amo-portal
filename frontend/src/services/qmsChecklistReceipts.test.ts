import { expect, it } from "vitest";
import { acceptChecklistReceipt, reconcileChecklistExecution, restoreChecklistReceipts } from "./qmsChecklistReceipts";
import type { ChecklistExecutionGovernanceResponse, ChecklistExecutionGovernanceRow } from "./qmsChecklistExecutionGovernance";
const row = (version: number, response = "YES", audit = "a") => ({ checklist_item_id: "q", audit_id: audit, entity_version: version, response_value: response }) as ChecklistExecutionGovernanceRow;
const pack = (item: ChecklistExecutionGovernanceRow) => ({ items: [item], canonical_response_values: [], legacy_compatibility: {} }) as ChecklistExecutionGovernanceResponse;
it("shows a committed receipt immediately and prevents an older read erasing it", () => {
  const committed = acceptChecklistReceipt(pack(row(0, "")), row(1))!;
  expect(committed.items[0].response_value).toBe("YES");
  expect(reconcileChecklistExecution(committed, pack(row(0, ""))).items[0].entity_version).toBe(1);
  expect(reconcileChecklistExecution(committed, pack(row(2, "NO"))).items[0].response_value).toBe("NO");
});
it("does not apply a receipt from another audit or manufacture unloaded data", () => {
  expect(acceptChecklistReceipt(pack(row(1)), row(2, "NO", "other"))?.items[0].response_value).toBe("YES");
  expect(acceptChecklistReceipt(undefined, row(1))).toBeUndefined();
});
it("restores a newer committed response over an older offline package without replacing a later response", () => {
  expect(restoreChecklistReceipts([row(0, "")], { q: row(1) })[0].response_value).toBe("YES");
  expect(restoreChecklistReceipts([row(2, "NO")], { q: row(1) })[0].response_value).toBe("NO");
  expect(restoreChecklistReceipts([row(0, "", "other")], { q: row(1) })[0].response_value).toBe("");
});
it("keeps unchanged checklist rows stable through refreshes and single-row receipts", () => {
  const previous = { ...pack(row(1)), items: [row(1), { ...row(1), checklist_item_id: "other" }] };
  expect(reconcileChecklistExecution(previous, JSON.parse(JSON.stringify(previous)))).toBe(previous);
  const updated = acceptChecklistReceipt(previous, row(2, "NO"))!;
  expect(updated.items[0]).not.toBe(previous.items[0]);
  expect(updated.items[1]).toBe(previous.items[1]);
});
