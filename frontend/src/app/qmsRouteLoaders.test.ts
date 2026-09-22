import { describe, expect, it } from "vitest";
import { qmsRouteLoaderKey } from "./qmsRouteLoaders";
import { QMS_ROUTE_REGISTRY, qmsModulePath } from "../pages/qms/routes/qmsRouteRegistry";

describe("QMS navigation preload coverage", () => {
  it("provides a Quality loader for every registered module", () => {
    for (const module of QMS_ROUTE_REGISTRY) {
      expect(qmsRouteLoaderKey(qmsModulePath("tenant", module.id, module.defaultView))).not.toBeNull();
    }
  });
  it.each([
    ["/maintenance/tenant/quality", "overview"],
    ["/maintenance/tenant/quality?workspace=people", "people"],
    ["/maintenance/tenant/quality?workspace=missions&tab=active", "missions"],
    ["/maintenance/tenant/quality?workspace=intelligence", "intelligence"],
    ["/maintenance/tenant/quality?hub=readiness", "assuranceHub"],
    ["/maintenance/tenant/quality/calendar/week", "planner"],
    ["/maintenance/tenant/quality/audits/audit-1/setup", "setup"],
    ["/maintenance/tenant/quality/audits/audit-1/follow-up", "followUp"],
    ["/maintenance/tenant/quality/audits/checklists", "checklist"],
    ["/maintenance/tenant/quality/audits/program/p1/items/i1/schedule", "programmeSchedule"],
    ["/maintenance/tenant/quality/suppliers/register", "providers"],
    ["/maintenance/tenant/quality/reports/car-performance", "carReport"],
    ["/maintenance/tenant/workforce", null],
  ])("selects %s without importing unrelated pages", (path, expected) => {
    expect(qmsRouteLoaderKey(path)).toBe(expected);
  });
});
