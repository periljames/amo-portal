import { describe, expect, it } from "vitest";

import {
  QMS_WORKSPACES,
  qmsWorkspaceEntryPath,
  qmsWorkspaceFromRelativePath,
  qmsWorkspaceNavigationItems,
  qmsWorkspacePath,
} from "./qmsWorkspaceRegistry";

describe("QMS assurance workspace registry", () => {
  it("defines exactly the six operating workspaces", () => {
    expect(QMS_WORKSPACES.map((workspace) => workspace.id)).toEqual([
      "control-room",
      "planner",
      "missions",
      "people",
      "assurance",
      "intelligence",
    ]);
    expect(new Set(QMS_WORKSPACES.map((workspace) => workspace.id)).size).toBe(6);
  });

  it("keeps the future canonical route tree compact", () => {
    expect(qmsWorkspacePath("SAF", "control-room")).toBe("/maintenance/SAF/quality/control-room");
    expect(qmsWorkspacePath("SAF", "missions")).toBe("/maintenance/SAF/quality/missions");
    expect(qmsWorkspacePath("Safari Link/AMO", "intelligence")).toBe(
      "/maintenance/Safari%20Link%2FAMO/quality/intelligence",
    );
  });

  it("consolidates transitional workspace entries on the Quality root", () => {
    expect(qmsWorkspaceEntryPath("SAF", "control-room")).toBe("/maintenance/SAF/quality");
    expect(qmsWorkspaceEntryPath("SAF", "planner")).toBe("/maintenance/SAF/quality/calendar/month");
    expect(qmsWorkspaceEntryPath("SAF", "missions")).toBe("/maintenance/SAF/quality?workspace=missions");
    expect(qmsWorkspaceEntryPath("SAF", "people")).toBe("/maintenance/SAF/quality?workspace=people");
    expect(qmsWorkspaceEntryPath("SAF", "assurance")).toBe("/maintenance/SAF/quality?workspace=assurance");
    expect(qmsWorkspaceEntryPath("SAF", "intelligence")).toBe("/maintenance/SAF/quality?workspace=intelligence");
  });

  it("maps legacy QMS modules into their owning workspace instead of new top-level registers", () => {
    expect(qmsWorkspaceFromRelativePath("")).toBe("control-room");
    expect(qmsWorkspaceFromRelativePath("calendar/month")).toBe("planner");
    expect(qmsWorkspaceFromRelativePath("change-control/register")).toBe("missions");
    expect(qmsWorkspaceFromRelativePath("audits/register")).toBe("assurance");
    expect(qmsWorkspaceFromRelativePath("cars/overdue")).toBe("assurance");
    expect(qmsWorkspaceFromRelativePath("equipment-calibration/overdue")).toBe("assurance");
    expect(qmsWorkspaceFromRelativePath("risk/risk-matrix")).toBe("intelligence");
    expect(qmsWorkspaceFromRelativePath("management-review/dashboard")).toBe("intelligence");
  });

  it("builds one navigation item per workspace", () => {
    const items = qmsWorkspaceNavigationItems("SAF");
    expect(items).toHaveLength(6);
    expect(items.map((item) => item.path)).toEqual([
      "/maintenance/SAF/quality",
      "/maintenance/SAF/quality/calendar/month",
      "/maintenance/SAF/quality?workspace=missions",
      "/maintenance/SAF/quality?workspace=people",
      "/maintenance/SAF/quality?workspace=assurance",
      "/maintenance/SAF/quality?workspace=intelligence",
    ]);
  });

  it("labels the cases workspace distinctly from Audit Assurance", () => {
    const assurance = QMS_WORKSPACES.find((workspace) => workspace.id === "assurance");
    expect(assurance?.label).toBe("Assurance Cases");
    expect(assurance?.shortLabel).toBe("Cases");
  });
});
