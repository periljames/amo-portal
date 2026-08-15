/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const plannerSource = readSource("./components/RosterPlannerV2.tsx");
const setupSource = readSource("./components/RosteringSetupWorkspace.tsx");
const commitmentServiceSource = readSource("../../services/rosterCommitments.ts");

describe("rostering cross-module commitment integration", () => {
  it("loads tenant commitments for the full month displayed by the planner", () => {
    expect(plannerSource).toContain("listRosterCommitments({ from: data.month.from, to: data.month.to })");
    expect(plannerSource).toContain('queryKey: ["rostering", "planner", "commitments", data.month.from, data.month.to]');
    expect(commitmentServiceSource).toContain("/rostering/commitments?");
  });

  it("renders source-owned training leave and Quality work inside person-day cells", () => {
    expect(plannerSource).toContain("CommitmentCard");
    expect(plannerSource).toContain("commitmentsByCell.get(key)");
    expect(plannerSource).toContain('sourceModule === "TRAINING"');
    expect(plannerSource).toContain('sourceModule === "QUALITY"');
  });

  it("prevents planner duty creation and drag moves onto blocking source commitments", () => {
    expect(plannerSource).toContain("const sourceConflict");
    expect(plannerSource).toContain("commitment.blocking");
    expect(plannerSource).toContain("preventBlockedAssignment(person, dutyWindow.starts_at, dutyWindow.ends_at)");
    expect(plannerSource).toContain("editable && !blocking");
    expect(plannerSource).toContain("Resolve or reschedule it in");
  });

  it("defers canonical tenant people data to the coverage and governance controls", () => {
    expect(setupSource).toContain("listAllRosterPeople");
    expect(setupSource).toContain('enabled: section === "control"');
    expect(setupSource).toContain("page_size: 250");
    expect(setupSource).toContain("active_only: true");
    expect(setupSource).toContain("roster_eligible_only: false");
    expect(setupSource).toContain('controlView === "governance"');
  });

  it("uses one draggable personnel column across every date in the month", () => {
    expect(plannerSource).toContain('className="wr-roster-grid wr-roster-grid--month"');
    expect(plannerSource).toContain("data.month.days.map");
    expect(plannerSource).toContain("<PersonCard person={person} />");
    expect(plannerSource).not.toContain('className="wr-people-panel"');
  });
});
