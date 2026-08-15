/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const unifiedPlannerSource = readSource("./components/UnifiedRosterPlanner.tsx");
const myRosterSource = readSource("./components/MyRosterWorkspace.tsx");
const calendarSecuritySource = readSource("./components/CalendarSubscriptionSecurityPanel.tsx");

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
    expect(myRosterSource).toContain('"attendance-history"');
    expect(myRosterSource).toContain("currentAttendance?.current_state");
    expect(myRosterSource).toContain('STALE_OPEN: ["CLOCK_OUT"]');
    expect(myRosterSource).toContain("downloadAttendanceExport");
    expect(myRosterSource).toContain("Attendance history");
  });

  it("keeps leave history visible and synchronizes approver queues", () => {
    expect(myRosterSource).toContain('label="Pending leave"');
    expect(myRosterSource).toContain("downloadLeaveRequestsExport");
    expect(myRosterSource).toContain("cancelLeaveRequest");
    expect(myRosterSource).toContain('queryKey: ["workforce", "hr"]');
    expect(myRosterSource).not.toContain("from: range.from,\n      to: range.to,\n      page_size: 100");
  });

  it("preserves configured or externally supplied calendar feed origins", () => {
    const rosterUiSource = readSource("./rosterUi.ts");
    expect(myRosterSource).toContain("VITE_API_BASE_URL");
    expect(rosterUiSource).toContain("subscription.https_url");
    expect(rosterUiSource).toContain("isLoopbackHostname");
    expect(myRosterSource).toContain("configuredApiOrigin");
  });

  it("does not share cached payloads between calendar link and status requests", () => {
    expect(myRosterSource).toContain("ROSTER_CALENDAR_LINK_QUERY_KEY");
    expect(myRosterSource).toContain("ROSTER_CALENDAR_STATUS_QUERY_KEY");
    expect(calendarSecuritySource).toContain("ROSTER_CALENDAR_STATUS_QUERY_KEY");
    expect(myRosterSource).not.toContain("subscription.feed_path.startsWith");
  });

  it("does not silently recreate a revoked calendar subscription", () => {
    expect(myRosterSource).toContain("enabled: calendarActive");
    expect(myRosterSource).toContain("createCalendarSubscription");
    expect(myRosterSource).toContain("Create secure link");
    expect(myRosterSource).toContain("if (calendarActive) refreshes.push(calendarQuery.refetch())");
    expect(calendarSecuritySource).toContain("cancelQueries({ queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY");
    expect(calendarSecuritySource).toContain("removeQueries({ queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY");
    expect(calendarSecuritySource).not.toContain("invalidateQueries({ queryKey: ROSTER_CALENDAR_QUERY_ROOT");
  });
});
