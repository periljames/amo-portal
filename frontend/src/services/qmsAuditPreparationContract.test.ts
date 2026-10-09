import { describe, expect, it } from "vitest";
import { requirePreparationContract } from "./qmsAuditPreparationContract";

describe("audit preparation authority", () => {
  it.each(["readiness", "context"] as const)("rejects a generic successful audit list instead of rendering unverified %s", (kind) => {
    expect(() => requirePreparationContract({ module: "audits", items: [] }, kind)).toThrow("could not be verified");
  });

  it("preserves legitimate incomplete readiness and server blockers", () => {
    const data = { issue_ready: false, fieldwork_ready: false, checks: [], issue_blockers: [{ type: "CHECKLIST", reason: "Checklist required" }], fieldwork_blockers: [], complete_count: 0, total_count: 0, percent: 0, source_fingerprint: "server-fingerprint" };
    expect(requirePreparationContract(data, "readiness")).toBe(data);
    expect(() => requirePreparationContract({ ...data, checks: undefined }, "readiness")).toThrow("could not be verified");
  });

  it("rejects audit records accidentally returned as activity events", () => {
    expect(() => requirePreparationContract({ items: [{ id: "audit-1", title: "Audit" }] }, "activity")).toThrow("could not be verified");
  });
});
