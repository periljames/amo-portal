import { expect, it } from "vitest";
import { occurrenceQueryNeedsRefresh } from "./qmsOccurrenceRefresh";
const answer = { event: "qms.audit.checklist_item.updated", data: { entityType: "qms.audit.checklist_item" } };
it.each(["live-audit-checklist", "audit-occurrence", "audit-session", "qms-audit-activity"])("refreshes %s after a cross-device answer", key => {
  expect(occurrenceQueryNeedsRefresh(["qms", key, "tenant", "audit"], [answer])).toBe(true);
});
it.each(["live-audit-bindings", "checklist-evidence-candidates", "external-finding-drafts", "qms-audit-preparation-context"])("does not refetch unchanged %s after each answer", key => {
  expect(occurrenceQueryNeedsRefresh(["qms", key, "tenant", "audit"], [answer])).toBe(false);
});
it("refreshes broadly for a batched finding, source change or stream reset", () => {
  const key = ["qms", "live-audit-findings", "tenant", "audit"];
  expect(occurrenceQueryNeedsRefresh(key, [answer, { event: "qms.finding.created", data: { entityType: "qms.finding" } }])).toBe(true);
  expect(occurrenceQueryNeedsRefresh(key, [{ event: "qms.preparation.issued", data: {} }])).toBe(true);
  expect(occurrenceQueryNeedsRefresh(key, [{ event: "qms.audit.checklist_item.created", data: { entityType: "qms.audit.checklist_item" } }])).toBe(true);
  expect(occurrenceQueryNeedsRefresh(key)).toBe(true);
});
