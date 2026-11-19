import { describe, expect, it } from "vitest";
import { qmsNavigationCatalogue, searchQualityDestinations } from "./qmsNavigationCatalogue";
import { QMS_ROUTE_REGISTRY, classifyQmsPath, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";

describe("Quality page discoverability", () => {
  it("provides a direct destination for every registered non-DMS view", () => {
    const items = qmsNavigationCatalogue("SAFARILINK");
    const paths = new Set(items.map(item => item.path));
    expect(paths.size).toBe(items.length);
    for (const module of QMS_ROUTE_REGISTRY.filter(m => !["documents", "aerodoc"].includes(m.id))) {
      for (const view of module.validViews) {
        const path = qmsModulePath("SAFARILINK", module.id, view);
        expect(paths.has(path), `${module.label} / ${view}`).toBe(true);
        expect(classifyQmsPath(path).kind).toBe("known");
      }
    }
  });
  it("finds pages using module and destination words and retains permission requirements", () => {
    const items = qmsNavigationCatalogue("SAFARILINK");
    const results = searchQualityDestinations(items, "management open");
    expect(results.map(item => item.path)).toEqual(["/maintenance/SAFARILINK/quality/management-review/open-actions"]);
    expect(results[0].permission).toBe("qms.management_review.view");
    expect(items.find(item => item.path.endsWith("/management-review/new"))?.permission).toBe("qms.management_review.manage");
    expect(items.find(item => item.path.endsWith("/findings/new"))?.permission).toBe("qms.finding.create");
    expect(items.some(item => item.path.includes("workspace=intelligence"))).toBe(true);
    expect(items.find(item => item.path.endsWith("?workspace=assurance"))?.label).toBe("Assurance cases");
    expect(items.filter(item => item.path.includes("?hub=")).map(item => item.label)).toEqual(["Control library", "Assurance readiness", "Control evidence", "Intelligence reviews"]);
    expect(items.some(item => item.path.includes("workspace=people") && item.path.includes("tab=administration"))).toBe(true);
    expect(searchQualityDestinations(items, "unavailable-destination")).toHaveLength(0);
  });
});
