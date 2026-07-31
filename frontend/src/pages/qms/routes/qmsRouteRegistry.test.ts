import { describe, expect, it } from "vitest";

import {
  QMS_ROUTE_REGISTRY,
  classifyQmsPath,
  qmsModulePath,
  qmsNavigationItems,
} from "./qmsRouteRegistry";

describe("QMS route registry", () => {
  it("keeps route ids and module segments unique", () => {
    expect(new Set(QMS_ROUTE_REGISTRY.map((route) => route.id)).size).toBe(QMS_ROUTE_REGISTRY.length);
    expect(new Set(QMS_ROUTE_REGISTRY.map((route) => route.segment)).size).toBe(QMS_ROUTE_REGISTRY.length);
  });

  it("builds canonical navigation links from the registry", () => {
    expect(qmsModulePath("SAF", "cars", "overdue")).toBe("/maintenance/SAF/quality/cars/overdue");
    expect(qmsNavigationItems("SAF").find((item) => item.id === "audits")?.path).toBe("/maintenance/SAF/quality/audits/dashboard");
  });

  it("recognises overview, specialist, canonical, and dynamic record routes", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality").kind).toBe("overview");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/schedule").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/91/overview").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128/fieldwork").kind).toBe("known");
  });

  it("does not silently accept misspelled modules or views", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality/carrs/overdue").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/ovverdue").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/schedul").kind).toBe("unknown");
  });

  it("maps intentional legacy aliases to canonical destinations", () => {
    expect(classifyQmsPath("/maintenance/SAF/qms")).toMatchObject({
      kind: "legacy",
      canonicalTarget: "/maintenance/SAF/quality",
    });
    expect(classifyQmsPath("/maintenance/SAF/quality/tasks")).toMatchObject({
      kind: "legacy",
      canonicalTarget: "/maintenance/SAF/quality/inbox/assigned-to-me",
    });
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/programme")).toMatchObject({
      kind: "legacy",
      canonicalTarget: "/maintenance/SAF/quality/audits/program",
    });
  });
});
