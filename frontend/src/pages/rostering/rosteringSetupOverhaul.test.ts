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
const legacyRouterSource = readSource("../../router.legacy.tsx");


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


  it("uses cadence-aware scheduling controls and normalizes run days", () => {
    expect(setupSource).toContain("Day of month");
    expect(setupSource).toContain("Weekday");
    expect(setupSource).toContain('draft.frequency === "MANUAL"');
    expect(setupSource).toContain("draft.run_day > 7 ? 1");
  });

  it("does not advertise unimplemented or optional safety behavior", () => {
    expect(setupSource).not.toContain("> Notify planners<");
    expect(setupSource).not.toContain("> Preserve source commitments<");
    expect(setupSource).toContain("source commitments are always preserved");
  });

  it("uses the controlled automation timezone for work patterns", () => {
    expect(setupSource).toContain("timezoneName={readiness.policy.timezone_name}");
    expect(setupSource).toContain("timezone_name: timezoneName");
    expect(setupSource).not.toContain('timezone_name: "Africa/Nairobi"');
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

  it("lets live Workforce permission holders reach the permission-aware workspace", () => {
    expect(legacyRouterSource).toContain('feature === "rostering.settings"');
    expect(legacyRouterSource).toContain('get("section") === "workforce"');
  });

  it("makes contracts editable only for authorized Workforce managers", () => {
    expect(hrSource).toContain("updateEmploymentContract");
    expect(hrSource).toContain("listBaseStations");
    expect(hrSource).toContain("dashboard.can_manage_contracts");
    expect(hrSource).toContain("Save contract");
    expect(hrSource).toContain("Read only");
  });

  it("keeps HR remediation inside HR-accessible Workforce surfaces", () => {
    expect(hrSource).not.toContain("/admin/users/");
    expect(hrSource).toContain('onOpen("people")');
    expect(hrSource).toContain("Open employment record");
  });

  it("simplifies primary navigation and combines reports with operations", () => {
    expect(shellSource).toContain('label: "Operations"');
    expect(shellSource).toContain('label: "Workforce"');
    expect(shellSource).not.toContain('label: "Capacity"');
    expect(shellSource).not.toContain('label: "Reports"');
    expect(pagesSource).toContain("LazyRosterOperationsWorkspace");
  });
});
