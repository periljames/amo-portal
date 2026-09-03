import { describe, expect, it } from "vitest";

import type { QMSAuditOut } from "../../services/qmsCore";
import { auditNavigationHref } from "./auditNavigation";

function audit(partial: Partial<QMSAuditOut> = {}): QMSAuditOut {
  return {
    id: "audit-1",
    audit_ref: "QAR/AC/26/001",
    title: "Maintenance audit",
    kind: "INTERNAL",
    status: "PLANNED",
    planned_start: "2026-03-01",
    planned_end: "2026-03-02",
    lead_auditor_user_id: "user-1",
    lead_auditor_name: "Lead",
    ...partial,
  } as QMSAuditOut;
}

describe("auditNavigationHref", () => {
  it("opens the current lifecycle stage using a slugged audit reference", () => {
    expect(auditNavigationHref("safarilink", audit())).toBe(
      "/maintenance/safarilink/quality/audits/QAR-AC-26-001/prepare",
    );
  });

  it("routes incomplete setup audits to setup", () => {
    expect(
      auditNavigationHref("safarilink", audit({ lead_auditor_user_id: null })),
    ).toBe("/maintenance/safarilink/quality/audits/QAR-AC-26-001/setup");
  });
});
