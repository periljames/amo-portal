/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const setupPageSource = readFileSync(
  new URL("./WorkforceRosteringPagesV2.tsx", import.meta.url),
  "utf8",
);
const setupWorkspaceSource = readFileSync(
  new URL("./components/RosteringSetupWorkspace.tsx", import.meta.url),
  "utf8",
);
const workforceSource = readFileSync(
  new URL("./components/WorkforceHrWorkspace.tsx", import.meta.url),
  "utf8",
);
const shellSource = readFileSync(
  new URL("./components/RosterShell.tsx", import.meta.url),
  "utf8",
);
const depthSource = readFileSync(
  new URL("../../styles/theme-depth.css", import.meta.url),
  "utf8",
);

describe("rostering setup experience", () => {
  it("routes Setup and Workforce through the replacement lazy workspaces", () => {
    expect(setupPageSource).toContain("LazyRosteringSetupWorkspace");
    expect(setupPageSource).toContain("LazyWorkforceHrWorkspace");
    expect(setupPageSource).toContain('eyebrow="Guided setup"');
    expect(setupPageSource).toContain('title="Roster setup"');
    expect(setupPageSource).toContain('get("section") === "workforce"');
    expect(setupPageSource).not.toContain("LazyRosterPeriodQuickActions");
    expect(setupPageSource).not.toContain("LazyRosterRuleQuickEditor");
    expect(setupPageSource).not.toContain("LazyUnifiedRosterSettings");
  });

  it("supports previewed, explicitly confirmed, draft-only roster automation", () => {
    expect(setupWorkspaceSource).toContain("previewRosterAutomation");
    expect(setupWorkspaceSource).toContain("runRosterAutomation");
    expect(setupWorkspaceSource).toContain("confirm_preview: true");
    expect(setupWorkspaceSource).toContain("Create draft and rotation");
    expect(setupWorkspaceSource).toContain("Automation creates a draft only");
    expect(setupWorkspaceSource).toContain("It never approves or publishes a roster");
  });

  it("provides actionable shift, work-pattern and controlled-policy setup", () => {
    expect(setupWorkspaceSource).toContain("createShiftTemplate");
    expect(setupWorkspaceSource).toContain("updateShiftTemplate");
    expect(setupWorkspaceSource).toContain("createWorkPattern");
    expect(setupWorkspaceSource).toContain("Visual work patterns");
    expect(setupWorkspaceSource).toContain("Compliance rules");
    expect(setupWorkspaceSource).toContain("RosterRuleQuickEditor");
    expect(setupWorkspaceSource).toContain("RosterGovernancePanel");
    expect(setupWorkspaceSource).toContain("showApprovalWorkflow={false}");
    expect(setupWorkspaceSource).toContain("roster.manage_approval_authorities");
    expect(setupWorkspaceSource).toContain("History & diagnostics");
  });

  it("keeps employee pattern assignment and staged approvals inside Workforce and HR", () => {
    expect(workforceSource).toContain("assignWorkforceHrPattern");
    expect(workforceSource).toContain("cycle_anchor_date: effectiveFrom");
    expect(workforceSource).toContain("dashboard.can_review_leave");
    expect(workforceSource).toContain("dashboard.can_approve_leave");
    expect(workforceSource).toContain("dashboard.can_approve_timesheet_supervisor");
    expect(workforceSource).toContain("dashboard.can_approve_timesheet_hr");
    expect(workforceSource).toContain("dashboard.attendance_exceptions.map");
    expect(workforceSource).toContain("roster_assignment_id");
  });

  it("gates Workforce and Setup navigation with effective server permissions", () => {
    expect(shellSource).toContain("getCurrentWorkforcePermissions");
    expect(shellSource).toContain('requiredPermissions: ["workforce.view_sensitive"]');
    expect(shellSource).toContain("livePermissions.includes(permission)");
    expect(setupPageSource).toContain('includes("workforce.view_sensitive")');
    expect(setupPageSource).toContain("This workspace requires the workforce.view_sensitive permission");
  });

  it("adds portal-wide dark surface separation without changing status colours", () => {
    expect(depthSource).toContain("--surface-elevated: rgba(19, 34, 55, 0.97)");
    expect(depthSource).toContain(".wr-panel");
    expect(depthSource).toContain(".qms-panel");
    expect(depthSource).toContain(".admin-panel");
    expect(depthSource).toContain("inset 0 1px 0");
    expect(depthSource).not.toContain("wr-pill--blocker");
  });
});
