import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const orchestrator = readFileSync(new URL("./DocumentControlRecordActions.tsx", import.meta.url), "utf-8");
const guardedLifecycle = readFileSync(new URL("./DocumentControlLifecycleActionsGuarded.tsx", import.meta.url), "utf-8");
const primaryActions = readFileSync(new URL("./DocumentControlPrimaryActions.tsx", import.meta.url), "utf-8");
const changeActions = readFileSync(new URL("./DocumentControlChangeRequestActions.tsx", import.meta.url), "utf-8");
const applicabilityActions = readFileSync(new URL("./DocumentControlApplicabilityActions.tsx", import.meta.url), "utf-8");
const integrationActions = readFileSync(new URL("./DocumentControlIntegrationActions.tsx", import.meta.url), "utf-8");
const retentionActions = readFileSync(new URL("./DocumentControlRetentionActions.tsx", import.meta.url), "utf-8");

describe("DMS production form contract", () => {
  it("never falls back to the monolithic legacy lifecycle form", () => {
    expect(guardedLifecycle).not.toContain('from "./DocumentControlLifecycleActions"');
    expect(guardedLifecycle).not.toContain("<DocumentControlLifecycleActions {...props}");
    expect(guardedLifecycle).toContain("Legacy raw-ID forms are intentionally not reachable");
  });

  it("uses governed evidence selection for the active publication action", () => {
    expect(primaryActions).toContain("DocumentEvidencePicker");
    expect(primaryActions).toContain('purpose="PUBLICATION_RELEASE"');
    expect(primaryActions).not.toContain("Retained evidence asset IDs");
    expect(primaryActions).not.toContain("One evidence asset ID per line");
    expect(primaryActions).not.toContain("evidenceFrom(");
  });

  it("mounts dedicated production forms for operational jobs", () => {
    for (const component of [
      "DocumentControlChangeRequestActions",
      "DocumentControlDistributionActions",
      "DocumentControlExternalSourceActions",
      "DocumentControlApplicabilityActions",
      "DocumentControlIntegrationActions",
      "DocumentControlRetentionActions",
      "DocumentEvidencePackAction",
    ]) {
      expect(orchestrator).toContain(component);
    }
  });

  it("resolves change, applicability, integration and retention targets instead of asking for database IDs", () => {
    expect(changeActions).toContain("source catalogue");
    expect(changeActions).not.toContain("Source entity ID</span><input");
    expect(applicabilityActions).toContain("GLOBAL");
    expect(applicabilityActions).not.toContain("Target ID</span><input");
    expect(integrationActions).toContain("Search live records");
    expect(integrationActions).not.toContain("Canonical entity ID</span><input");
    expect(retentionActions).toContain("Select controlled source");
    expect(retentionActions).not.toContain("Source ID</span><input");
  });
});
