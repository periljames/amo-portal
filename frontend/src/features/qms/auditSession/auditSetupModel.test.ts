import { describe, expect, it } from "vitest";

import { auditSetupIssues, auditSetupReadiness } from "./auditSetupModel";

const completeSetup = {
  title: "Internal compliance audit",
  scope: "Line maintenance records and release controls",
  criteria: "KCARs Part 145, company CAME/MOE and applicable procedures",
  plannedStart: "2026-09-11",
  plannedEnd: "2026-09-12",
  plannedStartTime: "09:00",
  plannedEndTime: "17:00",
  auditee: "Maintenance Manager",
  auditeeEmail: "",
  leadAuditorUserId: "lead-1",
};

describe("audit setup readiness", () => {
  it("accepts the authoritative dates, auditee and lead-auditor gate", () => {
    expect(auditSetupReadiness(completeSetup)).toEqual({
      definitionReady: true,
      leadAssigned: true,
      ready: true,
      issues: [],
    });
  });

  it("accepts auditee email when a display name is not available", () => {
    expect(
      auditSetupReadiness({ ...completeSetup, auditee: "", auditeeEmail: "auditee@example.com" }).ready,
    ).toBe(true);
  });

  it("reports every blocking setup issue without treating meetings or notice as mandatory", () => {
    const result = auditSetupReadiness({
      title: "",
      scope: "",
      criteria: "",
      plannedStart: "2026-09-12",
      plannedEnd: "2026-09-11",
      plannedStartTime: "09:00",
      plannedEndTime: "17:00",
      auditee: "",
      auditeeEmail: "",
      leadAuditorUserId: null,
    });

    expect(result.ready).toBe(false);
    expect(result.issues).toEqual([
      "Enter an audit title.",
      "Define the audit scope.",
      "Identify the applicable audit criteria and standards.",
      "Planned end cannot be before planned start.",
      "Identify the auditee representative or provide their email.",
      "Assign an eligible lead auditor.",
    ]);
  });

  it("identifies the exact first control that should receive one-time setup guidance", () => {
    const issues = auditSetupIssues({ ...completeSetup, scope: "", criteria: "", leadAuditorUserId: null });

    expect(issues).toEqual([
      { field: "scope", tile: "definition", message: "Define the audit scope." },
      { field: "criteria", tile: "definition", message: "Identify the applicable audit criteria and standards." },
      { field: "leadAuditorUserId", tile: "team", message: "Assign an eligible lead auditor." },
    ]);
  });
});

