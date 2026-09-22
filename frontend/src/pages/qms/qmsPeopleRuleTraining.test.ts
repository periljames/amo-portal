import { describe, expect, it } from "vitest";

import {
  authorizeValidityLabel,
  buildPrivilegeRuleScopeSchema,
  courseCodeSelected,
  defaultTrainingCodesForPrivilegeType,
  defaultTrainingExpression,
  evaluateTrainingExpression,
  formatTrainingRuleSummary,
  parseTrainingExpression,
  resolveCourseCounterpart,
  ruleConfiguredTrainingCodes,
  ruleRequiredTrainingPayload,
  toggleTrainingSelectionWithPairs,
} from "./qmsPeopleRuleTraining";

describe("qmsPeopleRuleTraining", () => {
  it("reads Lead competence package trainings for edit preselect", () => {
    const codes = ruleConfiguredTrainingCodes({
      required_training_course_codes: [],
      scope_schema: {
        qms_competence: {
          currency_any_of: ["QMS-INIT", "QMS-REF"],
          tracked_admin: "QMS-ADMIN",
        },
      },
    });
    expect(codes).toEqual(["QMS-INIT", "QMS-REF", "QMS-ADMIN"]);
  });

  it("matches course codes compactly for checkbox state", () => {
    expect(courseCodeSelected("QMS INIT", ["QMS-INIT", "QMS-REF"])).toBe(true);
    expect(courseCodeSelected("HF-INIT", ["QMS-INIT"])).toBe(false);
  });

  it("auto-selects REF when INIT is chosen and clears the pair together", () => {
    const added = toggleTrainingSelectionWithPairs([], "QMS-INIT", ["QMS-INIT", "QMS-REF", "QMS-ADMIN"]);
    expect(added.codes).toEqual(["QMS-INIT", "QMS-REF"]);
    expect(added.notice).toMatch(/Also selected QMS-REF/);

    const removed = toggleTrainingSelectionWithPairs(added.codes, "QMS-REF", ["QMS-INIT", "QMS-REF", "QMS-ADMIN"]);
    expect(removed.codes).toEqual([]);
    expect(removed.notice).toMatch(/together/);
  });

  it("summarises selected courses with AND by default", () => {
    expect(formatTrainingRuleSummary(["QMS-INIT", "QMS-REF", "QMS-ADMIN"])).toBe(
      "QMS-INIT AND QMS-REF AND QMS-ADMIN",
    );
    expect(defaultTrainingExpression(["QMS-INIT", "QMS-REF"], "OR")).toBe("QMS-INIT OR QMS-REF");
  });

  it("parses and evaluates AND / OR expressions without symbols", () => {
    const parsed = parseTrainingExpression("QMS-INIT AND QMS-REF AND QMS-ADMIN");
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.join).toBe("AND");
    expect(parsed.codes).toEqual(["QMS-INIT", "QMS-REF", "QMS-ADMIN"]);
    expect(evaluateTrainingExpression("QMS-INIT AND QMS-REF", ["QMS-INIT"])).toBe(false);
    expect(evaluateTrainingExpression("QMS-INIT OR QMS-REF", ["QMS-REF"])).toBe(true);
    expect(evaluateTrainingExpression("(QMS-INIT OR QMS-REF) AND QMS-ADMIN", ["QMS-REF", "QMS-ADMIN"])).toBe(true);
  });

  it("resolves INIT/REF counterparts from catalogue families", () => {
    expect(resolveCourseCounterpart("HF-INIT", ["HF-INIT", "HF-REF", "QMS-ADMIN"])).toBe("HF-REF");
    expect(resolveCourseCounterpart("QMS-REF", [])).toBe("QMS-INIT");
  });

  it("rebuilds competence package as AND of selected codes", () => {
    const scope = buildPrivilegeRuleScopeSchema({
      privilegeType: "LEAD_AUDITOR",
      supervisedDevelopment: false,
      selectedTrainingCodes: ["QMS-INIT", "QMS-ADMIN", "QMS-REF"],
      previousScope: {
        qms_competence: {
          currency_any_of: ["QMS-INIT", "QMS-REF"],
          tracked_admin: "QMS-ADMIN",
        },
      },
    });
    expect(scope.qms_competence).toEqual({
      codes: ["QMS-INIT", "QMS-ADMIN", "QMS-REF"],
      join: "AND",
      expression: "QMS-INIT AND QMS-ADMIN AND QMS-REF",
      currency_any_of: ["QMS-INIT", "QMS-REF"],
      tracked_admin: "QMS-ADMIN",
    });
    expect(ruleRequiredTrainingPayload({ usesCompetencePackage: true, selectedTrainingCodes: ["QMS-INIT"] })).toEqual([]);
  });

  it("honours an advanced OR expression when saving scope", () => {
    const scope = buildPrivilegeRuleScopeSchema({
      privilegeType: "LEAD_AUDITOR",
      supervisedDevelopment: false,
      selectedTrainingCodes: ["QMS-INIT", "QMS-REF"],
      expression: "QMS-INIT OR QMS-REF",
    });
    expect(scope.qms_competence).toMatchObject({
      codes: ["QMS-INIT", "QMS-REF"],
      join: "OR",
      expression: "QMS-INIT OR QMS-REF",
    });
  });

  it("drops deselected codes from the package", () => {
    const scope = buildPrivilegeRuleScopeSchema({
      privilegeType: "LEAD_AUDITOR",
      supervisedDevelopment: false,
      selectedTrainingCodes: ["QMS-INIT", "QMS-REF"],
      previousScope: {
        qms_competence: {
          codes: ["QMS-INIT", "QMS-REF", "QMS-ADMIN"],
          join: "AND",
          expression: "QMS-INIT AND QMS-REF AND QMS-ADMIN",
        },
      },
    });
    expect(scope.qms_competence).toMatchObject({
      codes: ["QMS-INIT", "QMS-REF"],
      join: "AND",
      expression: "QMS-INIT AND QMS-REF",
      tracked_admin: null,
    });
  });

  it("seeds default Lead trainings for create presets", () => {
    expect(defaultTrainingCodesForPrivilegeType("LEAD_AUDITOR")).toEqual([
      "QMS-INIT",
      "QMS-REF",
      "QMS-ADMIN",
    ]);
  });

  it("labels authorize validity and flags 60-day due-soon", () => {
    const soon = new Date();
    soon.setHours(0, 0, 0, 0);
    soon.setDate(soon.getDate() + 20);
    const label = authorizeValidityLabel({
      validUntil: soon.toISOString().slice(0, 10),
      matchReasons: ["RECORD"],
    });
    expect(label.text.startsWith("Valid until:")).toBe(true);
    expect(label.dueSoon).toBe(true);

    const scheduled = authorizeValidityLabel({
      validUntil: null,
      matchReasons: ["SCHEDULED"],
    });
    expect(scheduled.text).toBe("Scheduled");
    expect(scheduled.dueSoon).toBe(false);
  });
});
