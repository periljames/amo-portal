/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const unifiedPlannerSource = readSource("./components/UnifiedRosterPlanner.tsx");
const contextualHelpSource = readSource("../../components/UI/ContextualHelp.tsx");
const prerequisiteSource = readSource("../../components/UI/PrerequisiteDialog.tsx");
const operatingStructureSource = readSource("../AdminOperatingStructurePage.tsx");
const adminAssetsRouteSource = readSource("../AdminAmoAssetsPage.tsx");
const foundationServicesSource = readSource("../../../backend/amodb/apps/foundations/services.py");

describe("guided rostering setup", () => {
  it("removes the permanent read-only commitment board", () => {
    expect(unifiedPlannerSource).not.toContain("RosterCommitmentBoard");
    expect(unifiedPlannerSource).toContain("ContextualHelp");
    expect(unifiedPlannerSource).toContain('topic="rostering-source-commitments"');
    expect(unifiedPlannerSource).toContain("Use the help icon whenever this explanation is needed again");
  });

  it("remembers help by tenant, user, topic and version", () => {
    expect(contextualHelpSource).toContain("amo_portal_help_seen:");
    expect(contextualHelpSource).toContain("tenantId");
    expect(contextualHelpSource).toContain("userId");
    expect(contextualHelpSource).toContain("topic");
    expect(contextualHelpSource).toContain("version");
  });

  it("provides direct prerequisite actions instead of a dead empty state", () => {
    expect(unifiedPlannerSource).toContain("Open operating structure");
    expect(unifiedPlannerSource).toContain("Create shifts");
    expect(unifiedPlannerSource).toContain("Create period");
    expect(unifiedPlannerSource).toContain("PrerequisiteDialog");
    expect(prerequisiteSource).toContain("Setup required");
  });

  it("owns canonical bases in the admin operating structure workspace", () => {
    expect(adminAssetsRouteSource).toContain('section === "operating-structure"');
    expect(operatingStructureSource).toContain("canManageBaseMaster");
    expect(operatingStructureSource).toContain("Personnel base deployments");
    expect(operatingStructureSource).toContain("createUserBaseAssignment");
  });

  it("resolves temporary deployments ahead of the home base", () => {
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.TEMPORARY: 50");
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.RELIEF: 40");
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.HOME_BASE: 10");
    expect(foundationServicesSource).toContain("Another temporary, relief or training deployment");
  });
});
