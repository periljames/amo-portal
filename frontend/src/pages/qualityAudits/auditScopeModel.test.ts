import { describe, expect, it } from "vitest";

import type { PortalUser } from "../../services/auth";
import {
  auditScopeValidationError,
  canManageAuditScopes,
  emptyAuditScopeForm,
} from "./auditScopeModel";

function user(role: PortalUser["role"], overrides: Partial<PortalUser> = {}): PortalUser {
  return {
    id: "user-1",
    email: "quality@example.test",
    role,
    amo_id: "amo-1",
    is_active: true,
    is_superuser: false,
    is_amo_admin: false,
    ...overrides,
  } as PortalUser;
}

describe("audit scope governance", () => {
  it("matches the backend scope-administrator boundary", () => {
    expect(canManageAuditScopes(user("QUALITY_MANAGER"))).toBe(true);
    expect(canManageAuditScopes(user("AMO_ADMIN", { is_amo_admin: true }))).toBe(true);
    expect(canManageAuditScopes(user("QUALITY_OFFICER"))).toBe(false);
    expect(canManageAuditScopes(user("AUDITOR"))).toBe(false);
    expect(canManageAuditScopes(user("SUPERUSER", { is_superuser: true, amo_id: null }))).toBe(false);
  });

  it("validates the same code and sort-order bounds as the API schema", () => {
    const valid = { ...emptyAuditScopeForm(), code: "AC", name: "Aircraft audit" };
    expect(auditScopeValidationError(valid)).toBeNull();
    expect(auditScopeValidationError({ ...valid, code: "A" })).toContain("2–16");
    expect(auditScopeValidationError({ ...valid, code: "A-C" })).toContain("2–16");
    expect(auditScopeValidationError({ ...valid, sortOrder: "10000" })).toContain("0 to 9999");
  });
});
