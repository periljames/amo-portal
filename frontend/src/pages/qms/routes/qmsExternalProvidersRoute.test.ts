import { describe, expect, it } from "vitest";

import { classifyQmsPath, qmsModulePath, qmsNavigationItems } from "./qmsRouteRegistry";


describe("External Providers QMS route ownership", () => {
  it("uses the governed provider register as the canonical supplier workspace", () => {
    expect(qmsModulePath("SAF", "suppliers")).toBe("/maintenance/SAF/quality/suppliers/register");
    const item = qmsNavigationItems("SAF").find((candidate) => candidate.id === "suppliers");
    expect(item).toMatchObject({
      label: "External Providers",
      navigationLabel: "External Providers",
      componentType: "specialist",
    });
  });

  it("recognises every provider lifecycle detail tab before the QMS not-found guard", () => {
    for (const tab of ["overview", "approval", "contracts", "evidence", "monitoring"]) {
      const path = `/maintenance/SAF/quality/suppliers/17/${tab}`;
      expect(classifyQmsPath(path), path).toMatchObject({
        kind: "known",
        module: expect.objectContaining({ id: "suppliers" }),
      });
    }
  });

  it("preserves prior collection views while making register first-class", () => {
    for (const view of [
      "register",
      "approved-list",
      "evaluations",
      "supplier-audits",
      "supplier-findings",
      "expired-approvals",
    ]) {
      expect(classifyQmsPath(`/maintenance/SAF/quality/suppliers/${view}`).kind).toBe("known");
    }
  });
});
