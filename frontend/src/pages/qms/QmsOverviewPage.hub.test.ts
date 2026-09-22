import { describe, expect, it } from "vitest";

import { assuranceHub } from "./QmsOverviewPage";

describe("QMS overview assurance hub routing", () => {
  it("treats bare quality search as Control Room (no cockpit hub)", () => {
    expect(assuranceHub("")).toBeNull();
    expect(assuranceHub("?workspace=missions")).toBeNull();
    expect(assuranceHub("?hub=unknown")).toBeNull();
  });

  it("opens Continuous Assurance for every known hub including readiness", () => {
    expect(assuranceHub("?hub=readiness")).toBe("readiness");
    expect(assuranceHub("?hub=controls")).toBe("controls");
    expect(assuranceHub("?hub=evidence")).toBe("evidence");
    expect(assuranceHub("?hub=intelligence")).toBe("intelligence");
  });
});
