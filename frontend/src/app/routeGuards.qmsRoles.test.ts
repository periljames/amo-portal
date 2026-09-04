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
  it("gives the Quality Officer execution and CAR follow-up without governance or closure", () => {
    const officer = user("QUALITY_OFFICER");
    expect(userHasQmsRolePermission(officer, "qms.audit.execute")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.audit.manage")).toBe(false);
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
  });

  it("keeps manager, auditor, and administrator boundaries explicit", () => {
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.audit.notice.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("QUALITY_MANAGER"), "qms.reports.attest_authority")).toBe(false);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.audit.execute")).toBe(true);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.audit.manage")).toBe(false);
    expect(userHasQmsRolePermission(user("AUDITOR"), "qms.car.manage")).toBe(false);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.reports.attest_authority")).toBe(false);
    expect(userHasQmsRolePermission(user("AMO_ADMIN", { is_amo_admin: true }), "qms.audit.notice.manage")).toBe(true);
    expect(userHasQmsRolePermission(user("VIEW_ONLY"), "qms.reports.attest_authority")).toBe(false);
  });
});
