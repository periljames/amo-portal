import { describe, expect, it } from "vitest";

import {
  listedReadinessOf,
  readinessExceptionCount,
  readinessOf,
  type AuditProgramme,
  type AuditProgrammeOptimizer,
} from "./qmsAuditProgramme";

function programme(overrides: Partial<AuditProgramme> = {}): AuditProgramme {
  return {
    id: "programme-1",
    programme_ref: "AP-2026-001",
    programme_series: "AP-2026",
    programme_year: 2026,
    revision_no: 1,
    title: "2026 programme",
    assurance_model: "HYBRID",
    continuous_monitoring_enabled: true,
    optimizer_version: "v1",
    objectives: [],
    regulatory_basis: ["KCAR"],
    status: "ACTIVE",
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    metrics: {
      planned_audit_count: 9,
      completed_audit_count: 0,
      deferred_audit_count: 0,
      cancelled_audit_count: 0,
      follow_up_audit_count: 0,
      scheduled_audit_count: 0,
      unscheduled_audit_count: 9,
    },
    ...overrides,
  };
}

describe("audit programme readiness projection", () => {
  it("does not invent list readiness from generic audit metrics", () => {
    expect(listedReadinessOf(programme())).toBeNull();
  });

  it("uses governed unscheduled requirements and approval blockers", () => {
    const readiness = listedReadinessOf(programme({
      readiness: {
        ready_for_approval: false,
        blockers: [{ code: "MISSING_CRITERIA", message: "Criteria required." }],
        requirement_count: 3,
        mandatory_requirement_count: 2,
        mandatory_unscheduled_count: 1,
        high_risk_requirement_count: 1,
        unscheduled_requirement_count: 2,
        mandatory_coverage_gap_count: 0,
      },
    }));

    expect(readiness?.unscheduled_requirement_count).toBe(2);
    expect(readiness && readinessExceptionCount(readiness)).toBe(1);
  });

  it("adds optimizer mandatory gaps to Programme detail readiness", () => {
    const optimizer = {
      summary: { mandatory_coverage_gaps: 2 },
    } as AuditProgrammeOptimizer;

    const readiness = readinessOf(programme({ items: [] }), optimizer);

    expect(readiness.mandatory_coverage_gap_count).toBe(2);
    expect(readiness.blockers.some((blocker) => blocker.code === "MANDATORY_COVERAGE_GAP")).toBe(true);
  });
});
