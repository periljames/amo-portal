import { describe, expect, it } from "vitest";

import type { AuditProgramme } from "../../services/qmsAuditProgramme";
import {
  availableProgrammeKinds,
  canCreateAnotherProgramme,
  headProgrammesForYear,
  programmeDisplayLabel,
  programmeKindOf,
  programmeKindTitle,
  programmePortfolioSummary,
} from "./qmsAuditProgrammeDisplay";

function programme(partial: Partial<AuditProgramme> & Pick<AuditProgramme, "title" | "programme_series">): AuditProgramme {
  const { programme_series, title, ...overrides } = partial;
  return {
    id: overrides.id || "p1",
    programme_ref: "AP-2026-TEST-R01",
    programme_series,
    programme_year: overrides.programme_year ?? 2026,
    revision_no: overrides.revision_no ?? 1,
    title,
    assurance_model: "HYBRID",
    continuous_monitoring_enabled: true,
    optimizer_version: "HYBRID_ASSURANCE_V1",
    objectives: [],
    regulatory_basis: [],
    status: overrides.status ?? "DRAFT",
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    metrics: {
      planned_audit_count: 0,
      completed_audit_count: 0,
      deferred_audit_count: 0,
      cancelled_audit_count: 0,
      follow_up_audit_count: 0,
      scheduled_audit_count: 0,
    },
    ...overrides,
  };
}

describe("qmsAuditProgrammeDisplay", () => {
  it("formats display labels with year when missing", () => {
    expect(programmeDisplayLabel({ title: "Internal Audits", programme_year: 2026 })).toBe("Internal Audits (2026)");
    expect(programmeDisplayLabel({ title: "External Audits (2026)", programme_year: 2026 })).toBe("External Audits (2026)");
  });

  it("builds canonical kind titles", () => {
    expect(programmeKindTitle("INTERNAL", 2026)).toBe("Internal Audits (2026)");
  });

  it("keeps only the latest active revision per series", () => {
    const rows = headProgrammesForYear([
      programme({ id: "a", programme_series: "AP-2026-A", revision_no: 1, status: "SUPERSEDED", title: "Internal Audits (2026)" }),
      programme({ id: "b", programme_series: "AP-2026-A", revision_no: 2, status: "DRAFT", title: "Internal Audits (2026)" }),
      programme({ id: "c", programme_series: "AP-2026-B", revision_no: 1, status: "ACTIVE", title: "External Audits (2026)" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual(["c", "b"]);
  });

  it("blocks new programmes when a legacy title occupies the year", () => {
    const rows = [programme({ programme_series: "AP-2026-L", title: "2026 Quality Audit Programme" })];
    expect(programmeKindOf(rows[0])).toBe("LEGACY");
    expect(availableProgrammeKinds(rows)).toEqual([]);
    expect(canCreateAnotherProgramme(rows)).toBe(false);
  });

  it("allows external programme when internal already exists", () => {
    const rows = [programme({ programme_series: "AP-2026-I", title: "Internal Audits (2026)" })];
    expect(availableProgrammeKinds(rows)).toEqual(["EXTERNAL", "THIRD_PARTY"]);
    expect(canCreateAnotherProgramme(rows)).toBe(true);
  });

  it("summarizes portfolio cards without repeating period dates", () => {
    expect(
      programmePortfolioSummary({ metrics: { planned_audit_count: 3 } as AuditProgramme["metrics"] }, 2),
    ).toBe("3 audits · 2 need scheduling");
    expect(programmePortfolioSummary({ metrics: { planned_audit_count: 1 } as AuditProgramme["metrics"] })).toBe(
      "1 audit",
    );
  });
});
