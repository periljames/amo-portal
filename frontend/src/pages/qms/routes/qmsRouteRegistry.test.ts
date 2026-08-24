import { describe, expect, it } from "vitest";

import {
  QMS_ROUTE_REGISTRY,
  classifyQmsPath,
  isSafeRecordKey,
  qmsModulePath,
  qmsNavigationItems,
  qmsRecordPath,
} from "./qmsRouteRegistry";

describe("QMS route registry", () => {
  it("keeps route ids and module segments unique", () => {
    expect(new Set(QMS_ROUTE_REGISTRY.map((route) => route.id)).size).toBe(QMS_ROUTE_REGISTRY.length);
    expect(new Set(QMS_ROUTE_REGISTRY.map((route) => route.segment)).size).toBe(QMS_ROUTE_REGISTRY.length);
  });

  it("requires complete navigation and access metadata", () => {
    for (const route of QMS_ROUTE_REGISTRY) {
      expect(route.id.trim()).not.toBe("");
      expect(route.label.trim()).not.toBe("");
      expect(route.navigationLabel.trim()).not.toBe("");
      expect(route.permission).toMatch(/^qms\.[a-z0-9_-]+\.view$/);
      expect(route.validViews.length).toBeGreaterThan(0);
      expect(route.validViews).toContain(route.defaultView);
      expect(new Set(route.validViews).size).toBe(route.validViews.length);
    }
  });

  it("builds canonical module and record links", () => {
    expect(qmsModulePath("SAF", "cars", "overdue")).toBe("/maintenance/SAF/quality/cars/overdue");
    expect(qmsRecordPath("SAF", "audits", "QAR-MO-26-002")).toBe("/maintenance/SAF/quality/audits/QAR-MO-26-002");
    expect(qmsRecordPath("Safari Link/AMO", "cars", "CAR-24+1", "overview")).toBe(
      "/maintenance/Safari%20Link%2FAMO/quality/cars/CAR-24%2B1/overview",
    );
    expect(qmsNavigationItems("SAF").find((item) => item.id === "audits")?.path).toBe("/maintenance/SAF/quality/audits/dashboard");
    expect(qmsNavigationItems("Safari Link/AMO").every((item) => item.path.startsWith("/maintenance/Safari%20Link%2FAMO/quality/"))).toBe(true);
  });

  it("classifies every registered default and child view as known", () => {
    for (const route of QMS_ROUTE_REGISTRY) {
      const defaultPath = `/maintenance/SAF/quality/${route.segment}`;
      expect(classifyQmsPath(defaultPath), defaultPath).toMatchObject({ kind: "known", module: route });

      for (const view of route.validViews) {
        const path = `/maintenance/SAF/quality/${route.segment}/${view}`;
        expect(classifyQmsPath(path), path).toMatchObject({ kind: "known", module: route });
        expect(qmsModulePath("SAF", route.id, view)).toBe(path);
      }
    }
  });

  it("recognises overview and specialist record workspaces", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality").kind).toBe("overview");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/schedule").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/91/overview").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128/live").kind).toBe("known");
    expect(
      classifyQmsPath(
        "/maintenance/SAF/quality/audits/program/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128/items/91a3f9c2-0bc9-431a-9e68-4b51f4ae5128/schedule",
      ).kind,
    ).toBe("known");
  });

  it("rejects audit overview deep-links; setup is the canonical execution entry", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128/overview").kind).toBe(
      "unknown",
    );
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128/setup").kind).toBe(
      "known",
    );
  });

  it("keeps CAR overview as the canonical CAR record entry", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/91/overview").kind).toBe("known");
  });

  it("recognises every canonical live-audit stage before the not-found guard", () => {
    const auditId = "a22a4ec1-1bba-4b19-b2c1-f17b078a11ea";
    for (const stage of ["setup", "prepare", "live", "closing", "follow-up", "archive"]) {
      const path = `/maintenance/safarilink/quality/audits/${auditId}/${stage}`;
      expect(classifyQmsPath(path), path).toMatchObject({
        kind: "known",
        amoCode: "safarilink",
        module: expect.objectContaining({ id: "audits" }),
      });
    }
  });

  it("accepts human-readable audit and CAR references on canonical stages", () => {
    expect(classifyQmsPath("/maintenance/safarilink/quality/audits/QAR-MO-26-002/setup")).toMatchObject({
      kind: "known",
      amoCode: "safarilink",
      module: expect.objectContaining({ id: "audits" }),
    });
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/QAR-MO-26-002/live").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/schedules/AUD-SCH-2026-04").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/CAR-2026-014/evidence").kind).toBe("known");
  });

  it("recognises controlled document reader routes in the registry", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality/documents/reader/DOC-24/revisions/REV-3/view").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/documents/7f14b288/revisions/91/view").kind).toBe("known");
  });

  it("does not silently accept misspelled modules or views", () => {
    expect(classifyQmsPath("/maintenance/SAF/quality/carrs/overdue").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/cars/ovverdue").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/schedul").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/findings/register/unexpected-tail").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/QAR-MO-26-002/unregistered-stage").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/%2E%2E?tab=war-room").kind).toBe("unknown");
  });

  it("rejects removed aliases and pre-stage audit occurrence URLs", () => {
    expect(classifyQmsPath("/maintenance/SAF/qms").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/tasks").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/programme").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/QAR-MO-26-002").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/audits/QAR-MO-26-002/checklist").kind).toBe("unknown");
  });

  it("accepts opaque safe record keys without requiring digits", () => {
    expect(isSafeRecordKey("ev-demo")).toBe(true);
    expect(isSafeRecordKey("ev-1")).toBe(true);
    expect(isSafeRecordKey("ID-ABCDEFGH")).toBe(true);
    expect(isSafeRecordKey("2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128")).toBe(true);
    expect(isSafeRecordKey("QAR-MO-26-002")).toBe(true);

    expect(isSafeRecordKey("")).toBe(false);
    expect(isSafeRecordKey(".")).toBe(false);
    expect(isSafeRecordKey("..")).toBe(false);
    expect(isSafeRecordKey("../secret")).toBe(false);
    expect(isSafeRecordKey("foo/bar")).toBe(false);
    expect(isSafeRecordKey("foo\\bar")).toBe(false);
    expect(isSafeRecordKey("has space")).toBe(false);
    expect(isSafeRecordKey("bad\0id")).toBe(false);
    expect(isSafeRecordKey("ovverdue")).toBe(false);
    expect(isSafeRecordKey("schedul")).toBe(false);
    expect(isSafeRecordKey("a".repeat(161))).toBe(false);

    expect(classifyQmsPath("/maintenance/SAF/quality/evidence-vault/ev-demo").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/evidence-vault/ev-1").kind).toBe("known");
    expect(classifyQmsPath("/maintenance/SAF/quality/evidence-vault/%2e%2e").kind).toBe("unknown");
    expect(classifyQmsPath("/maintenance/SAF/quality/evidence-vault/foo%2Fbar").kind).toBe("unknown");
    // Registered views stay views, not record keys.
    expect(classifyQmsPath("/maintenance/SAF/quality/evidence-vault/search").kind).toBe("known");
    expect(qmsRecordPath("SAF", "evidence-vault", "ev-demo")).toBe(
      "/maintenance/SAF/quality/evidence-vault/ev-demo",
    );
  });
});
