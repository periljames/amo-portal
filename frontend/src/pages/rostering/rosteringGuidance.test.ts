/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const unifiedPlannerSource = readSource("./components/UnifiedRosterPlanner.tsx");
const myRosterSource = readSource("./components/MyRosterWorkspace.tsx");

describe("rostering self-service guidance", () => {
  it("replaces the permanent commitment board with zero-runtime native guidance", () => {
    expect(unifiedPlannerSource).not.toContain("RosterCommitmentBoard");
    expect(unifiedPlannerSource).not.toContain("PrerequisiteDialog");
    expect(unifiedPlannerSource).not.toContain("ContextualHelp");
    expect(unifiedPlannerSource).toContain("<details");
    expect(unifiedPlannerSource).toContain("Commitment sources");
    expect(unifiedPlannerSource).toContain("source modules rather than creating duplicate roster records");
  });

  it("keeps live attendance state independent from the selected report range", () => {
    expect(myRosterSource).toContain('"attendance-current"');
    expect(myRosterSource).toContain("currentAttendanceQuery");
    expect(myRosterSource).toContain("ALLOWED_ATTENDANCE_ACTIONS");
    expect(myRosterSource).toContain("Confirming the latest event before enabling controls");
    expect(myRosterSource).toContain("hidden={currentAttendanceQuery.isPending");
  });

  it("preserves configured or externally supplied calendar feed origins", () => {
    expect(myRosterSource).toContain("VITE_API_BASE_URL");
    expect(myRosterSource).toContain("subscription.https_url");
    expect(myRosterSource).toContain("isLoopbackHostname");
    expect(myRosterSource).toContain("configuredApiOrigin");
  });
});
