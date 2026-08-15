/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const setupSource = readSource("./components/RosteringSetupWorkspace.tsx");
const studioSource = readSource("./components/WorkPatternStudio.tsx");
const workforceSource = readSource("./components/WorkforceOperationsWorkspace.tsx");
const shellSource = readSource("./components/RosterShell.tsx");
const manifestSource = readSource("../../app/portalRouteManifest.ts");

describe("simplified rostering workflow", () => {
  it("uses one setup workspace with four plain-language sections", () => {
    expect(pagesSource).toContain('import("./components/RosteringSetupWorkspace")');
    expect(pagesSource).not.toContain("RosteringSetupWorkspaceWithCodeRegistry");
    expect(setupSource).toContain('{ id: "start", label: "Get started" }');
    expect(setupSource).toContain('{ id: "patterns", label: "Shifts & patterns" }');
    expect(setupSource).toContain('{ id: "control", label: "Coverage & approvals" }');
    expect(setupSource).toContain('{ id: "advanced", label: "Advanced" }');
    expect(setupSource).toContain('value === "shifts" || value === "patterns"');
  });

  it("offers compact presets and a spreadsheet-style rotation matrix", () => {
    expect(studioSource).toContain('title: "5D · 2O"');
    expect(studioSource).toContain('title: "4D · 4O"');
    expect(studioSource).toContain('title: "2D · 2N · 4O"');
    expect(studioSource).toContain("rs-rotation-matrix");
    expect(studioSource).toContain("rs-sequence-grid");
    expect(studioSource).not.toContain("rs-wizard-steps");
  });

  it("keeps employee assignment CRUD in one canonical Workforce surface", () => {
    expect(studioSource).not.toContain("listWorkPatternAssignments");
    expect(setupSource).not.toContain("updateWorkPatternAssignment");
    expect(workforceSource).toContain("listWorkPatternAssignments");
    expect(workforceSource).toContain("assignWorkforceHrPattern");
    expect(workforceSource).toContain("updateWorkPatternAssignment");
    expect(workforceSource).toContain("deleteWorkPatternAssignment");
    expect(workforceSource).toContain("Audited reason");
  });

  it("reduces duplicate navigation while preserving legacy routes", () => {
    expect(shellSource).not.toContain('label: "Reports"');
    expect(shellSource).not.toContain('label: "Compliance"');
    expect(manifestSource).not.toContain('feature("rostering-training"');
    expect(manifestSource).not.toContain('feature("rostering-reports"');
    expect(pagesSource).toContain("export function RosterReportsPage");
    expect(pagesSource).toContain("export function TrainingImpactPage");
  });
});
