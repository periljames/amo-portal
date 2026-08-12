import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf-8");
}

describe("controlled rostering frontend contract", () => {
  it("exposes exact version controlled PDF and XLSX downloads", () => {
    const service = source("../../services/rosteringControl.ts");
    const reports = source("./components/RosterReports.tsx");
    expect(service).toContain("/rostering/versions/${encodeURIComponent(versionId)}/controlled-roster.${format}");
    expect(reports).toContain("Controlled PDF");
    expect(reports).toContain("Controlled XLSX");
    expect(reports).toContain("immutable publication snapshot");
  });

  it("exposes tenant document-control settings and draft-watermark guidance", () => {
    const service = source("../../services/rosteringControl.ts");
    const panel = source("./components/ControlledRosterSettingsPanel.tsx");
    expect(service).toContain("/rostering/controlled-document/settings");
    expect(panel).toContain("Form number");
    expect(panel).toContain("Revision date");
    expect(panel).toContain("DRAFT — NOT CONTROLLED");
  });

  it("keeps roster semantics, verification and legacy aliases explicit", () => {
    const service = source("../../services/rosteringCodeRegistry.ts");
    const panel = source("./components/RosterCodeRegistryPanel.tsx");
    expect(service).toContain("RosterCodeVerificationStatus");
    expect(service).toContain("RosterDutySemantic");
    expect(service).toContain("/aliases");
    expect(panel).toContain("Unresolved or review-required codes block publication");
    expect(panel).toContain("Aircraft such as 5Y-SLC are allocated to the duty assignment");
  });

  it("provides calendar rotate and revoke controls without removing legacy self-service compatibility", () => {
    const service = source("../../services/rosteringControl.ts");
    const panel = source("./components/CalendarSubscriptionSecurityPanel.tsx");
    const pages = source("./WorkforceRosteringPagesV2.tsx");
    expect(service).toContain("/rostering/calendar/subscription/rotate");
    expect(service).toContain('method: "DELETE"');
    expect(panel).toContain("Rotate link");
    expect(panel).toContain("Revoke link");
    expect(pages).toContain("LazyCalendarSubscriptionSecurityPanel");
  });
});
