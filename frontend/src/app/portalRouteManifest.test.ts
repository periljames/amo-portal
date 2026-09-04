import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortalUser } from "../services/auth";
import { userHasQmsRolePermission } from "./routeGuards";
import {
  buildPortalNavigation,
  flattenPortalNavigation,
  type PortalNavItem,
} from "./portalRouteManifest";

const storage = new Map<string, string>();
const localStorageMock: Storage = {
  get length() { return storage.size; },
  clear() { storage.clear(); },
  getItem(key: string) { return storage.get(key) ?? null; },
  key(index: number) { return Array.from(storage.keys())[index] ?? null; },
  removeItem(key: string) { storage.delete(key); },
  setItem(key: string, value: string) { storage.set(key, String(value)); },
};

beforeEach(() => {
  storage.clear();
  vi.stubGlobal("localStorage", localStorageMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function user(overrides: Partial<PortalUser> = {}): PortalUser {
  return {
    id: "user-1",
    amo_id: "amo-1",
    department_id: "department-1",
    staff_code: "ST-001",
    email: "user@example.com",
    first_name: "Quality",
    last_name: "User",
    full_name: "Quality User",
    role: "QUALITY_MANAGER",
    position_title: "Quality Manager",
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
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function depth(item: PortalNavItem): number {
  if (!item.children?.length) return 1;
  return 1 + Math.max(...item.children.map(depth));
}

describe("portal route manifest", () => {
  it("routes a Quality Officer to Quality without exposing account administration", () => {
    const officer = user({ role: "QUALITY_OFFICER", position_title: "Quality Officer" });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: officer,
      contextDepartment: "quality",
      adminModeActive: false,
    }));

    expect(items.some((item) => item.id === "department-quality")).toBe(true);
    expect(items.some((item) => item.id === "admin-users")).toBe(false);
    expect(userHasQmsRolePermission(officer, "qms.car.manage")).toBe(true);
    expect(userHasQmsRolePermission(officer, "qms.audit.manage")).toBe(false);
  });

  it("keeps Accountable Executive Quality access read-only except Authority attestation", () => {
    const accountable = user({ role: "ACCOUNTABLE_EXECUTIVE", position_title: "Accountable Executive" });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: accountable,
      contextDepartment: "quality",
      adminModeActive: false,
    }));

    expect(items.some((item) => item.id === "department-quality")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.audit.view")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.reports.attest_authority")).toBe(true);
    expect(userHasQmsRolePermission(accountable, "qms.audit.manage")).toBe(false);
  });

  it("shows only the assigned department to a normal tenant user", () => {
    const groups = buildPortalNavigation({
      amoCode: "safarilink",
      user: user(),
      contextDepartment: "quality",
      adminModeActive: false,
    });
    const items = flattenPortalNavigation(groups);

    expect(items.some((item) => item.id === "department-quality")).toBe(true);
    expect(items.some((item) => item.id === "department-planning")).toBe(false);
    expect(items.some((item) => item.adminOnly)).toBe(false);
    expect(items.every((item) => item.path.startsWith("/maintenance/safarilink"))).toBe(true);
  });

  it("does not expose administration until the backend-confirmed mode is active", () => {
    const admin = user({
      role: "AMO_ADMIN",
      is_amo_admin: true,
      position_title: "AMO Administrator",
    });
    const normalMode = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "safarilink",
      user: admin,
      contextDepartment: "quality",
      adminModeActive: false,
    }));
    const elevatedMode = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "safarilink",
      user: admin,
      contextDepartment: "quality",
      adminModeActive: true,
    }));

    expect(normalMode.some((item) => item.adminOnly)).toBe(false);
    expect(elevatedMode.some((item) => item.id === "admin-users" && item.adminOnly)).toBe(true);
    expect(elevatedMode.some((item) => item.id === "department-planning")).toBe(true);
    expect(elevatedMode.some((item) => item.id === "department-quality")).toBe(true);
  });

  it("never produces navigation deeper than three selectable levels", () => {
    const admin = user({ role: "AMO_ADMIN", is_amo_admin: true });
    const groups = buildPortalNavigation({
      amoCode: "safarilink",
      user: admin,
      contextDepartment: "quality",
      adminModeActive: true,
    });
    const maximum = Math.max(...groups.flatMap((group) => group.items.map(depth)));
    expect(maximum).toBeLessThanOrEqual(3);
  });

  it("keeps every generated route inside the current tenant URL namespace", () => {
    const admin = user({ role: "AMO_ADMIN", is_amo_admin: true });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: admin,
      contextDepartment: "quality",
      adminModeActive: true,
    }));

    expect(items.length).toBeGreaterThan(20);
    expect(items.every((item) => item.path.startsWith("/maintenance/tenant-a"))).toBe(true);
    expect(items.some((item) => item.path.includes("tenant-b"))).toBe(false);
  });

  it("publishes explicit routes for Reliability and EHM destinations", () => {
    const admin = user({ role: "AMO_ADMIN", is_amo_admin: true });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: admin,
      contextDepartment: "reliability",
      adminModeActive: true,
    }));
    const paths = new Map(items.map((item) => [item.id, item.path]));

    expect(paths.get("reliability-workbench")).toBe("/maintenance/tenant-a/reliability");
    expect(paths.get("reliability-events")).toBe("/maintenance/tenant-a/reliability/events");
    expect(paths.get("reliability-alerts")).toBe("/maintenance/tenant-a/reliability/alerts");
    expect(paths.get("reliability-fracas")).toBe("/maintenance/tenant-a/reliability/cases");
    expect(paths.get("reliability-fleet")).toBe("/maintenance/tenant-a/reliability/fleet");
    expect(paths.get("reliability-systems")).toBe("/maintenance/tenant-a/reliability/systems");
    expect(paths.get("reliability-components")).toBe("/maintenance/tenant-a/reliability/components");
    expect(paths.get("reliability-engines")).toBe("/maintenance/tenant-a/reliability/engines");
    expect(paths.get("reliability-program")).toBe("/maintenance/tenant-a/reliability/program");
    expect(paths.get("reliability-changes")).toBe("/maintenance/tenant-a/reliability/changes");
    expect(paths.get("reliability-meetings")).toBe("/maintenance/tenant-a/reliability/meetings");
    expect(paths.get("reliability-reports")).toBe("/maintenance/tenant-a/reliability/reports");
    expect(paths.get("reliability-data-quality")).toBe("/maintenance/tenant-a/reliability/data-quality");
    expect(paths.get("reliability-sources")).toBe("/maintenance/tenant-a/reliability/sources");
    expect(paths.get("reliability-ingestion")).toBe("/maintenance/tenant-a/reliability/ingestion");
    expect(paths.get("reliability-calculations")).toBe("/maintenance/tenant-a/reliability/calculations");
    expect(paths.get("reliability-compliance")).toBe("/maintenance/tenant-a/reliability/compliance");
    expect(paths.get("reliability-handoffs")).toBe("/maintenance/tenant-a/reliability/handoffs");
    expect(paths.get("reliability-authority")).toBe("/maintenance/tenant-a/reliability/authority");
    expect(paths.get("reliability-ai")).toBe("/maintenance/tenant-a/reliability/ai");
    expect(paths.get("ehm-dashboard")).toBe("/maintenance/tenant-a/ehm/dashboard");
    expect(paths.get("ehm-trends")).toBe("/maintenance/tenant-a/ehm/trends");
    expect(paths.get("ehm-uploads")).toBe("/maintenance/tenant-a/ehm/uploads");
  });

  it("provides real home, operations and configuration routes for simple departments", () => {
    const admin = user({ role: "AMO_ADMIN", is_amo_admin: true });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: admin,
      contextDepartment: "safety",
      adminModeActive: true,
    }));
    const paths = new Set(items.map((item) => item.path));

    for (const department of ["safety", "stores", "workshops"]) {
      expect(paths.has(`/maintenance/tenant-a/${department}`)).toBe(true);
      expect(paths.has(`/maintenance/tenant-a/${department}/operations`)).toBe(true);
      expect(paths.has(`/maintenance/tenant-a/${department}/settings`)).toBe(true);
    }
  });

  it("exposes all eleven Training OS sections to a Training department user without QMS elevation", () => {
    const trainingUser = user({ role: "TECHNICIAN", position_title: "Training Officer" });
    const items = flattenPortalNavigation(buildPortalNavigation({
      amoCode: "tenant-a",
      user: trainingUser,
      contextDepartment: "training",
      adminModeActive: false,
    }));
    const trainingIds = items.filter((item) => item.id.startsWith("training-")).map((item) => item.id);
    expect(trainingIds).toEqual(expect.arrayContaining([
      "training-control-room", "training-people", "training-requirements", "training-plan",
      "training-sessions", "training-assessments", "training-authorizations", "training-certificates",
      "training-budget", "training-reports", "training-settings",
    ]));
    expect(items.some((item) => item.id === "department-quality")).toBe(false);
  });

  it("keeps the Training OS hidden from an ordinary employee while preserving My Training", () => {
    const ordinary = user({ role: "TECHNICIAN", position_title: "Technician" });
    const items = flattenPortalNavigation(buildPortalNavigation({ amoCode: "tenant-a", user: ordinary, contextDepartment: "maintenance", adminModeActive: false }));
    expect(items.some((item) => item.id === "training-competence")).toBe(false);
    expect(items.some((item) => item.id === "my-training")).toBe(true);
  });
});
