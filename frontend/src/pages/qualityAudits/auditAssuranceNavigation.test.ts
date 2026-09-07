import { describe, expect, it } from "vitest";

import {
  AUDIT_ASSURANCE_DESTINATIONS,
  auditAssuranceHref,
  isAuditAssuranceDestinationActive,
} from "./auditAssuranceNavigation";
import { classifyQmsPath } from "../qms/routes/qmsRouteRegistry";

describe("Audit Assurance navigation registry", () => {
  it("exposes every canonical top-level audit destination through a known route", () => {
    const expected = [
      "audits/dashboard",
      "audits/program",
      "audits/plan",
      "audits/scopes",
      "audits/workspace",
      "audits/checklists",
      "audits/register",
      "reports/car-performance",
      "suppliers/approved-list",
      "equipment-calibration/register",
      "external-interface/regulator-findings",
      "evidence-vault/search",
      "audits/bin",
    ];

    expect(AUDIT_ASSURANCE_DESTINATIONS.map((item) => item.relativePath)).toEqual(expected);
    for (const destination of AUDIT_ASSURANCE_DESTINATIONS) {
      const path = auditAssuranceHref("safarilink", destination);
      expect(classifyQmsPath(path), path).toMatchObject({ kind: "known" });
    }
  });

  it("keeps compatibility and record-detail routes on their canonical rail owner", () => {
    const activeId = (path: string) => AUDIT_ASSURANCE_DESTINATIONS.find((item) => (
      isAuditAssuranceDestinationActive(item, path, "safarilink")
    ))?.id;

    expect(activeId("/maintenance/safarilink/quality/audits/schedule")).toBe("planner");
    expect(activeId("/maintenance/safarilink/quality/audits/schedules/SCH-26-1")).toBe("planner");
    expect(activeId("/maintenance/safarilink/quality/audits/templates")).toBe("checklists");
    expect(activeId("/maintenance/safarilink/quality/audits/findings-actions")).toBe("findings-actions");
    expect(activeId("/maintenance/safarilink/quality/audits/QAR-MO-26-001/prepare")).toBe("audits");
    expect(activeId("/maintenance/safarilink/quality/evidence-vault/ev-demo")).toBe("evidence");
  });

  it("assigns each canonical route to exactly one visible destination", () => {
    expect(new Set(AUDIT_ASSURANCE_DESTINATIONS.map((item) => item.id)).size).toBe(
      AUDIT_ASSURANCE_DESTINATIONS.length,
    );
    for (const destination of AUDIT_ASSURANCE_DESTINATIONS) {
      const path = auditAssuranceHref("safarilink", destination);
      const active = AUDIT_ASSURANCE_DESTINATIONS.filter((candidate) => (
        isAuditAssuranceDestinationActive(candidate, path, "safarilink")
      ));
      expect(active.map((item) => item.id), path).toEqual([destination.id]);
    }
  });

  it("encodes tenant codes when it builds navigation links", () => {
    expect(auditAssuranceHref("Safari Link/AMO", AUDIT_ASSURANCE_DESTINATIONS[0])).toBe(
      "/maintenance/Safari%20Link%2FAMO/quality/audits/dashboard",
    );
  });
});
