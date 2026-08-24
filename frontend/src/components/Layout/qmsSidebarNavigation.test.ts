import { describe, expect, it } from "vitest";

import {
  QMS_AUDIT_DESTINATIONS,
  QMS_AUDIT_WORKSPACE_STAGES,
  QMS_CALENDAR_DESTINATIONS,
  QMS_NAVIGATION_GROUPS,
  buildAuditWorkspaceStagePath,
  getActiveAuditWorkspace,
  isQualityNavigationPath,
} from "./qmsSidebarNavigation";
import {
  QMS_ROUTE_REGISTRY,
  classifyQmsPath,
  qmsModulePath,
} from "../../pages/qms/routes/qmsRouteRegistry";
import { buildAuditWorkspacePath } from "../../utils/auditSlug";

describe("QMS sidebar navigation", () => {
  it("exposes Audit Assurance as a single sidebar hub (rail owns section destinations)", () => {
    expect(QMS_AUDIT_DESTINATIONS.map((item) => item.view)).toEqual(["dashboard"]);
    expect(QMS_AUDIT_DESTINATIONS).toHaveLength(1);
    expect(QMS_AUDIT_DESTINATIONS[0]?.label).toBe("Audit Assurance");
    expect(QMS_AUDIT_DESTINATIONS.some((item) => item.id === "audit-schedule")).toBe(false);
    expect(QMS_AUDIT_DESTINATIONS.some((item) => item.id === "audit-plan")).toBe(false);
    expect(QMS_AUDIT_DESTINATIONS.some((item) => item.id === "audit-programme")).toBe(false);

    for (const item of QMS_AUDIT_DESTINATIONS) {
      const path = qmsModulePath("safarilink", item.moduleId, item.view);
      expect(classifyQmsPath(path), path).toMatchObject({ kind: "known" });
    }
  });

  it("routes calendar browsing exclusively through Planner V2 destinations", () => {
    for (const item of QMS_CALENDAR_DESTINATIONS) {
      expect(item.moduleId).toBe("calendar");
      expect(qmsModulePath("safarilink", item.moduleId, item.view)).toContain("/quality/calendar/");
    }
  });

  it("keeps every functional Quality calendar view directly reachable", () => {
    expect(QMS_CALENDAR_DESTINATIONS.map((item) => item.view)).toEqual([
      "month",
      "week",
      "year",
      "list",
      "audits",
      "cars",
      "training",
      "management-review",
    ]);

    for (const item of QMS_CALENDAR_DESTINATIONS) {
      const path = qmsModulePath("safarilink", item.moduleId, item.view);
      expect(classifyQmsPath(path), path).toMatchObject({ kind: "known" });
    }
  });

  it("covers every registered module without returning to a flat module list", () => {
    const dedicated = new Set(["inbox", "calendar", "audits"]);
    const grouped = new Set(QMS_NAVIGATION_GROUPS.flatMap((group) => [...group.moduleIds]));
    const expected = QMS_ROUTE_REGISTRY
      .map((module) => module.id)
      .filter((moduleId) => !dedicated.has(moduleId));

    expect([...grouped].sort()).toEqual(expected.sort());
    expect(QMS_NAVIGATION_GROUPS.map((group) => group.id)).toEqual([
      "assurance",
      "controls",
      "review",
      "administration",
    ]);
  });

  it("exposes every active-audit workspace stage", () => {
    expect(QMS_AUDIT_WORKSPACE_STAGES.map((item) => item.stage)).toEqual([
      "setup",
      "prepare",
      "live",
      "closing",
      "follow-up",
      "archive",
    ]);

    const auditPath = "/maintenance/safarilink/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128";
    expect(getActiveAuditWorkspace(`${auditPath}/live`, "safarilink")).toEqual({
      auditKey: "2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128",
      basePath: auditPath,
    });
    expect(buildAuditWorkspaceStagePath(auditPath, "prepare", "?source=register&tab=war-room")).toBe(
      `${auditPath}/prepare?source=register`,
    );
    expect(getActiveAuditWorkspace("/maintenance/safarilink/quality/audits/plan", "safarilink")).toBeNull();
  });

  it("keeps reference-based audit workspaces canonical and active", () => {
    const auditPath = buildAuditWorkspacePath({
      amoCode: "safarilink",
      department: "quality",
      auditRef: "QAR/MO/26/002",
    });
    expect(auditPath).toBe("/maintenance/safarilink/quality/audits/QAR-MO-26-002/setup");
    expect(classifyQmsPath(auditPath)).toMatchObject({ kind: "known" });
    expect(getActiveAuditWorkspace(auditPath, "safarilink")).toEqual({
      auditKey: "QAR-MO-26-002",
      basePath: "/maintenance/safarilink/quality/audits/QAR-MO-26-002",
    });
  });

  it("recognises Quality and competence routes as part of the Quality workspace", () => {
    expect(isQualityNavigationPath("/maintenance/safarilink/quality", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/quality/calendar/month", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/quality/audits/schedule", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/training/competence/matrix", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/planning/dashboard", "safarilink")).toBe(false);
  });
});
