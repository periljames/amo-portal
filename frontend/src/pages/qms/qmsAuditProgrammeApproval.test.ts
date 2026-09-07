import { describe, expect, it } from "vitest";

import type { AuditProgramme } from "../../services/qmsAuditProgramme";
import {
  programmeApprovalStage,
  programmeCanBeEdited,
  programmeIsControlled,
} from "./qmsAuditProgrammeApproval";

const programme = (overrides: Partial<AuditProgramme> = {}) => ({
  id: "programme-1",
  programme_ref: "QAR/2026/R01",
  programme_series: "QAR/2026",
  programme_year: 2026,
  revision_no: 1,
  title: "2026 Quality Audit Programme",
  assurance_model: "HYBRID" as const,
  continuous_monitoring_enabled: true,
  optimizer_version: "v1",
  objectives: [],
  regulatory_basis: ["KCAR"],
  status: "DRAFT" as const,
  period_start: "2026-01-01",
  period_end: "2026-12-31",
  metrics: {
    planned_audit_count: 1,
    completed_audit_count: 0,
    deferred_audit_count: 0,
    cancelled_audit_count: 0,
    follow_up_audit_count: 0,
    scheduled_audit_count: 0,
  },
  ...overrides,
});

describe("audit programme approval workflow", () => {
  it("keeps Quality and executive review as distinct stages", () => {
    expect(programmeApprovalStage(programme({ status: "UNDER_REVIEW" }))).toBe("QUALITY_REVIEW");
    expect(programmeApprovalStage(programme({ status: "UNDER_REVIEW", quality_reviewed_at: "2026-09-05T12:00:00Z" }))).toBe("EXECUTIVE_APPROVAL");
  });

  it("freezes submitted revisions and exposes controlled outputs only after approval", () => {
    expect(programmeCanBeEdited(programme())).toBe(true);
    expect(programmeCanBeEdited(programme({ status: "UNDER_REVIEW" }))).toBe(false);
    expect(programmeIsControlled(programme({ status: "APPROVED" }))).toBe(true);
    expect(programmeIsControlled(programme())).toBe(false);
  });
});
