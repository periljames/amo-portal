import { describe, expect, it } from "vitest";

import { auditNoticePeriodInsufficient } from "./auditNoticePeriod";

describe("auditNoticePeriodInsufficient", () => {
  it("is false when notice leaves enough lead time", () => {
    expect(
      auditNoticePeriodInsufficient({
        plannedStart: "2026-10-20",
        noticeDate: "2026-10-01",
        requiredNoticeDays: 14,
      }),
    ).toBe(false);
  });

  it("is true when notice is inside the required lead time", () => {
    expect(
      auditNoticePeriodInsufficient({
        plannedStart: "2026-09-25",
        noticeDate: "2026-09-21",
        requiredNoticeDays: 14,
      }),
    ).toBe(true);
  });

  it("treats zero-day policy as always sufficient when notice is on or before start", () => {
    expect(
      auditNoticePeriodInsufficient({
        plannedStart: "2026-09-25",
        noticeDate: "2026-09-25",
        requiredNoticeDays: 0,
      }),
    ).toBe(false);
  });
});
