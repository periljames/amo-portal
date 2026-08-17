import { describe, expect, it } from "vitest";

import { auditOccurrenceResolverKey } from "../../../services/qmsAuditOccurrenceResolver";
import {
  auditSessionPath,
  auditSessionStageFromPath,
  legacyTabForAuditSessionStage,
} from "./auditSessionRoutes";

describe("audit session routes", () => {
  it("detects the occurrence stage from deep links", () => {
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001/live")).toBe("live");
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001/follow-up")).toBe("follow-up");
    expect(auditSessionStageFromPath("/maintenance/amo/quality/audits/QAR-26-001?tab=checklist")).toBeNull();
  });

  it("keeps new time-oriented routes compatible with the established run hub", () => {
    expect(legacyTabForAuditSessionStage("setup")).toBe("war-room");
    expect(legacyTabForAuditSessionStage("closing")).toBe("report");
    expect(legacyTabForAuditSessionStage("archive")).toBe("evidence");
  });

  it("builds encoded canonical occurrence links", () => {
    expect(auditSessionPath("tenant a", "QAR/MO/26/015", "live")).toBe(
      "/maintenance/tenant%20a/quality/audits/QAR%2FMO%2F26%2F015/live?tab=checklist",
    );
  });

  it("normalizes slash-containing audit references before backend resolution", () => {
    expect(auditOccurrenceResolverKey("QAR/MO/26/015")).toBe("qar-mo-26-015");
    expect(auditOccurrenceResolverKey(" QAR_MO.26 015 ")).toBe("qar-mo-26-015");
    expect(auditOccurrenceResolverKey("11111111-1111-4111-8111-111111111111")).toBe(
      "11111111-1111-4111-8111-111111111111",
    );
  });
});
