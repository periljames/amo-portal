/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const plannerSource = readSource("./components/RosterPlannerV2.tsx");
const setupSource = readSource("./components/UnifiedRosterSettings.tsx");
const commitmentServiceSource = readSource("../../services/rosterCommitments.ts");

describe("rostering cross-module commitment integration", () => {
  it("loads tenant commitments for the same week displayed by the planner", () => {
    expect(plannerSource).toContain("listRosterCommitments({ from: data.week.from, to: data.week.to })");
    expect(plannerSource).toContain('queryKey: ["rostering", "planner", "commitments", data.week.from, data.week.to]');
    expect(commitmentServiceSource).toContain("/rostering/commitments?");
  });

  it("renders source-owned training leave and Quality work inside person-day cells", () => {
    expect(plannerSource).toContain("CommitmentCard");
    expect(plannerSource).toContain("commitmentsByCell.get(key)");
    expect(plannerSource).toContain('sourceModule === "TRAINING"');
    expect(plannerSource).toContain('sourceModule === "QUALITY"');
  });

  it("prevents planner duty creation and drag moves onto blocking source commitments", () => {
    expect(plannerSource).toContain("blockingCommitmentsFor");
    expect(plannerSource).toContain("preventBlockedAssignment(person, day)");
    expect(plannerSource).toContain("editable && !blocking");
    expect(plannerSource).toContain("Resolve or reschedule it in");
  });

  it("uses the paginated canonical tenant people contract for setup", () => {
    expect(setupSource).toContain("listRosterPeoplePage");
    expect(setupSource).toContain("page_size: 250");
    expect(setupSource).toContain("active_only: true");
    expect(setupSource).toContain("roster_eligible_only: false");
  });
});
