import { describe, expect, it, vi } from "vitest";
import { retentionDate, retentionDispositionReady, type AmoCompliancePolicy, type RetentionRule } from "./amoCompliancePolicy";
const rule: RetentionRule = { code: "MAINTENANCE_RECORDS", label: "Maintenance", event: "release_signed_at", years: 3, days: 0, reference: "MOPM 2.14", regulatory_minimum_years: 2 };
describe("retention preview", () => {
  it("uses the release anniversary and handles leap days", () => {
    expect(retentionDate(rule, "2024-02-29")).toBe("2027-02-28");
    expect(retentionDate(rule, "2024-02-29", { extensions_years: { MAINTENANCE_RECORDS: 4 } })).toBe("2028-02-29");
  });
  it("preserves records with unknown dates or an undetermined schedule", () => {
    expect(retentionDate(rule, "")).toBe("");
    expect(retentionDate({ ...rule, years: 0 }, "2024-02-29")).toBe("");
  });
  it("calculates the standalone status summary's 90 days from withdrawal", () => {
    expect(retentionDate({ ...rule, years: 0, days: 90 }, "2026-01-01")).toBe("2026-04-01");
  });
  it("keeps disposition disabled for missing dates, live periods and preservation holds", () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-22T12:00:00Z"));
    try {
      const policy: AmoCompliancePolicy = { version: "test", source: "MOPM", retention: [rule], contracting: { maximum_supplier_review_days: 365, reference: "MOPM" } };
      const facts = { classes: [], events: { release_signed_at: "2020-01-01" } };
      expect(retentionDispositionReady(policy, rule.code, { compliance_retention: facts })).toBe(true);
      expect(retentionDispositionReady(policy, rule.code, { compliance_retention: { ...facts, events: {} } })).toBe(false);
      expect(retentionDispositionReady(policy, rule.code, { compliance_retention: { ...facts, preservation_hold: true } })).toBe(false);
      expect(retentionDispositionReady(policy, rule.code, { compliance_retention: { ...facts, requirements_unconfirmed: true } })).toBe(false);
      expect(retentionDispositionReady(policy, rule.code, { compliance_retention: facts }, "2030-01-01")).toBe(false);
    } finally { vi.useRealTimers(); }
  });
});
