import { describe, expect, it } from "vitest";
import type { QMSAuditOut } from "../../../services/qms";
import { meetingTimelineIssue, normalizePlannedAuditWindow, reconcileSetupDraft, savedTeamOptions, setupDateLabel } from "./auditSetupControls";

describe("audit setup integrity", () => {
  it("retains a saved auditor outside the directory page", () => {
    const audit = { lead_auditor_user_id: "saved-user", lead_auditor_name: "Saved Auditor" } as QMSAuditOut;
    const people = Array.from({ length: 200 }, (_, i) => ({ id: `user-${i}`, full_name: `Person ${i}` }));
    expect(savedTeamOptions(audit, people)).toContainEqual({ id: "saved-user", full_name: "Saved Auditor" });
    expect(savedTeamOptions(audit, [...people, { id: "saved-user", full_name: "Saved Auditor" }])).toHaveLength(201);
  });
  it("does not turn a directory failure into an unassigned team", () => {
    const audit = { lead_auditor_user_id: "saved-user" } as QMSAuditOut;
    expect(savedTeamOptions(audit, [])[0].id).toBe("saved-user");
  });
  it("rejects closing meetings before audit end and opening meetings after audit start", () => {
    expect(meetingTimelineIssue("CLOSING", "2026-09-09T17:00", "2026-09-09T18:00", "2026-09-22T09:00", "2026-09-22T17:00")).toMatch(/after the audit ends/);
    expect(meetingTimelineIssue("OPENING", "2026-09-22T10:00", "2026-09-22T11:00", "2026-09-22T09:00", "2026-09-22T17:00")).toMatch(/before the audit starts/);
  });
  it("accepts boundary meetings and rejects zero duration", () => {
    expect(meetingTimelineIssue("CLOSING", "2026-09-22T17:00", "2026-09-22T18:00", "2026-09-22T09:00", "2026-09-22T17:00")).toBeNull();
    expect(meetingTimelineIssue("OPENING", "2026-09-22T08:00", "2026-09-22T09:00", "2026-09-22T09:00", "2026-09-22T17:00")).toBeNull();
    expect(meetingTimelineIssue("OPENING", "2026-09-22T08:00", "2026-09-22T08:00", "", "")).toMatch(/after its start/);
  });
  it("preserves unsaved edits during a background refresh", () => {
    expect(reconcileSetupDraft({ title: "editing" }, { title: "saved" }, { title: "refetched" })).toEqual({ title: "editing" });
    expect(reconcileSetupDraft({ title: "saved" }, { title: "saved" }, { title: "refetched" })).toEqual({ title: "refetched" });
    expect(reconcileSetupDraft({ title: "previous audit" }, null, { title: "new audit" })).toEqual({ title: "new audit" });
  });
  it("preserves a multi-day audit ending at an earlier clock hour", () => {
    const window = normalizePlannedAuditWindow(
      "2026-11-12T16:00", "2026-11-13T10:00", "2026-10-12T09:00",
    );
    expect(window).toEqual({
      plannedStart: "2026-11-12",
      plannedStartTime: "16:00",
      plannedEnd: "2026-11-13",
      plannedEndTime: "10:00",
    });
  });
  it("renders calendar dates without shifting them to the browser timezone", () => {
    expect(setupDateLabel("2026-09-22T09:00")).toBe("22 Sept 2026 · 09:00");
  });
});
