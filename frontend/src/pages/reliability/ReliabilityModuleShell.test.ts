import { describe, expect, it } from "vitest";
import { RELIABILITY_GROUPS } from "./ReliabilityModuleShell";

describe("Reliability workspace navigation", () => {
  const paths = RELIABILITY_GROUPS.flatMap((group) => group.items.map((item) => item.path));

  it("exposes the major operational, analysis and governance workflows", () => {
    for (const path of [
      "", "analytics/operational", "analytics/network", "analytics/components",
      "analytics/oil", "analytics/engineering", "analytics/deferrals",
      "analytics/fracas", "analytics/data", "analytics/evidence",
      "analytics/formulae", "analytics/administration", "analytics/governance",
      "analytics/calculations", "operations", "events", "alerts", "cases",
      "octm", "workbook-registers", "workbook-mapping", "workbook-imports",
      "workbook-csv", "formal-review", "formal-reports", "programme-reports",
      "report-distribution",
    ]) {
      expect(paths).toContain(path);
    }
  });

  it("keeps every sidebar destination unique", () => {
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("keeps only legitimate relative routes in the tenant navigation", () => {
    for (const path of paths) {
      expect(path).not.toMatch(/^\/|:\/\/|\.\./);
    }
  });
});
