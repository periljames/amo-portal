import { describe, expect, it } from "vitest";
import { canFilterFindingSeverity, findingDistribution, findingTrendSummary, type FindingInsights } from "./findingAnalysisModel";

const data: FindingInsights = { year: 2026, total: 12, open: 5, unmapped: 0, months: [], groups: [
  { key: "MINOR", total: 3, open: 0 }, { key: "MAJOR", total: 7, open: 3 }, { key: "CRITICAL", total: 2, open: 2 },
] };
describe("finding analysis", () => {
  it("orders severity by risk rather than hiding critical findings behind larger minor groups", () => {
    expect(findingDistribution(data, "by-severity", false, "").map(group => group.key)).toEqual(["CRITICAL", "MAJOR", "MINOR"]);
    expect(findingDistribution(data, "by-severity", true, "").map(group => group.key)).toEqual(["CRITICAL", "MAJOR"]);
    expect(data.groups[0].key).toBe("MINOR");
  });
  it("filters processes without adding overlapping groups into a fabricated total", () => {
    const processes = { ...data, unmapped: 3, groups: [{ key: "Engineering", total: 7, open: 3 }, { key: "Flight operations", total: 4, open: 2 }] };
    expect(findingDistribution(processes, "by-process", true, " FLIGHT ")).toEqual([{ key: "Flight operations", total: 4, open: 2 }]);
    expect(processes.total - processes.unmapped).toBe(9);
  });
  it("treats closures from older cohorts as events, not a closure rate or backlog", () => {
    expect(findingTrendSummary([{ month: "2026-01", raised: 12, closed: 0 }, { month: "2026-03", raised: 0, closed: 14 }])).toEqual({ raised: 12, closed: 14, balance: -2 });
    expect(findingTrendSummary([])).toEqual({ raised: 0, closed: 0, balance: 0 });
  });
  it("does not advertise a severity drill-down the register cannot apply", () => {
    expect(canFilterFindingSeverity("MAJOR")).toBe(true);
    expect(canFilterFindingSeverity("UNCLASSIFIED")).toBe(false);
  });
});
