import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./apiClient";
import { projectOfflineChecklistBindings, readAuditOfflinePack } from "./qmsAuditOfflinePack";
import { getChecklistBinding, getChecklistBindingLineage, listChecklistBindings, type ChecklistBinding } from "./qmsChecklistTemplates";

vi.mock("./apiClient", () => ({ apiRequest: vi.fn(), qmsPath: (tenant: string, path: string) => `/quality/${tenant}${path}` }));
vi.mock("./qmsAuditOfflinePack", () => ({ readAuditOfflinePack: vi.fn(), projectOfflineChecklistBindings: vi.fn() }));

const bindings: ChecklistBinding[] = Array.from({ length: 101 }, (_, index) => ({
  id: `binding-${index}`, audit_id: "audit-1", template_id: `template-${index}`,
  template_revision_id: `revision-${index}`, template_code: `CHECK-${index}`, revision_no: 1,
  content_sha256: "a".repeat(64), instantiated_item_ids: [`item-${index}`],
  item_snapshot: [{ prompt: `Requirement ${index}`, regulatory_source_ref: `Reg ${index}`, expected_evidence: "Inspection record", mandatory: true, response_type: "YES_NO_NA", applicability: "APPLICABLE", sort_order: index }],
  source_references: [], application_reason: "Audit scope", applied_at: "2026-10-01T00:00:00Z",
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("navigator", { onLine: false });
  vi.mocked(readAuditOfflinePack).mockResolvedValue({} as Awaited<ReturnType<typeof readAuditOfflinePack>>);
  vi.mocked(projectOfflineChecklistBindings).mockReturnValue({ items: bindings } as ReturnType<typeof projectOfflineChecklistBindings>);
});
afterEach(() => vi.unstubAllGlobals());

describe("canonical checklist reads and downloaded audit continuity", () => {
  it("bounds the offline list while retaining the total and older pages", async () => {
    const page = await listChecklistBindings("tenant-a", "audit-1", undefined, { offset: 50, limit: 50 });
    expect(page.total).toBe(101);
    expect(page.items).toHaveLength(50);
    expect(page.items[0].id).toBe("binding-50");
    expect(apiRequest).not.toHaveBeenCalled();
  });
  it("retains every offline item's governed lineage beyond the list page", async () => {
    const lineage = await getChecklistBindingLineage("tenant-a", "audit-1");
    expect(lineage.items).toHaveLength(101);
    expect(lineage.items[100]).toMatchObject({ checklist_item_id: "item-100", source_context: { regulatory_source_ref: "Reg 100", mandatory: true } });
  });
  it("confirms a mutation by direct live ID without substituting the offline pack", async () => {
    vi.mocked(apiRequest).mockResolvedValue(bindings[100]);
    const row = await getChecklistBinding("tenant-a", "audit-1", "binding-100");
    expect(row.id).toBe("binding-100");
    expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining("/checklist-bindings/binding-100"), expect.objectContaining({ cacheTtlMs: 0 }));
    expect(readAuditOfflinePack).not.toHaveBeenCalled();
  });
  it("propagates authorization failures instead of serving an old offline projection", async () => {
    vi.stubGlobal("navigator", { onLine: true });
    vi.mocked(apiRequest).mockRejectedValue(new Error("Forbidden (403)"));
    await expect(getChecklistBindingLineage("tenant-a", "audit-1")).rejects.toThrow("Forbidden");
    expect(readAuditOfflinePack).not.toHaveBeenCalled();
  });
});
