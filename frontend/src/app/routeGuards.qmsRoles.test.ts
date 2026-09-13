import { describe, expect, it } from "vitest";

import type { AccountRole, PortalUser } from "../services/auth";
import { userHasQmsRolePermission } from "./routeGuards";

function user(role: AccountRole, overrides: Partial<PortalUser> = {}): PortalUser {
  return {
    id: `${role.toLowerCase()}-1`,
    amo_id: "amo-1",
    department_id: "quality-1",
    staff_code: "QMS-001",
    email: `${role.toLowerCase()}@example.test`,
    first_name: "Quality",
    last_name: "User",
    full_name: "Quality User",
    role,
    position_title: role.replaceAll("_", " "),
    phone: null,
    regulatory_authority: null,
    licence_number: null,
    licence_state_or_country: null,
    licence_expires_on: null,
    is_active: true,
    is_superuser: false,
    is_amo_admin: false,
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2026-09-03T00:00:00Z",
    updated_at: "2026-09-03T00:00:00Z",
    ...overrides,
  };
}

describe("QMS role permission boundaries", () => {
  it("lets the Quality Officer prepare and submit without either approval decision", () => {
    const officer = user("QUALITY_OFFICER");
    expect(userHasQmsRolePermission(officer, "qms.audit.execute")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.audit.manage")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.audit.programme.quality_review")).toBe(false);
    expect(userHasQmsRolePermission(officer, "qms.audit.programme.approve")).toBe(false);
    expect(userHasQmsRolePermission(officer, "qms.audit.notice.manage")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.car.manage")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.car.close")).toBe(false);
    expect(userHasQmsRolePermission(officer, "qms.reports.attest_authority")).toBe(false);
  });

  it("gives only the Accountable Executive the Authority attestation capability", () => {
    const accountable = user("ACCOUNTABLE_EXECUTIVE");
    expect(userHasQmsRolePermission(accountable, "qms.audit.view")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.external.view")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.reports.attest_authority")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.reports.export")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.audit.manage")).toBe(false);
    expect(userHasQmsRolePermission(accountable, "qms.audit.programme.quality_review")).toBe(false);
    expect(userHasQmsRolePermission(accountable, "qms.audit.programme.approve")).toBe(true);
  });

  it("keeps manager, auditor, and administrator boundaries explicit", () => {
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.programme.quality_review")).toBe(true);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.programme.approve")).toBe(false);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.notice.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.reports.attest_authority")).toBe(false);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.audit.execute")).toBe(true);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.audit.manage")).toBe(false);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.car.manage")).toBe(false);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.reports.attest_authority")).toBe(true);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.audit.programme.quality_review")).toBe(true);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.audit.programme.approve")).toBe(true);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.audit.notice.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("VIEW_ONLY"), "qms.reports.attest_authority")).toBe(false);
  });

  it("maps Quality Support and Document Control to their narrow read surfaces", () => {
    const support = user("QUALITY_SUPPORT_OFFICER");
    expect(userHasQmsRolePermission(support, "qms.dashboard.view")).toBe(true);
    expect(userHasQmsRolePermission(support, "qms.audit.view")).toBe(true);
    expect(userHasQmsRolePermission(support, "qms.reports.view")).toBe(true);
    expect(userHasQmsRolePermission(support, "qms.audit.execute")).toBe(false);
    expect(userHasQmsRolePermission(support, "qms.finding.create")).toBe(false);

    const documentControl = user("DOCUMENT_CONTROL_OFFICER");
    expect(userHasQmsRolePermission(documentControl, "qms.dashboard.view")).toBe(true);
    expect(userHasQmsRolePermission(documentControl, "qms.document.view")).toBe(true);
    expect(userHasQmsRolePermission(documentControl, "qms.evidence.download")).toBe(true);
    expect(userHasQmsRolePermission(documentControl, "qms.audit.view")).toBe(false);
    expect(userHasQmsRolePermission(documentControl, "qms.document.approve")).toBe(false);
  });

  it("uses writer-side capability codes as the authoritative modern profile boundary", () => {
    const narrowedOfficer = user("QUALITY_OFFICER", {
      module_access: { quality: "manage" },
      capability_codes: ["qms.audit.view"],
    });
    expect(userHasQmsRolePermission(narrowedOfficer, "qms.audit.view")).toBe(true);
    expect(userHasQmsRolePermission(narrowedOfficer, "qms.audit.manage")).toBe(false);
    expect(userHasQmsRolePermission(narrowedOfficer, "qms.car.manage")).toBe(false);

    const qualityReadProfile = user("SAFETY_OFFICER", {
      module_access: { quality: "view" },
      capability_codes: ["qms.dashboard.view", "qms.settings.view"],
    });
    expect(userHasQmsRolePermission(qualityReadProfile, "qms.settings.view")).toBe(true);
    expect(userHasQmsRolePermission(qualityReadProfile, "qms.audit.execute")).toBe(false);
  });

  it("keeps the mandatory Auditor/Inspector Control Centre reads during profile reconciliation", () => {
    for (const role of ["AUDITOR", "QUALITY_INSPECTOR"] as const) {
      const actor = user(role, {
        module_access: { quality: "manage" },
        capability_codes: ["qms.audit.view", "qms.audit.execute"],
      });
      expect(userHasQmsRolePermission(actor, "qms.management_review.view")).toBe(true);
      expect(userHasQmsRolePermission(actor, "qms.supplier.view")).toBe(true);
      expect(userHasQmsRolePermission(actor, "qms.training.view")).toBe(true);
      expect(userHasQmsRolePermission(actor, "qms.audit.manage")).toBe(false);
    }
  });

  it("never lets a module grant manufacture reserved executive or manager decisions", () => {
    const customAuditor = user("AUDITOR", {
      module_access: { quality: "manage" },
      capability_codes: [
        "qms.reports.attest_authority",
        "qms.audit.programme.approve",
        "qms.audit.programme.quality_review",
      ],
    });
    expect(userHasQmsRolePermission(customAuditor, "qms.reports.attest_authority")).toBe(false);
    expect(userHasQmsRolePermission(customAuditor, "qms.audit.programme.approve")).toBe(false);
    expect(userHasQmsRolePermission(customAuditor, "qms.audit.programme.quality_review")).toBe(false);
  });
});
