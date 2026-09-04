import { describe, expect, it } from "vitest";

import {
  auditOccurrenceQueryKey,
  auditOccurrenceResolverKey,
} from "../../../services/qmsAuditOccurrenceResolver";
import {
  auditOccurrenceFunctionalTabsForStage,
  auditSessionPath,
  auditSessionStageFromPath,
  isAtLeastLiveStage,
} from "./auditSessionRoutes";

describe("audit session routes", () => {
  it("detects the occurrence stage from deep links", () => {
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001/live")).toBe("live");
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001/follow-up")).toBe("follow-up");
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001?tab=checklist")).toBeNull();
  });

  it("treats live and later lifecycle stages as fieldwork-eligible", () => {
    expect(isAtLeastLiveStage("setup")).toBe(false);
    expect(isAtLeastLiveStage("prepare")).toBe(false);
    expect(isAtLeastLiveStage("live")).toBe(true);
    expect(isAtLeastLiveStage("closing")).toBe(true);
    expect(isAtLeastLiveStage("follow-up")).toBe(true);
    expect(isAtLeastLiveStage("archive")).toBe(true);
    expect(isAtLeastLiveStage(undefined)).toBe(false);
  });

  it("builds encoded canonical occurrence links", () => {
    expect(auditSessionPath("tenant a", "QAR/MO/26/015", "live")).toBe(
      "/maintenance/tenant%20a/quality/audits/QAR%2FMO%2F26%2F015/live",
    );
  });

  it("normalizes slash-containing audit references before backend resolution", () => {
    expect(auditOccurrenceResolverKey("QAR/MO/26/015")).toBe("qar-mo-26-015");
    expect(auditOccurrenceResolverKey(" QAR_MO.26 015 ")).toBe("qar-mo-26-015");
    expect(auditOccurrenceResolverKey("11111111-1111-4111-8111-111111111111")).toBe(
      "11111111-1111-4111-8111-111111111111",
    );
  });

  it("shares one tenant-scoped resolver cache key across occurrence panels", () => {
    expect(auditOccurrenceQueryKey(" Safarilink ", "QAR/AC/26/001")).toEqual([
      "qms",
      "audit-occurrence",
      "safarilink",
      "qar-ac-26-001",
    ]);
  });

  it("keeps workspace tabs inside the lifecycle stage being viewed", () => {
    expect(auditOccurrenceFunctionalTabsForStage("setup").map((tab) => tab.id)).toEqual(["overview", "team"]);
    expect(auditOccurrenceFunctionalTabsForStage("live").map((tab) => tab.id)).toEqual([
      "checklist",
      "evidence",
      "findings",
    ]);
    expect(auditOccurrenceFunctionalTabsForStage("prepare")).toEqual([]);
    expect(auditOccurrenceFunctionalTabsForStage("follow-up")).toEqual([]);
  });
});
