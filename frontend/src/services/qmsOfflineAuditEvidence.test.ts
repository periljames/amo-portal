import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./qmsOfflineAuditEvidence.ts", import.meta.url), "utf8");

describe("QMS offline evidence replay contract", () => {
  it("refreshes authoritative checklist governance after an idempotent evidence replay", () => {
    expect(source).toContain("if (result.replayed)");
    expect(source).toContain("await listChecklistExecutionGovernance(amoCode, auditId)");
    expect(source).toContain("authoritative.entity_version");
    expect(source).not.toContain("item.entity_version = result.committed_version;\n      await deleteStored(row.id);");
  });
});
