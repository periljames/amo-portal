/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const shellSource = readSource("./components/RosterShell.tsx");
const setupSource = readSource("./components/RosteringSetupWorkspace.tsx");
const studioSource = readSource("./components/WorkPatternStudio.tsx");
const hrSource = readSource("./components/WorkforceHrWorkspace.tsx");
const automationServiceSource = readSource("../../services/rosteringAutomation.ts");
const portalRoutesSource = readSource("../../portalRoutes.tsx");


describe("Rostering setup and Workforce ownership", () => {
  it("renders one canonical setup workspace instead of stacked duplicate forms", () => {
    expect(pagesSource).toContain("LazyRosteringSetupWorkspace");
    expect(pagesSource).toContain('import("./components/RosteringSetupWorkspace")');
    expect(pagesSource).not.toContain("RosteringSetupWorkspaceWithCodeRegistry");
    expect(pagesSource).not.toContain("LazyRosterPeriodQuickActions");
    expect(pagesSource).not.toContain("LazyRosterRuleQuickEditor");
    expect(pagesSource).not.toContain("LazyUnifiedRosterSettings");
  });

  it("exposes clear automatic period and draft rotation controls", () => {
    expect(setupSource).toContain("Create future periods automatically");
    expect(setupSource).toContain("Generate duties from work patterns");
    expect(setupSource).toContain("Creates a draft only");
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
    expect(studioSource).toContain("timezone_name: timezoneName");
    expect(studioSource).not.toContain('timezone_name: "Africa/Nairobi"');
  });

  it("uses one compact shift vocabulary for setup and the planner", () => {
    expect(studioSource).toContain("1–2 letters or numbers");
    expect(studioSource).toContain("Apply automatically");
    expect(studioSource).toContain("anchor_date: autoAssign ? anchorDate : null");
    expect(studioSource).toContain("Add the real codes used by your organization");
    expect(studioSource).toContain("Same type and hours as another code");
    expect(studioSource).not.toContain("Apply default day pattern");
  });

  it("requires both create and pattern permissions before generation", () => {
    expect(setupSource).toContain('can("roster.create") && can("roster.manage_patterns")');
    expect(setupSource).toContain("previewEnabled={canGenerate}");
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
    expect(hrSource).toContain("Overtime requests");
    expect(hrSource).toContain("Supervisor approve");
    expect(hrSource).toContain("HR approve");
    expect(hrSource).toContain("decideWorkforceHrOvertime");
  });

  it("lets live Workforce permission holders reach the permission-aware workspace", () => {
    expect(portalRoutesSource).toContain('feature === "rostering.settings"');
    expect(portalRoutesSource).toContain('get("section") === "workforce"');
  });

  it("shows leave rejection only to effective leave reviewers", () => {
    expect(hrSource).toContain("dashboard.can_review_leave ?");
    expect(hrSource).not.toContain("dashboard.can_review_leave || dashboard.can_approve_leave");
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


  it("keeps active tenant users visible when Workforce records are incomplete", () => {
    expect(hrSource).toContain("Every active tenant user appears here");
    expect(hrSource).toContain("Create contract");
    expect(hrSource).toContain("createEmploymentContract");
    expect(hrSource).not.toContain("Apply default day pattern");
    expect(studioSource).toContain("Apply automatically");
    expect(studioSource).toContain("Cycle day 1");
    expect(studioSource).toContain("Contracts");
    const workforceTypes = readSource("../../types/workforce.ts");
    expect(workforceTypes).toContain('"TEMPORARY"');
    expect(workforceTypes).not.toContain('"CASUAL"');
    expect(workforceTypes).not.toContain('"SECONDMENT"');
    expect(workforceTypes).not.toContain('"ENDED"');
  });
});
