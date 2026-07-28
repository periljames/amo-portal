/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const shellSource = readSource("./components/RosterShell.tsx");
const setupSource = readSource("./components/RosteringSetupWorkspace.tsx");
const hrSource = readSource("./components/WorkforceHrWorkspace.tsx");
const automationServiceSource = readSource("../../services/rosteringAutomation.ts");


describe("Rostering setup and Workforce ownership", () => {
  it("renders one canonical setup workspace instead of stacked duplicate forms", () => {
    expect(pagesSource).toContain("LazyRosteringSetupWorkspace");
    expect(pagesSource).not.toContain("LazyRosterPeriodQuickActions");
    expect(pagesSource).not.toContain("LazyRosterRuleQuickEditor");
    expect(pagesSource).not.toContain("LazyUnifiedRosterSettings");
  });

  it("exposes clear automatic period and draft rotation controls", () => {
    expect(setupSource).toContain("Create future periods automatically");
    expect(setupSource).toContain("Generate duties from work patterns");
    expect(setupSource).toContain("Automation creates a draft only");
    expect(automationServiceSource).toContain("/automation/preview");
    expect(automationServiceSource).toContain("/automation/run");
  });

  it("keeps HR-owned records out of roster setup", () => {
    expect(setupSource).not.toContain("createEmploymentContract");
    expect(setupSource).not.toContain("createLeaveType");
    expect(setupSource).not.toContain("approveTimesheet");
    expect(setupSource).not.toContain("downloadPayrollExport");
  });

  it("provides a canonical Workforce and HR workspace", () => {
    expect(pagesSource).toContain("LazyWorkforceHrWorkspace");
    expect(hrSource).toContain("People & contracts");
    expect(hrSource).toContain("Leave");
    expect(hrSource).toContain("Attendance & time");
    expect(hrSource).toContain("Work patterns");
    expect(hrSource).toContain("Reason or decision note");
  });

  it("simplifies primary navigation and combines reports with operations", () => {
    expect(shellSource).toContain('label: "Operations"');
    expect(shellSource).toContain('label: "Workforce"');
    expect(shellSource).not.toContain('label: "Capacity"');
    expect(shellSource).not.toContain('label: "Reports"');
    expect(pagesSource).toContain("LazyRosterOperationsWorkspace");
  });
});
