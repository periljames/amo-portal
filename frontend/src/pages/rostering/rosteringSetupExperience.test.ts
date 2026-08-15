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
const workPatternStudioSource = readFileSync(
  new URL("./components/WorkPatternStudio.tsx", import.meta.url),
  "utf8",
);
const workforceSource = readFileSync(
  new URL("./components/WorkforceHrWorkspace.tsx", import.meta.url),
  "utf8",
);
const workforceDirectorySource = readFileSync(
  new URL("./components/WorkforcePeopleDirectory.tsx", import.meta.url),
  "utf8",
);
const workforceDirectoryStyles = readFileSync(
  new URL("./components/workforce-people-directory.css", import.meta.url),
  "utf8",
);
const shellSource = readFileSync(
  new URL("./components/RosterShell.tsx", import.meta.url),
  "utf8",
);
const permissionHookSource = readFileSync(
  new URL("./hooks/useWorkforcePermissions.ts", import.meta.url),
  "utf8",
);
const workforceServiceSource = readFileSync(
  new URL("../../services/workforce.ts", import.meta.url),
  "utf8",
);
const depthSource = readFileSync(
  new URL("../../styles/theme-depth.css", import.meta.url),
  "utf8",
);
const layoutSafetySource = readFileSync(
  new URL("../../styles/foundations/layout-safety.css", import.meta.url),
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
    expect(setupWorkspaceSource).toContain("Create draft roster");
    expect(setupWorkspaceSource).toContain("Creates a draft only");
    expect(setupWorkspaceSource).toContain("Approval and publication always remain separate");
  });

  it("provides actionable shift, work-pattern and controlled-policy setup", () => {
    expect(workPatternStudioSource).toContain("createShiftTemplate");
    expect(workPatternStudioSource).toContain("updateShiftTemplate");
    expect(workPatternStudioSource).toContain("deleteUnusedRosterCode");
    expect(workPatternStudioSource).toContain("createWorkPattern");
    expect(workPatternStudioSource).toContain("updateWorkPattern");
    expect(workPatternStudioSource).toContain("deleteWorkPattern");
    expect(workPatternStudioSource).toContain("Repeating shift order");
    expect(workPatternStudioSource).toContain("Delete if unused");
    expect(setupWorkspaceSource).toContain("Compliance rules");
    expect(setupWorkspaceSource).toContain("RosterRuleQuickEditor");
    expect(setupWorkspaceSource).toContain("RosterGovernancePanel");
    expect(setupWorkspaceSource).toContain("showApprovalWorkflow={false}");
    expect(setupWorkspaceSource).toContain("roster.manage_approval_authorities");
    expect(setupWorkspaceSource).toContain("Advanced");
  });

  it("keeps employee pattern assignment and staged approvals inside Workforce and HR", () => {
    expect(workforceSource).toContain("assignWorkforceHrPattern");
    expect(workforceSource).toContain("cycle_anchor_date: effectiveFrom");
    expect(workforceSource).toContain("dashboard.can_review_leave");
    expect(workforceSource).toContain("dashboard.can_approve_leave");
    expect(workforceSource).toContain("dashboard.can_approve_timesheet_supervisor");
    expect(workforceSource).toContain("dashboard.can_approve_timesheet_hr");
    expect(workforceSource).toContain("dashboard.attendance_exceptions.map");
    expect(workforceSource).toContain("listWorkforceHrPeople");
    expect(workforceSource).toContain("Showing {people.length} of {total}");
    expect(workforceSource).toContain("roster_assignment_id");
  });

  it("gates Workforce and Setup navigation with effective server permissions", () => {
    expect(shellSource).toContain("useWorkforcePermissions");
    expect(shellSource).toContain('requiredPermissions: ["workforce.view_sensitive"]');
    expect(shellSource).toContain("livePermissions.includes(permission)");
    expect(setupPageSource).toContain('includes("workforce.view_sensitive")');
    expect(setupPageSource).toContain("permissionsQuery.isSuccess && !canView");
    expect(setupPageSource).toContain("Could not verify Workforce access");
    expect(setupPageSource).toContain("Waiting for the server to verify Workforce access");
    expect(permissionHookSource).toContain('["workforce", "permissions", "current"]');
    expect(permissionHookSource).toContain('networkMode: "online"');
    expect(permissionHookSource).toContain('refetchOnMount: "always"');
    expect(workforceServiceSource).toContain('cache: "no-store"');
    expect(workforceServiceSource).toContain("allowStaleFallback: false");
  });

  it("adds portal-wide dark surface separation without changing status colours", () => {
    expect(depthSource).toContain("--surface-elevated: rgba(19, 34, 55, 0.97)");
    expect(depthSource).toContain(".wr-panel");
    expect(depthSource).toContain(".qms-panel");
    expect(depthSource).toContain(".admin-panel");
    expect(depthSource).toContain("inset 0 1px 0");
    expect(depthSource).not.toContain("wr-pill--blocker");
  });

  it("keeps fields, labels and table content inside their layout boundaries", () => {
    expect(workforceDirectorySource).toContain("Imported hire date · re-import the personnel source to correct it.");
    expect(workforceDirectorySource).not.toContain("Re-employ from User Management");
    expect(workforceDirectorySource).toContain('<span>{key === "overtime_eligible"');
    expect(workforceDirectoryStyles).toContain("grid-template-columns: repeat(3, max-content)");
    expect(workforceDirectoryStyles).toContain(".workforce-directory__flags span");
    expect(workforceDirectoryStyles).toContain("text-overflow: ellipsis");
    expect(layoutSafetySource).not.toContain("overflow-wrap: anywhere");
    expect(layoutSafetySource).toContain("body :where(*):not(pre):not(code)");
    expect(layoutSafetySource).toContain('[class*="table-shell"]');
    expect(layoutSafetySource).toContain('input:not([type="checkbox"]):not([type="radio"])');
    expect(layoutSafetySource).toContain("white-space: nowrap");
  });
});
