import { describe, expect, it } from "vitest";

import {
  QMS_AUDIT_DESTINATIONS,
  QMS_AUDIT_WORKSPACE_TABS,
  QMS_CALENDAR_DESTINATIONS,
  QMS_NAVIGATION_GROUPS,
  buildAuditWorkspaceTabPath,
  getActiveAuditWorkspace,
  isQualityNavigationPath,
} from "./qmsSidebarNavigation";
import {
  QMS_ROUTE_REGISTRY,
  classifyQmsPath,
  qmsModulePath,
} from "../../pages/qms/routes/qmsRouteRegistry";

describe("QMS sidebar navigation", () => {
  it("keeps the complete audit preparation and reporting route set directly reachable", () => {
    expect(QMS_AUDIT_DESTINATIONS.map((item) => item.view)).toEqual([
      "dashboard",
      "program",
      "schedule",
      "plan",
      "register",
      "new",
      "checklists",
      "reports",
    ]);
    expect(new Set(QMS_AUDIT_DESTINATIONS.map((item) => item.id)).size).toBe(
      QMS_AUDIT_DESTINATIONS.length,
    );

    for (const item of QMS_AUDIT_DESTINATIONS) {
      const path = qmsModulePath("safarilink", item.moduleId, item.view);
      expect(classifyQmsPath(path), path).toMatchObject({ kind: "known" });
    }
  });

  it("keeps the operational Quality calendar views directly reachable", () => {
    expect(QMS_CALENDAR_DESTINATIONS.map((item) => item.view)).toEqual([
      "month",
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
    expect(QMS_AUDIT_WORKSPACE_TABS.map((item) => item.tab)).toEqual([
      "war-room",
      "checklist",
      "findings",
      "cars",
      "evidence",
      "report",
      "closeout",
    ]);

    const auditPath = "/maintenance/safarilink/quality/audits/2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128";
    expect(getActiveAuditWorkspace(`${auditPath}/fieldwork`, "safarilink")).toEqual({
      auditKey: "2ad3f9c2-0bc9-431a-9e68-4b51f4ae5128",
      basePath: auditPath,
    });
    expect(buildAuditWorkspaceTabPath(auditPath, "checklist", "?source=register&tab=war-room")).toBe(
      `${auditPath}?source=register&tab=checklist`,
    );
    expect(getActiveAuditWorkspace("/maintenance/safarilink/quality/audits/plan", "safarilink")).toBeNull();
  });

  it("recognises Quality and competence routes as part of the Quality workspace", () => {
    expect(isQualityNavigationPath("/maintenance/safarilink/quality", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/quality/calendar/month", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/quality/audits/schedule", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/training/competence/matrix", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/planning/dashboard", "safarilink")).toBe(false);
  });
});
