import { afterEach, expect, it, vi } from "vitest";
import { pendingFieldworkPlan, projectPendingChecklistItems } from "./qmsOfflineFieldworkProjection";
import type { OfflineOutboxEntry } from "./offlinePersistence";
import type { ChecklistExecutionGovernanceRow } from "./qmsChecklistExecutionGovernance";

const state = vi.hoisted(() => ({ entries: [] as OfflineOutboxEntry[] }));
vi.mock("./offlinePersistence", () => ({ listOfflineMutations: async () => state.entries }));
afterEach(() => { state.entries = []; });
function entry(version: number, fields = {}): OfflineOutboxEntry {
  return { path: "/api/maintenance/amo/quality/audits/a/checklist-items/i/fieldwork-mutations", entityType: "qms-audit-checklist-item", entityId: "i",
    status: "queued", body: JSON.stringify({ base_version: version, ...fields }) } as OfflineOutboxEntry;
}
it("chains repeated saves after their pending predecessors", async () => {
  state.entries = [entry(4), entry(5)];
  expect(await pendingFieldworkPlan("amo", "a", "i", 4)).toEqual({ baseVersion: 6, queueOnly: true });
  expect(await pendingFieldworkPlan("amo", "a", "other-item", 2)).toEqual({ baseVersion: 2, queueOnly: false });
});
it("retains a real server conflict for human review", async () => {
  state.entries = [{ ...entry(4), status: "conflict" }];
  await expect(pendingFieldworkPlan("amo", "a", "i", 4)).rejects.toThrow(/review/i);
});
it("reopens saved notes and assessments without changing the authoritative version", () => {
  const assessment = { documentary_status: "DOCUMENTED" };
  const item = { checklist_item_id: "i", entity_version: 4, auditor_notes: "Server notes" } as ChecklistExecutionGovernanceRow;
  const projected = projectPendingChecklistItems([item], [entry(4, { auditor_notes: "First notes" }), entry(5, { auditor_notes: "Latest notes", assessment })]);
  expect(projected[0]).toMatchObject({ entity_version: 4, auditor_notes: "Latest notes", assessment });
  expect(item.auditor_notes).toBe("Server notes");
});
