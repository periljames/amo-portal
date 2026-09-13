import { describe, expect, it } from "vitest";

import { cockpitDrilldownHref, type AssuranceCockpitDrilldown } from "./assuranceCockpit";


describe("Assurance cockpit drilldowns", () => {
  it("preserves contextual filters and drawer state in the URL", () => {
    const drilldown: AssuranceCockpitDrilldown = {
      path: "/maintenance/SLK/quality/audits/program",
      query: { period: "2026", view: "mine", focus: "unscheduled" },
      drawer: "unscheduled-requirements",
    };

    const href = cockpitDrilldownHref(drilldown);
    expect(href).toContain("/maintenance/SLK/quality/audits/program?");
    expect(href).toContain("period=2026");
    expect(href).toContain("view=mine");
    expect(href).toContain("focus=unscheduled");
    expect(href).toContain("drawer=unscheduled-requirements");
  });

  it("returns null when no drilldown is supplied", () => {
    expect(cockpitDrilldownHref(undefined)).toBeNull();
  });
});
