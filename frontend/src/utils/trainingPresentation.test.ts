import { describe, expect, it } from "vitest";

import {
  canonicalTrainingType,
  complianceStatusLabel,
  completedEventStatusWithoutRequirement,
  explicitTrainingRequirementKey,
  trainingLifecyclePhase,
  trainingTypeLabel,
} from "./trainingPresentation";

describe("training presentation semantics", () => {
  it("maps legacy REFRESHER to Recurrent without changing the controlled code", () => {
    const course = { id: "1", course_id: "HF-REF", kind: "REFRESHER" };
    expect(canonicalTrainingType(course)).toBe("RECURRENT");
    expect(trainingTypeLabel(course)).toBe("Recurrent");
    expect(course.course_id).toBe("HF-REF");
  });

  it("does not infer recurrence families from code suffixes", () => {
    expect(explicitTrainingRequirementKey({ id: "a", course_id: "HF-INIT" })).toBe("course:a");
    expect(explicitTrainingRequirementKey({ id: "b", course_id: "HF-REF" })).toBe("course:b");
  });

  it("uses explicit group and prerequisite relationships", () => {
    expect(explicitTrainingRequirementKey({ id: "a", group_code: "HF" })).toBe("group:hf");
    expect(explicitTrainingRequirementKey({ id: "b", prerequisite_course_id: "SMS-INIT" })).toBe("prerequisite:sms-init");
  });

  it("classifies phases only from controlled lifecycle fields", () => {
    expect(trainingLifecyclePhase({ id: "a", course_id: "HF-INIT", course_name: "Initial Human Factors" })).toBe("UNKNOWN");
    expect(trainingLifecyclePhase({ id: "b", course_id: "HF-REF", course_name: "Recurrent Human Factors" })).toBe("UNKNOWN");
    expect(trainingLifecyclePhase({ id: "c", kind: "INITIAL" })).toBe("INITIAL");
    expect(trainingLifecyclePhase({ id: "d", kind: "REFRESHER" })).toBe("REFRESHER");
    expect(trainingLifecyclePhase({ id: "e", kind: "ONE_OFF" })).toBe("ONE_OFF");
  });

  it("keeps event completion separate from compliance Current", () => {
    expect(completedEventStatusWithoutRequirement(true)).toBe("COMPLETED");
    expect(complianceStatusLabel("COMPLETED")).toBe("Completed");
    expect(complianceStatusLabel("OK")).toBe("Current");
  });

  it("uses required public wording", () => {
    expect(complianceStatusLabel("DUE_SOON")).toBe("Due Soon");
    expect(complianceStatusLabel("NOT_DONE")).toBe("Not completed");
  });
});
