import { describe, expect, it } from "vitest";

import {
  QMS_AUDIT_SHORTCUTS,
  isQualityNavigationPath,
} from "./qmsSidebarNavigation";

describe("QMS sidebar navigation", () => {
  it("keeps every primary audit page directly reachable", () => {
    expect(QMS_AUDIT_SHORTCUTS.map((item) => item.suffix)).toEqual([
      "audits/dashboard",
      "audits/program",
      "audits/schedule",
      "audits/checklists",
      "audits/reports",
    ]);
    expect(new Set(QMS_AUDIT_SHORTCUTS.map((item) => item.id)).size).toBe(
      QMS_AUDIT_SHORTCUTS.length,
    );
  });

  it("recognises Quality and competence routes as part of the Quality workspace", () => {
    expect(isQualityNavigationPath("/maintenance/safarilink/quality", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/quality/audits/schedule", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/training/competence/matrix", "safarilink")).toBe(true);
    expect(isQualityNavigationPath("/maintenance/safarilink/planning/dashboard", "safarilink")).toBe(false);
  });
});
