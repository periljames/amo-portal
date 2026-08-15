/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const setupSource = readSource("./components/RosteringSetupWorkspace.tsx");
const workforceOperationsSource = readSource("./components/WorkforceOperationsWorkspace.tsx");
const periodSource = readSource("./components/RosterPeriodQuickActions.tsx");
const plannerSource = readSource("./components/RosterPlannerV2.tsx");
const rosterServiceSource = readSource("../../services/rostering.ts");
const workforceServiceSource = readSource("../../services/workforce.ts");
const taskEditorSource = readSource("./components/RosterTaskAllocationEditor.tsx");
const governanceSource = readSource("./components/RosterGovernancePanel.tsx");
const ruleEditorSource = readSource("./components/RosterRuleQuickEditor.tsx");

describe("complete roster creation and recovery workflow", () => {
  it("exposes structured month creation and rejects overlapping periods before submit", () => {
    expect(setupSource).toContain("<RosterPeriodQuickActions />");
    expect(periodSource).toContain("This month");
    expect(periodSource).toContain("New period");
    expect(periodSource).toContain("Dates are locked after creation to preserve version history");
    expect(periodSource).toContain("This date range overlaps");
    expect(periodSource).toContain("Create amendment draft");
    expect(periodSource).toContain("copy_from_version_id");
    expect(periodSource).toContain("open task links and aircraft allocations will be copied");
  });

  it("prefills the selected period from effective rotations while protecting commitments", () => {
    expect(plannerSource).toContain("Prefill month");
    expect(plannerSource).toContain("generateRosterFromPattern");
    expect(plannerSource).toContain("Scheduled classes protected");
    expect(plannerSource).toContain("Collision-safe");
    expect(rosterServiceSource).toContain("/generate-from-pattern");
  });

  it("guides a monthly roster through create, generate, exceptions and review", () => {
    expect(plannerSource).toContain("createRosterVersion");
    expect(plannerSource).toContain("Create monthly roster");
    expect(plannerSource).toContain("Generate month");
    expect(plannerSource).toContain("OperationProgress");
    expect(plannerSource).toContain("Exceptions");
    expect(plannerSource).toContain("Review &amp; submit");
    expect(plannerSource).toContain("Submit for approval");
  });

  it("keeps conflicts actionable and advanced allocation collapsed", () => {
    expect(plannerSource).toContain("CellIssuePopover");
    expect(plannerSource).toContain("Open existing");
    expect(plannerSource).toContain("More details");
    expect(plannerSource).toContain("Work and aircraft allocation");
    expect(plannerSource).toContain("allocationOpen");
  });

  it("blocks occupied time and exposes ranked, auditable coverage rotations", () => {
    expect(plannerSource).toContain("OCCUPIED_STATUSES");
    expect(plannerSource).toContain("intervalsOverlap");
    expect(plannerSource).toContain("Rotation recommendations");
    expect(plannerSource).toContain("Best match");
    expect(plannerSource).toContain("applyRosterCoverageRecommendation");
    expect(rosterServiceSource).toContain("/coverage-recommendations/apply");
    expect(plannerSource).toContain("atomically");
  });

  it("provides read/write/remove visibility plus structured setup records", () => {
    expect(setupSource).toContain("My effective permissions");
    expect(setupSource).toContain("Delete draft duty");
    expect(setupSource).toContain("Required staffing windows");
    expect(setupSource).toContain("New staffing requirement");
    expect(workforceOperationsSource).toContain("Remove assignment");
    expect(workforceOperationsSource).toContain("updateWorkPatternAssignment");
    expect(workforceOperationsSource).toContain("deleteWorkPatternAssignment");
    expect(workforceServiceSource).toContain("updateWorkPatternAssignment");
    expect(workforceServiceSource).toContain("deleteWorkPatternAssignment");
    expect(taskEditorSource).toContain("allocateRosterAssignmentToTask");
    expect(taskEditorSource).toContain("deleteRosterTaskLink");
    expect(taskEditorSource).toContain("Audited reason");
    expect(governanceSource).toContain("updateRosterApprovalAuthority");
    expect(governanceSource).toContain("Grant publish");
    expect(governanceSource).toContain("Retire");
    expect(ruleEditorSource).toContain("Create compliance rule");
    expect(ruleEditorSource).toContain("createRosterRule");
  });

  it("shows live operational charts, status pills, exports and audited attendance correction", () => {
    expect(workforceOperationsSource).toContain("<PieChart>");
    expect(workforceOperationsSource).toContain("Open operational work");
    expect(workforceOperationsSource).toContain("downloadLeaveRequestsExport");
    expect(workforceOperationsSource).toContain("downloadAttendanceExport");
    expect(workforceOperationsSource).toContain("Audited time correction");
    expect(workforceOperationsSource).toContain("createAttendanceEvent");
    expect(workforceOperationsSource).toContain("refetchInterval: 15_000");
  });
});
