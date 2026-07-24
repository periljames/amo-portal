/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const unifiedPlannerSource = readSource("./components/UnifiedRosterPlanner.tsx");
const contextualHelpSource = readSource("../../components/UI/ContextualHelp.tsx");
const contextualGuidanceSource = readSource("../../services/contextualGuidance.ts");
const prerequisiteSource = readSource("../../components/UI/PrerequisiteDialog.tsx");
const operatingStructureSource = readSource("../AdminOperatingStructurePage.tsx");
const adminAssetsRouteSource = readSource("../AdminAmoAssetsPage.tsx");
const foundationServicesSource = readSource("../../../../backend/amodb/apps/foundations/services.py");
const foundationRouterSource = readSource("../../../../backend/amodb/apps/foundations/router.py");
const permissionSource = readSource("../../../../backend/amodb/apps/workforce/permissions.py");

describe("guided rostering setup", () => {
  it("removes the permanent read-only commitment board", () => {
    expect(unifiedPlannerSource).not.toContain("RosterCommitmentBoard");
    expect(unifiedPlannerSource).toContain("PlannerCommitmentHelp");
    expect(unifiedPlannerSource).toContain('HELP_TOPIC = "rostering-source-commitments"');
    expect(unifiedPlannerSource).toContain("Use the help icon whenever this explanation is needed again");
  });

  it("keeps planner guidance lightweight instead of importing the broad shared component", () => {
    expect(unifiedPlannerSource).not.toContain('import { ContextualHelp }');
    expect(unifiedPlannerSource).toContain("guidanceAcknowledged");
    expect(unifiedPlannerSource).toContain("acknowledgeGuidance");
  });

  it("persists help by tenant, user, topic and version with an offline fallback", () => {
    expect(contextualGuidanceSource).toContain("amo_portal_help_seen:");
    expect(contextualGuidanceSource).toContain("tenantId");
    expect(contextualGuidanceSource).toContain("userId");
    expect(contextualGuidanceSource).toContain("getPlannerPreferencesLite");
    expect(contextualGuidanceSource).toContain("updatePlannerPreferencesLite");
    expect(contextualHelpSource).toContain("acknowledgeGuidance");
  });

  it("does not acknowledge guidance merely because it was closed", () => {
    expect(contextualHelpSource).toContain('onClick={() => setOpen(false)}');
    expect(contextualHelpSource).toContain("Close help without acknowledging");
    expect(contextualHelpSource).toContain("onClick={() => void acknowledge()}");
    expect(unifiedPlannerSource).toContain("Close help without acknowledging");
  });

  it("provides blocking direct prerequisite actions instead of a dead empty state", () => {
    expect(unifiedPlannerSource).toContain("Open operating structure");
    expect(unifiedPlannerSource).toContain("Create shifts");
    expect(unifiedPlannerSource).toContain("Create period");
    expect(unifiedPlannerSource).toContain("returnTo");
    expect(unifiedPlannerSource).toContain("allowReadOnly={false}");
    expect(prerequisiteSource).toContain("allowReadOnly");
  });

  it("owns canonical bases in the admin operating structure workspace", () => {
    expect(adminAssetsRouteSource).toContain('section === "operating-structure"');
    expect(operatingStructureSource).toContain('organisation.bases.manage');
    expect(operatingStructureSource).toContain('workforce.deployments.manage');
    expect(operatingStructureSource).toContain("Personnel base deployments");
    expect(operatingStructureSource).toContain("getBaseStationImpact");
    expect(operatingStructureSource).toContain("cancelUserBaseAssignment");
  });

  it("uses scoped capability checks rather than granting Quality movement authority", () => {
    expect(permissionSource).toContain('ORGANISATION_BASES_MANAGE = "organisation.bases.manage"');
    expect(permissionSource).toContain('WORKFORCE_DEPLOYMENTS_MANAGE = "workforce.deployments.manage"');
    expect(foundationRouterSource).toContain("PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE");
    expect(permissionSource).toContain("QUALITY = EMPLOYEE");
  });

  it("resolves temporary deployments ahead of the home base", () => {
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.TEMPORARY: 50");
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.RELIEF: 40");
    expect(foundationServicesSource).toContain("models.BaseAssignmentKind.HOME_BASE: 10");
    expect(foundationServicesSource).toContain("Another temporary, relief or training deployment");
  });

  it("blocks unsafe base deactivation and stale writes", () => {
    expect(foundationServicesSource).toContain("base_station_dependency_impact");
    expect(foundationRouterSource).toContain("BASE_DEACTIVATION_BLOCKED");
    expect(foundationRouterSource).toContain("BASE_STATION_REVISION_CONFLICT");
    expect(operatingStructureSource).toContain("expected_updated_at");
  });
});
