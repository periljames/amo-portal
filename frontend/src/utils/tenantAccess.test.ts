import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { PortalUser } from "../services/auth";
import { getAssignedDepartment } from "./departmentAccess";
import { canPerformAction, canViewFeature, getFirstAccessibleModuleRoute } from "./roleAccess";
import { isTenantAdmin, userBelongsToTenant } from "./tenantAccess";
import { userHasQmsRolePermission, userHasTrainingRolePermission } from "../app/routeGuards";
import { resolvePostLoginReturnTarget } from "../app/loginRedirect";
import { buildPortalNavigation, flattenPortalNavigation } from "../app/portalRouteManifest";

const state = vi.hoisted(() => ({ user: null as PortalUser | null, active: false }));
vi.mock("../services/auth", async (original) => ({
  ...await original<typeof import("../services/auth")>(),
  getCachedUser: () => state.user,
  getContext: () => ({ amoCode: "tenant-a", amoSlug: "tenant-a", department: "production" }),
}));
vi.mock("../services/adminProfileMode", () => ({
  readCachedAdminProfileState: (code: string) => ({ active: code === "tenant-a" && state.active }),
}));

function user(overrides: Partial<PortalUser> = {}): PortalUser {
  return {
    id: "one", amo_id: "id-a", amo_code: "AMO-A", amo_slug: "tenant-a",
    department_id: "maintenance-a", department_code: "maintenance", role: "TECHNICIAN",
    is_active: true, is_amo_admin: false, is_superuser: false,
    module_access: { planning: "view", production: "view", maintenance: "manage", rostering: "view" },
    ...overrides,
  } as PortalUser;
}

beforeEach(() => { state.user = user(); state.active = false; vi.stubGlobal("window", {}); });
afterEach(() => vi.unstubAllGlobals());

describe("tenant administrator and home routing", () => {
  it("keeps the assigned home ahead of stale context and other accessible modules", () => {
    expect(getAssignedDepartment(state.user, "production")).toBe("maintenance");
    expect(getFirstAccessibleModuleRoute("wrong-tenant", state.user, "planning")).toBe("/maintenance/tenant-a/maintenance");
    const home = flattenPortalNavigation(buildPortalNavigation({ amoCode: "tenant-a", user: state.user, contextDepartment: "production" })).find((item) => item.id === "home");
    expect(home?.path).toBe("/maintenance/tenant-a/maintenance");
  });

  it("does not send a user without an assignment into another department", () => {
    state.user = user({ department_id: null, department_code: null });
    expect(getAssignedDepartment(state.user, "production")).toBeNull();
    expect(getFirstAccessibleModuleRoute("tenant-a", state.user, "production")).toBe("/maintenance/tenant-a/profile");
  });

  it("lets an enrolled employee open their home and their own roster", () => {
    state.user = user({ role: "USER", module_access: { rostering: "view" } });
    expect(getFirstAccessibleModuleRoute("tenant-a", state.user)).toBe("/maintenance/tenant-a/maintenance");
    expect(canViewFeature(state.user, "rostering.my-roster")).toBe(true);
    expect(canViewFeature(state.user, "planning.dashboard")).toBe(false);
  });

  it.each([false, true])("gives standing and active delegated admins the same tenant tasks (delegated=%s)", (delegated) => {
    state.user = user({ is_amo_admin: !delegated, module_access: {} });
    state.active = delegated;
    expect(isTenantAdmin(state.user)).toBe(true);
    expect(canPerformAction(state.user, "production.perform-review")).toBe(true);
    expect(userHasQmsRolePermission(state.user, "qms.audit.programme.approve")).toBe(true);
    expect(userHasTrainingRolePermission(state.user, "training.authorization.issue")).toBe(true);
    expect(state.user.role).toBe("TECHNICIAN");
    state.active = false;
    if (delegated) expect(isTenantAdmin(state.user)).toBe(false);
  });

  it("never shares delegated elevation with a different user", () => {
    state.active = true;
    expect(isTenantAdmin(user({ id: "two" }))).toBe(false);
    expect(isTenantAdmin(user({ amo_id: null, is_amo_admin: true }))).toBe(false);
    expect(isTenantAdmin(user({ is_superuser: true, is_amo_admin: true }))).toBe(false);
  });

  it("rejects return URLs for another tenant or the platform and traversal aliases", () => {
    expect(userBelongsToTenant(state.user, "AMO-A")).toBe(true);
    expect(userBelongsToTenant(state.user, "tenant-b")).toBe(false);
    for (const path of ["/maintenance/tenant-b/quality", "/platform/control", "/maintenance/tenant-a/%2e%2e/tenant-b/quality", "//example.test/"]) {
      expect(resolvePostLoginReturnTarget(path, false, state.user, "tenant-a")).toBeNull();
    }
    expect(resolvePostLoginReturnTarget("/maintenance/tenant-a/maintenance", false, state.user, "tenant-a")).toBe("/maintenance/tenant-a/maintenance");
    expect(getFirstAccessibleModuleRoute("tenant-a", user({ is_superuser: true }))).toBe("/platform/control");
  });
});
